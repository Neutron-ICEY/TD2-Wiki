import argparse
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import stat
import sys
import uuid

from .timing import Timings, timed_files


ROOT = Path(__file__).resolve().parents[2]
HASH = re.compile(r'[0-9a-f]{64}\Z')


class ResourceError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ResourceError(message)


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')


def read_json(path):
    return json.loads(Path(path).read_text('utf-8'))


def write_json(path, value):
    with Path(path).open('xb') as stream:
        stream.write(encoded(value))
        stream.flush()
        os.fsync(stream.fileno())


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def relative(value):
    require(isinstance(value, str) and value and '\\' not in value and ':' not in value,
            'INVALID_RESOURCE_PATH')
    parts = value.split('/')
    require(not value.startswith('/') and '\x00' not in value and all(
        part not in ('', '.', '..') and not part.endswith((' ', '.')) for part in parts),
        'INVALID_RESOURCE_PATH: ' + value)
    return value


def linked(info):
    return stat.S_ISLNK(info.st_mode) or bool(getattr(info, 'st_file_attributes', 0) & 0x400)


def no_links(path):
    path = Path(path).absolute()
    for part in [*reversed(path.parents), path]:
        try:
            require(not linked(part.lstat()), 'LINK_NOT_ALLOWED: ' + str(part))
        except FileNotFoundError:
            continue
    return path


def child(base, name):
    path = no_links(Path(base) / relative(name))
    require(path.resolve().is_relative_to(Path(base).resolve()), 'PATH_OUTSIDE_RESOURCE_ROOT')
    return path


class ResourcePaths:
    """Check each directory once per maintenance pass; never follow resource links."""
    def __init__(self, base, create=False):
        self.base = no_links(base)
        require(self.base.is_dir(), 'RESOURCE_DIRECTORY_MISSING: ' + str(base))
        self.checked = {self.base}
        self.create = create

    def directory(self, path):
        if path in self.checked:
            return
        self.directory(path.parent)
        try:
            info = path.lstat()
        except FileNotFoundError:
            require(self.create, 'RESOURCE_DIRECTORY_MISSING: ' + str(path))
            path.mkdir()
        else:
            require(not linked(info), 'LINK_NOT_ALLOWED: ' + str(path))
            require(stat.S_ISDIR(info.st_mode), 'RESOURCE_PATH_KIND_CHANGE: ' + str(path))
        self.checked.add(path)

    def file(self, name):
        path = self.base / relative(name)
        self.directory(path.parent)
        try:
            info = path.lstat()
        except FileNotFoundError:
            return path
        require(not linked(info), 'LINK_NOT_ALLOWED: ' + name)
        require(stat.S_ISREG(info.st_mode), 'RESOURCE_PATH_KIND_CHANGE: ' + name)
        return path


def store_at(root):
    root = Path(root).resolve()
    return no_links(root / 'resources/game')


@contextmanager
def locked(store):
    store.mkdir(parents=True, exist_ok=True)
    path = no_links(store / '.lock')
    with path.open('a+b') as stream:
        if stream.tell() == 0:
            stream.write(b'0')
            stream.flush()
        stream.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            raise ResourceError('RESOURCE_LIBRARY_BUSY') from error
        try:
            yield
        finally:
            stream.seek(0)
            if os.name == 'nt':
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def files_in(base, prefix='', excluded=(), skipped=None, discovery=None):
    with os.scandir(base) as entries:
        items = sorted(entries, key=lambda entry: (entry.name + ('/' if entry.is_dir(follow_symlinks=False) else '')).casefold())
    seen = set()
    for entry in items:
        require(entry.name.casefold() not in seen, 'CASE_COLLISION: ' + entry.name)
        seen.add(entry.name.casefold())
        name = relative(prefix + entry.name)
        info = entry.stat(follow_symlinks=False)
        require(not linked(info), 'LINK_NOT_ALLOWED: ' + name)
        if stat.S_ISDIR(info.st_mode):
            key = name.casefold()
            whole = discovery is None or key in discovery.directories
            if key in excluded or not whole and key not in discovery.parents:
                if skipped is not None:
                    skipped.add(name)
                continue
            yield from files_in(entry.path, name + '/', excluded, skipped, None if whole else discovery)
        else:
            require(stat.S_ISREG(info.st_mode), 'NOT_A_REGULAR_FILE: ' + name)
            if discovery is None or name.casefold() in discovery.paths:
                yield name, Path(entry.path), info


