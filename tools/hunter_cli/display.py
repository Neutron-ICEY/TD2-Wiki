"""Inspect and operate the stock window without a Computer Use session."""
import ctypes
from ctypes import wintypes
import os
from pathlib import Path
import subprocess
import time


def compile_reader(directory):
    win = Path(os.environ['SystemRoot'])
    framework = win / 'Microsoft.NET' / 'Framework64' / 'v4.0.30319'
    gac = win / 'Microsoft.NET' / 'assembly' / 'GAC_MSIL'
    refs = []
    for name in ('System.Runtime', 'System.Runtime.WindowsRuntime'):
        ref = next((gac/name).glob('v4.0_4.0.0.0__*/'+name+'.dll'),None)
        if ref is None:
            raise RuntimeError('Windows OCR bridge requires the .NET Framework assembly '+name)
        refs.append(ref)
    refs.extend(win / 'System32' / 'WinMetadata' / ('Windows.' + n + '.winmd')
                for n in ('Foundation', 'Globalization', 'Media', 'Graphics', 'Storage'))
    program = Path(directory).resolve() / 'HunterText.exe'
    subprocess.run([framework / 'csc.exe', '/nologo', '/out:' + str(program),
                    *['/r:' + str(p) for p in refs], Path(__file__).resolve().with_name('HunterText.cs')],
                   check=True, stdin=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)
    return program


