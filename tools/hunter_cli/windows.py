"""少量 Win32 互操作；所有窗口均按目标进程定位。"""
import ctypes as c
from ctypes import wintypes as w
import time

u = c.WinDLL('user32', use_last_error=True)
k = c.WinDLL('kernel32', use_last_error=True)
u.SetProcessDpiAwarenessContext(c.c_void_p(-4))

def declare(lib, name, result, args):
    f = getattr(lib, name)
    f.restype, f.argtypes = result, args
    return f

declare(u, 'GetWindowThreadProcessId', w.DWORD, [w.HWND, c.POINTER(w.DWORD)])
declare(u, 'GetWindowTextW', c.c_int, [w.HWND, w.LPWSTR, c.c_int])
declare(u, 'GetClassNameW', c.c_int, [w.HWND, w.LPWSTR, c.c_int])
declare(u, 'IsWindowVisible', w.BOOL, [w.HWND])
declare(u, 'GetDlgCtrlID', c.c_int, [w.HWND])
declare(u, 'SendMessageTimeoutW', c.c_ssize_t,
        [w.HWND, w.UINT, w.WPARAM, w.LPARAM, w.UINT, w.UINT, c.POINTER(c.c_size_t)])
declare(u, 'SetForegroundWindow', w.BOOL, [w.HWND])
declare(u, 'GetForegroundWindow', w.HWND, [])
declare(u, 'ShowWindow', w.BOOL, [w.HWND, c.c_int])
declare(u, 'OpenClipboard', w.BOOL, [w.HWND])
declare(u, 'CloseClipboard', w.BOOL, [])
declare(u, 'EmptyClipboard', w.BOOL, [])
declare(u, 'GetClipboardData', w.HANDLE, [w.UINT])
declare(u, 'SetClipboardData', w.HANDLE, [w.UINT, w.HANDLE])
declare(u, 'GetClipboardSequenceNumber', w.DWORD, [])
declare(k, 'GlobalAlloc', w.HGLOBAL, [w.UINT, c.c_size_t])
declare(k, 'GlobalLock', c.c_void_p, [w.HGLOBAL])
declare(k, 'GlobalUnlock', w.BOOL, [w.HGLOBAL])
declare(k, 'GlobalFree', w.HGLOBAL, [w.HGLOBAL])

def windows(pid, parent=None):
    result = []
    @c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def visit(hwnd, _):
        found = w.DWORD()
        u.GetWindowThreadProcessId(hwnd, c.byref(found))
        if found.value == pid:
            title, cls = c.create_unicode_buffer(2048), c.create_unicode_buffer(256)
            u.GetWindowTextW(hwnd, title, len(title))
            u.GetClassNameW(hwnd, cls, len(cls))
            result.append(dict(hwnd=hwnd, title=title.value, cls=cls.value,
                               control_id=u.GetDlgCtrlID(hwnd), visible=bool(u.IsWindowVisible(hwnd))))
        return True
    if parent is None:
        u.EnumWindows(visit, 0)
    else:
        declare(u, 'EnumChildWindows', w.BOOL, [w.HWND, type(visit), w.LPARAM])(parent, visit, 0)
    return result

def main_window(pid):
    matches = [v for v in windows(pid) if v['title'] == 'Hunter v2.2.9']
    if len(matches) != 1:
        raise RuntimeError('HUNTER_WINDOW_NOT_UNIQUE')
    return matches[0]['hwnd']

def request_close(pid):
    hwnd = main_window(pid)
    post = declare(u, 'PostMessageW', w.BOOL, [w.HWND, w.UINT, w.WPARAM, w.LPARAM])
    if not post(hwnd, 0x0010, 0, 0):  # WM_CLOSE
        raise c.WinError(c.get_last_error())

def send(hwnd, message, wp=0, lp=0):
    result = c.c_size_t()
    c.set_last_error(0)
    if not u.SendMessageTimeoutW(hwnd, message, wp, lp, 2, 5000, c.byref(result)):
        raise OSError(c.get_last_error(), 'WINDOW_MESSAGE_FAILED')
    return result.value

def set_text(hwnd, text):
    buf = c.create_unicode_buffer(text)
    return send(hwnd, 0xC, 0, c.addressof(buf))

def clipboard(text=None):
    for _ in range(20):
        if u.OpenClipboard(None):
            break
        time.sleep(.05)
    else:
        raise RuntimeError('CLIPBOARD_BUSY')
    try:
        if text is not None:
            data = (text + '\0').encode('utf-16le')
            mem = k.GlobalAlloc(0x42, len(data))
            if not mem:
                raise c.WinError(c.get_last_error())
            ptr = k.GlobalLock(mem)
            c.memmove(ptr, data, len(data))
            k.GlobalUnlock(mem)
            if not u.EmptyClipboard() or not u.SetClipboardData(13, mem):
                k.GlobalFree(mem)
                raise c.WinError(c.get_last_error())
            return text
        mem = u.GetClipboardData(13)
        if not mem:
            return None
        ptr = k.GlobalLock(mem)
        try:
            return c.wstring_at(ptr)
        finally:
            k.GlobalUnlock(mem)
    finally:
        u.CloseClipboard()

class KEYBDINPUT(c.Structure):
    _fields_ = [('vk',w.WORD),('scan',w.WORD),('flags',w.DWORD),('time',w.DWORD),('extra',c.c_size_t)]
class MOUSEINPUT(c.Structure):
    _fields_ = [('dx',w.LONG),('dy',w.LONG),('data',w.DWORD),('flags',w.DWORD),('time',w.DWORD),('extra',c.c_size_t)]
class INPUT_UNION(c.Union):
    _fields_ = [('ki',KEYBDINPUT),('mi',MOUSEINPUT)]
