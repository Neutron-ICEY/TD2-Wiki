"""Resolve independent armor attribute and Gear socket counts from saved definitions."""
import json
from pathlib import Path
from tools.asset_import.text_evidence import native_definitions


def contexts(record, links, kind):
    rows = record['properties'] + record.get('empty_blocks', []) + links
    found = {}
    for row in rows:
        for index, part in enumerate(row['context']):
            if part['resource_type'] == kind:
                context = row['context'][:index + 1]
                found[json.dumps(context, sort_keys=True)] = context
    return list(found.values())


def attribute_categories(parsed):
    return {row['resource_uid']: next(part['internal_name'] for part in row['parents']
            if part['resource_type'] == 'AttributeDefinitionList')
            for row in parsed['resources'] if row['resource_type'] == 'AttributeDefinition'}


def minor_count(record, links, quality='Orange', categories=None):
    """Return None when this definition has no selected quality override."""
    if any(row['field'] == 'myAttributeSlots' for row in record.get('empty_blocks', [])):
        return 0
    groups = contexts(record, links, 'QualityAttributeSlots')
    groups = [group for group in groups if any(
        prop['field'] == 'myQuality' and prop['raw_value'] == quality
        and prop['context'] == group for prop in record['properties'])]
    if not groups:
        return None
    if len(groups) != 1:
        raise ValueError('AMBIGUOUS_ATTRIBUTE_QUALITY')
    group = groups[0]
    slots = [context for context in contexts(record, links, 'ItemAttributeSlot')
             if context[:len(group)] == group]
    count = 0
    for slot in slots:
        props = {prop['field']: prop['raw_value'] for prop in record['properties'] if prop['context'] == slot}
        if props.get('myIsCoreAttribute') == 'TRUE':
            continue
        preset = props.get('myPresetAttribute')
        if preset and preset != '0' * 32:
            if categories is None or preset not in categories:
                raise ValueError('NATIVE_ATTRIBUTE_SEMANTICS_UNKNOWN: ' + preset)
            if categories[preset].startswith('Talent_Parameters_'):
                continue
        count += 1
    return count


def mod_count(record, links, quality='Orange'):
    """Count Gear sockets only; an explicit empty collection is zero, omission is unknown."""
    if not contexts(record, links, 'myItemSockets'):
        return None
    qualities = ['Grey', 'Green', 'Blue', 'Purple', 'Orange', 'Prototype']
    sockets = contexts(record, links, 'ItemSocket')
    count = 0
    for socket in sockets:
        props = [prop for prop in record['properties'] if prop['context'][:len(socket)] == socket]
        if not any(prop.get('value_type') == 'ItemModTag' and prop['raw_value'] == 'Gear' for prop in props):
            continue
        required = [prop['raw_value'] for prop in props if prop['field'] == 'myRequiredItemQuality']
        if len(required)==1 and required[0]==quality:
            count += 1
            continue
        if len(required) != 1 or required[0] not in qualities or quality not in qualities:
            raise ValueError('UNRESOLVED_SOCKET_QUALITY')
        count += qualities.index(required[0]) <= qualities.index(quality)
    return count


