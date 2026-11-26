from pathlib import Path
import unittest

from wiki_subset import WikiSubset


ROOT = Path(__file__).resolve().parents[1]


class ReferenceBoundaryTests(unittest.TestCase):
    def test_current_note_template_expands_named_and_unnamed_ref_arguments(self):
        view = WikiSubset(ROOT)
        for name in ('', 'note<&"'):
            text = view.template('TD2注释', {'1': 'NON-GAME-FACT {{#if:1|body|unused}}', '名称': name})
            self.assertEqual(view.ref_calls[-1], {'body': 'NON-GAME-FACT body', 'attributes': {'name': name}})
            self.assertIn('>NON-GAME-FACT body</ref>', text)
            self.assertEqual('name=' in text, bool(name))
            if name:
                self.assertIn('name="note&lt;&amp;&quot;"', text)

    def test_unimplemented_extension_attributes_are_not_silently_accepted(self):
        with self.assertRaisesRegex(AssertionError, 'ref 属性'):
            WikiSubset(ROOT).expand('{{#tag:ref|NON-GAME-FACT|unhandled=value}}', {})
