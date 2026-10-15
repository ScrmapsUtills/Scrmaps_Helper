import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recognition import Reader, linked, url_project


class RecognitionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.image=Path(self.temp.name)/"sample.png"
        Image.new("RGB",(800,600)).save(self.image)
        self.reader=Reader.__new__(Reader)
        self.code_box=(180,130,140,20)
        self.url_box=(100,220,300,20)

    def tearDown(self):
        self.temp.cleanup()

    def read(self, first="ZQWMD4FFZ", second="ZQWMD4FFZ", score=.98, urls=None, extras=None):
        urls=urls if urls is not None else [(self.url_box,"www.scrmaps.com/testmap")]
        data={box:(text,.99) for box,text in urls}
        boxes=[self.code_box]+[b for b,t in extras or []]
        def line(_mask,box,scale):
            if box==self.code_box:
                return (first if scale==3 else second),score
            if box in data:
                return data[box]
            return next((text,.99) for b,text in extras if b==box)
        self.reader.line=line
        with patch("recognition.line_boxes",side_effect=[[box for box,_text in urls],boxes]):
            return self.reader.read(self.image)

    def test_code_and_url_agree(self):
        result=self.read()
        self.assertEqual((result.code,result.project),("ZQWMD4FFZ","testmap"))
        self.assertTrue(result.confident)

    def test_disagreement_requires_review(self):
        self.assertFalse(self.read(second="ZQWMD4FF2").confident)
        self.assertFalse(self.read(score=.88).confident)

    def test_no_url_does_not_auto_submit(self):
        result=self.read(urls=[])
        self.assertEqual(result.code,"ZQWMD4FFZ")
        self.assertFalse(result.confident)
        self.assertEqual(result.project,"")

    def test_multiple_auth_lines_require_review(self):
        result=self.read(extras=[((180,170,140,20),"ABCDE2345")])
        self.assertFalse(result.confident)

    def test_lowercase_hud_label_is_not_a_code(self):
        result=self.read(first="Level",second="Level",urls=[])
        self.assertEqual(result.code,"")

    def test_forbidden_characters_are_not_guessed(self):
        result=self.read(first="ZQWMD4FF0",second="ZQWMD4FF0")
        self.assertFalse(result.confident)
        self.assertEqual(result.code,"")

    def test_conflicting_map_urls_require_review(self):
        result=self.read(urls=[(self.url_box,"scrmaps.com/firstmap"),((100,260,300,20),"scrmaps.com/secondmap")])
        self.assertFalse(result.confident)
        self.assertEqual(result.project,"")

    def test_full_image_no_fixed_region(self):
        result=self.read()
        self.assertEqual(result.box,self.code_box)
        with patch("recognition.line_boxes",side_effect=[[],[]]):
            self.assertEqual(self.reader.read(self.image,[0,0,.01,.01]).code,"")

    def test_project_host_is_restricted(self):
        self.assertEqual(url_project("www.scrmaps.com/ theking"),"theking")
        self.assertEqual(url_project("https://SCRMaps.com/test-map"),"test-map")
        for value in ("https://evil.com/x","evilscrmaps.com/x","www.scrmaps.com.evil.com/x","scrmaps.com/x/evil","scrmaps.com/login","https://evil.com/scrmaps.com/x","scrmaps.com/x?session=abc"):
            with self.subTest(value=value):
                self.assertEqual(url_project(value),"")

    def test_spatial_context_ignores_hud_row(self):
        self.assertTrue(linked(self.code_box,self.url_box))
        self.assertFalse(linked((180,300,140,20),self.url_box))
        self.assertFalse(linked((650,130,100,20),self.url_box))

    def test_numeric_resource_like_string_requires_review(self):
        self.assertFalse(self.read(first="234567892",second="234567892").confident)


if __name__=="__main__":
    unittest.main()
