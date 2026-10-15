"""Execute the production C host against a simulated OS/Py_Main boundary."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
STUBS=Path(__file__).parent/'host_stubs'

@unittest.skipUnless(shutil.which('gcc'),'Requires a host C compiler')
class NativeHostTests(unittest.TestCase):
    def test_startup_argument_forwarding_exit_status_and_failures(self):
        with tempfile.TemporaryDirectory() as folder:
            exe=Path(folder)/'host-test'
            subprocess.run(['gcc','-std=c11','-Wall','-Wextra','-Werror','-I',str(STUBS),
                            str(ROOT/'offline_launcher.c'),str(STUBS/'host_driver.c'),'-o',str(exe)],check=True)
            for case in ('ok','self-test','main-error','truncated','missing-dll','missing-pth',
                         'missing-script','directories-fail','load-fail','export-fail','argv-fail','allocation-fail'):
                with self.subTest(case=case):subprocess.run([str(exe),case],check=True)

if __name__=='__main__':unittest.main()