def clear_button_x(image):
    """The manual-search and instant-search layouts put Clear in different columns."""
    from itertools import groupby
    row = image.crop((358,58,540,59)).getdata()
    blue = [b-r > 55 and b > 105 for r,g,b in row]
    buttons = []
    for active,group in groupby(enumerate(blue,358),key=lambda pair: pair[1]):
        span = list(group)
        if active and len(span) >= 32:
            buttons.append((span[0][0]+span[-1][0])//2)
    if not buttons:
        raise RuntimeError('HUNTER_CLEAR_BUTTON_NOT_VISIBLE')
    return buttons[-1]


class Window:
    def __init__(self, hwnd, directory, program):
        from . import windows
        self.win = windows
        self.hwnd = hwnd
        windows.u.ShowWindow(hwnd, 9)
        windows.declare(windows.u, 'SetWindowPos', wintypes.BOOL, [wintypes.HWND, wintypes.HWND,
                        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, wintypes.UINT])
        if not windows.u.SetWindowPos(hwnd,-1,0,0,0,0,0x13):
            raise ctypes.WinError(ctypes.get_last_error())
        self.capture_file = directory / 'controls.png'
        self.ocr = subprocess.Popen([program], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                    encoding='utf-8', creationflags=subprocess.CREATE_NO_WINDOW)
        self.win.declare(self.win.u, 'PostMessageW', wintypes.BOOL,
                         [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM])

    def close(self):
        self.ocr.stdin.close()
        try:
            self.ocr.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.ocr.kill()
            self.ocr.wait()
        self.ocr.stdout.close()

    def capture(self):
        from PIL import ImageGrab
        image = ImageGrab.grab(window=int(self.hwnd))
        scale = self.win.u.GetDpiForWindow(self.hwnd) / 96
        if abs(image.width / scale - 980) > 3 or abs(image.height / scale - 625) > 3:
            raise RuntimeError('WINDOW_LAYOUT_CHANGED')
        return image.resize((980, 625))

    def export_enabled(self):
        border = self.capture().crop((248, 582, 308, 585))
        return max(b - r for r, g, b in border.getdata()) > 75

    def text(self):
        from PIL import Image, ImageOps
        image = self.capture()
        bars = Image.new('RGB', (970, 110))
        bars.paste(image.crop((8, 52, 978, 94)), (0, 0))
        bars.paste(image.crop((8, 568, 978, 625)), (0, 50))
        ImageOps.invert(bars).resize((1455, 165)).save(self.capture_file)
        self.ocr.stdin.write(str(self.capture_file.resolve()) + '\n')
        self.ocr.stdin.flush()
        text = self.ocr.stdout.readline()
        if not text:
            raise RuntimeError('WINDOW_OCR_UNAVAILABLE')
        return text.strip()

    def click(self, x, y):
        win = self.win
        scale = win.u.GetDpiForWindow(self.hwnd) / 96
        pt = wintypes.POINT(round(x * scale), round(y * scale))
        packed = (pt.y << 16) | pt.x
        saved = wintypes.POINT()
        win.u.GetCursorPos(ctypes.byref(saved))
        win.u.ClientToScreen(self.hwnd, ctypes.byref(pt))
        if not win.u.SetCursorPos(pt.x, pt.y):
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            time.sleep(.15)
            for message, button in ((0x200, 0), (0x201, 1), (0x202, 0)):
                win.send(self.hwnd, message, button, packed)
                time.sleep(.12)
            time.sleep(.22)
        finally:
            current = wintypes.POINT()
            win.u.GetCursorPos(ctypes.byref(current))
            if (current.x, current.y) == (pt.x, pt.y):
                win.u.SetCursorPos(saved.x, saved.y)
        time.sleep(.22)

    def settings(self, wanted):
        positions = {'models':173, 'animations':201, 'images':230, 'materials':259,
                     'sounds':288, 'raw_files':317}
        def selected(image, y):
            box = image.crop((282, y - 8, 302, y + 8))
            if sum(b > 140 and b > r + 80 for r, g, b in box.getdata()) < 110:
                image.save(self.capture_file.with_name('settings-failure.png'))
                raise RuntimeError('HUNTER_SETTINGS_NOT_RECOGNIZED')
            return sum(min(rgb) > 215 for rgb in box.getdata()) > 8

        for _ in range(3):
            screen = self.capture()
            blue = screen.crop((18,582,50,585)).getdata()
            if max(b-r for r,g,b in blue) > 75:
                self.click(925,24)
            self.click(130,97)
            screen = self.capture()
            try:
                current = {key for key,y in positions.items() if selected(screen,y)}
            except RuntimeError:
                continue
            for key,y in positions.items():
                if (key in current) != (key in wanted):
                    self.click(292,y)
            final = self.capture()
            if {key for key,y in positions.items() if selected(final,y)} == set(wanted):
                self.click(925,24)
                return
        raise RuntimeError('HUNTER_SCOPE_READBACK_FAILED')

    def clear_filter(self, total):
        from .bulk import visible_count
        text = self.text()
        if visible_count(text) == (total,total) and 'showing' not in text.lower():
            return
        self.click(clear_button_x(self.capture()), 73)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            text = self.text()
            if visible_count(text) == (total,total) and 'showing' not in text.lower():
                return
            time.sleep(.2)
        raise RuntimeError('HUNTER_SEARCH_CLEAR_FAILED')

    def search(self, query):
        from .bulk import SEARCH_TEXT, visible_count
        if not SEARCH_TEXT.fullmatch(query):
            raise ValueError('UNSUPPORTED_HUNTER_SEARCH_TEXT')
        self.click(105, 73)
        def type_key(key, character=None):
            code = self.win.u.MapVirtualKeyW(key, 0) << 16 | 1
            self.win.u.PostMessageW(self.hwnd, 0x100, key, code)
            if character is not None:
                self.win.u.PostMessageW(self.hwnd, 0x102, ord(character), code)
            self.win.u.PostMessageW(self.hwnd, 0x101, key, code | 0xC0000000)
            time.sleep(.08)
        for char in query:
            vk = self.win.u.VkKeyScanW(ord(char)) & 255
            type_key(vk, char)
        type_key(13)
        deadline = time.monotonic() + 8
        previous = None
        while time.monotonic() < deadline:
            text = self.text()
            counts = visible_count(text)
            if counts and query.casefold() in text.casefold() and 'showing' in text.casefold():
                if counts == previous:
                    return counts, True
                previous = counts
            else:
                previous = None
            time.sleep(.35)
        self.capture().save(self.capture_file.with_name('query-failure.png'))
        self.capture_file.with_name('query-failure.txt').write_text(text, encoding='utf8')
        # An unreadable filter must never narrow the discovery scope silently.
        self.click(clear_button_x(self.capture()), 73)
        time.sleep(.4)
        text = self.text()
        counts = visible_count(text)
        if not counts or counts[0] != counts[1] or 'showing' in text.lower():
            raise RuntimeError('HUNTER_SEARCH_CLEAR_FAILED')
        return counts, False

    def load(self, pid, index):
        self.click(50, 598)
        deadline = time.monotonic() + 12
        while not any('Select game files' in row['title'] for row in self.win.windows(pid)):
            if time.monotonic() > deadline:
                raise RuntimeError('HUNTER_FILE_DIALOG_TIMEOUT')
            time.sleep(.15)
        self.win.open_file_dialog(pid, index)