def fingerprint(path, before):
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        require((before.st_size, before.st_mtime_ns) == (opened.st_size, opened.st_mtime_ns),
                'FILE_CHANGED_BEFORE_READ: ' + str(path))
        result = hashlib.file_digest(stream, 'sha256').hexdigest()
        closed = os.fstat(stream.fileno())
    after = path.stat(follow_symlinks=False)
    identity = lambda info: (info.st_size, info.st_mtime_ns, info.st_ino)
    require(not linked(after) and identity(opened) == identity(closed) == identity(after),
            'FILE_CHANGED_DURING_READ: ' + str(path))
    return result


def inventory(base, output, source_id, excluded=(), timing=None, report_duplicates=False, discovery=None):
    timing = timing or Timings()
    excluded = frozenset(p.casefold() for p in excluded)
    skipped = set()
    base = no_links(base)
    require(base.is_dir(), 'EXPORT_DIRECTORY_MISSING')
    duplicate_index = Path(output).with_suffix('.hashes.sqlite')
    database = None
    if report_duplicates:
        require(not duplicate_index.exists(), 'DUPLICATE_SCAN_INDEX_EXISTS')
        database = sqlite3.connect(duplicate_index)
        database.execute('PRAGMA journal_mode=OFF')
        database.execute('PRAGMA cache_size=-1024')
        database.execute('CREATE TABLE hashes (sha TEXT PRIMARY KEY, path TEXT) WITHOUT ROWID')
    duplicates = {'files': 0, 'bytes': 0, 'examples': []}
    count = total = 0
    try:
        with Path(output).open('xb') as stream:
            for name, path, info in timed_files(files_in(base, excluded=excluded, skipped=skipped, discovery=discovery), timing):
                with timing.stage('resource_hash', files=1, bytes=info.st_size):
                    sha = fingerprint(path, info)
                with timing.stage('manifest_write', files=1):
                    stream.write(encoded({'path': name, 'bytes': info.st_size, 'sha256': sha, 'source_id': source_id}))
                count += 1
                total += info.st_size
                if count % 10000 == 0:
                    print('Hashed ' + str(count) + ' resources (' + str(total) + ' bytes)', file=sys.stderr, flush=True)
                if database is not None:
                    with timing.stage('duplicate_index', files=1):
                        inserted = database.execute('INSERT OR IGNORE INTO hashes VALUES (?, ?)', (sha, name))
                        if not inserted.rowcount:
                            duplicates['files'] += 1
                            duplicates['bytes'] += info.st_size
                            if len(duplicates['examples']) < 20:
                                first = database.execute('SELECT path FROM hashes WHERE sha = ?', (sha,)).fetchone()[0]
                                duplicates['examples'].append([first, name])
            with timing.stage('manifest_flush'):
                stream.flush()
                os.fsync(stream.fileno())
    finally:
        if database is not None:
            database.close()
            duplicate_index.unlink()
    return {'files': count, 'bytes': total, 'duplicates': duplicates if report_duplicates else None,
            **({'skipped_directories': sorted(skipped)} if excluded else {})}


def rows(path, hasher=None):
    previous = None
    with Path(path).open('rb') as stream:
        for line in stream:
            if hasher is not None:
                hasher.update(line)
            row = json.loads(line)
            require(set(row) == {'path', 'bytes', 'sha256', 'source_id'}, 'INVALID_MANIFEST_RECORD')
            key = relative(row['path']).casefold()
            require(previous is None or previous < key, 'UNSORTED_OR_DUPLICATE_MANIFEST')
            require(type(row['bytes']) is int and row['bytes'] >= 0 and isinstance(row['sha256'], str)
                    and HASH.fullmatch(row['sha256']) and isinstance(row['source_id'], str) and row['source_id'],
                    'INVALID_MANIFEST_RECORD')
            previous = key
            yield row


def metadata(value):
    require(isinstance(value, dict), 'INVALID_SOURCE_METADATA')
    require(isinstance(value.get('source_id'), str) and value['source_id'].strip(), 'SOURCE_ID_REQUIRED')
    require(isinstance(value.get('origin'), str) and value['origin'].strip(), 'SOURCE_ORIGIN_REQUIRED')
    require('game_build' in value and (value['game_build'] is None or
            isinstance(value['game_build'], str) and value['game_build'].strip()), 'GAME_BUILD_REQUIRED_OR_NULL')
    require('source_container_sha256' in value and (value['source_container_sha256'] is None or
            isinstance(value['source_container_sha256'], str) and HASH.fullmatch(value['source_container_sha256'])),
            'SOURCE_CONTAINER_HASH_REQUIRED_OR_NULL')
    return value