class INPUT(c.Structure):
    _fields_ = [('kind',w.DWORD),('value',INPUT_UNION)]
declare(u,'SendInput',w.UINT,[w.UINT,c.POINTER(INPUT),c.c_int])
declare(u,'MapVirtualKeyW',w.UINT,[w.UINT,w.UINT])
declare(u,'ClientToScreen',w.BOOL,[w.HWND,c.POINTER(w.POINT)])
declare(u,'GetClientRect',w.BOOL,[w.HWND,c.POINTER(w.RECT)])
declare(u,'GetDpiForWindow',w.UINT,[w.HWND])
declare(u,'SetCursorPos',w.BOOL,[c.c_int,c.c_int])
declare(u,'WindowFromPoint',w.HWND,[w.POINT])
declare(k,'GetCurrentThreadId',w.DWORD,[])
declare(u,'AttachThreadInput',w.BOOL,[w.DWORD,w.DWORD,w.BOOL])

def focus(hwnd):
    u.ShowWindow(hwnd, 9)
    for _ in range(5):
        u.SetForegroundWindow(hwnd)
        time.sleep(.15)
        if u.GetForegroundWindow() == hwnd: return
        # 后台守护进程没有最近的用户输入；短暂连接前台线程输入队列后立即解除。
        foreground=u.GetForegroundWindow()
        thread=u.GetWindowThreadProcessId(foreground,None)
        current=k.GetCurrentThreadId()
        attached=thread!=current and u.AttachThreadInput(current,thread,True)
        try:
            if attached: u.SetForegroundWindow(hwnd)
        finally:
            if attached: u.AttachThreadInput(current,thread,False)
        time.sleep(.15)
        if u.GetForegroundWindow()==hwnd: return
    raise RuntimeError('FOCUS_NOT_ACQUIRED')

def key(hwnd, vk, modifiers=()):
    if u.GetForegroundWindow() != hwnd:
        raise RuntimeError('FOCUS_LOST')
    sequence = [(m,0) for m in modifiers]+[(vk,0),(vk,2)]+[(m,2) for m in reversed(modifiers)]
    # Winit 依据扫描码识别修饰键；只填写虚拟键会出现字母可用、Ctrl 组合失效。
    events = (INPUT * len(sequence))(*[INPUT(1,INPUT_UNION(ki=KEYBDINPUT(
        v,u.MapVirtualKeyW(v,0),f | (1 if v in (33,34,35,36,37,38,39,40,45,46) else 0),0,0))) for v,f in sequence])
    for event in events:
        if u.SendInput(1, c.byref(event), c.sizeof(INPUT)) != 1:
            raise RuntimeError('KEY_INPUT_FAILED')
        time.sleep(.04)
    time.sleep(.15)

def open_file_dialog(pid, path):
    dialogs = [v for v in windows(pid) if v['cls']=='#32770' and 'Select game files' in v['title']]
    if len(dialogs)!=1:
        raise RuntimeError('FILE_DIALOG_NOT_FOUND')
    dialog = dialogs[0]['hwnd']
    edits = [v for v in windows(pid,dialog) if v['cls']=='Edit' and v['control_id']==1148]
    if len(edits)!=1:
        raise RuntimeError('FILE_NAME_EDIT_NOT_FOUND')
    set_text(edits[0]['hwnd'],str(path))
    send(dialog,0x111,1,0)

def choose_export_folder(pid, path):
    dialogs=[v for v in windows(pid) if v['cls']=='#32770' and 'Select an export directory' in v['title']]
    if len(dialogs)!=1: raise RuntimeError('EXPORT_FOLDER_DIALOG_NOT_FOUND')
    dialog=dialogs[0]['hwnd']
    edits=[v for v in windows(pid,dialog) if v['cls']=='Edit' and v['control_id']==1152]
    if len(edits)!=1: raise RuntimeError('FOLDER_EDIT_NOT_FOUND')
    # 先导航并回读地址栏，再提交“当前文件夹”；避免快速双确认选到旧目录。
    focus(dialog);key(dialog,ord('D'),(18,))
    clipboard(str(path));key(dialog,ord('V'),(17,));key(dialog,13)
    from pathlib import Path
    actual=None
    for _ in range(5):
        time.sleep(.5)
        key(dialog,ord('D'),(18,));clipboard('__FOLDER_ADDRESS__');key(dialog,ord('C'),(17,))
        actual=clipboard()
        if actual and Path(actual).resolve()==Path(path).resolve(): break
    else:
        raise RuntimeError('FOLDER_ADDRESS_READBACK_FAILED')
    set_text(edits[0]['hwnd'],'')
    send(dialog,0x111,1,0)

def click_client(hwnd, x, y):
    """仅供固定版本实验；调用方必须用剪贴板回读验证实际资源，不能靠坐标认定身份。"""
    focus(hwnd)
    scale=u.GetDpiForWindow(hwnd)/96
    point=w.POINT(round(x*scale),round(y*scale));u.ClientToScreen(hwnd,c.byref(point))
    if u.WindowFromPoint(point)!=hwnd:
        raise RuntimeError('TARGET_OCCLUDED')
    u.SetCursorPos(point.x,point.y)
    time.sleep(.1)
    for flag in (2,4):
        event=INPUT(0,INPUT_UNION(mi=MOUSEINPUT(0,0,0,flag,0,0)))
        if u.SendInput(1,c.byref(event),c.sizeof(INPUT))!=1:
            raise RuntimeError('MOUSE_INPUT_FAILED')
        time.sleep(.08)
    time.sleep(.25) # 等待 Iced 完成控件切换后再操作下一项。
