import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from tools.github_sync import BASE_REF, git, sync


class CheckoutSyncTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo, self.full = (Path(tmp.name).resolve() / name for name in ('collaboration', 'full'))
        for root in (self.repo, self.full):
            root.mkdir()
            git(root, 'init', '-q')
            git(root, 'config', 'user.name', 'Test')
            git(root, 'config', 'user.email', 'test@example.invalid')
            (root / '.gitattributes').write_text('*.txt text eol=lf\n/.gitattributes td2-manual\n/.gitignore td2-manual\n')
            (root / '.gitignore').write_text('private/\n')
            (root / 'article.txt').write_bytes(b'first\n' if root == self.repo else b'first\r\n')
            (root / 'image.bin').write_bytes(b'\0\r\n')
            git(root, 'add', '.')
            git(root, 'commit', '-qm', 'initial')
        self.run_sync('checkpoint')

    def run_sync(self, action, *paths):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            sync(self.repo, self.full, action, list(paths))
        return output.getvalue()

    def test_both_directions_and_new_reviewed_files(self):
        (self.full / 'article.txt').write_bytes(b'full\r\n')
        (self.repo / 'image.bin').write_bytes(b'\0\n')
        (self.full / 'new.txt').write_bytes(b'new\n')
        report = self.run_sync('status')
        self.assertIn('export article.txt', report)
        self.assertIn('import image.bin', report)
        self.assertNotIn('new.txt', report)
        self.run_sync('export')
        self.assertFalse((self.repo / 'new.txt').exists())
        self.run_sync('export', 'new.txt')
        self.run_sync('import')
        self.assertEqual((self.full / 'image.bin').read_bytes(), b'\0\n')
        self.assertEqual((self.repo / 'article.txt').read_text(), 'full\n')
        with self.assertRaises(ValueError):
            self.run_sync('checkpoint')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-qm', 'both sides')
        self.run_sync('checkpoint')
        self.assertEqual(git(self.repo, 'rev-parse', BASE_REF), git(self.repo, 'rev-parse', 'HEAD'))
        self.assertIn('0 differed', self.run_sync('status'))

    def test_conflicts_deletions_and_private_paths(self):
        (self.repo / 'article.txt').write_text('one')
        (self.full / 'article.txt').write_text('two')
        (self.full / 'image.bin').unlink()
        with self.assertRaises(ValueError):
            self.run_sync('export')
        self.assertEqual((self.repo / 'article.txt').read_text(), 'one')
        self.assertTrue((self.repo / 'image.bin').is_file())
        self.assertIn('review-deletion image.bin', self.run_sync('status'))
        for path in ('private/example.txt', '.gitignore', '../other', '.git/config'):
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.run_sync('export', path)

    def test_incoming_deletion_in_a_commit_and_untracked_collision(self):
        git(self.repo, 'rm', 'article.txt')
        (self.repo / 'new.txt').write_text('collaborator')
        git(self.repo, 'add', 'new.txt')
        git(self.repo, 'commit', '-qm', 'incoming')
        (self.full / 'new.txt').write_text('local draft')
        report = self.run_sync('status')
        self.assertIn('review-deletion article.txt', report)
        self.assertIn('conflict new.txt', report)
        with self.assertRaises(ValueError):
            self.run_sync('import')
        self.assertTrue((self.full / 'article.txt').exists())