def manifest_info(path, sources):
    counts = Counter()
    count = total = 0
    hasher = hashlib.sha256()
    for row in rows(path, hasher):
        require(row['source_id'] in sources, 'UNKNOWN_RESOURCE_SOURCE')
        counts[row['source_id']] += 1
        count += 1
        total += row['bytes']
    return {'schema_version': 1, 'manifest_sha256': hasher.hexdigest(), 'files': count, 'bytes': total,
            'sources': sources, 'source_counts': dict(counts), 'verified_at': utc_now()}


def current_info(store):
    if (store / '.transaction').exists():
        marker = child(store / '.transaction', 'state.json')
        state = read_json(marker) if marker.exists() else {'state': 'not_started'}
        raise ResourceError('PENDING_TRANSACTION_USE_RECOVER: ' + json.dumps(
            {key: state[key] for key in ('state', 'plan') if key in state}, ensure_ascii=False))
    require(not (store / '.initializing.json').exists(), 'PENDING_INITIALIZATION_USE_RECOVER')
    value = read_json(no_links(store / 'source.json'))
    require(value.get('schema_version') == 1 and isinstance(value.get('sources'), dict), 'INVALID_LIBRARY_METADATA')
    for source_id, source in value['sources'].items():
        require(metadata(source)['source_id'] == source_id, 'SOURCE_ID_MISMATCH')
    observed = manifest_info(no_links(store / 'manifest.jsonl'), value['sources'])
    for key in ('manifest_sha256', 'files', 'bytes', 'source_counts'):
        require(value.get(key) == observed[key], 'LIBRARY_MANIFEST_MISMATCH: ' + key)
    return value


def verify_files(base, manifest, excluded=(), timing=None):
    timing = timing or Timings()
    actual = timed_files(files_in(no_links(base), excluded=frozenset(p.casefold() for p in excluded)), timing)
    count = total = 0
    for expected in rows(manifest):
        found = next(actual, None)
        require(found is not None and found[0] == expected['path'], 'RESOURCE_PATH_DRIFT: ' + expected['path'])
        name, path, info = found
        with timing.stage('resource_hash', files=1, bytes=info.st_size):
            require(info.st_size == expected['bytes'] and fingerprint(path, info) == expected['sha256'],
                    'RESOURCE_CONTENT_DRIFT: ' + name)
        count += 1
        total += info.st_size
    require(next(actual, None) is None, 'UNREGISTERED_RESOURCE_FILE')
    return {'files': count, 'bytes': total}


def initialize(root, source):
    """Hash the existing current export and register its explicit provenance without copying raw files."""
    store = store_at(root)
    source = metadata(source)
    with Timings('init') as timing, locked(store):
        require(not (store / 'source.json').exists() and not (store / 'manifest.jsonl').exists(), 'LIBRARY_ALREADY_INITIALIZED')
        require(not (store / '.transaction').exists(), 'PENDING_TRANSACTION_USE_RECOVER')
        require(not (store / '.initializing.json').exists(), 'PENDING_INITIALIZATION_USE_RECOVER')
        current = no_links(store / 'current')
        require(current.is_dir(), 'CURRENT_EXPORT_MISSING')
        staging = store / '.init-manifest.jsonl'
        require(not any((store / name).exists() for name in ('.init-manifest.jsonl',
                '.init-manifest.hashes.sqlite', '.init-source.json', '.initializing-next.json')),
                'INCOMPLETE_INITIALIZATION_MANIFEST')
        try:
            write_json(store / '.initializing.json', {'state': 'preparing'})
            stats = timing.call('inventory', inventory, current, staging, source['source_id'], timing=timing)
            value = timing.call('manifest_next', manifest_info, staging, {source['source_id']: source})
            write_json(store / '.init-source.json', value)
            write_json(store / '.initializing-next.json', {
                'state': 'ready', 'manifest.jsonl': digest(staging),
                'source.json': digest(store / '.init-source.json')})
            os.replace(store / '.initializing-next.json', store / '.initializing.json')
            os.replace(staging, store / 'manifest.jsonl')
            os.replace(store / '.init-source.json', store / 'source.json')
            (store / '.initializing.json').unlink()
        except Exception:
            recover_initialization(store)
            raise
    return {'status': 'initialized', 'content_checked': True, **stats,
            'manifest_sha256': value['manifest_sha256'], 'timings': timing.result()}


