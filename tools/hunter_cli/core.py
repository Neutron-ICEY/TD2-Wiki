"""固定 Hunter 2.2.9 的实验性 GUI 桥接。资源身份依赖名称回读，不依赖截图。"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import time
import uuid

HUNTER_SHA256 = '7f7279795df8573ef8211f03ed39b373bdb9c88339df5158291b067d8eccc014'
ROOT = Path(__file__).resolve().parents[2]

def now():
    return datetime.now(timezone.utc).isoformat()

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()

def write_json(path, value):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temp.replace(path)

def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))

def image_query(query):
    terms = [x.strip() for x in query.split(',') if x.strip()]
    if len(terms)>3 or any('\n' in x or '\r' in x for x in terms):
        raise ValueError('QUERY_REQUIRES_AT_MOST_THREE_TERMS')
    # Hunter 自带 font/console_font 也会出现在图片列表；这里只处理游戏 hunter/ 命名空间。
    return ','.join(['width:>0','hunter/']+terms)

def raw_query(query,namespace='hunter'):
    terms=[x.strip() for x in query.split(',') if x.strip()]
    if namespace not in ('hunter','rogue') or not terms or len(terms)>3 or any(c in query for c in '\r\n'):
        raise ValueError('EXPLICIT_RAW_QUERY_AND_NAMESPACE_REQUIRED')
    return ','.join([namespace+'/']+terms)


def resource_path(name,kind='image'):
    p = PurePosixPath(name)
    prefixes=('hunter/','rogue/') if kind=='raw' else ('hunter/',)
    if (kind not in ('image','raw') or not name.startswith(prefixes) or p.is_absolute() or str(p)!=name or
        any(part in ('','.','..') or part.endswith((' ','.')) for part in p.parts) or
        any(ch in name for ch in '\\:*?"<>|\r\n\0')):
        raise ValueError('UNSAFE_OR_UNSUPPORTED_RESOURCE_NAME')
    return Path('raw_files',*p.parts) if kind=='raw' else Path('images', *p.parts).with_name(p.name+'.png')

def validate_targets(names,kind='image'):
    if not isinstance(names,list) or not 1<=len(names)<=20 or not all(isinstance(n,str) for n in names):
        raise ValueError('EXPLICIT_LIST_OF_1_TO_20_RESOURCE_NAMES_REQUIRED')
    paths=[str(resource_path(n,kind)).casefold() for n in names]
    if len(set(paths))!=len(paths):
        raise ValueError('DUPLICATE_OR_CASE_COLLIDING_TARGETS')
    if kind=='raw' and any(p+'.decompiled' in paths for p in paths):
        raise ValueError('RAW_SIDECAR_TARGET_COLLISION')
    for n in names:
        if ',' in n: raise ValueError('RESOURCE_NAME_CONTAINS_SEARCH_DELIMITER')
    return names

def input_fingerprint(index):
    index=Path(index)
    return dict(path=str(index),sha256=sha(index),size=index.stat().st_size,mtime_ns=index.stat().st_mtime_ns)

class Bridge:
    def __init__(self,pid,session):
        from . import windows
        self.w=windows
        self.pid=pid
        self.session=Path(session)
        self.hwnd=self.w.main_window(pid)

    def layout(self):
        # 固定布局原型必须拒绝窗口大小变化；DPI 按 Win32 实际比例换算。
        w=self.w
        rect=w.w.RECT();w.u.GetClientRect(self.hwnd,w.c.byref(rect))
        scale=w.u.GetDpiForWindow(self.hwnd)/96
        if abs(rect.right/scale-980)>3 or abs(rect.bottom/scale-625)>3:
            raise RuntimeError('WINDOW_LAYOUT_CHANGED')
        w.focus(self.hwnd)

    def copied_selection(self):
        marker='HUNTER_CLI_'+uuid.uuid4().hex
        self.w.clipboard(marker)
        self.w.key(self.hwnd,ord('C'),(17,))
        value=self.w.clipboard()
        return None if value in (None,marker,'') else value

    def search(self,query,limit=20,kind='image',namespace='hunter'):
        if not 1<=limit<=100: raise ValueError('LIMIT_MUST_BE_1_TO_100')
        self.layout()
        w,h=self.w,self.hwnd
        compiled=raw_query(query,namespace) if kind=='raw' else image_query(query)
        prefix=namespace+'/' if kind=='raw' else 'hunter/'
        w.key(h,ord('F'),(17,));w.clipboard(compiled);w.key(h,ord('V'),(17,))
        # 在执行查询前读回搜索框，发现粘贴失效便退出，避免操作旧查询的结果。
        w.key(h,ord('A'),(17,))
        if self.copied_selection()!=compiled: raise RuntimeError('QUERY_READBACK_FAILED')
        w.key(h,13);time.sleep(.6)
        w.click_client(h,150,140)
        name=self.copied_selection()
        if name is None:
            return dict(query=compiled,resources=[],end_observed=True,complete_catalog=False)
        if not name.startswith(prefix) or '\n' in name:
            raise RuntimeError('RESOURCE_NAME_READBACK_FAILED')
        names=[];end=False
        for _ in range(limit):
            if name in names:
                end=True;break
            names.append(name)
            w.key(h,40)
            next_name=self.copied_selection()
            if next_name==name:
                end=True;break
            if not next_name or not next_name.startswith(prefix) or '\n' in next_name:
                raise RuntimeError('RESOURCE_ENUMERATION_INTERRUPTED')
            name=next_name
        return dict(query=compiled,resources=[dict(name=n,native_id=None,
                    filtered_as='any_loaded_type' if kind=='raw' else 'image',
                    type_evidence='Name filter only; raw type requires export verification' if kind=='raw' else 'Hunter width:>0 filter') for n in names],
                    end_observed=end,complete_catalog=False,limit=limit)

    def select_exact(self,name,kind='image'):
        result=self.search(name,20,kind,name.split('/')[0]) if kind=='raw' else self.search(name,20)
        names=[r['name'] for r in result['resources']]
        if names.count(name)!=1: raise RuntimeError('TARGET_NOT_FOUND')
        if not result['end_observed']: raise RuntimeError('TARGET_SEARCH_TOO_BROAD')
        # 枚举已停在末项，用方向键返回目标；最终再次逐字回读。
        for _ in range(len(names)-1-names.index(name)):
            self.w.key(self.hwnd,38)
        if self.copied_selection()!=name: raise RuntimeError('EXACT_SELECTION_READBACK_FAILED')

    def set_output(self,out):
        self.layout()
        w,h=self.w,self.hwnd
        out=Path(out).resolve()
        if not out.is_dir() or any(out.iterdir()): raise RuntimeError('OUTPUT_MUST_BE_NEW_AND_EMPTY')
        w.click_client(h,925,24)
        w.click_client(h,130,97)
        w.click_client(h,799,397)
        deadline=time.monotonic()+5
        while not any('Select an export directory' in x['title'] for x in w.windows(self.pid)):
            if time.monotonic()>deadline: raise RuntimeError('EXPORT_FOLDER_DIALOG_TIMEOUT')
            time.sleep(.1)
        w.choose_export_folder(self.pid,out)
        deadline=time.monotonic()+5
        while any('Select an export directory' in x['title'] for x in w.windows(self.pid)):
            if time.monotonic()>deadline: raise RuntimeError('EXPORT_FOLDER_CONFIRM_TIMEOUT')
            time.sleep(.1)
        w.click_client(h,450,397);w.key(h,ord('A'),(17,))
        actual=self.copied_selection()
        if actual is None or Path(actual).resolve()!=out: raise RuntimeError('OUTPUT_DIRECTORY_READBACK_FAILED')
        w.click_client(h,925,24)
        return str(out)

    def load(self,index):
        self.layout()
        self.w.click_client(self.hwnd,50,598)
        deadline=time.monotonic()+5
        while not any('Select game files' in x['title'] for x in self.w.windows(self.pid)):
            if time.monotonic()>deadline: raise RuntimeError('FILE_DIALOG_TIMEOUT')
            time.sleep(.1)
        self.w.open_file_dialog(self.pid,index)

    def enable_raw_loading(self):
        """仅在固定 EXE、配置锁及首次加载前调用；默认 Raw Files 关闭，只切换一次。"""
        self.layout()
        self.w.click_client(self.hwnd,925,24)
        self.w.click_client(self.hwnd,130,97)
        self.w.click_client(self.hwnd,293,316)
        self.w.click_client(self.hwnd,925,24)

    def raw_record(self,path,name,source,deadline):
        """等待原文件及可选反编译文件稳定；不把文件存在误称为定义语义已验证。"""
        last=None;stable_since=None
        while time.monotonic()<deadline:
            if (self.session/'cancel').exists(): raise RuntimeError('CANCELLED')
            files=[p for p in (path,Path(str(path)+'.decompiled')) if p.is_file()]
            snapshot=[(str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in files]
            if path.is_file() and snapshot==last:
                if stable_since is None: stable_since=time.monotonic()
                if time.monotonic()-stable_since>=3:
                    records=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p),
                                  role='raw' if p==path else 'decompiled') for p in files]
                    if snapshot==[(str(p),p.stat().st_size,p.stat().st_mtime_ns) for p in files]:
                        return dict(resource_name=name,resource_id='UNKNOWN',game_build='UNKNOWN',
                            source_container=source['path'],source_container_sha256=source['sha256'],
                            hunter_version='2.2.9',exported_at=now(),files=records,
                            exported_file_sha256=records[0]['sha256'],validation='FILE_STABLE_ONLY',
                            entity_mapping_confirmed=False,definition_semantics_verified=False)
            else: stable_since=None
            last=snapshot;time.sleep(.3)
        raise RuntimeError('RAW_OUTPUT_TIMEOUT_OR_UNSTABLE')

    def batch(self,names,source,timeout=30,kind='image'):
        from tools.asset_import.hunter import exported_record
        validate_targets(names,kind)
        job=self.session/'jobs'/uuid.uuid4().hex
        raw=job/'hunter/raw';raw.mkdir(parents=True)
        receipt=dict(schema_version=1,job_id=job.name,started_at=now(),status='RUNNING',
                     export_method='EXPERIMENTAL_GUI_BRIDGE',resource_kind=kind,exports=[],items=[],source=source,
                     requested_names=list(names),success_count=0,failed_count=0,
                     not_attempted_count=len(names),hunter_gui_status_available=False)
        write_json(job/'result.json',receipt)
        try:
            self.set_output(raw)
        except Exception as error:
            receipt.update(status='FAILED_SETUP',error=str(error),finished_at=now())
            write_json(job/'result.json',receipt)
            raise
        receipt['confirmed_output_directory']=str(raw.resolve())
        fatal=False
        for name in names:
            item=dict(resource_name=name,status='NOT_ATTEMPTED',error=None)
            receipt['items'].append(item)
            if fatal: continue
            try:
                if (self.session/'cancel').exists(): raise RuntimeError('CANCELLED')
                if kind=='raw': self.select_exact(name,kind)
                else: self.select_exact(name)
                path=raw/resource_path(name,kind)
                if path.exists() or (kind=='raw' and Path(str(path)+'.decompiled').exists()): raise RuntimeError('OUTPUT_ALREADY_EXISTS')
                if (self.session/'cancel').exists(): raise RuntimeError('CANCELLED')
                self.w.key(self.hwnd,ord('E'))
                deadline=time.monotonic()+timeout
                record=None;last_error=None
                if kind=='raw': record=self.raw_record(path,name,source,deadline)
                while kind=='image' and time.monotonic()<deadline:
                    if (self.session/'cancel').exists(): raise RuntimeError('CANCELLED')
                    if path.is_file():
                        try:
                            before=sha(path)
                            record=exported_record(job,path,dict(source_container=source['path'],
                                source_container_sha256=source['sha256'],hunter_version='2.2.9',
                                game_build='UNKNOWN',resource_name=name,resource_id='UNKNOWN',
                                exported_at=now(),export_settings={'image_format':'PNG','settings_basis':'locked-config defaults of pinned EXE'},
                                original_image_sha256='UNKNOWN'))
                            time.sleep(.3)
                            if before==sha(path): break
                        except (OSError,ValueError) as error:
                            last_error=str(error);record=None
                    time.sleep(.2)
                else:
                    if kind=='image': raise RuntimeError('OUTPUT_TIMEOUT_OR_INVALID_PNG'+(':'+last_error if last_error else ''))
                record['export_method']='EXPERIMENTAL_GUI_BRIDGE'
                receipt['exports'].append(record)
                item.update(status='RAW_FILE_STABLE' if kind=='raw' else 'EXPORTED_FILE_VALIDATED',exported_path=str(path),sha256=record['exported_file_sha256'])
            except Exception as error:
                item.update(status='FAILED',error=str(error))
                # 未找到资源不影响其它目标；未知 UI/导出状态必须停止，避免对忙碌窗口继续发命令。
                fatal=str(error)!='TARGET_NOT_FOUND'
            receipt.update(success_count=len(receipt['exports']),
                           failed_count=sum(x['status']=='FAILED' for x in receipt['items']))
            receipt['not_attempted_count']=len(names)-receipt['success_count']-receipt['failed_count']
            write_json(job/'result.json',receipt)
        receipt.update(finished_at=now(),success_count=len(receipt['exports']),
                       failed_count=sum(x['status']=='FAILED' for x in receipt['items']),
                       not_attempted_count=sum(x['status']=='NOT_ATTEMPTED' for x in receipt['items']))
        receipt['status']='SUCCEEDED' if receipt['success_count']==len(names) else 'PARTIAL_OR_FAILED'
        write_json(job/'result.json',receipt)
        manifest='raw-export-manifest.json' if kind=='raw' else 'export-manifest.json'
        write_json(job/'hunter'/manifest,dict(schema_version=1,exports=receipt['exports'],resource_kind=kind,
                   exported_file_count=sum(len(r['files']) if kind=='raw' else 1 for r in receipt['exports']),export_method=receipt['export_method']))
        receipt['receipt_path']=str(job/'result.json')
        return receipt
