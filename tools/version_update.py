"""Local version-update entry points. All generated candidates and offline bundles stay local."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import quote

from tools import game_resources, version_review
from tools.game_resources.timing import Timings
from tools.hunter_cli.core import write_json

ROOT = Path(__file__).resolve().parents[1]


def resources(root, session, output, apply=False):
    session = game_resources.no_links(session).resolve()
    receipt = json.loads((session/'export.json').read_bytes())
    source = session/'export'
    if (receipt.get('status') != 'completed' or Path(receipt['source_directory']) != source
            or Path(receipt['source_metadata']) != session/'source.json'):
        raise ValueError('A committed Hunter export is required')
    metadata = json.loads((session/'source.json').read_bytes())
    if (metadata['source_container_sha256'] != receipt['source']['index']['sha256']
            or metadata['game_build'] != receipt['source']['game_build'] or metadata['coverage'] != receipt['options']):
        raise ValueError('Export metadata and receipt disagree')
    from tools.hunter_cli.bulk import KINDS, covers_daily, known_image_collisions, recorded_passes
    options = receipt['options']
    queries = options.get('queries', [options.get('query', '')])
    if set(options['types']) != set(KINDS):
        raise ValueError('Daily version updates require coverage of all three resource types')
    def check_coverage(selection, required):
        passes = recorded_passes(receipt)
        if ((options['profile'] != 'daily' and queries != ['']) or
                any(row['status'] != 'committed' for row in passes) or
                not covers_daily(selection, required, KINDS, passes)):
            raise ValueError('Export does not cover current daily discovery and registrations')
        # Use the index fingerprint for older receipts as well as newly annotated exports.
        registered = {name.casefold() for name in required}
        roots = tuple(p.casefold() + '/' for p in selection['discovery_directories'])
        for path in known_image_collisions(metadata['source_container_sha256']):
            if path.casefold() in registered or path.casefold().startswith(roots):
                raise ValueError('DAILY_IMAGE_NAME_AMBIGUOUS: ' + path)
    validation = game_resources.PlanValidation()
    result = game_resources.make_plan(root, source, metadata, output/'resource-plan', profile='daily',
                                      validation=validation, coverage_check=check_coverage)
    changes = result['changes']
    changed = any(changes[k] for k in ('added','modified','deleted'))
    plan = json.loads((output/'resource-plan/plan.json').read_bytes())
    provenance_changed = plan['base_manifest_sha256'] != plan['artifacts']['next.jsonl']
    needs_commit = changed or provenance_changed
    outcome = {'game_build':metadata['game_build'], 'plan':result, 'provenance_changed':provenance_changed,
               'status':'review_required' if needs_commit else 'unchanged'}
    if apply and needs_commit:
        outcome['apply'] = game_resources.apply_plan(root, output/'resource-plan', validation=validation)
        outcome['status'] = 'applied'
    write_json(output/'resources.json', outcome)
    return outcome


def call(root, output, name, command):
    from tools.verify import run_step
    env = dict(os.environ, PYTHONUTF8='1', PYTHONDONTWRITEBYTECODE='1', TD2_PYTHON=sys.executable)
    row = run_step(root, output, env, name, command)
    write_json(output/(name+'.metrics.json'), row)
    if row['exit_code'] or row['skipped']:
        raise RuntimeError(name + ' failed. See ' + str(output/row['log']))
    return row


def activate_index(root, output, directory):
    from tools.asset_import.text_library import TextLibrary
    if not directory:
        raise ValueError('A reviewed --index-output under evidence/asset-import/native is required')
    path = game_resources.no_links(root/directory).resolve()
    base = root/'evidence/asset-import/native'
    if path == base or not path.is_relative_to(base):
        raise ValueError('An active index must be in a persistent native evidence directory')
    registration = game_resources.no_links(root/'data/asset-import/text-sources.json')
    candidate = game_resources.no_links(path/'text-sources-candidate.json')
    report = json.loads((path/'report.json').read_bytes())
    ledger = json.loads((path/'provenance.json').read_bytes())
    store = game_resources.store_at(root)
    with game_resources.locked(store):
        if ((store/'.transaction').exists() or (store/'.initializing.json').exists()
                or report['status'] != 'REVIEW_CANDIDATE' or report['issues']
                or game_resources.digest(store/'source.json') != ledger['source']['sha256']
                or game_resources.digest(store/'manifest.jsonl') != report['source_manifest_sha256']
                or game_resources.digest(candidate) != report.get('candidate_sha256')):
            raise ValueError('Candidate or resource state changed. Rebuild the native index.')
        active = json.loads(candidate.read_bytes())
        for section in ('native_definitions','native_references'):
            spec = active[section]
            file = game_resources.no_links(root/game_resources.relative(spec['file'])).resolve()
            if file.parent != path or game_resources.digest(file) != spec['sha256']:
                raise ValueError('Native candidate artifact changed: '+section)
        before = game_resources.digest(registration)
        if before == report['candidate_sha256']:
            result = dict(status='already_active',active_sha256=before,candidate=candidate.relative_to(root).as_posix())
            write_json(output/'index-activation.json',result)
            return result
        if before != report.get('registration_sha256'):
            raise ValueError('Active text registration changed since candidate generation')
        issues = TextLibrary(root,index=candidate.relative_to(root).as_posix()).query(limit=1)['issues']
        if issues:
            raise ValueError('Candidate native lookup failed: '+str(issues))
        (output/'previous-text-sources.json').write_bytes(registration.read_bytes())
        # Use the candidate bytes so the on-disk registration retains its frozen digest.
        import tempfile
        with tempfile.NamedTemporaryFile(dir=registration.parent,delete=False) as stream:
            temporary = Path(stream.name)
            try:
                stream.write(candidate.read_bytes())
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException:
                stream.close()
                temporary.unlink(missing_ok=True)
                raise
        try:
            if game_resources.digest(registration) != before:
                raise ValueError('Active text registration changed during validation')
            os.replace(temporary,registration)
        finally:
            temporary.unlink(missing_ok=True)
        result=dict(status='activated',previous_sha256=before,active_sha256=report['candidate_sha256'],
                    candidate=candidate.relative_to(root).as_posix())
        write_json(output/'index-activation.json',result)
        return result


def review(root, output, previous_ids=None, previous_review=None, resource_build=None, binding_review=None, discovery_raw=None, index_output=None):
    from tools.asset_import.native_index import build
    from tools.equipment.native import Native
    from tools.equipment.native_tree import item_generation_version
    raw = root/'resources/game/current/raw_files'
    node = shutil.which('node')
    python = [sys.executable,'-B','-X','utf8']
    with Timings('version-review') as timing:
        version = timing.call('generation_version',item_generation_version,Native(raw))
        ids = timing.call('discover_identities',version_review.identities,discovery_raw or raw)
        write_json(output/'identities.json',ids)
        index_directory = game_resources.no_links(root/index_output).resolve() if index_output else output/'native-index'
        native_index = timing.call('native_index',build,root,index_directory.relative_to(root).as_posix())
        if native_index['issues']:
            raise ValueError('Native index requires review: '+str(index_directory/'report.json'))
        timing.call('projection',call,root,output,'projection',python+['-m','tools.equipment.native',
                    '--resources',str(raw),'--output',str(output/'projection.json')])
        timing.call('import_preview',call,root,output,'import-preview',[node,'tools/equipment/import.cjs',
                    str(output/'projection.json'),str(output/'equipment-import')])
        projection = json.loads((output/'equipment-import/result.json').read_bytes())
        registry = json.loads((root/'publishing/registry.json').read_bytes())['entries']
        pages = {r.get('related_entity'):r['title'] for r in registry if r['kind']=='pages'}
        rows = [{'id':r['id'],'title':pages.get(r['id'],r['source']),'fields':r['fields']}
                for r in projection['pages'] if r['fields'] or r.get('initialized')]
        prior = json.loads(previous_review.read_bytes()) if previous_review else None
        unavailable = projection['unavailable']
        old_unknowns = None if prior is None else prior.get('unavailable_after',prior.get('unavailable'))
        migration = json.loads(binding_review.read_bytes()) if binding_review else None
        if migration and 'binding_migration' in migration:
            migration = migration['binding_migration']
        if migration and migration['new_version'] != version:
            raise ValueError('Talent observation version differs from the projected native version')
        if not migration and prior and str(prior.get('current_steam_build')) == str(resource_build):
            candidate = prior.get('binding_migration', {})
            if candidate.get('new_version') == version:
                migration = candidate
        result = dict(version=version, index_candidate=str(index_directory), resource_build=resource_build, identities=len(ids), discovery_source=str(discovery_raw or raw),
                      talent_observations=version_review.talent_references(migration['talent_references']) if migration else None,
                      identity_delta=version_review.changes(json.loads(previous_ids.read_bytes()),ids) if previous_ids else None,
                      indexed_definitions=native_index['parsed_definition_files'], changed_equipment_pages=rows,
                      changed_catalog_fields=projection['catalogs'], unavailable=unavailable,
                      unavailable_comparison=version_review.unknowns(old_unknowns,unavailable) if old_unknowns is not None else None,
                      chart_evidence=version_review.chart_evidence(root,resource_build))
    result['timings'] = timing.result()
    write_json(output/'review.json',result)
    lines=['# 本地版本资料审查','',f'物品生成版本 {version}。发现 {len(ids):,} 个稳定身份，解析 {result["indexed_definitions"]:,} 个登记定义。','',
           '| 待审资料页 | 变化字段 |','| --- | --- |']
    for row in rows:
        url='https://td2.huijiwiki.com/wiki/'+quote(row['title'].replace(' ','_'),safe=':/_-')
        lines.append('| ['+row['title']+']('+url+') | '+'、'.join(dict.fromkeys(f['field'] if isinstance(f, dict) else str(f) for f in row['fields']))+' |')
    if not rows:
        lines.append('| 本次投影无页面字段变化 | 0 |')
    delta=result['identity_delta']
    if delta:
        lines += ['', '### 原生身份', '', f'新增 {len(delta["added"])}，来源或名称改变 {len(delta["modified"])}，本次输入未出现 {len(delta["removed"])}。']
        if delta['added']:
            lines += ['', '| 新 UID | 类型与原生名称 |', '| --- | --- |']
            for uid in delta['added']:
                group, name, _ = ids[uid][0]
                lines.append(f'| {uid} | {group} {name.replace("|","｜")} |')
    catalog = result['changed_catalog_fields']
    if catalog:
        from collections import Counter
        lines += ['', '### 目录变化', '', '| 资料源 | 字段数 |', '| --- | ---: |']
        lines += [f'| {name} | {count} |' for name,count in sorted(Counter(c['file'] for c in catalog).items())]
    if result['unavailable_comparison'] is not None:
        u = result['unavailable_comparison']
        lines += ['',f'按内容去重后，新增未知 {len(u["introduced"])} 项，延续 {len(u["carried"])} 项，已解决 {len(u["resolved"])} 项。']
    lines+=['',f'未确认投影字段 {len(unavailable)} 项。完整字段、目录变化、原生身份比较和后坐轨迹的版本见 [review.json](review.json)。']
    (output/'review.md').write_text('\n'.join(lines)+'\n',encoding='utf8',newline='\n')
    return result


def prepare(root, output, generate=False, full=False):
    python = [sys.executable,'-B','-X','utf8']
    node = shutil.which('node')
    if generate:
        # The asset mapping rendered by Catalog is an input to the exotic templates.
        jobs = [
            ('brands',python+['-m','tools.brand_sets','generate']),
            ('gear-sets',[node,'tools/gear_sets/generate.cjs','templates']),
            ('catalog',[node,'tools/equipment/catalog.cjs']),
            ('exotics',[node,'tools/exotic_gear/generate.cjs','generate']),
            ('weapons',python+['-m','tools.equipment.weapons','generate']),
            ('season',python+['-m','tools.homepage_season','--write']),
            ('events',python+['-m','tools.homepage_events','--write']),
        ]
        for name, command in jobs:
            call(root,output,name,command)
    check = call(root,output,'verification',python+['-m','tools.verify','--resources','--output',
                str((output/'verification').relative_to(root))]+([] if full else ['--preflight']))

    changes = version_review.offline_changes(root,output/'verification')
    write_json(output/'page-changes.json',changes)
    lines = ['# 本地候选与发布基准', '',
             f'登记对象 {changes["registry_items"]} 项，前端对象 {changes["frontend_items"]} 项。对照本地保存回执，线上状态须在发布时复核。']
    if not changes['groups']:
        lines += ['', '本地候选与已记录的发布基准一致。']
    for group,items in changes['groups'].items():
        lines += ['', f'## {group}', '', '| 页面或文件 | 差异 | 基准修订 |', '| --- | --- | ---: |']
        for item in sorted(items,key=lambda i:i['title']):
            title=item['title']
            address='https://td2.huijiwiki.com/wiki/'+quote(title.replace(' ','_'),safe=':/_-')
            lines.append(f'| [{title}]({address}) | {item["operation"]} | {item["baseline_revision"] or "未知"} |')
    (output/'page-changes.md').write_text('\n'.join(lines)+'\n','utf8',newline='\n')
    return check


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=('run','resources','review','prepare','activate-index'))
    parser.add_argument('--root',type=Path,default=ROOT)
    parser.add_argument('--output',type=Path,required=True,help='Fresh directory under the selected project’s dist')
    parser.add_argument('--export-session',type=Path)
    parser.add_argument('--apply-resources',action='store_true')
    parser.add_argument('--previous-identities',type=Path)
    parser.add_argument('--previous-review',type=Path)
    parser.add_argument('--binding-review',type=Path,help='Version-matched native binding migration observations')
    parser.add_argument('--index-output',type=Path,help='Persistent candidate directory under evidence/asset-import/native')
    parser.add_argument('--discovery-raw',type=Path,help='Fresh raw_files tree for independent identity discovery')
    parser.add_argument('--resource-build',help='Steam resource build for a standalone review')
    parser.add_argument('--generate',action='store_true',help='Regenerate registered outputs from already reviewed source data')
    parser.add_argument('--full',action='store_true',help='Include the full regression suite in offline preparation')
    args=parser.parse_args(argv)
    if args.stage in ('run','review','prepare') and not shutil.which('node'):
        parser.error('Node.js is required for data projection and offline preparation')
    root=args.root.resolve()
    output=game_resources.no_links(root/args.output).resolve()
    if not output.is_relative_to(root/'dist') or output==root/'dist':
        parser.error('Output must be a fresh dist subdirectory')
    if args.stage in ('run','resources') and not args.export_session:
        parser.error('--export-session is required for resource import')
    output.mkdir(parents=True,exist_ok=False)
    started=time.monotonic()
    state={'status':'running','stages':{},'publication_performed':False}
    def execute(name, func, *values):
        start=time.monotonic()
        state['current_stage']=name
        write_json(output/'run.json',state)
        try:
            return func(*values)
        finally:
            state['stages'][name]={'seconds':time.monotonic()-start}
    try:
        resource_build=args.resource_build
        discovery_raw=args.discovery_raw
        if args.stage in ('run','resources'):
            outcome=execute('resources',resources,root,args.export_session,output,args.apply_resources)
            resource_build=outcome['game_build']
            discovery_raw=args.export_session.resolve()/'export/raw_files'
            if args.stage=='run' and outcome['status']=='review_required':
                state['status']='resource_plan_ready'
                return 2
        if args.stage=='activate-index':
            execute('activate_index',activate_index,root,output,args.index_output)
        if args.stage in ('run','review'):
            candidate=execute('review',review,root,output,args.previous_identities,args.previous_review,
                              resource_build,args.binding_review,discovery_raw,args.index_output)
            state['review_items']=dict(pages=len(candidate['changed_equipment_pages']),
                  catalog_fields=len(candidate['changed_catalog_fields']),unavailable=len(candidate['unavailable']),
                  identities={k:len(v) for k,v in (candidate['identity_delta'] or {}).items()})

        if args.stage in ('run','prepare'):
            execute('prepare',prepare,root,output,args.generate,args.full)
        state['status']='passed'
        return 0
    except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as error:
        state.update(status='failed',error=str(error))
        print(str(error),file=sys.stderr)
        return 1
    finally:
        state['seconds']=time.monotonic()-started
        write_json(output/'run.json',state)


if __name__=='__main__':
    raise SystemExit(main())

