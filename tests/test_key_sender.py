import ctypes
import queue
import sys
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from key_sender import CodeTyper, HotkeyMonitor, INPUT, LETTER_SCANS, scan_plan

class FakeKeyboard:
    def __init__(self):
        self.focus = (100, 123)
        self.game = True
        self.sent = []
        self.keys = set()
        self.on_send = lambda *_: None
    def target(self): return self.focus
    def is_game(self, target): return self.game
    def caps(self): return False
    def down(self, vk): return vk in self.keys
    def send(self, scan, down):
        self.sent.append((scan, down))
        self.on_send(scan, down)
    def permission_error(self):return ''

class FastEvent:
    """Real cancellation flag with virtual time advancement for sender tests."""
    def __init__(self, clock):self.event=threading.Event();self.clock=clock
    def is_set(self):return self.event.is_set()
    def set(self):self.event.set()
    def clear(self):self.event.clear()
    def wait(self, seconds):self.clock[0]+=seconds;return self.is_set()

class KeyboardTests(unittest.TestCase):
    def run_job(self, keyboard, code='ABCDE2345'):
        events=queue.Queue();typer=CodeTyper(events, keyboard);clock=[0.0]
        typer.cancel=FastEvent(clock)
        with patch('key_sender.time.monotonic',side_effect=lambda:clock[0]):
            typer._run(code, keyboard.target(), False)
        return typer, [events.get_nowait()[1]['text'] for _ in range(events.qsize())]

    def assert_released(self, sent):
        held=set()
        for scan,down in sent:
            if down:held.add(scan)
            else:held.discard(scan)
        self.assertEqual(held,set())

    def test_windows_input_abi(self):
        self.assertEqual(ctypes.sizeof(INPUT),40 if ctypes.sizeof(ctypes.c_void_p)==8 else 28)

    def test_physical_code_and_exactly_two_enters(self):
        keyboard=FakeKeyboard();_,status=self.run_job(keyboard)
        keys=[s for s,down in keyboard.sent if down and s!=0x2a]
        self.assertEqual(keys,[LETTER_SCANS[i] for i in range(5)]+[3,4,5,6,0x1c,0x1c])
        self.assert_released(keyboard.sent)
        self.assertIn('Enter 2회 완료',status[-1])

    def test_invalid_code_sends_nothing(self):
        keyboard=FakeKeyboard();self.run_job(keyboard,'ABCD0')
        self.assertEqual(keyboard.sent,[])

    def test_caps_lock_does_not_reverse_case(self):
        self.assertFalse(any(shift for _,shift in scan_plan('ABCDE2345',True)))
        self.assertTrue(scan_plan('ABCDE2345',False)[0][1])

    def test_focus_change_releases_keys_and_never_sends_enter(self):
        keyboard=FakeKeyboard()
        def change(scan,down):
            if down and scan!=0x2a:keyboard.focus=(200,456)
        keyboard.on_send=change
        _,status=self.run_job(keyboard)
        self.assertIn('다른 창',status[-1]);self.assert_released(keyboard.sent)
        self.assertFalse(any(s==0x1c for s,_ in keyboard.sent))

    def test_f9_cancels_and_releases_shift(self):
        keyboard=FakeKeyboard()
        keyboard.on_send=lambda scan,down:keyboard.keys.add(0x78) if down and scan!=0x2a else None
        _,status=self.run_job(keyboard)
        self.assertIn('중단',status[-1]);self.assert_released(keyboard.sent)

    def test_send_failure_still_attempts_key_up(self):
        keyboard=FakeKeyboard()
        def fail(scan,down):
            if scan!=0x2a and down:raise OSError('injection failed')
        keyboard.on_send=fail
        _,status=self.run_job(keyboard)
        self.assertIn('injection failed',status[-1]);self.assert_released(keyboard.sent)

    def test_f8_held_times_out_without_typing(self):
        keyboard=FakeKeyboard();keyboard.keys.add(0x77)
        _,status=self.run_job(keyboard)
        self.assertEqual(keyboard.sent,[]);self.assertIn('F8 키',status[-1])

    def test_ctrl_prevents_typing(self):
        keyboard=FakeKeyboard();keyboard.keys.add(0x11)
        self.run_job(keyboard);self.assertEqual(keyboard.sent,[])

    def test_non_game_foreground_never_starts(self):
        keyboard=FakeKeyboard();keyboard.game=False
        typer=CodeTyper(queue.Queue(),keyboard)
        self.assertFalse(typer.start('ABCDE2345'));self.assertIsNone(typer.thread)

    def test_second_f8_does_not_start_parallel_job(self):
        keyboard=FakeKeyboard();typer=CodeTyper(queue.Queue(),keyboard)
        keyboard.keys.add(0x77)
        self.assertTrue(typer.start('ABCDE2345'))
        try:self.assertFalse(typer.start('ABCDE2345'))
        finally:typer.close()
        self.assert_released(keyboard.sent)

    def test_focus_changed_before_gui_drains_f8_does_not_type(self):
        keyboard=FakeKeyboard();typer=CodeTyper(queue.Queue(),keyboard)
        self.assertFalse(typer.start('ABCDE2345',expected_target=(200,456)))
        self.assertEqual(keyboard.sent,[])

    def test_caps_lookup_failure_is_reported_without_crashing_gui(self):
        keyboard=FakeKeyboard();keyboard.caps=lambda:(_ for _ in ()).throw(OSError('caps failed'))
        events=queue.Queue();typer=CodeTyper(events,keyboard)
        self.assertFalse(typer.start('ABCDE2345'))
        self.assertIn('caps failed',events.get_nowait()[1]['text'])

