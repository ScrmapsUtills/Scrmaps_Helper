import io
import tempfile
import unittest
import zipfile
import sys
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_offline import safe_extract,inventory

class OfflineBuildTests(unittest.TestCase):
    def test_omitted_files_cannot_reenter_installer_from_staging(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);(root/'runtime').mkdir()
            (root/'runtime'/'needed.dll').write_bytes(b'needed')
            (root/'runtime'/'unused.dll').write_bytes(b'leftover from extraction')
            (root/'runtime-trim.json').write_text(json.dumps({'removed':[{'path':'unused.dll'}]}))
            names={x['path'] for x in inventory(root)}
            self.assertIn('runtime/needed.dll',names)
            self.assertNotIn('runtime/unused.dll',names)

    def test_archive_cannot_escape_destination(self):
        for name in ('../outside','/absolute','C:/absolute','inside/../../outside','bad\\name'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as folder:
                root=Path(folder);archive=root/'bad.zip'
                with zipfile.ZipFile(archive,'w') as z:z.writestr(name,b'bad')
                with self.assertRaises(ValueError):safe_extract(archive,root/'out')
                self.assertFalse((root/'outside').exists())

    def test_wheel_data_layout_and_exact_binary_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);archive=root/'package.whl'
            with zipfile.ZipFile(archive,'w') as z:
                z.writestr('package/plugin.pyd',b'MZ\x00\xff')
                z.writestr('package.data/purelib/helper.py',b'pass')
                z.writestr('package.data/scripts/unused.exe',b'unused')
                z.writestr('package.dist-info/METADATA',b'Name: package')
            safe_extract(archive,root/'out',wheel=True)
            self.assertEqual((root/'out/package/plugin.pyd').read_bytes(),b'MZ\x00\xff')
            self.assertEqual((root/'out/helper.py').read_bytes(),b'pass')
            self.assertTrue((root/'out/package.dist-info/METADATA').exists())
            self.assertFalse((root/'out/package.data/scripts/unused.exe').exists())

if __name__=='__main__':unittest.main()
