"""Exact relocation of recorded source paths without changing evidence identity."""
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import re


DEFAULT_LOCATIONS = 'data/asset-import/locations.json'


def repository_path(root, value, base='.', resolve=True, historical_roots=()):
    """Resolve a repository file or an explicitly recorded former repository root."""
    if not value:
        return None
    root = Path(root).resolve()
    path = Path(value)
    for previous in historical_roots:
        recorded, origin = PureWindowsPath(value), PureWindowsPath(previous)
        if recorded.is_relative_to(origin):
            suffix = recorded.relative_to(origin)
            if '..' in suffix.parts:
                raise ValueError('PATH_OUTSIDE_ROOT')
            path = root.joinpath(*suffix.parts)
            break
    path = path if path.is_absolute() else root / base / path
    path = path.resolve() if resolve else Path(os.path.abspath(path))
    if not path.is_relative_to(root):
        raise ValueError('PATH_OUTSIDE_ROOT')
    return path


def _relative(value):
    if (not isinstance(value, str) or not value or '\\' in value or ':' in value
            or PurePosixPath(value).is_absolute()
            or any(p in ('', '.', '..') for p in value.split('/'))):
        raise ValueError('UNSAFE_LOCATION_PATH')
    return value


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('DUPLICATE_LOCATION_KEY')
        result[key] = value
    return result


class SourceLocations:
    def __init__(self, root, index=DEFAULT_LOCATIONS):
        self.root = Path(root).resolve()
        self.locations = {}
        self._lookup = {}
        try:
            text = repository_path(self.root, index).read_text(encoding='utf-8-sig')
        except FileNotFoundError:
            return
        data = json.loads(text, object_pairs_hook=_unique)
        if data.get('schema_version') != 1 or not isinstance(data.get('locations'), dict):
            raise ValueError('INVALID_SOURCE_LOCATIONS')
        recorded_paths = {PureWindowsPath(old) for old in data['locations']}
        assets = {}
        if any(isinstance(row,dict) and row.get('asset_ref') for row in data['locations'].values()):
            from tools.identity import registry
            assets = {row['id']:row for row in registry(self.root) if row['kind']=='assets'}
        for old, row in data['locations'].items():
            _relative(old)
            key = PureWindowsPath(old)
            if key in self._lookup:
                raise ValueError('CASE_CONFLICTING_SOURCE_LOCATION')
            if not isinstance(row, dict):
                raise ValueError('INVALID_SOURCE_LOCATION')
            if bool(row.get('path')) == bool(row.get('asset_ref')):
                raise ValueError('SOURCE_LOCATION_REQUIRES_ONE_TARGET')
            if row.get('asset_ref'):
                if row['asset_ref'] not in assets:raise ValueError('UNKNOWN_LOCATION_ASSET')
                target = _relative(assets[row['asset_ref']]['source'])
            else:target = _relative(row['path'])
            if not isinstance(row.get('sha256'), str) or not re.fullmatch('[0-9a-f]{64}', row['sha256']):
                raise ValueError('INVALID_LOCATION_HASH')
            if PureWindowsPath(target) in recorded_paths:
                raise ValueError('CHAINED_SOURCE_LOCATION')
            self.locations[old] = row
            self._lookup[key] = dict(row, path=target)

    def resolve(self, value, base='.', resolve=True, historical_roots=()):
        """Use recorded Windows path identity; no prefix, version or hash fallback."""
        recorded = repository_path(self.root, value, base, False, historical_roots)
        if recorded is None:
            return None
        row = self._lookup.get(PureWindowsPath(recorded.relative_to(self.root).as_posix()))
        return repository_path(self.root, row['path'] if row else recorded, resolve=resolve)
