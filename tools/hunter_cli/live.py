"""Reuse one loaded Hunter index across independently committed name filters."""
from contextlib import ExitStack
import ctypes
import json
import re
import sys
import time
from .core import now, write_json
from .display import Window
from tools.process_metrics import snapshot, difference


class SessionPool:
    def __init__(self, args, program):
        self.args = args
        self.program = program
        self.stack = ExitStack()
        self.types = None
        self.before = None

    def failure_observation(self):
        guard = getattr(self, "guard", None)
        if guard is None or guard.child is None:
            return None
        values = snapshot(guard.child._handle)
        return difference(self.before, values) if self.before else values

    def close(self, exc_type=None, exc=None, tb=None):
        guard = getattr(self, 'guard', None)
        try:
            self.stack.__exit__(exc_type, exc, tb)
        finally:
            self.types = self.guard = self.before = None
            if guard is not None and guard.child is not None:
                write_json(self.host/'child-process.json', dict(pid=guard.child.pid, shutdown=guard.shutdown,
                           exit_code=guard.child.returncode, process=snapshot(guard.child._handle)))

    def running(self):
        if self.guard.child.poll() is not None:
            raise RuntimeError('HUNTER_EXITED')
        if (self.args.session/'cancel').exists():
            raise KeyboardInterrupt
        if time.monotonic() - self.started > self.args.timeout:
            raise TimeoutError('HUNTER_PASS_TIMEOUT')

    def open(self, types):
        from .__main__ import ProtectedHunter
        from .windows import main_window
        from .bulk import visible_count
        self.close()
        self.host = self.args.session/('host-' + str(time.time_ns()))
        self.host.mkdir()
        self.guard = self.stack.enter_context(ProtectedHunter(self.args.hunter,self.host,allow_missing_config=True))
        if self.args.cpu_limit:
            handle = ctypes.c_void_p(int(self.guard.child._handle))
            allowed, system = ctypes.c_size_t(), ctypes.c_size_t()
            kernel = ctypes.windll.kernel32
            if not kernel.GetProcessAffinityMask(handle,ctypes.byref(allowed),ctypes.byref(system)):
                raise ctypes.WinError()
            cpus = [1 << i for i in range(allowed.value.bit_length()) if allowed.value & (1 << i)]
            if not kernel.SetProcessAffinityMask(handle,ctypes.c_size_t(sum(cpus[:self.args.cpu_limit]))):
                raise ctypes.WinError()
        while True:
            self.running()
            try:
                hwnd = main_window(self.guard.child.pid)
                break
            except RuntimeError:
                time.sleep(.2)
        time.sleep(1.5)
        self.display = Window(hwnd,self.host,self.program)
        self.stack.callback(self.display.close)
        self.display.settings(types)
        start = time.monotonic()
        self.display.load(self.guard.child.pid,self.args.index)
        while True:
            self.running()
            text = self.display.text()
            counts = visible_count(text)
            if counts and counts[1] and 'export all' in text.lower() and self.display.export_enabled():
                break
            time.sleep(.5)
        self.types = tuple(types)
        self.total = counts[1]
        return time.monotonic()-start

    @staticmethod
    def report(job,event,**values):
        row = dict(event=event,utc=now(),**values)
        print(json.dumps(row,ensure_ascii=False),file=sys.stderr,flush=True)
        with (job/'progress.jsonl').open('a',encoding='utf8') as f:
            f.write(json.dumps(row,ensure_ascii=False)+'\n')

    def export(self,job,record,query):
        from .bulk import visible_count, merge_outputs
        self.started = time.monotonic()
        self.before = None
        reuse = self.types == tuple(record['types'])
        record['filter_seconds'] = 0
        if reuse:
            record.update(host=self.host.name,index_reused=True)
            self.before = snapshot(self.guard.child._handle)
            clear_start = time.monotonic()
            try:
                self.display.clear_filter(self.total)
            finally:
                record['filter_seconds'] = time.monotonic() - clear_start
            index_seconds = 0
        else:
            index_seconds = self.open(record['types'])
        before = self.before = snapshot(self.guard.child._handle)
        record.update(host=self.host.name, index_reused=reuse, loaded_assets=self.total,
                      index_seconds=round(index_seconds,3), cpu_limit=self.args.cpu_limit)
        if not reuse:
            record['load_process'] = before
        self.report(job,'index_ready',**record)
        counts = (self.total,self.total)
        if query:
            search_start = time.monotonic()
            try:
                counts, applied = self.display.search(query)
                if not applied:
                    tile = re.fullmatch(r'ts?\[(-?\d+)',query)
                    if tile and tile[1] != '0':
                        # A confirmed literal substring strictly widens this tile search.
                        query = tile[1]
                        counts, applied = self.display.search(query)
                    if not applied:
                        raise RuntimeError('HUNTER_QUERY_READBACK_FAILED: ' + query)
            finally:
                record['filter_seconds'] = round(record['filter_seconds'] + time.monotonic() - search_start, 3)
        record.update(visible_assets=counts[0],applied_query=query)
        self.report(job,'scope_ready',query=query,visible_assets=counts[0],loaded_assets=counts[1])
        output = self.host/'app/exported_files'
        if output.exists() and any(output.iterdir()):
            raise RuntimeError('HUNTER_EXPORT_OUTPUT_NOT_EMPTY')
        export_start = time.monotonic()
        busy = False
        if counts[0]:
            self.display.click(278,598)
            stable = 0
            start_attempts = 1
            last_click = time.monotonic()
            last_progress = last_heartbeat = last_count = None
            idle_since = None
            ready_since = None
            while True:
                self.running()
                text = self.display.text()
                percent = re.search(r'(\d{1,3})\s*%',text)
                busy |= 'cancel' in text.lower() or bool(percent)
                progress = int(percent[1]) if percent else None
                if last_heartbeat is None or progress != last_progress or time.monotonic()-last_heartbeat >= 20:
                    self.report(job,'export_progress',percent=progress,process=snapshot(self.guard.child._handle))
                    last_progress, last_heartbeat = progress,time.monotonic()
                current = visible_count(text)
                complete = (current and current[1] == self.total and (current == counts or query.casefold() in text.casefold())
                            and 'cancel' not in text.lower() and self.display.export_enabled())
                has_output = output.is_dir() and any(output.iterdir())
                stable = stable+1 if complete and has_output and current == last_count else 0
                if complete and has_output:
                    if not stable or ready_since is None:
                        ready_since = time.monotonic()
                else:
                    ready_since = None
                last_count = current
                if not complete and has_output and current and self.display.export_enabled() and 'cancel' not in text.lower():
                    idle_since = idle_since or time.monotonic()
                    if time.monotonic()-idle_since > 30:
                        self.display.capture().save(self.host/'completion-failure.png')
                        raise RuntimeError('HUNTER_COMPLETION_READBACK_FAILED: '+text)
                else:
                    idle_since = None
                if stable >= 2:
                    record['completed_visible_assets'] = current[0]
                if not busy and not has_output and time.monotonic()-last_click > 5:
                    if start_attempts >= 3:
                        self.display.capture().save(self.host/'export-start-failure.png')
                        raise RuntimeError('HUNTER_EXPORT_DID_NOT_START')
                    if self.display.export_enabled():
                        self.display.click(278,598)
                        start_attempts += 1
                        last_click = time.monotonic()
                if stable >= 2:
                    record['confirmation_seconds'] = round(time.monotonic()-ready_since,3)
                    break
                time.sleep(min(.25,self.args.poll) if ready_since is not None else self.args.poll)
        elif query:
            output.mkdir(exist_ok=True)
        else:
            raise RuntimeError('NO_MATCHING_ASSETS')
        record.update(export_seconds=round(time.monotonic()-export_start,3),busy_observed=busy,
                      hunter_process=difference(before,snapshot(self.guard.child._handle)),per_asset_errors=None)
        self.report(job,'export_finished',**record)
        merge_outputs(output,job/'outputs',self.args.session)
        return job.name+'/outputs'

