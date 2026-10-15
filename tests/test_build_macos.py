import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_macos
import build_offline

class MacBuildTests(unittest.TestCase):
    def test_wrong_host_fails_before_installing_dependencies(self):
        with patch.object(sys,'platform','linux'),patch.object(sys,'argv',['build_macos.py']),patch.object(build_macos,'run') as run:
            with self.assertRaisesRegex(SystemExit,'real Mac'):build_macos.main()
            run.assert_not_called()

    def test_generated_spec_handles_spaces_and_is_valid_python(self):
        root=Path('/directory with spaces')
        for arch in ('arm64','x86_64'):
            text=build_macos.spec_text(root,arch,root/'notices',root/'source.zip')
            compile(text,'SCRMapsHelper.spec','exec')
            self.assertIn("console=False",text)
            self.assertIn("'rapidocr_onnxruntime'",text)
            self.assertNotIn('collect_all',text)

    def test_cross_platform_export_contains_build_workflow_but_not_sessions(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'.github/workflows').mkdir(parents=True);(root/'embedded_profile').mkdir()
            (root/'app.py').write_text('pass');(root/'mac_keyboard.py').write_text('pass')
            (root/'build_macos.py').write_text('pass');(root/'BUILD_MACOS_ko.txt').write_text('build')
            (root/'.github/workflows/macos-build.yml').write_text('on: workflow_dispatch')
            (root/'embedded_profile/Cookies').write_text('private')
            (root/'install_files.nsh').write_text('private absolute build paths')
            dest=root/'source.zip'
            with patch.object(build_offline,'ROOT',root):build_offline.sources_zip(dest)
            with zipfile.ZipFile(dest) as archive:
                names=set(archive.namelist())
                self.assertIn('.github/workflows/macos-build.yml',names)
                self.assertIn('mac_keyboard.py',names)
                self.assertFalse(any('Cookies' in x or 'install_files' in x for x in names))

if __name__=='__main__':unittest.main()
