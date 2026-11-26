from contextlib import redirect_stderr
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools.asset_import import investigate, pipeline


class PackageInputTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(dir=os.environ.get('TD2_ASSET_LIBRARY_TEST_TMP'))
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.inputs = {'apk': 'new/custom.apk', 'windows': 'new/custom.exe'}
        for name in self.inputs.values():
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'synthetic package path fixture')
        self.output = self.root / 'dist/review'

    def test_explicit_inputs_have_no_historical_name_dependency(self):
        self.assertEqual(self.inputs, investigate.resolve_inputs(self.root, self.output, self.inputs))
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
        row = investigate.image_record('apk', 'icons/sample.svg', svg, self.output, self.inputs['apk'])
        self.assertEqual(row['source_package'], 'new/custom.apk')
        self.assertEqual((self.output / row['raw_path']).read_bytes(), svg)

    def test_missing_inputs_fail_before_creating_output(self):
        for inputs in (None, {}, {'apk': self.inputs['apk']}, dict(self.inputs, windows='missing.exe')):
            with self.subTest(inputs=inputs):
                with self.assertRaisesRegex(ValueError, 'EXPLICIT_PACKAGE_INPUTS_REQUIRED|EXPECTED_INPUT_MISSING'):
                    investigate.investigate(self.root, self.output, 'unused-pwsh', inputs)
                with self.assertRaisesRegex(ValueError, 'EXPLICIT_PACKAGE_INPUTS_REQUIRED|EXPECTED_INPUT_MISSING'):
                    pipeline.run_import(self.root, self.output, self.root / 'dist/staging', 'unused-pwsh', inputs)
                self.assertFalse(self.output.exists())

    def test_distinct_sources_must_be_outside_output(self):
        with self.assertRaisesRegex(ValueError, 'PACKAGE_INPUTS_MUST_BE_DISTINCT'):
            investigate.resolve_inputs(self.root, self.output, {'apk': self.inputs['apk'], 'windows': self.inputs['apk']})
        with self.assertRaisesRegex(ValueError, 'PACKAGE_INPUT_OVERLAPS_OUTPUT'):
            investigate.resolve_inputs(self.root, self.root / 'new', self.inputs)

    def test_both_cli_entries_require_explicit_packages(self):
        for module in (investigate, pipeline):
            for arguments in ([], ['--apk', 'new.apk'], ['--windows', 'new.exe']):
                with self.subTest(module=module.__name__, arguments=arguments):
                    with patch('sys.argv', ['test', '--pwsh', 'unused-pwsh', *arguments]):
                        with redirect_stderr(io.StringIO()):
                            with self.assertRaises(SystemExit) as error:
                                module.main()
                    self.assertEqual(error.exception.code, 2)
        self.assertFalse(self.output.exists())

    def test_report_accepts_new_package_metadata_without_legacy_filename_version(self):
        base = dict(size=1, file_signature='synthetic', sha256='a' * 64)
        apk = dict(base, relative_path='new/custom.apk', absolute_path=str(self.root / 'new/custom.apk'),
                   filename='custom.apk', metadata=dict(package='fixture', versionName='31.0', versionCode='31',
                   minSdkVersion='1', targetSdkVersion='2'), structure={})
        windows = dict(base, relative_path='new/custom.exe', absolute_path=str(self.root / 'new/custom.exe'),
                       filename='custom.exe', version_info=dict(ProductName='fixture', ProductVersion='32.0',
                       FileVersion='32.0'), assembly_version='32.0', pe=dict(type='PE32+', architecture='x64'),
                       bundle=dict(single_file=True, format_version=[6, 0], entry_count=0), maui=False,
                       self_contained=False, runtime={}, missing_external_dependencies=[], pe_image_resource_count=0)
        package = dict(apk=apk, windows=windows, version_relationship='different',
                       skipped_unrelated_strings=0, immutable_verification={})
        contract = dict(explanation='synthetic', examples=[], automatic_normalization_gate='CLOSED',
                        naming_contract_conflicts=[])
        self.output.mkdir(parents=True)
        pipeline.write_report(self.root, self.output, package, [], [], [], [], [], [], contract,
                              dict(approved_image_count=0), {})
        report = (self.output / 'ASSET-IMPORT-REPORT.md').read_text('utf-8')
        self.assertIn('new/custom.apk', report)
        self.assertIn('**different**', report)
        self.assertNotIn('29.0.0', report)
        self.assertNotIn('manifest index 98', report)


if __name__ == '__main__':
    unittest.main()
