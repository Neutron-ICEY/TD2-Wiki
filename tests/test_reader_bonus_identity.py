import json
from pathlib import Path
import unittest
import hashlib

from tools.brand_sets.model import load_catalog
from formal_candidate import candidate
from fixture_corpus import corpus_path
from wiki_subset import WikiSubset

ROOT=Path(__file__).resolve().parents[1]


class ReaderBonusIdentityTests(unittest.TestCase):
    def test_native_identity_and_locale_evidence_do_not_merge_threat_variants(self):
        prefix = 'dist/text-library-20261017-002/inputs/lab/hunter-exports/raw_files/'
        raw = corpus_path(prefix + 'rogue/game system data/juice/attribute/dictionary/_bonus_dictionary.mdict').read_text('utf-8')
        self.assertIn('WeaponThreatPerBulletPositiveModBonus < uid=4F5DDEA254886BEB00003ADA117FFB91 >', raw)
        self.assertIn('WeaponThreatPerBulletNegativeModBonus < uid=4F5DDEA2543FCB9300000DF59A13A4FB >', raw)
        chinese = corpus_path(prefix + 'hunter/localization/packages/chinesegav/menus.locpack').read_text('utf-8')
        self.assertIn('4F5DDEA254886B9600003AD9CFF9ABE1,1,增加威胁,', chinese)


    def test_threat_variants_are_not_merged_in_current_catalog(self):
        catalog,_=load_catalog(ROOT)
        self.assertNotIn('降低威胁度',next(x for x in catalog['attributes'] if x['id']=='bonus_increased_threat')['search_aliases'])


if __name__=='__main__':
    unittest.main()
