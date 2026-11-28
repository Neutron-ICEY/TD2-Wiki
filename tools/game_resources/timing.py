"""Per-command timings; counters never participate in resource identity."""
from collections import defaultdict
from contextlib import contextmanager
import json
import sys
from time import perf_counter
from tools.process_metrics import snapshot, difference


# Per-file counters stay in the existing tight loop. Sample OS accounting only at batch boundaries.
MEASURE_PROCESS = {
    'inventory', 'apply_files', 'dependency_check', 'dependency_recheck', 'manifest_current',
    'manifest_next', 'manifest_merge', 'plan_validation', 'layer_validation', 'native_index',
    'discover_identities', 'projection', 'import_preview', 'hunter_pass', 'commit_output',
    'count_exported_files', 'check_source_metadata', 'verify_complete_source',
}


class Timings:
    def __init__(self, command=None):
        self.command = command
        self.started = perf_counter()
        self.start_metrics = snapshot()
        self.end_metrics = None
        self.finished = None
        self.stages = defaultdict(lambda: {'seconds': 0.0, 'exclusive_seconds': 0.0, 'calls': 0, 'files': 0, 'bytes': 0})
        self.children = []
        self.covered = 0.0

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        self.finished = perf_counter()
        self.end_metrics = snapshot()
        print(json.dumps({'event': 'resource_timing', 'command': self.command,
                          'succeeded': kind is None, **self.result()}, separators=(',', ':')),
              file=sys.stderr, flush=True)

    def add(self, name, seconds, files=0, bytes=0, exclusive=None):
        row = self.stages[name]
        row['seconds'] += seconds
        row['exclusive_seconds'] += seconds if exclusive is None else exclusive
        row['calls'] += 1
        row['files'] += files
        row['bytes'] += bytes

    @contextmanager
    def stage(self, name, files=0, bytes=0):
        start_process = snapshot() if name in MEASURE_PROCESS else None
        started = perf_counter()
        self.children.append(0.0)
        try:
            yield
        finally:
            elapsed = perf_counter() - started
            children = self.children.pop()
            if self.children:
                self.children[-1] += elapsed
            else:
                self.covered += elapsed
            self.add(name, elapsed, files, bytes, elapsed - children)
            if start_process is not None:
                metrics = self.stages[name].setdefault('process_inclusive', {})
                for key, value in difference(start_process, snapshot()).items():
                    if key == 'peak_working_set_bytes':
                        metrics[key] = max(metrics.get(key,0),value)
                    else:
                        metrics[key] = metrics.get(key,0) + value

    def call(self, name, function, *args, **kwargs):
        with self.stage(name):
            return function(*args, **kwargs)

    def result(self):
        elapsed = (self.finished or perf_counter()) - self.started
        return {'process': difference(self.start_metrics, self.end_metrics or snapshot()), 'elapsed_seconds': round(elapsed, 6),
                'unattributed_seconds': round(max(0.0, elapsed - self.covered), 6),
                'stages': {name: {**row, 'seconds': round(row['seconds'], 6),
                                 'exclusive_seconds': round(row['exclusive_seconds'], 6)}
                           for name, row in sorted(self.stages.items())}}


def timed_files(iterator, timing):
    """Time generator advancement, excluding the caller's hashing/processing time."""
    iterator = iter(iterator)
    while True:
        with timing.stage('scan'):
            item = next(iterator, None)
        if item is None:
            return
        yield item