class StructureReader:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.cache = {}
        self.category_cache = {}

    def categories(self, path):
        raw_root = next(parent for parent in path.parents if parent.name == 'raw_files')
        if raw_root not in self.category_cache:
            categories = {}
            for branch in ('hunter', 'rogue'):
                folder = raw_root / branch / 'game system data/juice/attribute/dictionary'
                for source in sorted(folder.glob('*.mdict')):
                    categories.update(attribute_categories(self.read(source)))
            self.category_cache[raw_root] = categories
        return self.category_cache[raw_root]

    def read(self, path):
        path = path.resolve()
        if not path.is_relative_to(self.root):
            raise ValueError('NATIVE_SOURCE_OUTSIDE_ROOT')
        if path not in self.cache:
            self.cache[path] = native_definitions(path.read_bytes(), include_data=True, include_objects=True)
        return self.cache[path]

    def resolve(self, path, name, counter, seen=None):
        seen = set() if seen is None else seen
        if (path, name) in seen:
            raise ValueError('NATIVE_STRUCTURE_INHERITANCE_CYCLE')
        seen.add((path, name))
        parsed = self.read(path)
        found = [(index, row) for index, row in enumerate(parsed['resources']) if row['internal_name'] == name]
        if len(found) != 1:
            raise ValueError('NATIVE_STRUCTURE_DEFINITION_AMBIGUOUS: ' + name)
        index, record = found[0]
        links = [link for link in parsed['links'] if link['source_index'] == index]
        value = (minor_count(record, links, categories=self.categories(path))
                 if counter is minor_count else counter(record, links))
        proof = dict(file=path.relative_to(self.root).as_posix(), definition=name, line=record['location']['line_lf'])
        if value is not None:
            return value, [proof]
        base = record.get('inheritance_name')
        aliases=[link for link in links if link['field']==':alias']
        if not base and len(aliases)==1:
            base=aliases[0]['target_name']
            if not any(row['internal_name']==base and row['resource_uid']==aliases[0]['target_uid'] for row in parsed['resources']):
                raise ValueError('NATIVE_STRUCTURE_ALIAS_IDENTITY')
        if not base:
            raise ValueError('NATIVE_STRUCTURE_UNKNOWN: ' + name)
        if not any(row['internal_name'] == base for row in parsed['resources']):
            raw_root = next(parent for parent in path.parents if parent.name == 'raw_files')
            candidates = [raw_root / inc['path'] if inc['path'].startswith(('hunter/', 'rogue/')) else path.parent / inc['path']
                          for inc in parsed['includes'] if Path(inc['path']).stem == base]
            if len(candidates) != 1 or not candidates[0].is_file():
                raise ValueError('NATIVE_STRUCTURE_BASE_MISSING: ' + base)
            path = candidates[0]
        value, chain = self.resolve(path, base, counter, seen)
        return value, [proof] + chain

    def structure(self, item):
        """Use the item's explicit UID and shared config-link UID, never its display name."""
        path = self.root / item['resource_file']
        parsed = self.read(path)
        found = [(index, row) for index, row in enumerate(parsed['resources'])
                 if row['resource_type'] == 'ArmorItem' and row['resource_uid'] == item['uid']]
        if len(found) != 1 or found[0][1]['internal_name'] != item['internal_name']:
            raise ValueError('NATIVE_STRUCTURE_ITEM_IDENTITY')
        index, record = found[0]
        bindings = [link for link in parsed['links'] if link['source_index'] == index and link['field'] == 'myItemGenerationConfig']
        binding = item['generation_binding']
        if len(bindings) != 1 or bindings[0]['target_uid'] != binding['shared_config_link_uid']:
            raise ValueError('NATIVE_STRUCTURE_CONFIG_IDENTITY')
        context = binding['generation_context']
        if (context['code_version'], context['data_version']) != (1, 23):
            raise ValueError('NATIVE_STRUCTURE_UNREVIEWED_VERSION')
        config_path = self.root / binding['binding_evidence']['resource_file']
        configs = self.read(config_path)
        matches = [link for link in configs['links'] if link['field'] == 'myItemGenerationConfigLink'
                   and link['target_uid'] == bindings[0]['target_uid']]
        if len(matches) != 1:
            raise ValueError('NATIVE_STRUCTURE_CONFIG_JOIN')
        config = configs['resources'][matches[0]['source_index']]
        minor, minor_evidence = self.resolve(config_path, config['internal_name'], minor_count)
        mods, mod_evidence = self.resolve(path, record['internal_name'], mod_count)
        return dict(minor_attribute_slots=minor, mod_slot_count=mods,
                    minor_evidence=minor_evidence, mod_evidence=mod_evidence)


def project_fields(structure, base, fields):
    """Project each verified count independently into the existing exception fields."""
    result = dict(fields)
    for key, flag, field in (('minor_attribute_slots', '次属性槽例外', '次属性槽数'),
                             ('mod_slot_count', '插件槽例外', '插件槽数')):
        value = structure[key]
        if type(value) is not int or value < 0:
            raise ValueError('NATIVE_STRUCTURE_COUNT_UNKNOWN: ' + key)
        enabled = value != base[key]
        result[flag] = '是' if enabled else '否'
        if enabled:
            result[field] = str(value)
        else:
            result.pop(field, None)
    return result


def enrich(root, data):
    """Prepare named structures without changing ordinary models or raw source evidence."""
    import copy
    data = copy.deepcopy(data)
    base = json.loads((Path(root) / 'data/brand-sets/equipment-base-rules.json').read_text('utf-8'))['部位']
    reader = StructureReader(root)
    for brand in data['brands']:
        for item in brand['named_records']:
            item['structure'] = reader.structure(item)
            item['fields'] = project_fields(item['structure'], base[item['gear_slot']], item.get('fields', {}))
    return data


if __name__ == '__main__':
    import sys
    print(json.dumps(enrich(Path(__file__).resolve().parents[2], json.load(sys.stdin)), ensure_ascii=False))
