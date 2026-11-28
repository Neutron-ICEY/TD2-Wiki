"""Opt-in directory exclusions and guards over existing dependency registrations."""
import hashlib
import json
from pathlib import Path, PureWindowsPath
import posixpath
import re

from . import child, digest, encoded, relative, require
from tools.asset_import.library import Library
from tools.asset_import.locations import SourceLocations


PROFILE_FILE = 'data/asset-import/resource-scope.json'
DISCOVERY_ROOTS = ('raw_files/hunter/game system data', 'raw_files/rogue/game system data')
LAYER_PATH = re.compile(r'raw_files/hunter/maps/[0-9a-f]{32}/settings/[0-9a-f]{32}\Z')
IMAGE_IDENTITIES = {('source', 'entry'), ('source_entry',), ('resource_name',),
                    ('provenance', 'resource_name'), ('provenance', 'internal_asset_name'),
                    ('sprite',), ('sprite', 'name')}


def native_include_path(owner, value):
    """Resolve an include in the raw namespace without opening resource files."""
    require(isinstance(value, str) and value, 'INVALID_NATIVE_INCLUDE')
    value = value.replace('\\', '/')
    require(not value.startswith('/') and not PureWindowsPath(value).drive, 'ABSOLUTE_NATIVE_INCLUDE')
    if not value.startswith(('hunter/', 'rogue/', 'snowdrop/')):
        require(owner is not None and owner.casefold().startswith('raw_files/'), 'NATIVE_INCLUDE_OWNER_MISSING')
        # Native.lineage resolves relative includes from the defining file, not
        # from the index JSON or the saved fragment's evidence directory.
        value = posixpath.join(posixpath.dirname(relative(owner)[len('raw_files/'):]), value)
    value = posixpath.normpath(value)
    require(value != '..' and not value.startswith('../'), 'NATIVE_INCLUDE_OUTSIDE_RAW_ROOT')
    return 'raw_files/' + relative(value)


def load_selection(root, profile):
    if profile == 'daily':
        name = 'data/asset-import/resource-daily.json'
        blob = child(root, name).read_bytes()
        rules = json.loads(blob)
        require(set(rules) == {'schema_version','id','discovery_directories','excluded_directories','export_terms'}
                and rules['schema_version'] == 1 and rules['id'] == profile, 'INVALID_DAILY_PROFILE')
        includes = [relative(v).casefold() for v in rules['discovery_directories']]
        excludes = [relative(v).casefold() for v in rules['excluded_directories']]
        require(set(DISCOVERY_ROOTS) <= set(includes) and len(includes) == len(set(includes))
                and not any(i == e or i.startswith(e + '/') or e.startswith(i + '/') for i in includes for e in excludes),
                'INVALID_DAILY_DISCOVERY_ROOTS')
        terms = rules['export_terms']
        require(isinstance(terms,list) and terms and all(isinstance(t,str) and re.fullmatch(r'[a-z0-9 /_]{2,30}',t) for t in terms),
                'INVALID_HUNTER_DISCOVERY_TERMS')
        return dict(schema_version=1, export_terms=terms, profile=profile, file=name, sha256=hashlib.sha256(blob).hexdigest(),
                    discovery_directories=includes, excluded_directories=excludes)
    require(profile == 'wiki', 'UNKNOWN_RESOURCE_PROFILE')
    blob = child(root, PROFILE_FILE).read_bytes()
    rules = json.loads(blob)
    require(isinstance(rules, dict) and rules.get('schema_version') in (1, 2), 'INVALID_RESOURCE_PROFILE')
    version = rules['schema_version']
    require(set(rules) == {'schema_version', 'id', 'excluded_directories'} | ({'layer_types'} if version == 2 else set())
            and rules['id'] == profile,
            'INVALID_RESOURCE_PROFILE')
    paths = rules['excluded_directories']
    require(isinstance(paths, list) and paths, 'INVALID_EXCLUDED_DIRECTORIES')
    paths = [relative(p) for p in paths]
    folded = [p.casefold() for p in paths]
    require(len(set(folded)) == len(paths) and not any(
        a != b and a.startswith(b + '/') for a in folded for b in folded),
        'OVERLAPPING_EXCLUDED_DIRECTORIES')
    require(not any(p == root or p.startswith(root + '/') or root.startswith(p + '/')
                    for p in folded for root in DISCOVERY_ROOTS), 'DISCOVERY_SCOPE_EXCLUDED')
    layer_types = rules.get('layer_types', {})
    require(isinstance(layer_types, dict), 'INVALID_LAYER_TYPES')
    require(all(relative(p) in paths and LAYER_PATH.fullmatch(p.casefold())
                and kind in ('navmesh', 'globalillumination') for p, kind in layer_types.items()), 'INVALID_LAYER_TYPES')
    require({p.casefold() for p in layer_types} == {p for p in folded if p.startswith('raw_files/hunter/maps/')},
            'MAP_EXCLUSION_REQUIRES_LAYER_TYPE')
    require('raw_files/hunter/maps' not in folded, 'MAP_EXCLUSION_REQUIRES_LAYER_TYPE')
    return {'schema_version': version, 'profile': profile, 'file': PROFILE_FILE,
            'sha256': hashlib.sha256(blob).hexdigest(),
            'excluded_directories': sorted(paths, key=str.casefold),
            **({'layer_types': dict(sorted(layer_types.items()))} if version == 2 else {})}


