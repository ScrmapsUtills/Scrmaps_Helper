import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from build_name_update import FILES,REMOVED_FILES,updated_manifest

class NameUpdateTests(unittest.TestCase):
    def test_only_existing_tracked_files_change_and_original_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);files=[]
            for name in FILES:
                if name=='payload-manifest.json':continue
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'new')
                files.append({'path':name,'bytes':3,'sha256':'old'})
            files.append({'path':'runtime/python312.dll','bytes':100,'sha256':'runtime-unchanged'})
            original={'version':'1.4.2','files':files};before=json.dumps(original,sort_keys=True)
            result=updated_manifest(original,root)
            self.assertEqual(before,json.dumps(original,sort_keys=True))
            self.assertEqual(result['files'][-1],original['files'][-1])
            self.assertTrue(all(x['sha256']!='old' for x in result['files'][:-1]))
            self.assertEqual(len(result['files']),len(files))
            self.assertFalse(any(x.startswith('runtime/') for x in FILES))

    def test_wrong_base_fails_before_modifying_anything(self):
        with self.assertRaisesRegex(ValueError,'1.4.2'):updated_manifest({'version':'1.3','files':[]},Path('/unused'))

    def test_removal_is_limited_to_named_root_documents(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);entries=[]
            for name in FILES:
                if name=='payload-manifest.json':continue
                p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text('new')
                entries.append({'path':name,'bytes':3,'sha256':'old'})
            entries.extend({'path':name,'bytes':1,'sha256':'old'} for name in REMOVED_FILES)
            entries.append({'path':'runtime/LICENSE.txt','bytes':1,'sha256':'license'})
            result=updated_manifest({'version':'1.4.2','files':entries},root)
            names={x['path'] for x in result['files']}
            self.assertFalse(names.intersection(REMOVED_FILES));self.assertIn('runtime/LICENSE.txt',names)
            self.assertTrue(all('/' not in name and '\\' not in name and '*' not in name for name in REMOVED_FILES))

if __name__=='__main__':unittest.main()
