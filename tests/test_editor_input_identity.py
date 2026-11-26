import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

from formal_candidate import ROOT, candidate
from tools.brand_sets.production import assemble


class EditorInputIdentityTests(unittest.TestCase):
    def rejected(self, mutate):
        with tempfile.TemporaryDirectory(dir=ROOT / 'dist') as temp:
            output = Path(temp)
            shutil.copytree(candidate() / 'editor', output / 'editor')
            manifest_file = output / 'editor/manifest.json'
            manifest = json.loads(manifest_file.read_text(encoding='utf8'))
            mutate(manifest, output / 'editor')
            manifest_file.write_text(json.dumps(manifest), encoding='utf8')
            with self.assertRaisesRegex(ValueError, 'input identity/version'):
                assemble(ROOT, output, True)
            self.assertFalse((output / 'resources').exists())
            self.assertFalse((output / 'resource-plan.json').exists())

    def test_complete_input_set_and_hashes_are_required(self):
        for mutate in [lambda m, _: m['inputs'].pop(),
                       lambda m, _: m['inputs'].append(dict(m['inputs'][0])),
                       lambda m, _: m['inputs'][0].update(source='data/unknown.json'),
                       lambda m, _: m['inputs'][0].update(sha256='0' * 64)]:
            with self.subTest(mutate=mutate):
                self.rejected(mutate)

    def test_manifest_version_and_changed_runtime_are_rejected(self):
        self.rejected(lambda m, _: m.update(version='editor-forged-version'))
        def forge(manifest, editor):
            file = editor / 'TD2EditorRuntime.js'
            file.write_bytes(file.read_bytes() + b'\n/* stale compiled runtime */\n')
        self.rejected(forge)

    def test_readonly_verifier_does_not_create_or_modify_candidate_files(self):
        import subprocess
        editor = candidate() / 'editor'
        before = {p.name: p.read_bytes() for p in editor.iterdir()}
        builder = ROOT / 'ui/editor/production/build.cjs'
        result = subprocess.run(['node', str(builder), '--verify-inputs', str(editor), '--root', str(ROOT)],
                                capture_output=True, text=True, encoding='utf8')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({p.name: p.read_bytes() for p in editor.iterdir()}, before)
