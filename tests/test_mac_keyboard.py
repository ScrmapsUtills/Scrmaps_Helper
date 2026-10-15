import sys
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from key_sender import scan_plan
from mac_keyboard import MacKeyboard,SCAN_TO_MAC,CAPS_FLAG,SHIFT_FLAG
from paths import data_folder

class MacTests(unittest.TestCase):
    def keyboard(self):
        keyboard=object.__new__(MacKeyboard)
        keyboard.cg=Mock();keyboard.cf=Mock();keyboard.shift=False
        keyboard.permission_error=lambda:'';keyboard.caps=lambda:False
        keyboard.cg.CGEventCreateKeyboardEvent.return_value=123
        return keyboard

    def test_code_maps_to_apple_physical_keys_with_two_returns(self):
        self.assertEqual([SCAN_TO_MAC[s] for s,_ in scan_plan('ABCDE2345')],
                         [0,11,8,2,14,19,20,21,23,36,36])
        for char in 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789':
            self.assertIn(scan_plan(char*5)[0][0],SCAN_TO_MAC)

    def test_event_modifier_flags_and_release_are_explicit(self):
        keyboard=self.keyboard();keyboard.send(0x2a,True);keyboard.send(0x1e,True)
        keyboard.cg.CGEventSetFlags.assert_called_with(123,SHIFT_FLAG)
        keyboard.send(0x1e,False);keyboard.send(0x2a,False)
        keyboard.cg.CGEventSetFlags.assert_called_with(123,0)
        self.assertEqual(keyboard.cf.CFRelease.call_count,4)

    def test_caps_lock_and_injection_failure_cleanup(self):
        keyboard=self.keyboard();keyboard.caps=lambda:True
        keyboard.cg.CGEventPost.side_effect=OSError('blocked')
        with self.assertRaises(OSError):keyboard.send(0x1e,True)
        keyboard.cg.CGEventSetFlags.assert_called_once_with(123,CAPS_FLAG)
        keyboard.cf.CFRelease.assert_called_once_with(123)

    def test_missing_permission_blocks_key_down_but_allows_cleanup(self):
        keyboard=self.keyboard();keyboard.permission_message='권한 필요'
        keyboard.permission_error=lambda:keyboard.permission_message
        with self.assertRaisesRegex(OSError,'권한 필요'):keyboard.send(0x1e,True)
        keyboard.cg.CGEventCreateKeyboardEvent.assert_not_called()
        keyboard.send(0x1e,False);keyboard.cf.CFRelease.assert_called_once()

    def test_stores_sessions_in_platform_user_data_directories(self):
        self.assertEqual(data_folder('darwin','/user',{}),Path('/user/Library/Application Support/SCRMapsHelper'))
        self.assertEqual(data_folder('win32','/user',{'LOCALAPPDATA':'/local'}),Path('/local/SCRMapsHelper'))

if __name__=='__main__':unittest.main()
