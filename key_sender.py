"""Global F8/F9 detection and cancellable physical-key typing."""
from __future__ import annotations
import ctypes as C
import sys
import threading
import time
from pathlib import Path
from core import valid_code

LETTER_SCANS = (0x1e,0x30,0x2e,0x20,0x12,0x21,0x22,0x23,0x17,0x24,0x25,0x26,0x32,0x31,0x18,0x19,0x10,0x13,0x1f,0x14,0x16,0x2f,0x11,0x2d,0x15,0x2c)

class Interrupted(Exception):
    pass

class KEYBDINPUT(C.Structure):
    _fields_ = [('wVk', C.c_uint16), ('wScan', C.c_uint16), ('dwFlags', C.c_uint32),
                ('time', C.c_uint32), ('dwExtraInfo', C.c_size_t)]

class MOUSEINPUT(C.Structure):
    _fields_ = [('dx', C.c_int32), ('dy', C.c_int32), ('mouseData', C.c_uint32),
                ('dwFlags', C.c_uint32), ('time', C.c_uint32), ('dwExtraInfo', C.c_size_t)]

class HARDWAREINPUT(C.Structure):
    _fields_ = [('uMsg', C.c_uint32), ('wParamL', C.c_uint16), ('wParamH', C.c_uint16)]

class INPUTUNION(C.Union):
    _fields_ = [('ki', KEYBDINPUT), ('mi', MOUSEINPUT), ('hi', HARDWAREINPUT)]

class INPUT(C.Structure):
    _anonymous_ = ('value',)
    _fields_ = [('type', C.c_uint32), ('value', INPUTUNION)]

def scan_plan(code, caps=False):
    """Validate the entire code before sending anything. Exactly two trailing Enters."""
    code = valid_code(code)
    return [(LETTER_SCANS[ord(c)-65], not caps) if 'A' <= c <= 'Z'
            else (ord(c)-ord('1')+2, False) for c in code] + [(0x1c, False)] * 2

class WindowsKeyboard:
    def __init__(self):
        if sys.platform != 'win32':
            raise OSError('키보드 자동 입력은 Windows에서 사용할 수 있어요.')
        self.u = C.WinDLL('user32', use_last_error=True)
        self.k = C.WinDLL('kernel32', use_last_error=True)
        self.u.GetForegroundWindow.restype = C.c_void_p
        self.u.GetForegroundWindow.argtypes = []
        self.u.GetWindowThreadProcessId.argtypes = [C.c_void_p, C.POINTER(C.c_uint32)]
        self.u.GetWindowThreadProcessId.restype = C.c_uint32
        self.u.GetAsyncKeyState.argtypes = [C.c_int]
        self.u.GetAsyncKeyState.restype = C.c_int16
        self.u.GetKeyState.argtypes = [C.c_int]
        self.u.GetKeyState.restype = C.c_int16
        self.u.SendInput.argtypes = [C.c_uint32, C.POINTER(INPUT), C.c_int]
        self.u.SendInput.restype = C.c_uint32
        self.k.OpenProcess.argtypes = [C.c_uint32, C.c_int, C.c_uint32]
        self.k.OpenProcess.restype = C.c_void_p
        self.k.QueryFullProcessImageNameW.argtypes = [C.c_void_p, C.c_uint32, C.c_wchar_p, C.POINTER(C.c_uint32)]
        self.k.QueryFullProcessImageNameW.restype = C.c_int
        self.k.CloseHandle.argtypes = [C.c_void_p]
        self.k.CloseHandle.restype = C.c_int

    def permission_error(self):
        return ''

    def request_permissions(self):
        return ''

    def target(self):
        hwnd = self.u.GetForegroundWindow()
        pid = C.c_uint32()
        self.u.GetWindowThreadProcessId(hwnd, C.byref(pid))
        return hwnd, pid.value

    def process_name(self, target):
        process = self.k.OpenProcess(0x1000, False, target[1])
        if not process:
            raise OSError('활성 프로그램을 확인하지 못했어요 (Windows 오류 %s). 스타와 Helper를 같은 일반 권한으로 실행하세요.' % C.get_last_error())
        try:
            name = C.create_unicode_buffer(32768)
            size = C.c_uint32(len(name))
            if not self.k.QueryFullProcessImageNameW(process, 0, name, C.byref(size)):
                raise OSError('활성 프로그램 이름을 확인하지 못했어요 (Windows 오류 %s).' % C.get_last_error())
            return Path(name.value).name.lower()
        finally:
            self.k.CloseHandle(process)

    def is_game(self, target):
        return self.process_name(target) in {'starcraft.exe', 'starcraft_x64.exe', 'starcraft remastered.exe'}

    def describe_target(self, target):
        return '%s · PID %s' % (self.process_name(target), target[1])

    def down(self, vk):
        return bool(self.u.GetAsyncKeyState(vk) & 0x8000)

    def caps(self):
        return bool(self.u.GetKeyState(0x14) & 1)

    def send(self, scan, down):
        value = INPUT(type=1)
        value.ki = KEYBDINPUT(0, scan, 0x0008 | (0 if down else 0x0002), 0, 0)
        if self.u.SendInput(1, C.byref(value), C.sizeof(INPUT)) != 1:
            raise OSError('키 입력이 차단됐어요 (Windows 오류 %s). 스타와 Helper를 같은 일반 권한으로 실행하고 다시 시도하세요.' % C.get_last_error())

def make_keyboard():
    if sys.platform == 'win32':
        return WindowsKeyboard()
    if sys.platform == 'darwin':
        from mac_keyboard import MacKeyboard
        return MacKeyboard()
    raise OSError('자동 입력은 Windows와 macOS에서 지원해요.')

