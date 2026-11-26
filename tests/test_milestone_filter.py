import json
import unittest
from pathlib import Path
from tools.brand_sets.member_filter import is_milestone


class MilestoneFilterTests(unittest.TestCase):
    def test_native_inventory_scope(self):
        root = Path(__file__).resolve().parents[1]
        inventory = json.loads((root / 'tests/fixtures/milestone-native-members.json').read_text(encoding='utf-8'))
        affected = {brand['title']: sum(is_milestone(item) for item in brand['members']) for brand in inventory['brands']}
        self.assertEqual({title: count for title, count in affected.items() if count}, {'芬里斯集团公司': 6, '先驱工业': 3})
        self.assertFalse(is_milestone({'internal_name': 'normal', 'name': 'Milestone'}))
        self.assertFalse(is_milestone({'internal_name': 'player_milestones_normal'}))
