"""Select fixed regression sentinels or their disjoint complement from unittest discovery."""
import argparse
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
SMOKE = {
    'test_equipment_native.NativeImportTests.test_stable_attribute_slots_survive_reorder_and_preserve_other_fields',
    'test_equipment_native.NativeImportTests.test_memento_talent_relation_is_followed_and_missing_target_is_unavailable',
    'test_native_crafting.NativeCraftingTests.test_first_import_resolves_new_projected_weapon_before_catalog_is_saved',
    'test_native_crafting.NativeCraftingTests.test_reward_highlight_and_mail_delivery_preserve_direct_recipe_grants',
}


def cases(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from cases(test)
        else:
            yield test


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('selection', choices=('smoke', 'remaining'))
    args = parser.parse_args(argv)
    sys.path.insert(0, str(ROOT/'tests'))
    if args.selection == 'smoke':
        suite = unittest.defaultTestLoader.loadTestsFromNames(sorted(SMOKE))
    else:
        discovered = unittest.defaultTestLoader.discover(str(ROOT/'tests'))
        suite = unittest.TestSuite(test for test in cases(discovered) if test.id() not in SMOKE)
    return 0 if unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())

