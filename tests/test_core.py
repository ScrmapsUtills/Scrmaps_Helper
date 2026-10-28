import sys
import tempfile
import sqlite3
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core import History, NewFiles, project_slug, valid_code, validate_roi
from web_gateway import MapParser
from PIL import Image


class ValidationTests(unittest.TestCase):
    def test_map_scope(self):
        self.assertEqual(project_slug('CR2'),'cr2')
        self.assertEqual(project_slug("https://www.scrmaps.com/theking/"),"theking")
        self.assertEqual(project_slug("asdasd"),"asdasd")
        for text in ("https://evil.example/theking","https://www.scrmaps.com.evil.com/theking","https://www.scrmaps.com@evil.com/x","http://www.scrmaps.com/x","https://www.scrmaps.com:444/x","../x","api","login","https://www.scrmaps.com/x?y=1","https://www.scrmaps.com/x#z"):
            with self.subTest(text=text),self.assertRaises(ValueError):
                project_slug(text)

    def test_codes_are_not_silently_guessed(self):
        self.assertEqual(valid_code("zqwm d4ffz"),"ZQWMD4FFZ")
        for value in ("ZQWMD4FF0","ZQWMD4FF1","ZQWMD4FFI","ZQWMD4FFO","ABCD","A"*65,"ABCDE;DELETE"):
            with self.subTest(value=value),self.assertRaises(ValueError):
                valid_code(value)

    def test_save_display_separators_are_removed_without_changing_auth_validation(self):
        from core import valid_save_code
        for text in ['9G5 - C4B - A5R','9G5-C4B-A5R','9G5 – C4B – A5R','9G5 — C4B — A5R','9G5 − C4B − A5R','9g5  c4b  a5r']:
            with self.subTest(text=text):self.assertEqual(valid_save_code(text),'9G5C4BA5R')
        with self.assertRaises(ValueError):valid_code('9G5-C4B-A5R')
        for text in ['https://www.scrmaps.com/ABC-DEF','/ABC-DEF','ABC_DEF','-ABCDE','ABCDE-', '9G5-C4B-A50','9G5-C4B-A51','9G5-C4B-A5I','9G5-C4B-A5O']:
            with self.subTest(text=text),self.assertRaises(ValueError):valid_save_code(text)
        with self.assertRaises(ValueError):valid_save_code('ABC - DEF',project='abc-def')
        with self.assertRaises(ValueError):valid_save_code('9G5 - C4B - A5R',auth='9G5C4BA5R')

    def test_roi(self):
        self.assertEqual(validate_roi([0,.3,1,.42]),(0,.3,1,.42))
        for roi in ([0,0,0,1],[0,.6,1,.3],[-1,0,1,1],[0,0,2,1]):
            with self.assertRaises(ValueError): validate_roi(roi)

    def test_map_parser(self):
        parser=MapParser()
        parser.feed('<a href="/"><img alt="SCRMaps"></a><a href="/theking"><article><img alt="The King RPG"></article></a><a href="/api"><img alt="No"></a>')
        self.assertEqual(parser.cards,{"theking":"The King RPG"})


class HistoryTests(unittest.TestCase):
    def test_duplicate_and_account_project_separation(self):
        with tempfile.TemporaryDirectory() as directory:
            h=History(Path(directory)/"history.db")
            h.put("map1","PlayerA","ZQWMD4FFZ","submitting")
            h.put("map1","PlayerA","ZQWMD4FFZ","ok","9G5C4BA5R")
            h.put("map1","PlayerB","ZQWMD4FFZ","check",detail="error")
            h.put("map2","PlayerA","ZQWMD4FFZ","login")
            self.assertEqual(len(h.list()),3)
            self.assertEqual(h.get("map1","PlayerA","ZQWMD4FFZ")["save"],"9G5C4BA5R")
            self.assertEqual(h.get("map1","PlayerB","ZQWMD4FFZ")["save"],"")
            h.close()
            h=History(Path(directory)/"history.db")
            self.assertEqual(len(h.list("map1","PlayerA")),1)
            h.close()

    def test_legacy_database_retains_data_but_requires_a_site_recheck(self):
        from core import verified_save,SAVE_RESULT_REVISION
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'history.db'
            db=sqlite3.connect(path)
            db.execute("CREATE TABLE runs(id INTEGER PRIMARY KEY,project TEXT,nickname TEXT,auth TEXT,save TEXT,status TEXT,detail TEXT DEFAULT '',image_hash TEXT DEFAULT '',created TEXT DEFAULT '',UNIQUE(project,nickname,auth))")
            db.execute("INSERT INTO runs(project,nickname,auth,save,status) VALUES('testmap','PlayerA','ZQWMD4FFZ','ASDDSA','ok')")
            db.commit();db.close()
            h=History(path);row=h.get('testmap','PlayerA','ZQWMD4FFZ')
            self.assertEqual(row['save'],'ASDDSA');self.assertFalse(verified_save(row))
            h.put('testmap','PlayerA','ZQWMD4FFZ','recovered',save='9G5C4BA5R',result_revision=SAVE_RESULT_REVISION)
            self.assertTrue(verified_save(h.get('testmap','PlayerA','ZQWMD4FFZ')))
            h.close()


class WatcherTests(unittest.TestCase):
    def test_old_files_and_partial_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            Image.new("RGB",(8,8)).save(folder/"old.png")
            now=[0.0]
            watcher=NewFiles(folder,clock=lambda:now[0])
            self.assertEqual(watcher.poll(),[])
            path=folder/"new.png"
            path.write_bytes(b"\x89PNG")
            self.assertEqual(watcher.poll(),[])
            now[0]=1
            self.assertEqual(watcher.poll(),[])
            Image.new("RGB",(10,10),"green").save(path)
            self.assertEqual(watcher.poll(),[])
            now[0]=1.7
            jobs=watcher.poll()
            self.assertEqual([j.path.name for j in jobs],["new.png"])
            now[0]=3
            self.assertEqual(watcher.poll(),[])
            Image.new("RGB",(12,12),"blue").save(path)
            self.assertEqual(watcher.poll(),[])
            now[0]=4
            self.assertEqual(len(watcher.poll()),1)

    def test_recursive_is_opt_in(self):
        with tempfile.TemporaryDirectory() as directory:
            folder=Path(directory)
            (folder/"child").mkdir()
            now=[0.0]
            flat=NewFiles(folder,False,lambda:now[0])
            recursive=NewFiles(folder,True,lambda:now[0])
            Image.new("RGB",(8,8)).save(folder/"child"/"new.png")
            flat.poll(); recursive.poll(); now[0]=1
            self.assertEqual(flat.poll(),[])
            self.assertEqual(len(recursive.poll()),1)


if __name__ == "__main__": unittest.main()