class HotkeyTests(unittest.TestCase):
    def setUp(self):
        self.events=queue.Queue();self.keyboard=FakeKeyboard();self.monitor=HotkeyMonitor(self.events,self.keyboard)
    def messages(self):
        return [self.events.get_nowait() for _ in range(self.events.qsize())]
    def keys(self):
        return [p for kind,p in self.messages() if kind=='hotkey']

    def test_one_press_one_action_even_when_key_repeats(self):
        self.monitor.sample();self.messages()
        self.keyboard.keys.add(0x77)
        for _ in range(30):self.monitor.sample()
        self.assertEqual(self.keys(),[{'key':'F8','target':(100,123)}])
        self.keyboard.keys.clear();self.monitor.sample()
        self.keyboard.keys.add(0x77);self.monitor.sample()
        self.assertEqual(len(self.keys()),1)

    def test_held_key_on_start_or_permission_grant_never_types(self):
        self.keyboard.keys.add(0x77);self.monitor.sample();self.assertEqual(self.keys(),[])
        self.keyboard.permission_error=lambda:'권한 필요';self.monitor.sample()
        self.keyboard.permission_error=lambda:'';self.monitor.sample()
        self.assertEqual(self.keys(),[])
        self.keyboard.keys.clear();self.monitor.sample()
        self.keyboard.keys.add(0x77);self.monitor.sample();self.assertEqual(len(self.keys()),1)

    def test_simultaneous_f9_takes_precedence(self):
        self.monitor.sample();self.messages()
        self.keyboard.keys={0x77,0x78};self.monitor.sample()
        self.assertEqual(self.keys(),[{'key':'F9'}])

    def test_f8_captures_target_at_detection(self):
        self.monitor.sample();self.messages();self.keyboard.keys.add(0x77);self.monitor.sample()
        self.keyboard.focus=(200,456)
        self.assertEqual(self.keys(),[{'key':'F8','target':(100,123)}])

    def test_monitor_runs_without_qt_window_or_event_dispatch(self):
        self.monitor.start()
        try:
            self.assertEqual(self.events.get(timeout=1)[0],'hotkey_state')
            # Wait until the initial key-state sample is complete.
            import time
            deadline=time.monotonic()+1
            while self.monitor.previous is None and time.monotonic()<deadline:time.sleep(.005)
            self.keyboard.keys.add(0x77)
            kind,payload=self.events.get(timeout=1)
            self.assertEqual((kind,payload['key']),('hotkey','F8'))
        finally:self.monitor.close()
        self.assertFalse(self.monitor.thread.is_alive())

if __name__=='__main__':unittest.main()
