"""Compare the full checkout and the collaboration checkout against a local Git ref."""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from tools.asset_import.static_formats import safe_relative


BASE_REF = 'refs/td2-sync/base'


def git(root, *args, data=b'', allowed=(0,)):
    result = subprocess.run(['git', '-C', root, *args], input=data, capture_output=True)
    if result.returncode not in allowed:
        raise ValueError(result.stderr.decode('utf8', 'replace').strip() or f'git {args[0]} failed')
    return result.stdout


def fields(data):
    return data.decode('utf8').rstrip('\0').split('\0') if data else []


def names_input(names):
    return b''.join(name.encode('utf8') + b'\0' for name in names)


def check_name(name):
    parts = safe_relative(name).parts
    if any(part.casefold() == '.git' for part in parts):
        raise ValueError(f'Unsupported Git path: {name}')
    return name


def regular(root, name):
    path = root / name
    if path.resolve() != path or path.is_symlink():
        raise ValueError(f'Linked path: {name}')
    if path.exists() and not path.is_file():
        raise ValueError(f'Expected a regular file: {name}')
    return path.is_file()


def fingerprints(root, names):
    existing = [name for name in names if regular(root, name)]
    lines = ''.join(name + '\n' for name in existing).encode('utf8')
    hashes = git(root, 'hash-object', '--stdin-paths', data=lines).decode('ascii').splitlines()
    return dict(zip(existing, hashes, strict=True))


def baseline_files(repo, ref):
    items = {}
    for line in fields(git(repo, 'ls-tree', '-rz', ref)):
        meta, name = line.split('\t', 1)
        mode, _, oid = meta.split()
        if mode not in ('100644', '100755'):
            raise ValueError(f'Unsupported Git entry: {name}')
        items[name] = oid
    return items


def shared_names(repo, candidates, explicit):
    for name in candidates:
        check_name(name)
    data = names_input(candidates)
    ignored = set(fields(git(repo, 'check-ignore', '--no-index', '-z', '--stdin', data=data, allowed=(0, 1))))
    attrs = fields(git(repo, 'check-attr', '-z', '--stdin', 'td2-manual', data=data))
    manual = {name for name, _, value in zip(attrs[::3], attrs[1::3], attrs[2::3]) if value == 'set'}
    excluded = ignored | manual
    if rejected := excluded.intersection(explicit):
        raise ValueError('Local or manually maintained: ' + ', '.join(sorted(rejected)))
    return sorted(set(candidates) - excluded)


def transfer(src, dst, name, original, target):
    source, dest = src / name, dst / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as temp:
        temp_path = Path(temp.name)
    try:
        shutil.copyfile(source, temp_path)
        oid = git(dst, 'hash-object', '--path=' + name, '--', str(temp_path)).decode().strip()
        if oid != original or fingerprints(dst, [name]).get(name) != target:
            raise ValueError('Changed during sync or inconsistent Git attributes: ' + name)
        shutil.copymode(dest if dest.exists() else source, temp_path)
        os.replace(temp_path, dest)
    finally:
        temp_path.unlink(missing_ok=True)


def sync(repo, full, action, selected):
    for root in (repo, full):
        actual = Path(git(root, 'rev-parse', '--show-toplevel').decode().strip()).resolve()
        if actual != root:
            raise ValueError(f'Expected a checkout root: {root}')
    if repo == full or repo in full.parents or full in repo.parents:
        raise ValueError('Supply two separate checkout roots.')
    if git(repo, 'check-attr', 'td2-manual', '--', '.gitignore').strip().split()[-1:] != [b'set']:
        raise ValueError('Run from the collaboration checkout with its Git file policy.')
    if git(repo, 'ls-files', '-u'):
        raise ValueError('Resolve the collaboration index conflicts first.')
    if action == 'checkpoint' and (selected or git(repo, 'status', '--porcelain')):
        raise ValueError('Checkpoint needs the entire clean collaboration checkout.')
    head = git(repo, 'rev-parse', 'HEAD').decode().strip()
    base = git(repo, 'rev-parse', '--verify', '-q', BASE_REF, allowed=(0, 1)).decode().strip()
    if not base and action not in ('status', 'checkpoint'):
        raise ValueError('Establish a reviewed checkpoint first.')
    if base:
        git(repo, 'merge-base', '--is-ancestor', base, head)
    old = baseline_files(repo, base or head)
    indexed = fields(git(repo, 'ls-files', '--cached', '-z'))
    candidates = selected or sorted(set(indexed) | old.keys())
    names = shared_names(repo, candidates, selected)
    left, right = fingerprints(full, names), fingerprints(repo, names)
    changes = []
    for name in names:
        a, b = left.get(name), right.get(name)
        if name in selected and a is None and b is None and name not in old:
            raise ValueError('Unknown file: ' + name)
        if a == b:
            continue
        before = old.get(name)
        if b == before:
            direction = 'export'
        elif a == before:
            direction = 'import'
        else:
            direction = 'conflict'
        if direction != 'conflict' and (a if direction == 'export' else b) is None:
            direction = 'review-deletion'
        changes.append((direction, name))
        print(direction, name)
    if action == 'checkpoint':
        if changes:
            raise ValueError('Shared files still differ. Review them before advancing the checkpoint.')
        git(repo, 'update-ref', BASE_REF, head, base or '0' * len(head))
        print('Checkpoint', head)
    elif action in ('export', 'import'):
        if any(label in ('conflict', 'review-deletion') for label, _ in changes):
            raise ValueError('Resolve the listed paths or select the independent files to transfer.')
        for label, name in changes:
            if label == action:
                if label == 'export':
                    transfer(full, repo, name, left[name], right.get(name))
                else:
                    transfer(repo, full, name, right[name], left.get(name))
    print(f'{len(names)} shared paths checked, {len(changes)} differed.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'export', 'import', 'checkpoint'), default='status', nargs='?')
    parser.add_argument('paths', nargs='*', help='Exact reviewed relative paths, including new files')
    parser.add_argument('--full', type=Path, help='Full checkout (or configure git config td2sync.full)')
    args = parser.parse_args()
    repo = Path.cwd().resolve()
    configured = git(repo, 'config', '--local', '--get', 'td2sync.full', allowed=(0, 1)).decode().strip()
    if not args.full and not configured:
        parser.error('Set --full or git config --local td2sync.full.')
    try:
        sync(repo, (args.full or Path(configured)).resolve(), args.action, args.paths)
    except (OSError, ValueError) as error:
        sys.exit(str(error))


if __name__ == '__main__':
    main()
