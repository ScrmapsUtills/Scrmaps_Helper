import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recognition import Reader, Reading, linked, url_project, rank_readings, code_views, color_masks, glyph_spans, auth_boxes
import numpy as np


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
        self.reader.line=lambda _mask,box,scale:data[box]
        def read_code(_source,_mask,box):
            texts=[first,second,second] if box==self.code_box else [next(text for b,text in extras if b==box)]*3
            readings=[Reading(text,score,(score,)*len(text)) for text in texts]
            code,alts,positions,strong,average=rank_readings(readings)
            return dict(code=code,alternatives=alts,uncertain=positions,trusted=strong,
                        score=average,uppercase=any(t==t.upper() for t in texts))
        self.reader.read_code=read_code
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


class CharacterVerificationTests(unittest.TestCase):
    def test_label_is_separated_at_a_real_gap_without_a_fixed_screen_region(self):
        for offset in [0,73]:
            mask=np.zeros((30,180+offset),np.uint8)
            mask[5:18,offset:offset+9]=255;mask[5:18,offset+12:offset+20]=255
            for i in range(9):mask[6:17,offset+35+i*6:offset+39+i*6]=255
            boxes=auth_boxes(mask,(offset,3,100,18))
            self.assertEqual(len(boxes),1);self.assertEqual(boxes[0][0],offset+34)

    def test_strong_conflict_survives_normalization_and_chunk_success(self):
        reader=Reader.__new__(Reader)
        wrong=Reading('ABGDE2345',.999,(.999,)*9)
        weak=Reading('ABGDE2345',.8,(.8,)*9)
        good=Reading('ABCDE2345',.999,(.999,)*9)
        readings=iter([wrong,weak,weak,good,good,good])
        reader.observe=lambda _image:next(readings)
        mask=np.zeros((12,55),np.uint8)
        for i in range(9):mask[2:10,i*6:i*6+4]=255
        with patch('recognition.code_views',return_value=([(255-mask,True)]*3,mask)),patch.object(reader,'verify_chunks',return_value=(True,[])):
            result=reader.read_code(None,None,None)
        self.assertEqual(result['code'],good.code);self.assertFalse(result['trusted']);self.assertIn(3,result['uncertain'])

    def test_two_weak_characters_hidden_by_a_high_mean_are_not_trusted(self):
        code='ABCDEFGHJKL23456789'
        chars=[.999]*len(code);chars[2]=.72;chars[7]=.70
        rows=[Reading(code,sum(chars)/len(chars),tuple(chars))]*3
        best,alts,positions,trusted,score=rank_readings(rows)
        self.assertGreater(score,.96)
        self.assertEqual(best,code);self.assertEqual(positions,[3,8]);self.assertFalse(trusted)

    def test_one_high_confidence_alternate_is_never_silently_outvoted(self):
        a=Reading('B855Z2G6R',.99,(.99,)*9);b=Reading('B8S5Z2G6R',.99,(.99,)*9)
        code,alts,positions,trusted,_=rank_readings([a,a,b])
        self.assertEqual(code,a.code);self.assertEqual(set(alts),{a.code,b.code})
        self.assertEqual(positions,[3]);self.assertFalse(trusted)

    def test_faint_edge_read_with_strong_letters_beats_two_weak_threshold_reads(self):
        wrong=Reading('B855Z2G6R',.96,(.99,.99,.65,.99,.99,.99,.99,.99,.99))
        good=Reading('B8S5Z2G6R',.999,(.999,)*9)
        code,alts,positions,trusted,_=rank_readings([wrong,wrong,good])
        self.assertEqual(code,good.code);self.assertEqual(alts[0],good.code)
        self.assertIn(3,positions);self.assertFalse(trusted)

    def test_missing_character_confidence_does_not_auto_submit(self):
        self.assertFalse(rank_readings([Reading('ABCDE2345',.999)]*3)[3])

    def test_length_disagreement_marks_review_instead_of_guessing_alignment(self):
        a=Reading('ABCDE2345',.99,(.99,)*9);b=Reading('ABCDE235',.99,(.99,)*8)
        result=rank_readings([a,a,b]);self.assertFalse(result[3]);self.assertEqual(result[2],list(range(1,10)))

    def test_no_forbidden_character_substitutions(self):
        for c in '01IO':
            text='ABCDE234'+c
            self.assertEqual(rank_readings([Reading(text,.999,(.999,)*9)]*3)[0],'')

    def test_preprocessing_keeps_faint_strokes_that_the_old_threshold_loses(self):
        a=np.zeros((12,30,3),np.uint8);a[3:9,4:8]=[0,240,0];a[3:9,8:10]=[0,75,0]
        image=Image.fromarray(a);mask,_=color_masks(image);views,_=code_views(image,mask,(0,0,30,12))
        strict,loose,soft=[q[0] for q in views]
        self.assertGreater(np.count_nonzero(loose<255),np.count_nonzero(strict<255))
        self.assertTrue(np.any((soft>0)&(soft<255)))

    def test_overlapping_chunk_check_exposes_a_systematic_whole_line_error(self):
        reader=Reader.__new__(Reader);mask=np.zeros((12,55),np.uint8)
        for i in range(9):mask[2:10,i*6:i*6+4]=255
        views=[(255-mask,True)]*3
        self.assertEqual(len(glyph_spans(mask)),9)
        # Actual glyphs spell ABCDE2345; the full-line model guessed G at #3.
        rows=iter([Reading('ABCDE2',.99,(.99,)*6)]*2+[Reading('DE2345',.99,(.99,)*6)]*2)
        reader.observe=lambda _image:next(rows)
        trusted,positions=reader.verify_chunks(views,mask,'ABGDE2345')
        self.assertFalse(trusted);self.assertEqual(positions,[3])

    def test_touching_glyphs_do_not_get_arbitrarily_split_to_force_a_match(self):
        reader=Reader.__new__(Reader);mask=np.ones((12,55),np.uint8)*255
        self.assertEqual(reader.verify_chunks([(255-mask,True)]*3,mask,'ABCDE2345'),(False,[]))

    def test_pinned_rapidocr_character_metadata_is_retained(self):
        class Engine:
            def text_rec(self,_image,return_word_box):
                assert return_word_box
                return [('AB C',.97,[20,[['A','B','C']],[[2,5,8]],['en&num'],[.99,.98,.75,.94]])],0.
        reader=Reader.__new__(Reader);reader.engine=Engine()
        result=reader.observe(np.zeros((10,30,3),np.uint8))
        self.assertEqual(result.code,'ABC');self.assertEqual(result.chars,(.99,.98,.94))


if __name__=="__main__":
    unittest.main()
