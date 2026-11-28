"""Read-only lookup over explicitly registered historical resource records.

No extraction, discovery walk, persistent cache, identity promotion or write path.
Byte/pixel groups retain every observation and never choose a preferred asset.
"""
import argparse
from collections import defaultdict
import json
from pathlib import Path, PureWindowsPath
import sys

from .static_formats import sha256
from .locations import SourceLocations, repository_path


DEFAULT_INDEX = 'data/asset-import/batches.json'
ROOT = Path(__file__).resolve().parents[2]
UNKNOWN = (None, '', 'UNKNOWN', 'unknown')


def known(value):
    return None if value in UNKNOWN else value


def local_path(root, value, base='.', resolve=True, historical_roots=()):
    """Resolve only local repository files; container paths remain plain evidence."""
    return repository_path(root, value, base, resolve, historical_roots)


def read_index(root, index=DEFAULT_INDEX):
    root = Path(root).resolve()
    data = json.loads(local_path(root, index).read_text(encoding='utf-8-sig'))
    if data.get('schema_version') != 1:
        raise ValueError('UNSUPPORTED_LIBRARY_INDEX')
    historical_roots = data.get('historical_roots', [])
    if not isinstance(historical_roots, list) or any(not isinstance(p, str) or not PureWindowsPath(p).is_absolute() for p in historical_roots):
        raise ValueError('INVALID_HISTORICAL_ROOTS')
    ids = [b['id'] for b in data['batches']]
    if len(ids) != len(set(ids)):
        raise ValueError('DUPLICATE_BATCH_ID')
    return data


def names(record):
    return {
        'recorded': sorted(set(record.get('chinese_names', []) + record.get('english_names', []))),
        'proposed': sorted(set(record.get('proposed_chinese_names', []) + record.get('proposed_english_names', []))),
        'catalog': [],
    }


def source(record, package=None):
    provenance = record.get('provenance') or record
    return dict(container=known(provenance.get('source_container') or record.get('source_package')),
                container_sha256=known(provenance.get('source_container_sha256') or (package or {}).get('sha256')),
                entry=known(provenance.get('resource_name') or record.get('source_entry')),
                resource_id=known(provenance.get('resource_id')),
                original_resource_sha256=known(provenance.get('original_resource_sha256')),
                game_build=known(provenance.get('game_build')))


