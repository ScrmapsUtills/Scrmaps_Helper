"""macOS system-framework keyboard backend; no downloaded keyboard dependency.

Uses CoreGraphics for physical keys and AppKit only for the foreground app.
OS calls require real Mac validation before publishing a Mac binary.
"""
from __future__ import annotations
import ctypes as C
from pathlib import Path
import sys
import time
from key_sender import LETTER_SCANS

MAC_LETTERS = (0,11,8,2,14,3,5,4,34,38,40,37,46,45,31,35,12,15,1,17,32,9,13,7,16,6)
SCAN_TO_MAC = dict(zip(LETTER_SCANS, MAC_LETTERS))
SCAN_TO_MAC.update({3:19,4:20,5:21,6:23,7:22,8:26,9:28,10:25,0x1c:36,0x2a:56})
VK_TO_MAC = {0x77:(100,),0x78:(101,),0x14:(57,),0x11:(59,62),0x12:(58,61),
             0x5b:(55,),0x5c:(54,),0xa0:(56,),0xa1:(60,)}
CAPS_FLAG, SHIFT_FLAG = 1 << 16, 1 << 17

class MacKeyboard:
    def __init__(self):
        if sys.platform != 'darwin':
            raise OSError('macOS 전용 키보드입니다.')
        self.cg = C.CDLL('/System/Library/Frameworks/CoreGraphics.framework/CoreGraphics')
        self.cf = C.CDLL('/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation')
        self.appkit = C.CDLL('/System/Library/Frameworks/AppKit.framework/AppKit')
        self.objc = C.CDLL('/usr/lib/libobjc.A.dylib')
        def bind(lib, name, result, args):
            fn = getattr(lib, name);fn.restype = result;fn.argtypes = args
            return fn
        bind(self.cg,'CGEventSourceKeyState',C.c_bool,[C.c_int32,C.c_uint16])
        bind(self.cg,'CGEventSourceFlagsState',C.c_uint64,[C.c_int32])
        bind(self.cg,'CGEventCreateKeyboardEvent',C.c_void_p,[C.c_void_p,C.c_uint16,C.c_bool])
        bind(self.cg,'CGEventSetFlags',None,[C.c_void_p,C.c_uint64])
        bind(self.cg,'CGEventPost',None,[C.c_uint32,C.c_void_p])
        for name in ('CGPreflightListenEventAccess','CGPreflightPostEventAccess',
                     'CGRequestListenEventAccess','CGRequestPostEventAccess'):
            bind(self.cg,name,C.c_bool,[])
        bind(self.cf,'CFRelease',None,[C.c_void_p])
        bind(self.objc,'objc_getClass',C.c_void_p,[C.c_char_p])
        bind(self.objc,'sel_registerName',C.c_void_p,[C.c_char_p])
        bind(self.objc,'objc_autoreleasePoolPush',C.c_void_p,[])
        bind(self.objc,'objc_autoreleasePoolPop',None,[C.c_void_p])
        address = C.cast(self.objc.objc_msgSend,C.c_void_p).value
        self.msg = C.CFUNCTYPE(C.c_void_p,C.c_void_p,C.c_void_p)(address)
        self.msg_int = C.CFUNCTYPE(C.c_int,C.c_void_p,C.c_void_p)(address)
        self.msg_text = C.CFUNCTYPE(C.c_char_p,C.c_void_p,C.c_void_p)(address)
        self.selectors = {s:self.objc.sel_registerName(s.encode()) for s in
                          ('sharedWorkspace','frontmostApplication','processIdentifier','executableURL','path','UTF8String')}
        self.shift = False
        self.permission_checked = 0
        self.permission_message = ''

    def permission_error(self):
        now = time.monotonic()
        if now - self.permission_checked >= 1:
            missing = []
            if not self.cg.CGPreflightListenEventAccess():missing.append('입력 모니터링')
            if not self.cg.CGPreflightPostEventAccess():missing.append('손쉬운 사용')
            self.permission_message = ('macOS 권한 필요: '+', '.join(missing)+
                ' · 설정의 ‘키 입력 권한 확인’을 누르세요. 허용 후 앱을 다시 실행하세요.') if missing else ''
            self.permission_checked = now
        return self.permission_message

    def request_permissions(self):
        # Invoked from an explicit GUI button, never repeatedly from the poller.
        if not self.cg.CGPreflightListenEventAccess():self.cg.CGRequestListenEventAccess()
        if not self.cg.CGPreflightPostEventAccess():self.cg.CGRequestPostEventAccess()
        self.permission_checked = 0
        return self.permission_error()

    def target(self):
        pool = self.objc.objc_autoreleasePoolPush()
        try:
            workspace = self.msg(self.objc.objc_getClass(b'NSWorkspace'),self.selectors['sharedWorkspace'])
            app = self.msg(workspace,self.selectors['frontmostApplication'])
            if not app:return 0,''
            pid = self.msg_int(app,self.selectors['processIdentifier'])
            url = self.msg(app,self.selectors['executableURL'])
            path = self.msg(url,self.selectors['path'])
            text = self.msg_text(path,self.selectors['UTF8String'])
            return pid,(text or b'').decode('utf-8','replace')
        finally:
            self.objc.objc_autoreleasePoolPop(pool)

    def is_game(self, target):
        return Path(target[1]).name.lower() in {'starcraft','starcraft64','starcraft remastered','starcraft x64'}

    def describe_target(self, target):
        return '%s · PID %s' % (Path(target[1]).name or '알 수 없는 앱',target[0])

    def down(self, vk):
        return any(self.cg.CGEventSourceKeyState(1,key) for key in VK_TO_MAC.get(vk,()))

    def caps(self):
        return bool(self.cg.CGEventSourceFlagsState(1) & CAPS_FLAG)

    def send(self, scan, down):
        if scan not in SCAN_TO_MAC:raise ValueError('지원하지 않는 키 코드')
        # Key-up must remain possible after permission revocation for cleanup.
        if down and self.permission_error():raise OSError(self.permission_message)
        event = self.cg.CGEventCreateKeyboardEvent(None,SCAN_TO_MAC[scan],down)
        if not event:raise OSError('macOS 키 입력 이벤트를 만들지 못했어요.')
        if scan == 0x2a:self.shift = down
        try:
            flags = (CAPS_FLAG if self.caps() else 0) | (SHIFT_FLAG if self.shift else 0)
            self.cg.CGEventSetFlags(event,flags)
            self.cg.CGEventPost(0,event)
        finally:
            self.cf.CFRelease(event)
