import unittest
from unittest.mock import patch
from pathlib import Path

from tools.equipment.crafting import Crafting
from tools.equipment import native_sources as sources, native_tree as tree


ROOT = Path(__file__).resolve().parents[1]
KINDS = ('exotic_cache', 'reconstructed_cache', 'vendor')


def block(header, body):
    return header + '\n{\n' + body + '\n}\n'


def fixture(kind, properties=''):
    """Minimal native entry -> table -> group -> item chain, with two targets."""
    item = lambda tag: block('LootItem ' + tag,
        block('myIncludeLootTags', 'ItemTag Test ' + tag))
    table_uid = {'exotic_cache': '83ED36DA5E172C4B000353E3FB01798A',
                 'reconstructed_cache': 'FB6E28D2643FE7A5000720187D9D4F14',
                 'vendor': 'A' * 32}[kind]
    table_source = sources.LOOT + {'exotic_cache': 'ltdrp_sealed_cache_exotic_item.mloottable',
        'reconstructed_cache': 'ltdrp_sealed_cache_sd_nemesis9_defeat.mloottable',
        'vendor': 'vendor_table.mloottable'}[kind]
    entry_source = {'exotic_cache': sources.ITEM + 'sealed_cache_season_exotic_item.mitem',
        'reconstructed_cache': sources.ITEM + 'sealed_cache_sd_nemesis9_defeat.mitem',
        'vendor': sources.VENDOR}[kind]
    reference = 'myLootTable < uid=' + 'B' * 32 + ' > = vendor_table ' + table_uid
    entry_type = 'VendorConfig' if kind == 'vendor' else 'BundleItem'
    entry = block(entry_type + ' Test < uid=' + 'C' * 32 + ' >', reference)
    documents = {entry_source: entry}
    if kind == 'exotic_cache':
        # The parent group is in a different document from the LootItems.
        content = 'myLootItemList = itemlist_exotics_all ' + '0' * 32
        documents['hunter/game system data/rejuice/itemlist_exotics_all.rejuice'] = block(
            'LootItemList itemlist_exotics_all', item('First') + item('Second'))
        groups = block('LootGroup First', properties + '\n' + content)
    else:
        groups = block('LootGroup First', properties + '\n' + block('myLootItemList', item('First')))
        groups += block('LootGroup Second', block('myLootItemList', item('Second')))
    documents[table_source] = block('LootTable Test < uid=' + table_uid + ' >', block('myLootGroups', groups))
    targets = {'D' * 32: {'tags': ['First']}, 'E' * 32: {'tags': ['Second']}}
    return {name: tree.parse(text) for name, text in documents.items()}, targets


def project(kind, properties=''):
    documents, targets = fixture(kind, properties)
    crafting = Crafting(None, ROOT)

    def document(source):
        if source not in documents:
            raise ValueError('Unrelated fixture entry')
        return documents[source]

    with patch.object(crafting, 'document', side_effect=document):
        sources.project(crafting, targets, targets, [])
    groups = [u['value'] for u in crafting.units if u['path'] == ['routes', kind]]
    return crafting, groups


class NativeSourceProbabilityTests(unittest.TestCase):
    def test_zero_parent_probability_disables_only_its_routes(self):
        for kind in KINDS:
            with self.subTest(kind=kind):
                _, groups = project(kind, 'myDropChancePercentage 0')
                self.assertEqual(len(groups), 1, 'Disabled groups must update old membership, not be unavailable')
                self.assertEqual({uid for route in groups[0].values() for uid in route['targets']}, {'D' * 32, 'E' * 32})
                targets = {uid for route in groups[0].values() if route.get('entry_scope', 'route') == 'route' for uid in route['targets']}
                self.assertEqual(targets, set() if kind == 'exotic_cache' else {'E' * 32})
                self.assertTrue(any(route.get('entry_scope') == 'disabled' for route in groups[0].values()))

    def test_default_and_positive_parent_probabilities_keep_the_same_routes(self):
        for kind in KINDS:
            _, expected = project(kind)
            self.assertTrue(expected[0])
            for chance in ('0.25', '100.0'):
                with self.subTest(kind=kind, chance=chance):
                    _, groups = project(kind, 'myDropChancePercentage ' + chance)
                    self.assertEqual(groups, expected)

    def test_unresolved_parent_probability_preserves_previous_relation_group(self):
        for kind in KINDS:
            for properties in ('myDropChancePercentage unknown', 'myDropChancePercentage NaN',
                               'myDropChancePercentage Infinity', 'myDropChancePercentage -1',
                               'myDropChancePercentage 101',
                               'myDropChancePercentage 0\nmyDropChanceModifierAttribute ' + 'F' * 32):
                with self.subTest(kind=kind, properties=properties):
                    crafting, groups = project(kind, properties)
                    self.assertEqual(groups, [])
                    target = 'crafting_vendor' if kind == 'vendor' else kind
                    self.assertTrue(any(row['target'] == target for row in crafting.unavailable))


if __name__ == '__main__':
    unittest.main()
