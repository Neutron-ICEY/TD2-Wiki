"""Run the maintained offline checks and record one comparable result bundle."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]


def output_directory(root, requested):
    """Create a fresh result directory under this checkout's dist tree."""
    path = root / (requested or ('dist/verify-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:6]))
    path = Path(os.path.abspath(path))
    if not path.is_relative_to(root / 'dist') or path == root / 'dist':
        raise ValueError('Verification output must be a fresh dist subdirectory')
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink() or parent.is_junction():
            raise ValueError('Verification output must not traverse links')
    path.mkdir(parents=True, exist_ok=False)
    return path


def run_step(root, output, env, name, command):
    """Record the real subprocess result and any skipped checks without hiding failures."""
    started = time.monotonic()
    log = output / (name + '.log')
    print(name + ' ...', flush=True)
    with log.open('w', encoding='utf8', newline='\n') as stream:
        result = subprocess.run(command, cwd=root, env=env, stdout=stream, stderr=subprocess.STDOUT)
    text = log.read_text('utf8', errors='replace')
    skipped = max([int(value) for value in re.findall(r'\bskipped=(\d+)', text)] +
                  [int(value) for value in re.findall(r'^# skipped (\d+)$', text, re.MULTILINE)] + [0])
    counts = re.findall(r'^Ran (\d+) tests? in ', text, re.MULTILINE) or re.findall(r'^# tests (\d+)$', text, re.MULTILINE)
    row = dict(name=name, command=command, exit_code=result.returncode, skipped=skipped,
               tests=int(counts[-1]) if counts else None, log=log.name,
               seconds=round(time.monotonic() - started, 3))
    print(name + ': ' + ('passed' if result.returncode == 0 and not skipped else 'incomplete' if result.returncode == 0 else 'failed'), flush=True)
    return row


def compare_artifacts(output):
    """Extract stable payload identities; timestamps and review-directory names are excluded."""
    result = {}
    manifest = output / 'publish/manifest.json'
    if manifest.is_file():
        result['publishing'] = sorted([
            {key: row.get(key) for key in ('id', 'title', 'namespace', 'source', 'content_hash', 'ownership', 'operation', 'conflicts')}
            for row in json.loads(manifest.read_text('utf8'))['entries']], key=lambda row: row['id'])
    plan = output / 'frontend/resource-plan.json'
    if plan.is_file():
        result['frontend'] = sorted([
            {key: row.get(key) for key in ('title', 'source', 'sha256', 'status', 'operation', 'dependencies')}
            for row in json.loads(plan.read_text('utf8'))], key=lambda row: row['title'])
    return result


def record_result(output, node, checks, **details):
    summary = dict(schema_version=1, root=str(ROOT), python=sys.executable, node=node,
                   passed=all(row['exit_code'] == 0 and not row['skipped'] for row in checks),
                   checks=checks, artifacts=compare_artifacts(output), publication_performed=False, **details)
    (output / 'result.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf8', newline='\n')
    print(str(output / 'result.json'), flush=True)
    return 0 if summary['passed'] else 1


def main(argv=None):
    """Verify without changing maintained sources, binding an Entry or publishing anything."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', help='Fresh directory inside dist')
    parser.add_argument('--resources', action='store_true', help='Also test the installed game export, its manifest and registered resource inputs')
    parser.add_argument('--public', action='store_true', help='Run the checks supported by the public checkout')
    args = parser.parse_args(argv)
    if args.public and args.resources:
        parser.error('--public cannot be combined with --resources')
    output = output_directory(ROOT, args.output)
    temporary = output / 'tmp'
    temporary.mkdir()
    env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', TD2_PYTHON=sys.executable,
               TEMP=str(temporary), TMP=str(temporary), TD2_GAME_RESOURCES_TEST_TMP=str(temporary),
               TD2_ASSET_LIBRARY_TEST_TMP=str(temporary))
    if not env.get('TD2_LUA_TEST_PATH') and (ROOT / '.cache/python').is_dir():
        env['TD2_LUA_TEST_PATH'] = str(ROOT / '.cache/python')
    node = shutil.which('node')
    if not node:
        raise RuntimeError('Node.js is required')
    python = [sys.executable, '-B', '-X', 'utf8']
    dependency_check = "import os,sys; sys.path.insert(0,os.environ.get('TD2_LUA_TEST_PATH','')); import PIL; from PIL import features; from lupa.lua51 import LuaRuntime; import importlib.metadata as m; assert m.version('lupa')=='2.6'; assert features.check('webp'); print('Python, Pillow/WebP and Lua 5.1 dependencies available')"
    if args.public:
        from tools.public_checks import run
        checks, details = run(ROOT, output, python, node, dependency_check,
                              lambda name, command: run_step(ROOT, output, env, name, command))
        return record_result(output, node, checks, **details)
    checks = [run_step(ROOT, output, env, 'dependencies', python + ['-c', dependency_check])]
    if checks[0]['exit_code'] == 0:
        steps = [
            ('identity', python + ['-m', 'tools.identity']),
            ('python-tests', python + ['-m', 'unittest', 'discover', '-s', 'tests', '-v']),
            ('node-tests', [node, '--test', '--test-reporter=tap', '--test-concurrency=1', *[str(path.relative_to(ROOT)) for path in sorted((ROOT / 'tests').glob('test_*.cjs'))]]),
            ('brand-generation', python + ['-m', 'tools.brand_sets', 'check']),
            ('exotic-generation', [node, 'tools/exotic_gear/generate.cjs', 'check']),
            ('gear-generation', [node, 'tools/gear_sets/generate.cjs', 'check']),
            ('weapon-generation', python + ['-m', 'tools.equipment.weapons', 'check']),
            ('editor-data', [node, 'tools/equipment/catalog.cjs', 'check']),
            ('editor-build', [node, 'ui/editor/production/build.cjs', str(output / 'frontend')]),
        ]
        for name, command in steps:
            checks.append(run_step(ROOT, output, env, name, command))
        if checks[-1]['exit_code'] == 0:
            checks.append(run_step(ROOT, output, env, 'reader-assembly', python + ['-m', 'tools.brand_sets.production', '--output', str(output / 'frontend')]))
        checks.append(run_step(ROOT, output, env, 'publish-build', python + ['-m', 'tools.publish', 'build', '--output', (output / 'publish').relative_to(ROOT).as_posix()]))
        if checks[-1]['exit_code'] == 0:
            checks.append(run_step(ROOT, output, env, 'publish-prepare', python + ['-m', 'tools.publish', 'prepare', '--bundle', str(output / 'publish')]))
        if args.resources:
            checks.append(run_step(ROOT, output, env, 'weapon-resources', python + ['-m', 'unittest', 'discover', '-s', 'tests', '-p', 'resource_*.py', '-v']))
            checks.append(run_step(ROOT, output, env, 'resource-manifest', python + ['-m', 'tools.game_resources', 'status']))
            integration = "from tools.asset_import.text_library import TextLibrary; from tools.asset_import.library import Library; t=TextLibrary().query(limit=1); a=Library(); assert not t['issues'],t['issues']; assert not a.issues,a.issues; print('Registered text sources:',len(t['sources']),'asset observations:',len(a.records)); print('Raw payloads are not rehashed by this integration check')"
            checks.append(run_step(ROOT, output, env, 'registered-resources', python + ['-c', integration]))
    return record_result(output, node, checks)


if __name__ == '__main__':
    raise SystemExit(main())