def recover_initialization(store):
    marker = no_links(store / '.initializing.json')
    try:
        state = read_json(marker)
    except (FileNotFoundError, json.JSONDecodeError):
        require(not any((store / name).exists() for name in ('manifest.jsonl', 'source.json',
                '.init-manifest.jsonl', '.init-manifest.hashes.sqlite', '.init-source.json',
                '.initializing-next.json')), 'INITIALIZATION_STATE_MISSING_WITH_CONTENT')
        marker.unlink(missing_ok=True)
        return {'status': 'initialization_reset', 'content_checked': False}
    require(state.get('state') in ('preparing', 'ready'), 'UNKNOWN_INITIALIZATION_STATE')
    installed = []
    for name in ('manifest.jsonl', 'source.json'):
        path = no_links(store / name)
        if path.exists():
            require(state.get(name) == digest(path), 'INITIALIZATION_METADATA_DRIFT')
            installed.append(path)
    complete = len(installed) == 2
    if not complete:
        for path in installed:
            path.unlink()
    for name in ('.init-manifest.jsonl', '.init-manifest.hashes.sqlite', '.init-source.json',
                 '.initializing-next.json', '.initializing.json'):
        no_links(store / name).unlink(missing_ok=True)
    return {'status': 'initialization_completed' if complete else 'initialization_reset', 'content_checked': False}


def status(root, full=False):
    """Validate the saved manifest; full=True additionally hashes every current resource."""
    store = store_at(root)
    with Timings('verify' if full else 'status') as timing, locked(store):
        value = timing.call('manifest_current', current_info, store)
        if full:
            timing.call('source_verify', verify_files, store / 'current', store / 'manifest.jsonl', timing=timing)
    return {'status': 'verified' if full else 'manifest_validated', 'content_checked': full,
            'timings': timing.result(),
            **{key: value[key] for key in ('files', 'bytes', 'manifest_sha256', 'source_counts', 'verified_at')}}


def affected(name):
    name = name.casefold()
    result = []
    for fragment, domain in (('localization/', 'game_text'), ('/item', 'equipment'),
                             ('/attribute', 'attributes'), ('/talent', 'talents'),
                             ('/skill', 'skills'), ('/economy', 'acquisition'),
                             ('/loot', 'acquisition'), ('/craft', 'acquisition'),
                             ('/sprite', 'images'), ('images/', 'images'), ('materials/', 'images')):
        if fragment in name and domain not in result:
            result.append(domain)
    return result or ['other_native_resources']


def merge(before, imported, scopes, output, operations):
    older = iter(rows(before))
    newer = iter(rows(imported))
    old, new = next(older, None), next(newer, None)
    counts = Counter({'added': 0, 'modified': 0, 'deleted': 0, 'unchanged': 0, 'retained': 0, 'copy_bytes': 0})
    impacts = Counter()
    with Path(output).open('xb') as final, Path(operations).open('xb') as changes:
        while old is not None or new is not None:
            operation = None
            if new is None or old is not None and old['path'].casefold() < new['path'].casefold():
                if any(old['path'].casefold().startswith(scope.casefold() + '/') for scope in scopes):
                    operation = {'operation': 'deleted', 'path': old['path'], 'before': old, 'after': None}
                else:
                    final.write(encoded(old))
                    counts['retained'] += 1
                old = next(older, None)
            elif old is None or new['path'].casefold() < old['path'].casefold():
                final.write(encoded(new))
                operation = {'operation': 'added', 'path': new['path'], 'before': None, 'after': new}
                new = next(newer, None)
            else:
                require(old['path'] == new['path'], 'RESOURCE_PATH_CASE_CHANGED')
                final.write(encoded(new))
                if (old['bytes'], old['sha256']) == (new['bytes'], new['sha256']):
                    counts['unchanged'] += 1
                else:
                    operation = {'operation': 'modified', 'path': new['path'], 'before': old, 'after': new}
                old, new = next(older, None), next(newer, None)
            if operation:
                changes.write(encoded(operation))
                counts[operation['operation']] += 1
                counts['copy_bytes'] += operation['after']['bytes'] if operation['after'] else 0
                impacts.update(affected(operation['path']))
        for stream in (final, changes):
            stream.flush()
            os.fsync(stream.fileno())
    return {'changes': dict(counts), 'wiki_review': dict(impacts)}


@dataclass
class PlanValidation:
    """Only populated by this process after parsing and freezing a successful plan."""
    plan_sha256: str | None = None


