"""Prepare formal Reader / JS Editor resources for MANUAL review."""
import argparse
import hashlib
import subprocess
from pathlib import Path

from tools.publish.bundle import json_bytes, read_json, require, safe_path, load_state, title_key, wiki_text
from tools.publish.asset_dependencies import AssetDependencies
from .dependencies import dependencies


def reader_css(root, config=None):
    """Read the shared stylesheet without page-specific projections."""
    return (root / 'ui/brand-sets/brand-sets.css').read_text(encoding='utf8')


def assemble(root, output, resources_only=False):
    """Assemble registered formal sources and an exact maintained Editor build."""
    config = read_json(root / 'publishing/reader-editor-production.json')
    registry = read_json(root / 'publishing/registry.json')
    baseline = load_state(root / 'publishing/baseline.json', registry['target'], root=root)
    prefixes = {p.casefold(): int(ns) for ns, names in registry['namespace_prefixes'].items() for p in names}
    prefixes.update({'gadget': 2300, '零件': 2300, 'gadget definition': 2302, '零件定义': 2302})
    migration = config['resource_naming']
    editor = output / 'editor'
    manifest = read_json(editor / 'manifest.json')
    bindings = manifest['resourceBindings']
    require(bindings == {
        'runtime': {'file': 'TD2EditorRuntime.js', 'title': migration['runtime_title']},
        'entry': {'file': 'TD2EditorEntry.js', 'title': migration['entry_title']},
    }, 'Editor build must use formal resource bindings')
    destination = output / 'resources'
    require(not destination.exists(), 'Use a fresh resources directory')
    require(not (output / 'resource-plan.json').exists(), 'Use a fresh resource plan')
    builder = root / 'ui/editor/production/build.cjs'
    require(builder.is_file(), 'Maintained Editor builder is required for new candidate assembly')
    verified = subprocess.run(['node', str(builder), '--verify-inputs', str(editor.resolve()), '--root', str(root.resolve())],
                              capture_output=True, text=True, encoding='utf8')
    require(verified.returncode == 0, 'Editor input identity/version verification failed; rebuild a fresh candidate')
    rows, payloads = [], {}

    def add(title, filename, content, source, deps=(), status='LOCAL_CANDIDATE'):
        require(title not in {r['title'] for r in rows}, 'Duplicate formal target')
        require(isinstance(filename, str) and filename and Path(filename).name == filename
                and not any(c in filename for c in '\\/:') and not filename.startswith('.'), 'Invalid formal artifact path')
        require(filename.casefold() not in {'manifest.json', *(name.casefold() for name in payloads)}, 'Duplicate formal artifact path')
        prefix = title.split(':', 1)[0].casefold() if ':' in title else ''
        require(prefix in prefixes, 'Unknown formal namespace')
        previous = baseline.get(title_key(title, prefixes[prefix]))
        digest = hashlib.sha256(content).hexdigest()
        operation = 'create' if previous is None else 'unchanged' if digest == previous['content_hash'] else 'update'
        payloads[filename] = content
        rows.append(dict(title=title, file='resources/' + filename, source=source,
                         operation=operation, dependencies=list(deps), status=status,
                         baseline_revision=previous['revision_id'] if previous else None,
                         requires_fresh_preflight=True, sha256=digest))

    for row in migration['reader']:
        add(row['title'], row['file'], safe_path(root, row['source']).read_bytes(), row['source'])
    for role in ('runtime', 'entry'):
        binding = bindings[role]
        content = (editor / binding['file']).read_bytes()
        require(hashlib.sha256(content).hexdigest() == next(f['sha256'] for f in manifest['files'] if f['name'] == binding['file']),
                'Editor build hash mismatch')
        if role == 'entry':
            require(b'REEDIT_RUNTIME_REVISION' in content, 'Entry must remain UNBOUND before live readback')
        add(binding['title'], binding['file'], content, config['editor_build'],
            [bindings['runtime']['title']] if role == 'entry' else (), 'UNBOUND' if role == 'entry' else 'LOCAL_CANDIDATE')
    for gadget in migration['gadgets']:
        definition = gadget['definition']
        require(set(definition) == {'settings', 'module'}, 'Gadget definition requires settings/module')
        deps = ['Gadget:' + name for field in ('scripts', 'styles') for name in definition['module'][field]]
        add('Gadget definition:' + gadget['name'], gadget['name'] + '.json', json_bytes(definition),
            'publishing/reader-editor-production.json', deps)
        add('MediaWiki:Gadget-' + gadget['name'], 'Gadget-' + gadget['name'] + '.wiki',
            (gadget['label'] + '\n').encode('utf8'), 'publishing/reader-editor-production.json')
    if not resources_only:
        registered = {r['id']: r for r in registry['entries']}
        texts = {}

        def source_text(row):
            if row['id'] not in texts:
                source = row['source']
                texts[row['id']] = wiki_text(safe_path(root, source).read_bytes(), source)
            return texts[row['id']]

        assets = AssetDependencies(registry['entries'], source_text)
        for entry_id in config['content_ids']:
            row = registered[entry_id]
            text = source_text(row)
            deps = [('Module:' if k == 'module' else '模板:') + n for k, n in sorted(dependencies(text))]
            deps.extend(registered[asset_id]['title'] for asset_id in assets.resolve(row))
            add(row['title'], entry_id + '.wiki', text.encode('utf8'), row['source'], deps)
    destination.mkdir()
    for filename, content in payloads.items():
        (destination / filename).write_bytes(content)
    (destination / 'manifest.json').write_bytes(json_bytes(dict(
        version=manifest['version'], releaseMode=manifest['releaseMode'], production_approved=False,
        resourceBindings=bindings, files=[dict(name=r['file'].split('/')[-1], sha256=r['sha256']) for r in rows]
    )))
    (output / 'resource-plan.json').write_bytes(json_bytes(rows))
    return rows


def assemble_resources(root, output):
    """Prepare only formal resources and the existing Gadget registrations."""
    return assemble(root, output, resources_only=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--resources-only', action='store_true')
    args = parser.parse_args()
    plan = assemble(Path.cwd(), args.output, args.resources_only)
    print(f'{len(plan)} formal candidates; entry UNBOUND; MANUAL; no publication')
