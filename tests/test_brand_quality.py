"""NON-GAME-FACT checks: transparent padding and channel views cannot imply an upgrade."""
from pathlib import Path
import io
import tempfile
import unittest
from PIL import Image
from tools.asset_import.brand_quality import raster_measurements
from tools.asset_import.pipeline import review_html

def payload(image):
    buffer=io.BytesIO(); image.save(buffer,format='PNG'); return buffer.getvalue()

class RasterQualityTests(unittest.TestCase):
    def test_large_canvas_does_not_increase_effective_pattern(self):
        small=Image.new('RGBA',(32,32),(0,0,0,0)); small.paste((255,255,255,255),(8,10,16,18))
        large=Image.new('RGBA',(512,512),(0,0,0,0)); large.paste(small,(200,200))
        a=raster_measurements(payload(small)); b=raster_measurements(payload(large))
        self.assertGreater(b['pixel_count'],a['pixel_count'])
        self.assertEqual((b['effective_pattern_width'],b['effective_pattern_height']),(8,8))
        self.assertEqual(b['alpha_nonzero_pixels'],a['alpha_nonzero_pixels'])
        self.assertNotIn('preferred_asset',b)

    def test_low_alpha_fringe_is_distinct_from_substantial_region(self):
        image=Image.new('RGBA',(16,16),(255,255,255,0)); image.putpixel((0,0),(255,255,255,1)); image.paste((255,255,255,255),(6,6,10,10))
        result=raster_measurements(payload(image))
        self.assertEqual(result['effective_pattern_bbox'],[0,0,10,10])
        self.assertEqual(result['substantial_alpha_bbox'],[6,6,10,10])
        self.assertEqual(result['alpha_partial_pixels'],1)

    def test_single_channel_mask_is_not_claimed_as_transparent_png(self):
        image=Image.new('L',(16,16),0); image.paste(255,(6,6,10,10))
        result=raster_measurements(payload(image))
        self.assertFalse(result['alpha_channel'])
        self.assertEqual(result['effective_pattern_bbox'],[0,0,16,16])
        self.assertEqual(result['alpha_min'],255)

def review_asset():
    return dict(asset_id='NON-GAME-FACT',category='brand',status='candidate',source_platform='hunter',source_entry='fixture',
        source_filename='fixture.png',source_format='PNG',width=128,height=128,game_entities=[],chinese_names=[],english_names=[],
        stable_id=None,icon_key=None,normalized_filename=None,confidence='unverified',match_method=[],duplicate_group=[],evidence=[],
        naming_gate='PENDING',raw_path='fixture.png',review_platforms=['hunter','windows'],
        review_images=[dict(label='APP <script>',path='app.png'),dict(label='HUNTER',path='hunter.png',note='candidate')])

class QualityReviewTests(unittest.TestCase):
    def test_reuses_review_filters_and_escapes_native_comparison(self):
        with tempfile.TemporaryDirectory() as temp:
            out=Path(temp); review_html(out,[review_asset()],[]); text=(out/'review.html').read_text('utf-8')
            self.assertIn('APP &lt;script&gt;',text)
            self.assertIn('image-rendering:pixelated',text)
            self.assertIn('max-width:none',text)
            self.assertIn('<option value="hunter">Hunter</option>',text)
            self.assertIn('pageSize=48',text)
            self.assertNotIn('APP <script>',text)
            self.assertNotIn('mapping_verified',text)

    def test_comparison_rejects_external_and_parent_paths(self):
        with tempfile.TemporaryDirectory() as temp:
            for path in ('https://example.test/x.png','../external.png','C:/external.png'):
                with self.subTest(path=path):
                    item=review_asset(); item['review_images'][1]['path']=path
                    with self.assertRaises(ValueError): review_html(Path(temp),[item],[])

if __name__=='__main__':unittest.main()
