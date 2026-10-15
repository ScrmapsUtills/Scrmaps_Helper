import hashlib,io,json,sys,tempfile,unittest,zipfile
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import build_offline,build_macos
from release_files import LEGACY_DOCS
from core import APP_VERSION
from fetch_windows_inputs import download

class ReleasePolicyTests(unittest.TestCase):
    def test_public_export_keeps_build_files_and_excludes_private_data_and_old_txt(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            files={
                'app.py':'pass','README.md':'readme','THIRD_PARTY.md':'notices','requirements.txt':'deps',
                '.gitignore':'*.log','.github/workflows/macos-build.yml':'name: Installers',
                'docs/BUILD.md':'guide','settings.json':'private nickname','tokens.json':'private token',
                'history.sqlite3':'private history','embedded_profile/Cookies':'private cookie',
                'AppData/Local/SCRMapsHelper/private.txt':'private AppData',
            }
            files.update({name:'old explanation' for name in LEGACY_DOCS})
            for name,value in files.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text(value)
            archive=root/'source.zip';build_offline.sources_zip(archive,root=root)
            with zipfile.ZipFile(archive) as z:
                names=set(z.namelist())
                self.assertEqual(names,{'app.py','README.md','THIRD_PARTY.md','requirements.txt','.gitignore',
                                      '.github/workflows/macos-build.yml','docs/BUILD.md'})

    def test_installer_inventory_omits_explanation_txt_but_keeps_component_licenses(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name in (*LEGACY_DOCS,'runtime/LICENSE.txt','THIRD_PARTY_NOTICES/component/NOTICE.txt'):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('notice')
            names={x['path'] for x in build_offline.inventory(root)}
            self.assertEqual(names,{'runtime/LICENSE.txt','THIRD_PARTY_NOTICES/component/NOTICE.txt'})

    def test_mac_bundle_version_matches_application(self):
        text=build_macos.spec_text(Path('/work'),'arm64',Path('/notices'),Path('/source.zip'))
        self.assertIn(repr(APP_VERSION),text)
        self.assertEqual(build_offline.VERSION,APP_VERSION)

    def test_download_refuses_unverified_bytes_and_keeps_destination_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'runtime.zip';path.write_bytes(b'previous')
            expected={'bytes':4,'sha256':hashlib.sha256(b'good').hexdigest()}
            with patch('fetch_windows_inputs.urllib.request.urlopen',return_value=io.BytesIO(b'bad!')):
                with self.assertRaisesRegex(ValueError,'mismatch'):download('https://example.invalid/input',path,expected)
            self.assertEqual(path.read_bytes(),b'previous');self.assertFalse(path.with_suffix('.zip.part').exists())

    def test_download_accepts_only_exact_pinned_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'runtime.zip';expected={'bytes':4,'sha256':hashlib.sha256(b'good').hexdigest()}
            with patch('fetch_windows_inputs.urllib.request.urlopen',return_value=io.BytesIO(b'good')):
                download('https://example.invalid/input',path,expected)
            self.assertEqual(path.read_bytes(),b'good')

if __name__=='__main__':unittest.main()
