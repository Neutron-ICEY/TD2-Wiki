"""Process CPU, peak resident memory and OS-reported transfer counters."""
import os
import time


def snapshot(handle=None):
    if os.name != 'nt':
        import resource
        import sys
        usage = resource.getrusage(resource.RUSAGE_SELF)
        return {'cpu_seconds': time.process_time(),
                'peak_working_set_bytes': usage.ru_maxrss * (1 if sys.platform == 'darwin' else 1024)} if handle is None else {}
    import ctypes as c
    from ctypes import wintypes as w
    kernel = c.windll.kernel32
    process = w.HANDLE(-1 if handle is None else int(handle))

    class Memory(c.Structure):
        _fields_ = [('size', w.DWORD), ('faults', w.DWORD)] + [
            (name, c.c_size_t) for name in ('peak', 'working', 'peak_paged', 'paged',
                                            'peak_nonpaged', 'nonpaged', 'pagefile', 'peak_pagefile')]

    times = (c.c_uint64 * 4)()
    io = (c.c_uint64 * 6)()
    mem = Memory()
    mem.size = c.sizeof(mem)
    result = {}
    if kernel.GetProcessTimes(process, *[c.byref(times, i * 8) for i in range(4)]):
        result['cpu_seconds'] = (times[2] + times[3]) / 10_000_000
    if kernel.GetProcessIoCounters(process, c.byref(io)):
        result.update(read_operations=io[0], write_operations=io[1], read_bytes=io[3], write_bytes=io[4])
    if c.windll.psapi.GetProcessMemoryInfo(process, c.byref(mem), mem.size):
        result['peak_working_set_bytes'] = mem.peak
    return result


def difference(before, after):
    return {key: value if key == 'peak_working_set_bytes' else value - before[key]
            for key, value in after.items() if key in before}

