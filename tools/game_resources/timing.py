"""Per-command timings; counters never participate in resource identity."""
from collections import defaultdict
from contextlib import contextmanager
import json
import sys
from time import perf_counter


class Timings:
    def __init__(self, command=None):
        self.command = command
        self.started = perf_counter()
        self.finished = None
        self.stages = defaultdict(lambda: {'seconds': 0.0, 'exclusive_seconds': 0.0, 'calls': 0, 'files': 0, 'bytes': 0})
        self.children = []
        self.covered = 0.0

    def __enter__(self):
        return self

    def __exit__(self, kind, error, traceback):
        self.finished = perf_counter()
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

    def call(self, name, function, *args, **kwargs):
        with self.stage(name):
            return function(*args, **kwargs)

    def result(self):
        elapsed = (self.finished or perf_counter()) - self.started
        return {'elapsed_seconds': round(elapsed, 6),
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