class Library:
    def __init__(self, root=ROOT, index=DEFAULT_INDEX):
        self.root = Path(root).resolve()
        self.index = read_index(self.root, index)
        self.locations = SourceLocations(self.root)
        from tools.identity import registry
        try:self.wiki_assets = {row['id']:row for row in registry(self.root) if row['kind']=='assets'}
        except FileNotFoundError:self.wiki_assets = None
        self.records = []
        self.issues = []
        self._documents = {}
        for batch in self.index['batches']:
            try:
                records = self._batch(batch)
                if 'observations' in batch:
                    selected = batch['observations']
                    available = {row['record_key'].split('#', 1)[1] for row in records}
                    if (not isinstance(selected, list) or any(not isinstance(p, str) for p in selected)
                            or len(selected) != len(set(selected)) or not set(selected) <= available):
                        raise ValueError('INVALID_OBSERVATION_SELECTION')
                    selected = set(selected)
                    records = [row for row in records if row['record_key'].split('#', 1)[1] in selected]
                if 'historical_observations' in batch:
                    pointers = batch['historical_observations']
                    by_pointer = {row['record_key'].split('#', 1)[1]: row for row in records}
                    if (not isinstance(pointers, list) or any(not isinstance(p, str) for p in pointers)
                            or len(set(pointers)) != len(pointers) or not set(pointers) <= by_pointer.keys()):
                        raise ValueError('INVALID_HISTORICAL_OBSERVATION')
                    for pointer in pointers:
                        by_pointer[pointer]['historical_observation'] = True
                self.records.extend(records)
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.issues.append(dict(batch_id=batch['id'], state='unavailable', error=str(error)))
        self._enrich()

    def _path(self, value, base='.', resolve=True):
        return self.locations.resolve(value, base, resolve, self.index.get('historical_roots', []))

    def document(self, path):
        resolved = self._path(path)
        if resolved not in self._documents:
            self._documents[resolved] = json.loads(resolved.read_text(encoding='utf-8-sig'))
        return self._documents[resolved]

    def _record(self, batch, pointer, row, path, digest, kind='source', wiki_asset_id=None):
        wiki_asset_id = wiki_asset_id or row.get('asset_ref')
        if wiki_asset_id and (self.wiki_assets is None or wiki_asset_id not in self.wiki_assets):raise ValueError('UNKNOWN_WIKI_ASSET')
        try:
            if wiki_asset_id:
                resolved = repository_path(self.root,self.wiki_assets[wiki_asset_id]['source'],resolve=False)
            else:resolved = self._path(path, batch.get('base', '.'), resolve=False)
            file_state = 'not_checked' if resolved else 'unknown'
        except ValueError:
            resolved = None
            file_state = 'outside_root'
        return dict(record_key=batch['id'] + '#' + pointer, batch_id=batch['id'],
                    batch_role=batch['role'], record_type=kind, asset_id=known(row.get('asset_id')), wiki_asset_id=wiki_asset_id,
                    path=str(resolved) if resolved else None, recorded_path=path, file_state=file_state,
                    sha256=known(digest), pixel_hash=known(row.get('pixel_hash')),
                    width=row.get('width'), height=row.get('height'),
                    category=known(row.get('category')), technical_category=known(row.get('technical_category')),
                    primary_class=known(row.get('primary_class')), names=names(row),
                    mapping_status=known(row.get('mapping_status') or row.get('status')),
                    source=source(row), sprite=None, derivation=None, uses=[], references=[], review_labels=[], target_matches=[],
                    evidence=[dict(file=batch['file'], pointer=pointer)])

    def _batch(self, batch):
        data = self.document(batch['file'])
        fmt = batch['format']
        if fmt in ('game_sprites', 'material_sprites'):
            return self._sprites(batch, data)
        if fmt not in ('manifest', 'exports', 'derived', 'publications'):
            raise ValueError('UNSUPPORTED_BATCH_FORMAT: ' + fmt)
        collection = batch.get('collection', {'manifest': 'assets', 'exports': 'exports',
                                             'publications': 'images'}.get(fmt))
        rows = data[collection] if collection else data
        packages = self.document(batch['packages']) if batch.get('packages') else {}
        annotations = {a['asset_id']: a for a in self.document(batch['annotations'])['assets']} if batch.get('annotations') else {}
        result = []
        for i, row in enumerate(rows):
            pointer = '/' + (collection + '/' if collection else '') + str(i)
            if fmt == 'manifest':
                item = self._record(batch, pointer, row, row['raw_path'], row['source_sha256'])
                item['source'] = source(row, packages.get(row.get('source_platform')))
                annotation = annotations.get(row['asset_id'])
                if annotation:
                    if annotation['source_sha256'] != row['source_sha256']:
                        raise ValueError('ANNOTATION_CONTENT_CONFLICT')
                    item['names'] = names(annotation)
                    item['technical_category'] = known(annotation.get('technical_category'))
                    item['mapping_status'] = known(annotation.get('mapping_status'))
                    item['evidence'].append(dict(file=batch['annotations'], asset_id=row['asset_id']))
            elif fmt == 'exports':
                item = self._record(batch, pointer, row, row['exported_path'], row['exported_file_sha256'])
                item['pixel_hash'] = known(row.get('decoded_image_sha256'))
            elif fmt == 'publications':
                item = self._record(batch, pointer, row, 'assets/' + row['wiki_filename'], row['source_sha256'], 'use', row['registry_id'] if self.wiki_assets is not None else None)
                item['names']['recorded'] = [row['approved_label']] if row.get('approved_label') else []
                item['uses'] = [dict(registry_id=row['registry_id'], wiki_filename=row['wiki_filename'],
                                     current_filename=self.wiki_assets[row['registry_id']]['title'].split(':',1)[-1] if self.wiki_assets is not None else None,
                                     reader_role=row.get('reader_role'), selected_asset_id=row.get('selected_asset_id'),
                                     selected_raw_path=row.get('selected_raw_path'),
                                     semantic_identity_scope=row.get('semantic_identity_scope'))]
                item['source'] = source({})
            else:
                # Historical source_sha256 here may mean the PARENT, never the output.
                digest = row.get('derived_sha256') or row.get('native_crop_sha256') or row.get('sha256')
                item = self._record(batch, pointer, row, row.get('derived_file') or row.get('raw_path'), digest, 'derived')
                parent = row.get('original_atlas') or {}
                provenance = row.get('provenance') or {}
                item['source'] = source({})
                item['names']['recorded'] += [row[k] for k in ('zh', 'en', 'wiki_filename') if row.get(k)]
                if row.get('size'):
                    item['width'], item['height'] = row['size']
                rect = row.get('rect') or provenance.get('crop_box')
                item['derivation'] = dict(parent_sha256=parent.get('sha256') or row.get('source_sha256'),
                                          rect=rect,
                                          rect_convention=('xywh' if 'rect' in row else 'xyxy') if rect is not None else None,
                                          conversion=row.get('conversion'), output_sha256=digest)
                item['sprite'] = dict(name=row.get('sprite') or provenance.get('internal_asset_name'),
                                      definition=(row.get('sprite_definition') or {}).get('path'),
                                      rect=item['derivation']['rect'], rect_convention=item['derivation']['rect_convention'])
            result.append(item)
        return result

    def _sprites(self, batch, data):
        game = batch['format'] == 'game_sprites'
        sheets = data['spritesheets'] if game else data
        images = self.document(batch['images'])['assets'] if game else []
        image_paths = {self._path(r['raw_path'], batch['base'], resolve=False): r for r in images}
        result = []
        for i, sheet in enumerate(sheets):
            if game:
                image_path = (Path('hunter/raw/images') / sheet['texture']).with_suffix('.png').as_posix()
                resolved = self._path(image_path, batch['base'], resolve=False)
                image = image_paths.get(resolved)
                if image is None:
                    raise ValueError('SPRITE_ATLAS_REFERENCE_UNRESOLVED')
                digest = image['source_sha256']
                refs = [dict(path=str(self._path(sheet['path'], batch['base'], resolve=False)), sha256=sheet['source_sha256'])]
            else:
                image_path, digest = sheet['png']['path'], sheet['png']['sha256']
                refs = [sheet['definition'], sheet['decompiled']]
            for j, sprite in enumerate(sheet['sprites']):
                pointer = ('/spritesheets' if game else '') + '/' + str(i) + '/sprites/' + str(j)
                item = self._record(batch, pointer, {}, image_path, digest, 'sprite')
                uv = {k: sprite[k] for k in ('x', 'y', 'w', 'h')} if game else sprite['uv']
                rect = ([round(uv['x'] * sheet['width']), round(uv['y'] * sheet['height']),
                         round(uv['w'] * sheet['width']), round(uv['h'] * sheet['height'])] if game else sprite['rect'])
                item['width'], item['height'] = sheet['width'], sheet['height']
                item['source'] = source(image) if game else source({'source_entry': sheet['texture']})
                item['sprite'] = dict(name=sprite['name'], uv=uv, rect=rect, rect_convention='xywh',
                                      definition=str(self._path(refs[0]['path'], resolve=False)), line=sprite.get('line'),
                                      content_scope='atlas_file_not_region_hash')
                item['references'] = refs
                result.append(item)
        return result

    def _enrich(self):
        """Catalog relations join an explicit selected ID AND hash, never hash alone."""
        for config in self.index.get('catalogs', []):
            try:
                catalog = self.document(config['file'])
                by_id = {r['asset_id']: r for r in self.records if r['batch_id'] == config['batch_id']}
                for brand in catalog['brands']:
                    mapping = brand['asset_mapping']
                    item = by_id.get(mapping['selected_asset_id'])
                    if item is None or item['sha256'] != mapping['selected_source_sha256']:
                        raise ValueError('CATALOG_SOURCE_REFERENCE_CONFLICT')
                    item['names']['catalog'] = [brand[k] for k in ('zh_name', 'en_name') if brand.get(k)] + brand.get('search_aliases', [])
                    filename = self.wiki_assets[brand['asset_ref']]['title'].split(':',1)[-1] if brand.get('asset_ref') else brand['wiki_filename']
                    item['uses'].append(dict(entity_key=brand['entity_key'], wiki_asset_id=brand.get('asset_ref'), wiki_filename=filename,
                                             asset_role=mapping['asset_role'], identity_scope=brand.get('identity_verification_scope')))
                    item['evidence'].append(dict(file=config['file'], entity_key=brand['entity_key']))
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.issues.append(dict(file=config['file'], state='unavailable', error=str(error)))
        if self.index.get('targets'):
            try:
                notes = self.document(self.index['targets'])
                for label in notes.get('application_labels', []):
                    if label.get('availability') == 'retired':
                        continue
                    matches = [r for r in self.records if self._selected(r, label['selector'])]
                    if len(matches) != 1:
                        raise ValueError('APPLICATION_LABEL_REFERENCE_UNRESOLVED')
                    matches[0]['names']['recorded'].append(label['name'])
                    matches[0]['evidence'].append(label['evidence'])
                for target in notes['targets']:
                    for candidate in target['candidates']:
                        matches = [r for r in self.records if self._selected(r, candidate['selector'])]
                        if len(matches) != 1:
                            raise ValueError('TARGET_REFERENCE_UNRESOLVED')
                        item = matches[0]
                        item['primary_class'] = 'ui_symbol'  # Explicit review metadata only.
                        item['review_labels'].append(target['label'])
                        item['target_matches'].append(dict(target_id=target['id'], match_status=candidate['match_status']))
                        item['evidence'].append(dict(file=self.index['targets'], target_id=target['id']))
            except (OSError, ValueError, KeyError, TypeError) as error:
                self.issues.append(dict(file=self.index['targets'], state='unavailable', error=str(error)))

    @staticmethod
    def _selected(item, selector):
        if set(selector) - {'batch_id', 'asset_id', 'sprite_name'} or not ({'asset_id', 'sprite_name'} & set(selector)):
            raise ValueError('INVALID_REVIEW_SELECTOR')
        return (item['batch_id'] == selector['batch_id']
                and ('asset_id' not in selector or item['asset_id'] == selector['asset_id'])
                and ('sprite_name' not in selector or (item['sprite'] or {}).get('name') == selector['sprite_name']))

    def search(self, query='', field='any', batch_ids=()):
        ids = {b['id'] for b in self.index['batches']}
        if set(batch_ids) - ids:
            raise ValueError('UNKNOWN_BATCH_ID')
        needle = query.casefold().replace('\\', '/')
        result = []
        for item in self.records:
            if batch_ids and item['batch_id'] not in batch_ids:
                continue
            sprite = item['sprite'] or {}
            fields = dict(path=[item['path'], item['recorded_path'], item['source']['entry'], item['source']['container']],
                          sha256=[item['sha256']], id=[item['asset_id'], item.get('wiki_asset_id'), item['record_key']],
                          category=[item['category'] or 'unknown', item['technical_category'], item['primary_class']],
                          name=sum(item['names'].values(), []) + item['review_labels'], batch=[item['batch_id'], item['batch_role']],
                          sprite=[sprite.get('name'), sprite.get('definition')])
            values = sum(fields.values(), []) if field == 'any' else fields[field]
            normalized = [str(v).casefold().replace('\\', '/') for v in values if v is not None]
            if (needle in normalized if field == 'sha256' else any(needle in value for value in normalized)):
                result.append(item)
        return result

    def duplicates(self, kind='bytes'):
        if kind == 'shared':
            config = self.index.get('shared_relations')
            if not config:
                return []
            by_id = {r['asset_id']: r for r in self.records if r['batch_id'] == config['batch_id']}
            groups = self.document(config['file'])['groups']
            selected = [g for g in groups if g['type'] == 'pixel_duplicate' and g.get('legitimate_shared_icon')]
            if any(set(g['members']) - set(by_id) for g in selected):
                raise ValueError('SHARED_RELATION_MEMBER_UNAVAILABLE')
            return [dict(kind='shared_application_icon', identity_scope='recorded_application_bindings_not_wiki_entities',
                         key=g['digest'], entities=g['confirmed_application_entities'],
                         members=[by_id[m] for m in g['members']], evidence=config['file']) for g in selected]
        groups = defaultdict(list)
        for item in self.records:
            if item['record_type'] == 'sprite':
                continue  # Sprite observations share one atlas file; they are not copies.
            if kind == 'source':
                src = item['source']
                key = (src['container'], src['container_sha256'], src['entry']) if item['record_type'] == 'source' else None
                if key and not all(key):
                    key = None
            else:
                key = item['sha256'] if kind == 'bytes' else item['pixel_hash']
            if key:
                groups[key].append(item)
        return [dict(kind=kind, key=key, members=members) for key, members in sorted(groups.items()) if len(members) > 1]

    def verify(self, records):
        cache = {}
        result = []
        for item in records:
            checks = []
            for ref in [dict(path=item['path'], sha256=item['sha256'])] + item['references']:
                try:
                    p = self._path(ref.get('path'))
                    if p is None or not p.is_file():
                        state, actual = ('outside_root' if item['file_state'] == 'outside_root' else 'missing'), None
                    else:
                        if p not in cache:
                            cache[p] = sha256(p.read_bytes())
                        actual = cache[p]
                        state = ('match' if actual == ref['sha256'] else 'mismatch') if known(ref.get('sha256')) else 'unknown'
                except ValueError:
                    state, actual = 'outside_root', None
                checks.append(dict(path=ref.get('path'), expected=ref.get('sha256'), actual=actual, state=state))
            state = checks[0]['state']
            result.append(dict(item, file_state='present' if state in ('match', 'mismatch', 'unknown') else state,
                               verification=dict(passed=all(c['state'] == 'match' for c in checks), checks=checks)))
        return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--index', default=DEFAULT_INDEX)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('batches')
    search = commands.add_parser('search')
    search.add_argument('query', nargs='?', default='')
    search.add_argument('--field', choices=('any', 'path', 'sha256', 'id', 'name', 'category', 'batch', 'sprite'), default='any')
    search.add_argument('--batch', action='append', default=[])
    duplicates = commands.add_parser('duplicates')
    duplicates.add_argument('--kind', choices=('bytes', 'pixels', 'source', 'shared'), default='bytes')
    targets = commands.add_parser('targets')
    targets.add_argument('target', nargs='?')
    for command in (search, duplicates):
        command.add_argument('--limit', type=int, default=20)
        command.add_argument('--offset', type=int, default=0)
        command.add_argument('--verify', action='store_true')
    args = parser.parse_args(argv)
    try:
        if args.command == 'batches':
            output = read_index(args.root, args.index)
            output['root'] = str(args.root.resolve())
            code = 0
        else:
            library = Library(args.root, args.index)
            if args.command == 'targets':
                output = library.document(library.index['targets'])
                output = dict(output, targets=[t for t in output['targets'] if not args.target or t['id'] == args.target])
                if args.target and not output['targets']:
                    raise ValueError('UNKNOWN_UI_TARGET')
            else:
                if not 1 <= args.limit <= 1000 or args.offset < 0:
                    raise ValueError('INVALID_PAGINATION')
                rows = library.search(args.query, args.field, args.batch) if args.command == 'search' else library.duplicates(args.kind)
                selected = rows[args.offset:args.offset + args.limit]
                if args.verify:
                    selected = (library.verify(selected) if args.command == 'search' else
                                [dict(g, members=library.verify(g['members'])) for g in selected])
                output = dict(total=len(rows), offset=args.offset, limit=args.limit, results=selected)
            output.update(coverage='partial' if library.issues else 'registered_batches_only', issues=library.issues,
                          unknown_fields='null; no identity inferred; pixel groups use recorded strict RGBA8 hashes')
            code = 2 if library.issues else 0
            if getattr(args, 'verify', False):
                checked = output['results'] if args.command == 'search' else [r for g in output['results'] for r in g['members']]
                if any(not r['verification']['passed'] for r in checked):
                    code = 3
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return code
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps(dict(error=str(error), writes_performed=False), ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
