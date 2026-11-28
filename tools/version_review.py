"""Summarize stable native identities and distinguish measured and inherited evidence."""
import json
import re
import shutil
import subprocess


HEADER = re.compile(r'^(ArmorItem|WeaponItem|CraftingBlueprintItem|GearSet|GearBrand|Talent) (.+?) <\s*uid=([0-9A-Fa-f]{32})\s*>')
SUFFIXES = ('.mitem', '.mgearset', '.mgearbrand', '.mtalent')


def identities(raw):
    directories = [raw / n / 'game system data' for n in ('hunter', 'rogue')]
    if not all(d.is_dir() for d in directories):
        raise ValueError('Native discovery directories are missing')
    rows = {}
    def register(name, line):
        m = HEADER.match(line)
        if m:
            group, internal_name, uid = m.groups()
            rows.setdefault(uid.upper(), []).append([group, internal_name, name])
    if shutil.which('rg'):
        args = ['rg', '--no-config', '--json', '--color', 'never', '-e', HEADER.pattern]
        for ext in SUFFIXES:
            args += ['-g', '*' + ext]
        result = subprocess.run([*args, '--', *[d.relative_to(raw) for d in directories]],
                                cwd=raw, capture_output=True, check=True)
        for line in result.stdout.splitlines():
            event = json.loads(line)
            if event['type'] == 'match':
                body = event['data']
                register(body['path']['text'].replace('\\','/'), body['lines']['text'].strip())
    else:
        for directory in directories:
            for path in directory.rglob('*'):
                if path.suffix.lower() in SUFFIXES:
                    with path.open(encoding='utf-8-sig') as stream:
                        for line in stream:
                            register(path.relative_to(raw).as_posix(), line.rstrip())
    for items in rows.values():
        items.sort()
    return dict(sorted(rows.items()))


def changes(before, after):
    def descriptions(entries):
        return sorted([entry['type'],entry['name'],entry['source']] if isinstance(entry,dict) else entry
                      for entry in entries)
    return {'added': sorted(after.keys() - before.keys()), 'removed': sorted(before.keys() - after.keys()),
            'modified': sorted(k for k in before.keys() & after.keys() if descriptions(before[k]) != descriptions(after[k]))}


def unknowns(previous, current):
    def unique(rows):
        return {json.dumps(row, ensure_ascii=False, sort_keys=True): row for row in rows}
    a, b = unique(previous), unique(current)
    return {'introduced': [b[k] for k in sorted(b.keys()-a.keys())],
            'resolved': [a[k] for k in sorted(a.keys()-b.keys())],
            'carried': [b[k] for k in sorted(a.keys()&b.keys())]}


def talent_references(rows):
    refs = {}
    for row in rows:
        key = (row['entity'], row['source'], json.dumps(row['slot'], sort_keys=True))
        if key in refs and refs[key] != row:
            raise ValueError('Conflicting native targets for one registered talent slot: ' + str(key))
        refs[key] = row
    return {'observations': len(rows), 'distinct_slots': len(refs), 'repeated_observations': len(rows)-len(refs),
            'changed_talent_targets': sum(r['old_target'] != r['new_target'] for r in refs.values())}


def chart_evidence(root, target_build=None):
    from tools.equipment.weapon_chart_study import STUDY
    study = root / STUDY
    data = json.loads((study/'control-manifest.json').read_bytes())
    review = json.loads((study/'input-review.json').read_bytes())
    catalog = json.loads((root/'data/equipment/weapon-charts.json').read_bytes())
    if (data['resourceBuild'], data['codeBuild']) != (catalog['resourceBuild'], catalog['codeBuild']):
        raise ValueError('Chart catalog provenance disagrees with its observation manifest')
    inputs = review['new_inputs_without_trace']
    current = target_build is not None and str(target_build) == str(data['resourceBuild']) == str(data['codeBuild'])
    return dict(assessed_build=target_build, resource_build=data['resourceBuild'], camera_code_build=data['codeBuild'],
                candidate_windows=review['client_windows'], matching_windows=review['client_windows_confirmed'],
                archive_reused_traces=review['reused_traces'], reader_traces=len(catalog['traces']),
                reader_models_with_trace=sum('trace' in m for m in catalog['models'].values()),
                missing_input_count=len(inputs), missing_input_ids=sorted(inputs),
                code_status='same_build' if data['resourceBuild']==data['codeBuild'] else 'historical_code',
                current_build_confirmed_traces=len(catalog['traces']) if current else 0)



def offline_changes(root, verification):
    bundle = json.loads((verification/'publish/manifest.json').read_bytes())
    groups = {}
    for row in bundle['entries']:
        if row['operation'] != 'unchanged':
            groups.setdefault(row['kind'], []).append(dict(title=row['title'], operation=row['operation'],
                         source=row['source'], baseline_revision=row.get('baseline_revision'), conflicts=row['conflicts']))
    baseline = json.loads((root/'publishing/baseline.json').read_bytes())['entries']
    from tools.publish.bundle import baseline_operation
    previous = {row['revision_id']:row for row in baseline if row.get('revision_id') is not None}
    frontend = json.loads((verification/'frontend/resource-plan.json').read_bytes())
    for row in frontend:
        prior = previous.get(row.get('baseline_revision'))
        payload = (verification/'frontend'/row['file']).read_bytes()
        operation = baseline_operation(prior,'frontend',payload,row['sha256'])
        if operation == 'unchanged' or (prior and prior.get('candidate_sha256') == row['sha256']):
            continue
        groups.setdefault('frontend',[]).append(dict(title=row['title'],operation=operation,source=row['source'],
                      baseline_revision=row.get('baseline_revision'),conflicts=[]))
    return dict(groups=groups, registry_items=len(bundle['entries']),frontend_items=len(frontend),
                address_moves=bundle['address_moves'],delete_candidates=bundle['delete_candidates'])