class HotkeyMonitor:
    """Poll only F8/F9 on a separate thread, independent of Qt's HWND/message loop.

    Rising edges prevent repeated typing on key-repeat. Keys held when starting
    or granting permission must first be released. No keyboard contents logged.
    """
    def __init__(self, events, backend):
        self.events, self.backend = events, backend
        self.cancel = threading.Event()
        self.previous = None
        self.last_state = None
        self.thread = None

    def sample(self):
        error = self.backend.permission_error()
        state = error or 'F8/F9 감지 준비됨 · 스타 화면에서도 작동 · 키를 눌러 확인하세요.'
        if state != self.last_state:
            self.events.put(('hotkey_state', {'text': state}))
            self.last_state = state
        if error:
            self.previous = None
            return False
        current = {vk: self.backend.down(vk) for vk in (0x77, 0x78)}
        previous, self.previous = self.previous, current
        if previous is None:
            return True
        # F9 wins if both keys rise in the same sample.
        if current[0x78] and not previous[0x78]:
            self.events.put(('hotkey', {'key': 'F9'}))
        elif current[0x77] and not previous[0x77] and not current[0x78]:
            self.events.put(('hotkey', {'key': 'F8', 'target': self.backend.target()}))
        return True

    def _run(self):
        while not self.cancel.is_set():
            try:
                ready = self.sample()
            except Exception as exc:
                state = 'F8/F9 감지 오류: %s' % exc
                if state != self.last_state:
                    self.events.put(('hotkey_state', {'text': state}))
                    self.last_state = state
                self.previous = None
                ready = False
            self.cancel.wait(.01 if ready else 1)

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True, name='F8-F9')
        self.thread.start()

    def close(self):
        self.cancel.set()
        if self.thread:
            self.thread.join(timeout=1.2)

class CodeTyper:
    """One cancellable job; all status delivery goes through the GUI queue."""
    def __init__(self, events, backend=None):
        self.events = events
        self.backend = backend
        self.cancel = threading.Event()
        self.thread = None
        self.lock = threading.Lock()

    def report(self, text):
        self.events.put(('typing', {'text': text}))

    def start(self, code, expected_target=None):
        with self.lock:
            if self.thread and self.thread.is_alive():
                return False
            try:
                valid_code(code or '')
                if self.backend is None:
                    self.backend = make_keyboard()
                error = self.backend.permission_error() if hasattr(self.backend, 'permission_error') else ''
                if error:
                    raise OSError(error)
                target = self.backend.target()
                if expected_target is not None and target != expected_target:
                    raise ValueError('F8을 누른 뒤 창이 바뀌어서 입력하지 않았어요. 스타에서 다시 눌러 주세요.')
                if not self.backend.is_game(target):
                    raise ValueError('스타 화면에서 코드 입력 칸을 선택하고 F8을 눌러 주세요.')
                caps = self.backend.caps()
            except (ValueError, OSError) as exc:
                self.report(str(exc));return False
            self.cancel.clear()
            self.thread = threading.Thread(target=self._run, args=(code, target, caps), daemon=True)
            self.thread.start()
            return True

    def stop(self):
        self.cancel.set()

    def _run(self, code, target, caps):
        held = set()
        backend = self.backend
        def check():
            if self.cancel.is_set() or backend.down(0x78):
                raise Interrupted('입력을 중단했어요.')
            if backend.target() != target:
                raise Interrupted('다른 창으로 이동해서 입력을 중단했어요.')
            if backend.down(0x14):
                raise Interrupted('Caps Lock 키가 눌려 입력을 중단했어요.')
            # Our own left Shift is permitted while writing an uppercase letter.
            keys = (0x11, 0x12, 0x5b, 0x5c, 0xa1)
            if any(backend.down(k) for k in keys) or (0x2a not in held and backend.down(0xa0)):
                raise Interrupted('조합 키가 눌려 입력을 중단했어요.')
        def wait(seconds):
            deadline = time.monotonic() + seconds
            while True:
                check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                self.cancel.wait(min(.01, remaining))
        def press(scan):
            # Remember before the system call so cleanup also covers a partial failure.
            held.add(scan);backend.send(scan, True)
        def release(scan):
            backend.send(scan, False);held.discard(scan)
        try:
            plan = scan_plan(code, caps)
            self.report('입력 중 · F9 중단')
            # F8 is a hotkey: wait for release, then a short quiet period.
            deadline = time.monotonic() + 2.5
            while backend.down(0x77):
                wait(.01)
                if time.monotonic() >= deadline:
                    raise Interrupted('F8 키에서 손을 뗀 뒤 다시 눌러 주세요.')
            wait(.15)
            for scan, shift in plan:
                check()
                if shift:
                    press(0x2a)
                press(scan)
                wait(.10 if scan == 0x1c else .05)
                release(scan)
                if shift:
                    release(0x2a)
                # Enters have a longer gap than letters for the game's polling rate.
                wait(.20 if scan == 0x1c else .05)
            self.report('코드 입력 + Enter 2회 완료 · 다시 입력하려면 F8')
        except (Interrupted, OSError, ValueError) as exc:
            self.report(str(exc))
        except Exception:
            self.report('키보드 입력 중 오류가 발생했어요. 다시 시도해 주세요.')
        finally:
            for scan in sorted(held, key=lambda s: s == 0x2a):
                try:
                    backend.send(scan, False)
                except OSError:
                    self.report('키 해제를 확인하지 못했어요. Shift/Enter 키를 한 번 눌렀다 떼어 주세요.')

    def close(self):
        self.stop()
        if self.thread:
            self.thread.join(timeout=1)
