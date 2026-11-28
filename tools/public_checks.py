"""Run source checks that use the inputs distributed in the collaboration checkout."""
from pathlib import Path
import json
import sys
import unittest


# These modules open the named fixture while importing. The other exclusions are
# individual tests or classes whose shared setup needs the indicated real inputs.
IMPORT_INPUTS = {
    'test_brand_data_completeness': 'tests/fixtures/resource-corpus.zip',
    'test_named_structure': 'tests/fixtures/named-structures.json',
    'test_text_extract': 'tests/fixtures/resource-corpus.zip',
}
PRIVATE_TESTS = {
    'tests/fixtures/resource-corpus.zip': (
        'test_asset_library.ExistingCorpusTests',
        'test_reader_bonus_identity.ReaderBonusIdentityTests.test_native_identity_and_locale_evidence_do_not_merge_threat_variants',
        'test_text_evidence.RealEvidenceTests',
        'test_text_library.ExistingTextCorpusTests',
        'test_text_library.HistoricalTextInputTests.test_archived_inputs_fail_closed_without_current_data_fallback',
        'test_text_library.HistoricalTextInputTests.test_changed_snapshot_registry_is_rejected',
    ),
    'tests/fixtures/equipment-native/hunter and rogue': (
        'test_equipment_native.NativeImportTests.test_generation_version_is_read_from_native_table',
        'test_equipment_native.NativeImportTests.test_memento_talent_relation_is_followed_and_missing_target_is_unavailable',
        'test_equipment_native.NativeImportTests.test_real_brand_modes_and_nested_dictionary_percentage',
        'test_equipment_native.NativeImportTests.test_real_memento_pvp_parameter_change_is_independent',
        'test_equipment_native.NativeImportTests.test_real_mode_updates_import_only_changed_description_and_initialize_without_overwrite',
        'test_equipment_native.NativeImportTests.test_real_native_editor_reimport_and_reader_round_trip',
        'test_equipment_native.NativeImportTests.test_real_negotiator_pvp_tooltip_only_parameter_changes_its_mode',
        'test_equipment_native.NativeImportTests.test_real_perfect_talents_inherit_text_but_keep_child_parameters',
        'test_equipment_native.NativeImportTests.test_real_steel_pvp_update_preserves_pve_and_obeys_independent_switches',
        'test_equipment_native.NativeImportTests.test_stable_attribute_slots_survive_reorder_and_preserve_other_fields',
        'test_equipment_rules.EquipmentRulesTests.test_incomplete_pvp_override_does_not_use_pve',
        'test_equipment_rules.EquipmentRulesTests.test_invalid_pvp_text_does_not_fall_back_to_pve',
    ),
    'tests/fixtures/core-configs.json': (
        'test_equipment_rules.EquipmentRulesTests.test_actual_configs_keep_core_count_candidates_and_selection_independent',
    ),
    'registered Wiki image files': (
        'test_brand_publication.BrandPublicationTests.test_page_identity_stays_separate_from_verified_file_publication',
        'test_brand_publication.BrandPublicationTests.test_stage_blocks_unknown_remote_state_and_alternative_payload',
        'test_exotic_lua.ExoticLuaTests.test_talent_logos_reuse_registered_files_and_acosta_remains_distinct',
        'test_icon_parser_budget.IconParserBudgetTests.test_registered_projection_matches_current_catalog',
        'test_image_naming.ImageNamingTests.test_registered_assets_have_unique_current_addresses',
        'test_local_equipment_icons.LocalEquipmentIconsTests.test_contract_is_scoped_and_not_publication',
        'test_reader_logo_fit.ReaderLogoFitTests.test_registered_logos_fit_the_shared_area_at_native_size',
        'test_reader_materials.ReaderMaterialTests.test_five_explicit_names_and_quality',
        'test_reader_status_icons.ReaderStatusIconsTests.test_approved_icons_remain_local_ready',
        'test_weapons.WeaponsTests.test_all_navigation_targets_and_registered_images',
        'test_weapons.WeaponsTests.test_weapon_records_share_the_identity_validator',
    ),
    'publication history and readback receipts': (
        'test_brand_publication.BrandPublicationTests.test_unrecorded_file_revision_or_changed_upload_is_rejected',
        'test_publishing.PublishingTests.test_repository_baseline_receipts_are_available',
    ),
    'homepage snapshot and registered images': (
        'test_homepage.HomepageIndexTests.test_homepage_uses_the_game_calendar_and_its_registered_images',
    ),
}