def make_plan(root, source, source_metadata, output, complete_scopes=(), profile=None, report_duplicates=False, *, validation=None, coverage_check=None):
    """Compare an isolated export with the registered library; only explicit complete scopes imply deletions."""
    root = Path(root).resolve()
    store = store_at(root)
    source = no_links(Path(source).absolute()).resolve()
    output = no_links(Path(output).absolute()).resolve()
    require(source.is_dir(), 'IMPORT_SOURCE_MISSING')
    require(not source.is_relative_to(store) and not store.is_relative_to(source), 'IMPORT_OVERLAPS_LIBRARY')
    require(output.is_relative_to(root / 'dist') and not output.is_relative_to(source)
            and not source.is_relative_to(output), 'PLAN_OUTPUT_MUST_BE_SEPARATE_DIST_DIRECTORY')
    require(not output.exists(), 'PLAN_OUTPUT_ALREADY_EXISTS')
    source_metadata = metadata(source_metadata)
    scopes = sorted({relative(scope) for scope in complete_scopes})
    require(not (profile and scopes), 'FILTERED_COMPLETE_SCOPE_NOT_ALLOWED')
    for scope in scopes:
        require(child(source, scope).is_dir(), 'COMPLETE_SCOPE_DIRECTORY_MISSING: ' + scope)
    with Timings('plan') as timing, locked(store):
        selection = dependency_snapshot = layer_evidence = discovery = None
        if profile:
            from .selection import load_selection, dependencies, check_unchanged
            from .layers import inspect_layers
            selection = load_selection(root, profile)
            layer_evidence = timing.call('layer_validation', inspect_layers, source, selection)
            if profile == 'daily':
                from .selection import DiscoveryPaths
                required = set()
                dependency_snapshot = timing.call('dependency_check', dependencies, root, selection, required_output=required)
                if coverage_check is not None:
                    coverage_check(selection, required)
                discovery = DiscoveryPaths(selection['discovery_directories'], required)
            else:
                dependency_snapshot = timing.call('dependency_check', dependencies, root, selection)
            import_scope = {'mode': 'partial', 'selection': selection}
            require(source_metadata.get('import_scope', import_scope) == import_scope, 'SOURCE_IMPORT_SCOPE_CONFLICT')
            source_metadata = {**source_metadata, 'import_scope': import_scope}
        previous = timing.call('manifest_current', current_info, store)
        sources = dict(previous['sources'])
        source_id = source_metadata['source_id']
        require(source_id not in sources or sources[source_id] == source_metadata, 'SOURCE_ID_METADATA_CONFLICT')
        sources[source_id] = source_metadata
        output.mkdir(parents=True)
        stats = timing.call('inventory', inventory, source, output / 'incoming.jsonl', source_id,
                            excluded=selection['excluded_directories'] if selection else (), timing=timing,
                            report_duplicates=report_duplicates, discovery=discovery)
        require(stats['files'] or scopes, 'EMPTY_PARTIAL_IMPORT')
        summary = timing.call('manifest_merge', merge, store / 'manifest.jsonl', output / 'incoming.jsonl', scopes,
                        output / 'next.jsonl', output / 'operations.jsonl')
        value = timing.call('manifest_next', manifest_info, output / 'next.jsonl', sources)
        write_json(output / 'sources.json', value)
        plan = {'schema_version': 1, 'store': str(store), 'source': str(source), 'created_at': utc_now(),
                'complete_scopes': scopes, 'base_manifest_sha256': previous['manifest_sha256'],
                'base_metadata_sha256': digest(store / 'source.json'), 'summary': {**summary, **stats},
                'artifacts': {name: timing.call('plan_artifact_hash', digest, output / name) for name in
                              ('incoming.jsonl', 'next.jsonl', 'operations.jsonl', 'sources.json')}}
        if selection:
            timing.call('dependency_recheck', check_unchanged, root, selection, dependency_snapshot, source, layer_evidence)
            plan.update(selection=selection, dependencies=dependency_snapshot)
            if selection.get('layer_types'):
                plan['layer_evidence'] = layer_evidence
        write_json(output / 'plan.json', plan)
        plan_hash = digest(output / 'plan.json')
        (output / 'plan.sha256').write_text(plan_hash + '\n', encoding='ascii')
        if validation is not None:
            validation.plan_sha256 = plan_hash
    return {'status': 'planned', 'plan': str(output), **plan['summary'], 'timings': timing.result()}


def check_complete_scopes(source, scopes):
    require(no_links(source).is_dir(), 'IMPORT_SOURCE_MISSING')
    for scope in scopes:
        require(child(source, scope).is_dir(), 'COMPLETE_SCOPE_DIRECTORY_MISSING: ' + scope)


