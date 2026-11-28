"""用法：python tools/hunter_cli --help（也支持 python -m tools.hunter_cli）。"""
import argparse
from contextlib import ExitStack
import ctypes as c
from ctypes import wintypes as w
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback
import uuid

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path: sys.path.insert(0,str(ROOT))
from tools.hunter_cli.core import (Bridge,HUNTER_SHA256,image_query,raw_query,input_fingerprint,
                                  now,read_json,sha,validate_targets,write_json)

def config_path():
    return Path(os.environ['APPDATA'])/'DTZxPorter/GameTools/config/hunter.dat'

def emit(value):
    print(json.dumps(value,ensure_ascii=False),flush=True)

class ProtectedHunter:
    """原配置独占只读锁 + 原样 EXE 副本；Job Object 防止守护进程退出后遗留 Hunter。"""
    def __init__(self,exe,session, allow_missing_config=False):
        self.allow_missing_config=allow_missing_config
        self.exe,self.session=Path(exe),Path(session)
        self.child=None;self.lock=None;self.job=None
        self.shutdown = None

    def __enter__(self):
        from tools.hunter_cli.windows import k,declare
        self.k=k
        declare(k,'CreateFileW',w.HANDLE,[w.LPCWSTR,w.DWORD,w.DWORD,c.c_void_p,w.DWORD,w.DWORD,w.HANDLE])
        declare(k,'CloseHandle',w.BOOL,[w.HANDLE])
        config = config_path()
        if config.is_file():
            self.before = sha(config)
            self.lock = k.CreateFileW(str(config),0x80000000,0,None,3,0x80,None)
        elif self.allow_missing_config:
            config.parent.mkdir(parents=True,exist_ok=True)
            self.before = None
            # CREATE_NEW and DELETE_ON_CLOSE leave a pre-existing user configuration untouched.
            self.lock = k.CreateFileW(str(config),0x80010000,0,None,1,0x04000100,None)
        else:
            raise RuntimeError('EXISTING_HUNTER_CONFIG_REQUIRED')
        if self.lock==c.c_void_p(-1).value:
            self.lock=None;raise RuntimeError('CONFIG_LOCK_FAILED')
        try:
            # 在同一普通桌面权限下验证读取也被锁拒绝，避免 Hunter 悄悄使用旧输出目录。
            check=k.CreateFileW(str(config_path()),0x80000000,7,None,3,0x80,None)
            if check!=c.c_void_p(-1).value:
                k.CloseHandle(check);raise RuntimeError('CONFIG_LOCK_NOT_EFFECTIVE')
            if c.get_last_error()!=32: raise RuntimeError('CONFIG_LOCK_NOT_VERIFIED')
            if sha(self.exe)!=HUNTER_SHA256: raise RuntimeError('UNSUPPORTED_HUNTER_BINARY')
            app=self.session/'app';app.mkdir()
            shutil.copyfile(self.exe,app/'hunter.exe')
            if sha(app/'hunter.exe')!=HUNTER_SHA256: raise RuntimeError('EXE_COPY_MISMATCH')
            self.job=self.create_job()
            self.child=subprocess.Popen([str(app/'hunter.exe')],cwd=app,
                stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            declare(k,'AssignProcessToJobObject',w.BOOL,[w.HANDLE,w.HANDLE])
            if not k.AssignProcessToJobObject(self.job,int(self.child._handle)):
                raise c.WinError(c.get_last_error())
            return self
        except BaseException:
            self.close();raise

    def create_job(self):
        from tools.hunter_cli.windows import declare
        class Basic(c.Structure):
            _fields_=[('process_time',c.c_int64),('job_time',c.c_int64),('flags',w.DWORD),
                      ('min_ws',c.c_size_t),('max_ws',c.c_size_t),('active',w.DWORD),
                      ('affinity',c.c_size_t),('priority',w.DWORD),('scheduling',w.DWORD)]
        class Extended(c.Structure):
            _fields_=[('basic',Basic),('io',c.c_uint64*6),('process_mem',c.c_size_t),
                      ('job_mem',c.c_size_t),('peak_process',c.c_size_t),('peak_job',c.c_size_t)]
        k=self.k
        declare(k,'CreateJobObjectW',w.HANDLE,[c.c_void_p,w.LPCWSTR])
        declare(k,'SetInformationJobObject',w.BOOL,[w.HANDLE,c.c_int,c.c_void_p,w.DWORD])
        job=k.CreateJobObjectW(None,None)
        if not job: raise c.WinError(c.get_last_error())
        info=Extended();info.basic.flags=0x2000 # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not k.SetInformationJobObject(job,9,c.byref(info),c.sizeof(info)):
            k.CloseHandle(job);raise c.WinError(c.get_last_error())
        return job

    def close(self, graceful=False):
        try:
            if self.child is not None and graceful:
                if self.child.poll() is None:
                    from tools.hunter_cli.windows import request_close
                    self.shutdown = 'window_close_requested'
                    request_close(self.child.pid)
                    self.child.wait(timeout=10)
                    self.shutdown = 'window_close'
                else:
                    self.shutdown = 'already_exited'
                if self.child.returncode != 0:
                    raise RuntimeError('HUNTER_EXIT_CODE: ' + str(self.child.returncode))
        finally:
            try:
                if self.child is not None and self.child.poll() is None:
                    self.shutdown = 'forced_after_close_failure' if graceful else 'terminated_on_error'
                    self.child.terminate()
                    self.child.wait(timeout=10)
            finally:
                if self.job: self.k.CloseHandle(self.job);self.job=None
                if self.lock: self.k.CloseHandle(self.lock);self.lock=None

    def __exit__(self,*args):
        try:
            self.close(graceful=args[0] is None)
        finally:
            if self.allow_missing_config:
                path = config_path()
                after = sha(path) if path.is_file() else None
                if self.before != after:
                    raise RuntimeError('ORIGINAL_HUNTER_CONFIGURATION_CHANGED')

def data_metadata(index):
    return {p.name:[p.stat().st_size,p.stat().st_mtime_ns] for p in Path(index).parent.iterdir() if p.is_file()}

def worker(session):
    session=Path(session).resolve();settings=read_json(session/'session.json')
    state=dict(status='STARTING',worker_pid=os.getpid(),started_at=now(),mode='EXPERIMENTAL_GUI_BRIDGE',
               native_api=False,load_raw=settings.get('load_raw',False),layout_clicks_required=True,source=input_fingerprint(settings['index']),
               original_exe_sha256=sha(settings['hunter']),config_sha256_before=sha(config_path()))
    write_json(session/'state.json',state)
    before_meta=data_metadata(settings['index']);write_json(session/'input-metadata-before.json',before_meta)
    state_path=session/'state.json'
    try:
        with ProtectedHunter(settings['hunter'],session) as guard, ExitStack() as ui:
            state['hunter_pid']=guard.child.pid
            deadline=time.monotonic()+15
            while True:
                try: bridge=Bridge(guard.child.pid,session);break
                except RuntimeError:
                    if guard.child.poll() is not None or time.monotonic()>deadline: raise
                    time.sleep(.2)
            ui.callback(bridge.close)
            time.sleep(1.5) # Winit 创建 HWND 早于首帧与初始控件可交互时刻。
            # 首先明确设置并回读新输出目录；未通过此步骤时绝不加载或导出。
            initial=session/'initial/hunter/raw';initial.mkdir(parents=True)
            state['initial_output_directory']=bridge.set_output(initial)
            if settings.get('load_raw'): bridge.enable_raw_loading()
            bridge.load(settings['index'])
            state['status']='LOADING';write_json(state_path,state)
            deadline=time.monotonic()+settings['startup_timeout']
            while True:
                if (session/'cancel').exists(): raise RuntimeError('CANCELLED')
                if guard.child.poll() is not None: raise RuntimeError('HUNTER_EXITED')
                try:
                    probe=bridge.search('',1)
                    if probe['resources']:
                        state['load_probe']=probe['resources'][0];break
                except RuntimeError as error:
                    # 加载进度模态窗口仍存在时，主窗口暂时不能取得焦点。
                    if str(error) not in ('QUERY_READBACK_FAILED','FOCUS_NOT_ACQUIRED','TARGET_OCCLUDED',
                                          'FOCUS_LOST','RESOURCE_NAME_READBACK_FAILED'): raise
                if time.monotonic()>deadline: raise RuntimeError('INDEX_LOAD_TIMEOUT')
                time.sleep(2)
            state.update(status='READY',ready_at=now());write_json(state_path,state)
            last_request=time.monotonic()
            while guard.child.poll() is None:
                if (session/'cancel').exists(): state['status']='CANCELLED';break
                if time.monotonic()-last_request>1800: state['status']='IDLE_TIMEOUT';break
                for request in sorted((session/'requests').glob('*.json')):
                    response=session/'responses'/request.name
                    if response.exists(): continue
                    last_request=time.monotonic();command=read_json(request)
                    operation=command['operation']
                    if operation=='stop':
                        state['status']='STOPPING';write_json(state_path,state)
                        guard.close()
                        write_json(response,dict(ok=True,stopped=True))
                        break
                    if state['status']!='READY':
                        write_json(response,dict(ok=False,error='SESSION_NEEDS_ATTENTION'));continue
                    try:
                        state.update(status='BUSY',current_operation=operation,current_request=request.name)
                        write_json(state_path,state)
                        if input_fingerprint(settings['index'])!=state['source']:
                            raise RuntimeError('SOURCE_INDEX_CHANGED')
                        kind=command.get('kind','image')
                        if kind=='raw' and not settings.get('load_raw'):
                            raise ValueError('RAW_LOADING_NOT_ENABLED_START_WITH_LOAD_RAW')
                        if operation in ('search','list'):
                            result=bridge.search(command.get('query',''),command.get('limit',20),kind,command.get('namespace','hunter'))
                        elif operation in ('export','batch-export'):
                            result=bridge.batch(command['names'],state['source'],command.get('timeout',30),kind)
                        else: raise ValueError('UNKNOWN_OPERATION')
                        if input_fingerprint(settings['index'])!=state['source']:
                            raise RuntimeError('SOURCE_INDEX_CHANGED_DURING_OPERATION')
                        ok=result.get('status','SUCCEEDED')=='SUCCEEDED'
                        write_json(response,dict(ok=ok,result=result))
                        state['status']='READY'
                        if result.get('receipt_path'): state['last_receipt']=result['receipt_path']
                        if any(x.get('error') not in (None,'TARGET_NOT_FOUND','AMBIGUOUS_RESOURCE_NAME') for x in result.get('items',[])):
                            state['status']='NEEDS_ATTENTION'
                    except Exception as error:
                        write_json(response,dict(ok=False,error=str(error)))
                        state['status']='NEEDS_ATTENTION'
                    state.update(last_request=request.name,last_operation=operation,current_operation=None,current_request=None)
                    write_json(state_path,state)
                if state['status']=='STOPPING': break
                time.sleep(.1)
    except BaseException as error:
        traceback.print_exc()
        state.update(status='FAILED',error=str(error))
    finally:
        state['config_sha256_after']=sha(config_path())
        state['config_unchanged']=state['config_sha256_after']==state['config_sha256_before']
        state['original_exe_unchanged']=sha(settings['hunter'])==state['original_exe_sha256']
        state['source_index_unchanged']=input_fingerprint(settings['index'])==state['source']
        state['source_directory_metadata_unchanged']=data_metadata(settings['index'])==before_meta
        if state['status']=='STOPPING': state['status']='STOPPED'
        elif state['status']=='READY': state['status']='HUNTER_EXITED'
        state['finished_at']=now();write_json(state_path,state)

def parser():
    p=argparse.ArgumentParser(description='Hunter 2.2.9 实验性 GUI 桥接；默认 JSON 输出，需要交互式 Windows 桌面。')
    sub=p.add_subparsers(dest='command',required=True)
    d=sub.add_parser('doctor');d.add_argument('--hunter',type=Path,default=ROOT/'tools/hunter.exe')
    s=sub.add_parser('start');s.add_argument('--session',type=Path,required=True)
    s.add_argument('--index',type=Path,required=True);s.add_argument('--hunter',type=Path,default=ROOT/'tools/hunter.exe')
    s.add_argument('--experimental-gui',action='store_true',required=True,help='明确接受固定布局点击与前台/剪贴板依赖')
    s.add_argument('--startup-timeout',type=float,default=240)
    s.add_argument('--load-raw',action='store_true',help='首次加载前启用 Raw Files，保留图片加载')
    for name in ('search','list','export','batch-export','status','stop','cancel','_worker'):
        q=sub.add_parser(name);q.add_argument('--session',type=Path,required=True)
        if name in ('search','list','export','batch-export'):
            q.add_argument('--kind',choices=('image','raw'),default='image')
        if name in ('search','list'):
            q.add_argument('--query',default='');q.add_argument('--limit',type=int,default=20)
            q.add_argument('--namespace',choices=('hunter','rogue'),default='hunter',help='raw 查询的路径范围')
        if name=='export':q.add_argument('--name',required=True)
        if name=='batch-export':q.add_argument('--manifest',type=Path,required=True,help='JSON 字符串数组，1 至 20 个完整资源名')
        if name in ('export','batch-export'):q.add_argument('--timeout',type=float,default=30)
    from tools.hunter_cli.bulk import arguments
    arguments(sub)
    return p

def main(argv=None):
    args=parser().parse_args(argv)
    if args.command == 'bulk':
        from tools.hunter_cli.bulk import run
        try:
            result = run(args)
            emit({key: result[key] for key in ('status','source_directory','source_metadata','statistics',
                                               'known_image_collisions') if key in result})
            return 0
        except KeyboardInterrupt:
            emit({'error':'EXPORT_INTERRUPTED', 'session': str(args.session)})
            return 130
        except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as error:
            emit({'error': str(error), 'session': str(args.session)})
            return 2
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    if args.command=='doctor':
        result=dict(windows=os.name=='nt',python=sys.version.split()[0],pillow=bool(importlib.util.find_spec('PIL')),
                    hunter_exists=args.hunter.is_file(),config_exists=config_path().is_file(),
                    mode='EXPERIMENTAL_GUI_BRIDGE',native_cli=False)
        result['supported_binary']=result['hunter_exists'] and sha(args.hunter)==HUNTER_SHA256
        result['ok']=all(result[k] for k in ('windows','pillow','supported_binary','config_exists'))
        emit(result);return 0 if result['ok'] else 3
    session=args.session.resolve()
    try:
        if args.command=='_worker':worker(session);return 0
        if args.command=='start':
            if session.exists():raise ValueError('SESSION_DIRECTORY_ALREADY_EXISTS')
            index=args.index.resolve();hunter=args.hunter.resolve()
            if not index.is_file() or index.suffix.lower()!='.sdftoc':raise ValueError('INDEX_NOT_FOUND_OR_NOT_SDFTOC')
            if not hunter.is_file() or sha(hunter)!=HUNTER_SHA256:raise ValueError('UNSUPPORTED_HUNTER_BINARY')
            if importlib.util.find_spec('PIL') is None:raise ValueError('PILLOW_REQUIRED')
            if not config_path().is_file():raise ValueError('EXISTING_HUNTER_CONFIG_REQUIRED')
            sha(config_path()) # 已有会话锁定配置时，在创建新会话前明确拒绝。
            if args.startup_timeout<=0:raise ValueError('POSITIVE_TIMEOUT_REQUIRED')
            session.mkdir(parents=True);(session/'requests').mkdir();(session/'responses').mkdir()
            write_json(session/'session.json',dict(index=str(index),hunter=str(hunter),startup_timeout=args.startup_timeout,load_raw=args.load_raw))
            with (session/'worker.log').open('xb') as log:
                worker_process=subprocess.Popen([sys.executable,'-B',str(Path(__file__).parent),'_worker','--session',str(session)],
                    stdin=subprocess.DEVNULL,stdout=log,stderr=log,cwd=ROOT,
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
            deadline=time.monotonic()+args.startup_timeout+30
            last=None
            while time.monotonic()<deadline:
                if (session/'state.json').exists():
                    state=read_json(session/'state.json')
                    if state['status']!=last:
                        print('Hunter: '+state['status'],file=sys.stderr,flush=True);last=state['status']
                    if state['status']=='READY':emit(dict(ok=True,session=str(session),state=state));return 0
                    if state['status']=='FAILED':emit(dict(ok=False,state=state));return 3
                if worker_process.poll() is not None:raise RuntimeError('WORKER_EXITED_SEE_WORKER_LOG')
                time.sleep(.3)
            (session/'cancel').touch(exist_ok=False);raise RuntimeError('START_TIMEOUT_CANCEL_REQUESTED')
        if args.command=='status':
            state=read_json(session/'state.json')
            state['jobs']=[dict(job_id=p.parent.name,**{k:v for k,v in read_json(p).items()
                            if k in ('status','success_count','failed_count','not_attempted_count','error')})
                           for p in sorted((session/'jobs').glob('*/result.json'))]
            emit(state);return 0
        if args.command=='cancel':
            (session/'cancel').touch(exist_ok=True);emit(dict(ok=True,cancellation_requested=True));return 0
        state=read_json(session/'state.json')
        if state['status'] not in ('READY','BUSY','NEEDS_ATTENTION'):raise ValueError('SESSION_NOT_RUNNING')
        if state['status']=='BUSY' and args.command!='stop':raise ValueError('SESSION_BUSY')
        request=dict(operation=args.command)
        if hasattr(args,'kind'):
            if args.kind=='raw' and not state.get('load_raw'):
                raise ValueError('RAW_LOADING_NOT_ENABLED_START_WITH_LOAD_RAW')
            request['kind']=args.kind
        if args.command in ('search','list'):
            if args.kind=='raw':raw_query(args.query,args.namespace)
            else:
                if args.namespace!='hunter':raise ValueError('IMAGE_NAMESPACE_MUST_BE_HUNTER')
                image_query(args.query)
            if not 1<=args.limit<=100:raise ValueError('LIMIT_MUST_BE_1_TO_100')
            request.update(query=args.query,limit=args.limit,namespace=args.namespace)
        if args.command in ('export','batch-export'):
            names=[args.name] if args.command=='export' else read_json(args.manifest)
            request['names']=validate_targets(names,args.kind)
            if not 0<args.timeout<=300:raise ValueError('EXPORT_TIMEOUT_MUST_BE_0_TO_300_SECONDS')
            request['timeout']=args.timeout
        name=str(time.time_ns())+'-'+uuid.uuid4().hex+'.json'
        write_json(session/'requests'/name,request)
        deadline=time.monotonic()+30+request.get('limit',0)*2+len(request.get('names',[]))*(request.get('timeout',0)+25)
        response=session/'responses'/name
        while time.monotonic()<deadline:
            if response.exists():
                result=read_json(response)
                if args.command=='stop':
                    for _ in range(50):
                        if read_json(session/'state.json').get('finished_at'):break
                        time.sleep(.1)
                emit(result);return 0 if result['ok'] else 4
            time.sleep(.2)
        raise RuntimeError('RESPONSE_TIMEOUT_STATUS_UNKNOWN')
    except KeyboardInterrupt:
        if session.is_dir():(session/'cancel').touch(exist_ok=True)
        emit(dict(ok=False,error='INTERRUPTED_CANCEL_REQUESTED'));return 130
    except (ValueError,OSError,RuntimeError) as error:
        emit(dict(ok=False,error=str(error)));return 2 if isinstance(error,ValueError) else 3

if __name__=='__main__':raise SystemExit(main())
