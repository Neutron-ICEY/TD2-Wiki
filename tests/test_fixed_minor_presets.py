"""Fixed Minor Preset domain fixtures are not game facts."""
import copy
import unittest

from tools.brand_sets.fixed_minor import validate_catalog, resolve, encode, decode, decimal_text, search_records, candidates


class FixedMinorPresetTests(unittest.TestCase):
    def setUp(self):
        self.minor = {"schema_version": 2, "attributes": [{
            "id": "minor_attribute_test", "zh_name": "测试属性（非游戏事实）",
            "en_name": "Test Attribute", "category": "offense", "unit_type": "percent",
            "search_aliases": ["ceshi shuxing"], "active": True,
            "verification": "非游戏事实", "sources": []}]}
        self.data = {"schema_version": 1, "presets": [self.row("fixed_minor_test", "0")]}

    def row(self, key, value, active=True):
        return dict(id=key, minor_attribute_id="minor_attribute_test", value=value,
                    active=active, search_aliases=[], verification="非游戏事实", sources=[])

    def test_domain_and_reference_validation(self):
        validate_catalog(self.data, self.minor)
        for key in ("bonus_test", "minor_attribute_test", "unknown"):
            with self.assertRaises(ValueError): decode(key, self.data, self.minor)
        bad=copy.deepcopy(self.data)
        bad["presets"][0]["minor_attribute_id"]="bonus_test"
        with self.assertRaises(ValueError): validate_catalog(bad,self.minor)

    def test_decimal_and_semantic_duplicates(self):
        self.assertEqual(decimal_text("+012.00"), "12")
        self.assertEqual(decimal_text("-0.00"), "0")
        self.assertEqual(decimal_text("10"), "10")
        bad=copy.deepcopy(self.data)
        bad["presets"].append(self.row("fixed_minor_other", "0"))
        with self.assertRaises(ValueError): validate_catalog(bad,self.minor)
        bad["presets"][1]["active"]=False
        validate_catalog(bad,self.minor)
        bad["presets"][1]["value"]="00.0"
        with self.assertRaises(ValueError): validate_catalog(bad,self.minor)

    def test_assignment_order_and_old_format_rejection(self):
        self.data["presets"].append(self.row("fixed_minor_other", "12"))
        ids=["fixed_minor_other", "fixed_minor_test"]
        self.assertEqual(decode(encode(ids,self.data,self.minor),self.data,self.minor),ids)
        self.assertEqual(decode("",self.data,self.minor),[])
        for text in ("fixed_minor_test;fixed_minor_test", "0~a:minor_attribute_test", "fixed_minor_test;"):
            with self.assertRaises(ValueError): decode(text,self.data,self.minor)

    def test_inactive_is_known_and_search_metadata_is_deterministic(self):
        self.data["presets"][0]["active"]=False
        self.assertEqual(resolve(self.data,self.minor,"fixed_minor_test")["value"],"0")
        self.assertEqual(decode("fixed_minor_test",self.data,self.minor),["fixed_minor_test"])
        rows=search_records(self.data,self.minor)
        self.assertFalse(rows[0]["active"])
        self.assertEqual(candidates(self.data,self.minor),[])
        self.assertIn("ceshi shuxing",rows[0]["keys"])
        self.assertIn("test attribute",rows[0]["keys"])
        self.assertEqual(rows,search_records(self.data,self.minor))

    def test_duplicate_id_and_damaged_reference(self):
        bad=copy.deepcopy(self.data)
        bad['presets'].append(self.row('fixed_minor_test','12'))
        with self.assertRaises(ValueError):validate_catalog(bad,self.minor)
        bad=copy.deepcopy(self.data);bad['presets'][0]['minor_attribute_id']='minor_attribute_missing'
        with self.assertRaises(ValueError):resolve(bad,self.minor,'fixed_minor_test')