def read_operations(path):
    previous = None
    with Path(path).open('rb') as stream:
        for line in stream:
            value = json.loads(line)
            key = relative(value['path']).casefold()
            require(previous is None or previous < key, 'INVALID_OPERATION_ORDER')
            require(value.get('operation') in ('added', 'modified', 'deleted'), 'INVALID_OPERATION')
            before, after = value['before'], value['after']
            require((before is not None, after is not None) == {
                'added': (False, True), 'modified': (True, True), 'deleted': (True, False)
            }[value['operation']], 'INVALID_OPERATION')
            for row in (before, after):
                if row is not None:
                    require(row['path'] == value['path'] and type(row['bytes']) is int and row['bytes'] >= 0
                            and isinstance(row['sha256'], str) and HASH.fullmatch(row['sha256']), 'INVALID_OPERATION')
            previous = key
            yield value


def check_plan(store, directory):
    directory = no_links(Path(directory).absolute())
    require(digest(directory / 'plan.json') == (directory / 'plan.sha256').read_text('ascii').strip(), 'PLAN_CHANGED')
    plan = read_json(directory / 'plan.json')
    require(plan.get('schema_version') == 1 and plan.get('store') == str(store), 'PLAN_WRONG_LIBRARY')
    require(set(plan.get('artifacts', {})) == {'incoming.jsonl', 'next.jsonl', 'operations.jsonl', 'sources.json'}, 'INVALID_PLAN_ARTIFACTS')
    for name, sha in plan['artifacts'].items():
        require(digest(no_links(directory / name)) == sha, 'PLAN_ARTIFACT_CHANGED: ' + name)
    return plan


def remove_transaction(store):
    path = no_links(store / '.transaction')
    require(path.parent == store and path.name == '.transaction', 'INVALID_TRANSACTION_PATH')
    # Only flat temporary files belong to this updater; never recursively delete old data.
    for entry in path.iterdir():
        require(not linked(entry.lstat()) and entry.is_file(), 'UNEXPECTED_TRANSACTION_CONTENT')
        require(entry.name in ('state.json', 'state-next.json', 'payload', 'manifest.jsonl',
                              'source.json', 'receipt.json'), 'UNEXPECTED_TRANSACTION_CONTENT')
    for entry in path.iterdir():
        if entry.name == 'state.json':
            continue
        entry.unlink()
    (path / 'state.json').unlink(missing_ok=True)
    path.rmdir()


def set_state(transaction, state):
    temporary = transaction / 'state-next.json'
    temporary.unlink(missing_ok=True)
    write_json(temporary, state)
    os.replace(temporary, transaction / 'state.json')


def update_state(store):
    value = read_json(child(store / '.transaction', 'state.json'))
    require(value.get('schema_version') == 2, 'UNSUPPORTED_PENDING_UPDATE: preserve it and use its original tool version')
    require(value.get('state') in ('applying', 'committing', 'committed'), 'UNKNOWN_UPDATE_STATE')
    require(re.fullmatch('[0-9a-f]{32}', value.get('receipt_id', '')), 'INVALID_RECEIPT_ID')
    return value


def copy_verified(source, temporary, expected):
    """Hash the bytes being copied, without a second read of the destination."""
    hasher = hashlib.sha256()
    size = 0
    with source.open('rb') as incoming, temporary.open('wb') as output:
        before = os.fstat(incoming.fileno())
        require(before.st_size == expected['bytes'], 'RESOURCE_CONTENT_DRIFT: ' + expected['path'])
        while block := incoming.read(1024 * 1024):
            output.write(block)
            hasher.update(block)
            size += len(block)
        after = os.fstat(incoming.fileno())
        require((before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)
                and size == expected['bytes'] and hasher.hexdigest() == expected['sha256'],
                'RESOURCE_CONTENT_DRIFT: ' + expected['path'])


def finish_receipt(store):
    pending = child(store / '.transaction', 'receipt.json')
    if pending.exists():
        receipt = read_json(pending)
        require(re.fullmatch('[0-9a-f]{32}', receipt.get('receipt_id', '')), 'INVALID_RECEIPT_ID')
        receipts = no_links(store / 'updates')
        receipts.mkdir(exist_ok=True)
        target = child(receipts, receipt['receipt_id'] + '.json')
        if target.exists():
            require(digest(target) == digest(pending), 'RECEIPT_CONFLICT')
            pending.unlink()
        else:
            os.replace(pending, target)


def apply_plan(root, directory, allow_deletions=False, *, validation=None):
    """Install a frozen change set. Failures remain pending for forward retry."""
    store = store_at(root)
    with Timings('apply') as timing, locked(store):
        receipt = apply_locked(root, store, directory, allow_deletions, timing, validation)
    return {'status': 'applied', 'content_checked': True, 'content_scope': 'changed_files',
            **receipt, 'timings': timing.result()}


