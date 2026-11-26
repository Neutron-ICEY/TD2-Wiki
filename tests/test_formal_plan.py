import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from formal_candidate import ROOT, candidate
from tools.brand_sets.production import assemble
from tools.publish.bundle import read_json, title_key


class FormalPlanTests(unittest.TestCase):
    def test_content_plan_includes_the_files_used_by_shared_templates(self):
        catalog = read_json(ROOT / 'publishing/registry.json')['entries']
        assets = {row['id']: row['title'] for row in catalog if row['kind'] == 'assets'}
        selected = ['equipment-navbox', 'weapon-navigation', 'icon-resolver', 'material-row', 'brand-auto-image']
        entries = {row['id']: row for row in catalog if row['id'] in selected}

        def read_config(path):
            value = read_json(path)
            if path.name == 'reader-editor-production.json':
                value['content_ids'] = selected
            return value

        with tempfile.TemporaryDirectory(dir=ROOT / 'dist') as temp:
            output = Path(temp)
            shutil.copytree(candidate() / 'editor', output / 'editor')
            with patch('tools.brand_sets.production.read_json', side_effect=read_config):
                plan = {row['title']: row for row in assemble(ROOT, output)}
        for entry in entries.values():
            text = (ROOT / entry['source']).read_text(encoding='utf8')
            referenced = {title for title in assets.values() if title.split(':', 1)[1] in text}
            self.assertTrue(referenced, entry['id'])
            self.assertTrue(referenced.issubset(plan[entry['title']]['dependencies']), entry['id'])
        logos = set(plan[entries['brand-auto-image']['title']]['dependencies']).intersection(assets.values())
        self.assertTrue(logos.issubset(plan[entries['material-row']['title']]['dependencies']))

    def test_current_baseline_replaces_migration_revision_table(self):
        plan = json.loads((candidate() / 'resource-plan.json').read_text(encoding='utf8'))
        baseline = json.loads((ROOT / 'publishing/baseline.json').read_text(encoding='utf8'))['entries']
        for row in plan:
            self.assertNotIn('observed_revision', row)
            if row['source'].startswith('wiki/'):
                old = next((b for b in baseline if b['title'].split(':', 1)[-1] == row['title'].split(':', 1)[-1]), None)
                if old is None:
                    self.assertIsNone(row['baseline_revision'])
                    continue
                self.assertEqual(row['baseline_revision'], old['revision_id'])
                self.assertEqual(row['operation'], 'unchanged' if old['content_hash'] == row['sha256'] else 'update')

    def test_create_update_unchanged_use_alias_normalized_baseline(self):
        css = (ROOT / 'ui/brand-sets/brand-sets.css').read_bytes()
        for previous, expected in [(None, 'create'), ({'revision_id': 12, 'content_hash': '0' * 64}, 'update'),
                                   ({'revision_id': 13, 'content_hash': hashlib.sha256(css).hexdigest()}, 'unchanged')]:
            with tempfile.TemporaryDirectory(dir=ROOT / 'dist') as temp:
                output = Path(temp)
                shutil.copytree(candidate() / 'editor', output / 'editor')
                state = {title_key('零件:TD2Reader.css', 2300): previous} if previous else {}
                with patch('tools.brand_sets.production.load_state', return_value=state):
                    row = next(r for r in assemble(ROOT, output, True) if r['title'] == 'Gadget:TD2Reader.css')
                self.assertEqual(row['operation'], expected)
                self.assertEqual(row['baseline_revision'], previous['revision_id'] if previous else None)
                self.assertTrue(row['requires_fresh_preflight'])