def cases(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from cases(test)
        else:
            yield test


def python_tests(output):
    tests = Path(__file__).resolve().parents[1] / 'tests'
    sys.path.insert(0, str(tests))
    excluded = {name: reason for reason, names in PRIVATE_TESTS.items() for name in names}
    applicable = unittest.TestSuite()
    not_applicable = []
    for path in sorted(tests.glob('test_*.py')):
        if path.stem in IMPORT_INPUTS:
            not_applicable.append(dict(name=path.stem, reason='Module import requires ' + IMPORT_INPUTS[path.stem]))
            continue
        for test in cases(unittest.defaultTestLoader.loadTestsFromName(path.stem)):
            name = test.id()
            reason = excluded.get(name) or excluded.get(name.rpartition('.')[0])
            if reason:
                not_applicable.append(dict(name=name, reason=reason))
            else:
                applicable.addTest(test)
    output.write_text(json.dumps(not_applicable, indent=2) + '\n', encoding='utf8')
    result = unittest.TextTestRunner(verbosity=2).run(applicable)
    return 0 if result.wasSuccessful() and result.testsRun else 1


def run(root, output, python, node, dependency_check, run_step):
    """Use the same subprocess logs and exit-code/skip checks as the full verifier."""
    inventory = output / 'public-test-inputs.json'
    frontend = str(output / 'frontend')
    steps = [
        ('dependencies', python + ['-c', dependency_check]),
        ('brand-generation', python + ['-m', 'tools.brand_sets', 'check']),
        ('gear-generation', [node, 'tools/gear_sets/generate.cjs', 'check']),
        ('editor-data', [node, 'tools/equipment/catalog.cjs', 'check']),
        ('exotic-generation', [node, 'tools/exotic_gear/generate.cjs', 'check']),
        ('weapon-generation', python + ['-m', 'tools.equipment.weapons', 'check']),
        ('editor-build', [node, 'ui/editor/production/build.cjs', frontend]),
        ('reader-assembly', python + ['-m', 'tools.brand_sets.production', '--output', frontend]),
        ('node-tests', [node, '--test', '--test-reporter=tap', '--test-concurrency=1',
                        *[str(p.relative_to(root)) for p in sorted((root / 'tests').glob('test_*.cjs'))]]),
        ('python-tests', python + ['-m', 'tools.public_checks', str(inventory)]),
    ]
    not_applicable = [
        dict(name='identity', reason='Full registry validation reads registered Wiki image files'),
        dict(name='publish-build', reason='The complete content bundle requires registered binaries and publication history'),
        dict(name='publish-prepare', reason='Requires the complete content bundle'),
        dict(name='resource integration', reason='Requires installed game exports and private source indexes'),
    ]
    checks, not_run = [], []
    for name, command in steps:
        if checks and (checks[0]['exit_code'] or checks[0]['skipped']):
            not_run.append(name)
        elif name == 'reader-assembly' and (checks[-1]['exit_code'] or checks[-1]['skipped']):
            not_run.append(name)
        else:
            checks.append(run_step(name, command))
    if inventory.is_file():
        not_applicable.extend(json.loads(inventory.read_text('utf8')))
    print(f'{len(not_applicable)} checks or modules not applicable to the public checkout (see result.json)', flush=True)
    return checks, dict(mode='public', not_run=not_run, not_applicable=not_applicable)


if __name__ == '__main__':
    raise SystemExit(python_tests(Path(sys.argv[1])))
