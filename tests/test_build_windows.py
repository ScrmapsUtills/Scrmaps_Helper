import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_windows

class BuildTests(unittest.TestCase):
    def test_offline_resources_and_onefile_entrypoint(self):
        args=[str(a) for a in build_windows.options('python','onefile',Path('release'),Path('work'),Path('notices'),Path('sources.zip'))]
        self.assertIn('--onefile',args);self.assertIn('--windowed',args);self.assertIn('--noupx',args)
        for package in ('rapidocr_onnxruntime','onnxruntime','PySide6'):
            self.assertIn(package,args)
        self.assertTrue(args[-1].endswith('app.py'))
        self.assertFalse(any('AutoTyper' in arg for arg in args))

    def test_source_export_excludes_private_folders_and_executables(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'tests').mkdir();(root/'embedded_profile').mkdir()
            (root/'app.py').write_text('pass');(root/'requirements.txt').write_text('')
            (root/'secret.log').write_text('private');(root/'embedded_profile'/'Cookies').write_text('private')
            (root/'AutoTyper.exe').write_text('old');(root/'tests'/'test_example.py').write_text('pass')
            dest=root/'output.zip'
            with patch.object(build_windows,'ROOT',root):build_windows.source_archive(dest)
            with zipfile.ZipFile(dest) as archive:
                self.assertEqual(set(archive.namelist()),{'app.py','requirements.txt','tests/test_example.py'})

    def test_non_windows_build_fails_explicitly(self):
        with patch.object(sys,'platform','linux'),patch.object(sys,'argv',['build_windows.py']):
            with self.assertRaisesRegex(SystemExit,'Windows x64'):build_windows.main()

if __name__=='__main__':unittest.main()
