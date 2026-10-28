"""Real, offline RapidOCR tests on generated text, not user screenshots.

Set SCRMAPS_OCR_TEST=1 after installing requirements.txt. Fixtures are synthetic
green/cyan text on a dark background; they do not validate a real game's font.
"""
import os,socket,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

@unittest.skipUnless(os.environ.get('SCRMAPS_OCR_TEST')=='1','Enable SCRMAPS_OCR_TEST for actual bundled-model inference')
class OfflineOCRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from recognition import Reader
        cls.reader=Reader()

    def read(self,size):
        def offline(*args,**kwargs):raise AssertionError('OCR must not use the network')
        with patch.object(socket.socket,'connect',offline),patch.object(socket,'create_connection',offline):
            return self.reader.read(Path(__file__).parent/'fixtures'/f'ocr-{size}.png')

    def test_antialiased_s_is_preserved_and_verified_in_normalized_views(self):
        result=self.read(14)
        self.assertEqual(result.code,'B8S5Z2G6R')
        self.assertEqual(result.project,'testmap');self.assertTrue(result.confident)
        self.assertEqual(result.uncertain_positions,[])
        self.assertIn('B855Z2G6R',result.alternatives)

    def test_small_text_no_longer_accepts_the_old_consistent_z_to_seven_error(self):
        result=self.read(11)
        self.assertEqual(result.code,'B8S5Z2G6R')
        self.assertEqual(result.project,'testmap');self.assertFalse(result.confident)

    def test_clear_line_passes_whole_line_character_and_chunk_verification(self):
        result=self.read(18)
        self.assertEqual((result.code,result.project),('ZQWMD4FFZ','testmap'))
        self.assertTrue(result.confident)

    def test_larger_font_url_is_joined_as_one_hostname(self):
        result=self.read(22)
        self.assertEqual((result.code,result.project),('ABCDE2345','testmap'))
        self.assertTrue(result.confident)

    @unittest.skipUnless(os.environ.get('SCRMAPS_OCR_IMAGE') and os.environ.get('SCRMAPS_OCR_EXPECTED'),
                         'Set an external regression image and expected code; personal screenshots are not shipped')
    def test_external_regression_screenshot(self):
        result=self.reader.read(os.environ['SCRMAPS_OCR_IMAGE'])
        self.assertEqual(result.code,os.environ['SCRMAPS_OCR_EXPECTED'])
        if os.environ.get('SCRMAPS_OCR_PROJECT'):
            self.assertEqual(result.project,os.environ['SCRMAPS_OCR_PROJECT'])

if __name__=='__main__':unittest.main()