def apply_locked(root, store, directory, allow_deletions, timing, validation=None):
    directory = no_links(Path(directory).absolute())
    transaction = no_links(store / '.transaction')
    with timing.stage('prepare_update'):
        pending = update_state(store) if transaction.exists() else None
        plan = timing.call('plan_validation', check_plan, store, directory)
        plan_sha = digest(directory / 'plan.json')
        reuse = validation is not None and validation.plan_sha256 == plan_sha
        if pending:
            require(pending['plan'] == str(directory) and pending['plan_sha256'] == plan_sha, 'PENDING_UPDATE_PLAN_MISMATCH')
            allow_deletions = allow_deletions or pending['allow_deletions']
        else:
            previous = timing.call('manifest_current', current_info, store)
            require(previous['manifest_sha256'] == plan['base_manifest_sha256'] and
                    digest(store / 'source.json') == plan['base_metadata_sha256'], 'STALE_RESOURCE_PLAN')
        require(not plan['summary']['changes']['deleted'] or allow_deletions, 'DELETIONS_REQUIRE_ALLOW_DELETIONS')
        proposed = read_json(directory / 'sources.json')
        # The frozen plan and its artifact hashes identify the bytes already parsed in make_plan.
        if not reuse:
            inspected = timing.call('manifest_next', manifest_info, directory / 'next.jsonl', proposed['sources'])
            for key in ('files', 'bytes', 'source_counts', 'manifest_sha256'):
                require(inspected[key] == proposed[key], 'PLAN_METADATA_MISMATCH')
        for source_id, value in proposed['sources'].items():
            require(metadata(value)['source_id'] == source_id, 'PLAN_SOURCE_ID_MISMATCH')
        if not pending:
            for source_id, value in previous['sources'].items():
                require(proposed['sources'].get(source_id) == value, 'PLAN_REWRITES_SOURCE_HISTORY')
        state = pending or {'schema_version': 2, 'state': 'applying', 'plan': str(directory),
                            'plan_sha256': plan_sha, 'allow_deletions': allow_deletions,
                            'receipt_id': uuid.uuid4().hex}
        timing.call('metadata_check', check_update_metadata, store, plan, state['state'])
    if state['state'] == 'applying':
        source = no_links(Path(plan['source'])).resolve()
        require(not source.is_relative_to(store) and not store.is_relative_to(source), 'IMPORT_OVERLAPS_LIBRARY')
        scopes = [relative(scope) for scope in plan['complete_scopes']]
        selection = plan.get('selection')
        if selection:
            from .selection import dependencies, check_unchanged
            require(not scopes and not plan['summary']['changes']['deleted'], 'FILTERED_COMPLETE_SCOPE_NOT_ALLOWED')
            timing.call('dependency_recheck', check_unchanged, root, selection, plan['dependencies'], source, plan.get('layer_evidence'))
            if not reuse:
                require(timing.call('dependency_check', dependencies, root, selection) == plan['dependencies'],
                        'RESOURCE_DEPENDENCIES_CHANGED')
        check_complete_scopes(source, scopes)
        with timing.stage('apply_files'):
            inputs = ResourcePaths(source)
            targets = ResourcePaths(store / 'current', create=True)
            if not pending:
                transaction.mkdir()
                set_state(transaction, state)
            temporary = child(transaction, 'payload')
            for operation in read_operations(directory / 'operations.jsonl'):
                with timing.stage('path_check'):
                    target = targets.file(operation['path'])
                    incoming = inputs.file(operation['path']) if operation['after'] else None
                if operation['after']:
                    with timing.stage('copy_hash', files=1, bytes=operation['after']['bytes']):
                        copy_verified(incoming, temporary, operation['after'])
                    timing.call('install_files', os.replace, temporary, target)
                else:
                    require(allow_deletions, 'DELETIONS_REQUIRE_ALLOW_DELETIONS')
                    timing.call('install_files', target.unlink, missing_ok=True)
        check_complete_scopes(source, scopes)
        if selection:
            timing.call('dependency_recheck', check_unchanged, root, selection, plan['dependencies'], source, plan.get('layer_evidence'))
        timing.call('metadata_check', check_update_metadata, store, plan, 'applying')
        receipt = {'schema_version': 1, 'receipt_id': state['receipt_id'],
                   'completed_at': utc_now(), 'plan_sha256': plan_sha,
                   'manifest_sha256': proposed['manifest_sha256'], 'source_counts': proposed['source_counts'],
                   'plan': str(directory), **plan['summary']}
        if selection:
            receipt['selection'] = selection
            if selection.get('layer_types'):
                receipt['layer_evidence'] = plan['layer_evidence']
        # A failed receipt write is replaceable while still in the applying state.
        child(transaction, 'receipt.json').unlink(missing_ok=True)
        write_json(transaction / 'receipt.json', receipt)
        state = {**state, 'state': 'committing'}
        set_state(transaction, state)
    else:
        pending_receipt = transaction / 'receipt.json'
        receipt = read_json(no_links(pending_receipt if pending_receipt.exists() else
                                     store / 'updates' / (state['receipt_id'] + '.json')))
    if state['state'] == 'committing':
        with timing.stage('install_metadata'):
            for source_name, target_name in (('next.jsonl', 'manifest.jsonl'), ('sources.json', 'source.json')):
                temporary = child(transaction, target_name)
                shutil.copyfile(directory / source_name, temporary)
                os.replace(temporary, no_links(store / target_name))
            state = {**state, 'state': 'committed'}
            set_state(transaction, state)
    with timing.stage('finish_update'):
        timing.call('receipt', finish_receipt, store)
        timing.call('cleanup', remove_transaction, store)
    return receipt


