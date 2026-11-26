from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import formal_candidate


class FormalCandidateRetryTests(unittest.TestCase):
    def test_failed_build_or_assembly_can_retry_in_the_same_process(self):
        for failure in ('build', 'assemble'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                with (patch.object(formal_candidate, 'ROOT', root),
                      patch.object(formal_candidate, '_temporary', None),
                      patch.object(formal_candidate.subprocess, 'run') as build,
                      patch.object(formal_candidate, 'assemble') as assemble):
                    if failure == 'build':
                        error = subprocess.CalledProcessError(1, 'node')
                        build.side_effect = [error, None]
                    else:
                        error = ValueError('invalid assembly input')
                        assemble.side_effect = [error, None]
                    with self.assertRaises(type(error)) as raised:
                        formal_candidate.candidate()
                    self.assertIs(raised.exception, error)
                    self.assertIsNone(formal_candidate._temporary)
                    self.assertEqual(list((root / 'dist').iterdir()), [])
                    candidate = formal_candidate.candidate()
                    self.assertEqual(formal_candidate.candidate(), candidate)
                    self.assertEqual(build.call_count, 2)
                    self.assertEqual(assemble.call_count, 1 if failure == 'build' else 2)
                    self.assertNotEqual(build.call_args_list[0].args[0][-1], str(candidate))
                    self.assertEqual(assemble.call_args.args, (root, candidate))