def check_snapshot(root, inputs):
    for name, expected in inputs.items():
        require(not name.casefold().startswith(('resources/game/current/', 'incoming/')),
                'DEPENDENCY_METADATA_IN_RESOURCE_TREE')
        require(digest(child(root, name)) == expected, 'DEPENDENCY_INPUT_CHANGED: ' + name)


def check_unchanged(root, selection, dependencies, source=None, layer_evidence=None):
    require(load_selection(root, selection['profile']) == selection, 'SELECTION_RULES_CHANGED')
    check_snapshot(root, dependencies['inputs'])
    if selection.get('layer_types'):
        from .layers import inspect_layers
        require(source is not None and layer_evidence is not None, 'LAYER_EVIDENCE_REQUIRED')
        require(inspect_layers(source, selection) == layer_evidence, 'LAYER_EVIDENCE_CHANGED')


def dependencies(root, selection, *, required_output=None):
    """Read metadata only, including active image parent evidence and parsed includes.

    Unknown resource directories remain selected. This is a registration conflict
    guard, not a claim to discover every unimplemented game-engine dependency.
    """
    root = Path(root).resolve()
    inputs, documents, required = {}, {}, set()

    def read_document(path, expected=None):
        path = Path(path)
        name = (path.relative_to(root).as_posix() if path.is_absolute() else relative(path.as_posix()))
        require(not name.casefold().startswith(('resources/game/current/', 'incoming/')),
                'DEPENDENCY_METADATA_IN_RESOURCE_TREE: ' + name)
        if name not in documents:
            blob = child(root, name).read_bytes()
            inputs[name] = hashlib.sha256(blob).hexdigest()
            documents[name] = json.loads(blob)
        require(expected is None or inputs[name] == expected, 'DEPENDENCY_INDEX_HASH_MISMATCH: ' + name)
        return documents[name]

    read_document('data/asset-import/locations.json')
    locations = SourceLocations(root)
    batches = read_document('data/asset-import/batches.json')
    historical_roots = batches.get('historical_roots', [])

    def path_reference(value, base):
        value = re.sub(r':\d+(?::\d+)?$', '', value.replace('\\', '/').strip('"').split('#', 1)[0])
        folded = value.casefold()
        if folded.startswith(('raw_files/', 'images/', 'materials/')):
            return value
        # Exact relocation preserves existing evidence identities, including old
        # export paths. Explicit export parents also carry raw_files/images roots.
        repository_relative = folded.startswith(('resources/', 'dist/', 'incoming/'))
        if (repository_relative or folded.startswith(str(root).replace('\\', '/').casefold() + '/')
                or folded.startswith(('hunter/raw/', 'rogue/raw/', 'snowdrop/raw/'))
                or ':' in value and any(PureWindowsPath(value).is_relative_to(p) for p in historical_roots)):
            resolved = locations.resolve(value, base='.' if repository_relative else base,
                                         resolve=False, historical_roots=historical_roots)
            name = resolved.relative_to(root).as_posix()
            if name.casefold().startswith('resources/game/current/'):
                return name[len('resources/game/current/'):]
            if name.casefold().startswith(('dist/', 'incoming/')):
                parts = name.split('/')
                for i, part in enumerate(parts):
                    if part.casefold() in ('raw_files', 'images', 'materials'):
                        return '/'.join(parts[i:])
        if folded.startswith(('hunter/', 'rogue/', 'snowdrop/')):
            return 'raw_files/' + value
        return None

    def visit(value, base='.', image_evidence=False, trail=()):
        if isinstance(value, dict):
            for key, item in value.items():
                # These identify an image inside a container, not an exported raw
                # file. Actual images, parents and sprite definitions stay below.
                if image_evidence and isinstance(item, str) and trail + (key,) in IMAGE_IDENTITIES:
                    continue
                visit(item, base, image_evidence, trail + (key,))
        elif isinstance(value, list):
            for item in value:
                visit(item, base, image_evidence, trail + ('[]',))
        elif isinstance(value, str):
            logical = value.replace('\\','/').strip('"')
            folded = logical.casefold()
            atlas_texture = image_evidence and trail in {('provenance', 'texture'), ('original_atlas', 'resource_name')}
            native_dds = trail[-1:] == ('raw_value',) and folded.endswith('.dds')
            if image_evidence and folded.startswith(('hunter/raw/images/', 'hunter/raw/raw_files/', 'hunter/raw/materials/')):
                path = logical[len('hunter/raw/'):]
            elif (atlas_texture or native_dds) and folded.startswith(('hunter/', 'rogue/', 'snowdrop/')):
                # Atlas names and native DDS references identify Images in the Hunter export.
                stem = logical[:-4] if folded.endswith(('.dds', '.png')) else logical
                path = 'images/' + stem + '.png'
            else:
                path = path_reference(value, base)
            if path:
                required.add(relative(path))

    mapping = read_document('data/equipment/native-map.json')
    require(mapping.get('schema_version') == 1 and isinstance(mapping.get('entities'), list),
            'INVALID_NATIVE_DEPENDENCY_REGISTRATION')
    visit(mapping)
    if selection['profile'] == 'daily':
        # Maintained recipes contain the exact map buckets and interaction files read by the projector.
        crafting = read_document('data/equipment/crafting.json')
        visit(crafting)
        for sections in crafting.get('source_contexts', {}).values():
            if isinstance(sections, dict):
                visit(list(sections))
        for skin in read_document('data/equipment/weapon-skins.json')['skins']:
            if skin.get('image_source'):
                visit(skin['image_source'])
    index = read_document('data/asset-import/text-sources.json')
    require(index.get('schema_version') == 1 and isinstance(index.get('sources'), list),
            'INVALID_TEXT_DEPENDENCY_REGISTRATION')
    visit(index['sources'])
    for key in ('native_definitions', 'native_references'):
        spec = index[key]
        document = read_document(locations.resolve(spec['file'], resolve=False), spec['sha256'])
        require(isinstance(document.get('files'), list), 'INVALID_NATIVE_DEPENDENCY_INDEX')
        visit({k: v for k, v in document.items() if k != 'files'})
        for item in document['files']:
            parsed = item.get('parsed', {})
            visit({**item, 'parsed': {k: v for k, v in parsed.items() if k != 'includes'}})
            for include in parsed.get('includes', []):
                owner = path_reference(item.get('resource_name') or item.get('file') or '', '.')
                required.add(native_include_path(owner, include['path']))

    class RegisteredImages(Library):
        def document(self, path):
            return read_document(self._path(path, resolve=False))

    images = RegisteredImages(root)
    require(not images.issues, 'IMAGE_DEPENDENCY_REGISTRATION_UNAVAILABLE: ' + json.dumps(images.issues))
    for record in images.records:
        if (selection['profile'] == 'daily' and record.get('historical_observation')
                and not (record['uses'] or record['wiki_asset_id'] or record['target_matches'])):
            continue
        visit(record, image_evidence=True)
        # Only selected observations, never entire historical batch arrays.
        for evidence in record['evidence']:
            if 'pointer' not in evidence:
                continue
            row = images.document(evidence['file'])
            for token in evidence['pointer'].split('/')[1:]:
                token = token.replace('~1', '/').replace('~0', '~')
                row = row[int(token)] if isinstance(row, list) else row[token]
            batch = next(b for b in batches['batches'] if b['id'] == record['batch_id'])
            visit(row, batch.get('base', '.'), image_evidence=True)

    excluded = tuple(p.casefold() for p in selection['excluded_directories'])
    conflicts = sorted(p for p in required if any(
        p.casefold() == prefix or p.casefold().startswith(prefix + '/') for prefix in excluded))
    require(not conflicts, 'REQUIRED_RESOURCE_EXCLUDED: ' + ', '.join(conflicts[:10]))
    check_snapshot(root, inputs)
    if required_output is not None:
        required_output.update(required)
    return {'inputs': dict(sorted(inputs.items())), 'required_paths': len(required),
            'required_paths_sha256': hashlib.sha256(encoded(sorted(required))).hexdigest()}


class DiscoveryPaths:
    """Prune at directory boundaries while retaining every registered input."""

    def __init__(self, directories, required):
        self.directories = {v.casefold() for v in directories}
        self.paths = {v.casefold() for v in required}
        self.parents = set()
        for path in self.directories | self.paths:
            while '/' in path:
                path = path.rsplit('/', 1)[0]
                self.parents.add(path)