def check_update_metadata(store, plan, state):
    for name, before, after in (
            ('manifest.jsonl', plan['base_manifest_sha256'], plan['artifacts']['next.jsonl']),
            ('source.json', plan['base_metadata_sha256'], plan['artifacts']['sources.json'])):
        allowed = (before,) if state == 'applying' else (after,) if state == 'committed' else (before, after)
        require(digest(no_links(store / name)) in allowed, 'RESOURCE_METADATA_CHANGED: ' + name)


def recover(root):
    """Retry an incomplete update; initialization recovery never changes raw files."""
    store = store_at(root)
    with Timings('recover') as timing, locked(store):
        if (store / '.initializing.json').exists():
            return recover_initialization(store)
        transaction = no_links(store / '.transaction')
        require(transaction.is_dir(), 'NO_PENDING_TRANSACTION')
        if not (transaction / 'state.json').exists():
            require(all(p.name == 'state-next.json' for p in transaction.iterdir()), 'TRANSACTION_STATE_MISSING_WITH_CONTENT')
            remove_transaction(store)
            return {'status': 'cleaned', 'previous_state': 'not_started', 'content_checked': False}
        state = update_state(store)
        receipt = apply_locked(root, store, state['plan'], state['allow_deletions'], timing)
    return {'status': 'applied', 'previous_state': state['state'], 'content_checked': True, 'content_scope': 'changed_files',
            **receipt, 'timings': timing.result()}


def main(argv=None):
    """Run offline resource maintenance; these commands never edit Wiki catalogs or publish."""
    parser = argparse.ArgumentParser(description='Maintain the local game resource library.')
    parser.add_argument('--root', type=Path, default=ROOT)
    commands = parser.add_subparsers(dest='command', required=True)
    initialize_parser = commands.add_parser('init')
    initialize_parser.add_argument('--metadata', type=Path, required=True)
    plan_parser = commands.add_parser('plan')
    plan_parser.add_argument('--source', type=Path, required=True)
    plan_parser.add_argument('--metadata', type=Path, required=True)
    plan_parser.add_argument('--output', type=Path, required=True)
    plan_parser.add_argument('--complete-scope', action='append', default=[])
    plan_parser.add_argument('--report-duplicates', action='store_true', help='Opt in to the temporary duplicate-content report.')
    selection = plan_parser.add_mutually_exclusive_group()
    selection.add_argument('--profile', choices=['wiki','daily'], default='wiki',
                           help='Resource selection profile (default: wiki for routine Wiki updates).')
    selection.add_argument('--unfiltered', dest='profile', action='store_const', const=None,
                           help='Scan the entire supplied source for investigation or targeted exports.')
    apply_parser = commands.add_parser('apply')
    apply_parser.add_argument('--plan', type=Path, required=True)
    apply_parser.add_argument('--allow-deletions', action='store_true')
    commands.add_parser('status')
    commands.add_parser('verify')
    commands.add_parser('recover')
    for command in commands.choices.values():
        command.add_argument('--root', type=Path, default=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    try:
        if args.command == 'init':
            result = initialize(args.root, read_json(args.metadata))
        elif args.command == 'plan':
            result = make_plan(args.root, args.source, read_json(args.metadata), args.output,
                               args.complete_scope, args.profile, args.report_duplicates)
        elif args.command == 'apply':
            result = apply_plan(args.root, args.plan, args.allow_deletions)
        elif args.command == 'recover':
            result = recover(args.root)
        else:
            result = status(args.root, full=args.command == 'verify')
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ResourceError, OSError, ValueError, KeyError) as error:
        print(json.dumps({'status': 'error', 'error': str(error)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('Interrupted; run recover if a transaction is pending.', file=sys.stderr)
        return 130
