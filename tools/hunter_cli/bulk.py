"""Run the installed Hunter's bulk exporter and hand off a committed export tree."""
import argparse
from contextlib import ExitStack
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time

from .core import HUNTER_SHA256, ROOT, input_fingerprint, now, read_json, sha, write_json
from tools.game_resources import locked, no_links, relative
from tools.game_resources.timing import Timings
from .live import SessionPool

KINDS = ('images', 'materials', 'raw_files')
NUMBER = r'([0-9Oo][0-9Oo., ]*)'
SEARCH_TEXT = re.compile(r'[A-Za-z0-9_!/, .\[\]-]{1,34}')


def number(s):
    return int(re.sub(r'[., ]', '', s).upper().replace('O', '0'))


def visible_count(text):
    subset = re.search(r'Showing\s+' + NUMBER + r'\s+assets?\s+out of\s+' + NUMBER + r'\s+loaded', text, re.I)
    if subset:
        return number(subset[1]), number(subset[2])
    total = re.search(NUMBER + r'\s+assets?\s+loaded', text, re.I)
    if total:
        return number(total[1]), number(total[1])
    return None


def source(index, executable, build, previous=None):
    index = no_links(index).resolve(strict=True)
    if index.suffix.lower() != '.sdftoc' or (previous is None and sha(executable) != HUNTER_SHA256):
        raise ValueError('SUPPORTED_HUNTER_AND_SDF_INDEX_REQUIRED')
    meta = hashlib.sha256()
    with os.scandir(index.parent) as entries:
        files = sorted((e for e in entries if e.name.lower().endswith(('.sdftoc', '.sdfdata'))),
                       key=lambda e: e.name.casefold())
    for entry in files:
        st = entry.stat(follow_symlinks=False)
        meta.update(json.dumps([entry.name, st.st_size, st.st_mtime_ns], separators=(',', ':')).encode() + b'\n')
    acf = next((p / 'appmanifest_2221490.acf' for p in index.parents if (p / 'appmanifest_2221490.acf').is_file()), None)
    manifest = None
    if acf:
        text = acf.read_text('utf8')
        match = re.search(r'"buildid"\s*"(\d+)"', text, re.I)
        installed = match[1] if match else None
        if build and installed and build != installed:
            raise ValueError('INSTALLED_BUILD_MISMATCH')
        build = installed or build
        match = re.search(r'"2221491"\s*\{\s*"manifest"\s*"(\d+)"', text)
        manifest = match[1] if match else None
    if previous is None:
        identity = input_fingerprint(index)
    else:
        st = index.stat()
        identity = dict(path=str(index),sha256=previous['index']['sha256'],size=st.st_size,mtime_ns=st.st_mtime_ns)
    return dict(index=identity, game_build=build, depot_manifest=manifest,
                container_count=len(files), container_directory_metadata_sha256=meta.hexdigest(),
                hunter_sha256=HUNTER_SHA256, hunter_version='2.2.9')


def known_image_collisions(index_sha256, folder=None):
    """Number of independently exported Hunter rows observed writing each path."""
    conflicts = read_json(ROOT / 'data/asset-import/hunter-image-collisions.json').get(index_sha256, {})
    if folder is None:
        return conflicts
    return {path: count for path, count in conflicts.items() if (folder/path).is_file()}


def inventory(folder):
    groups = {}
    structure = hashlib.sha256()

    def scan(directory, prefix='', group=None):
        with os.scandir(directory) as walker:
            entries = sorted(walker, key=lambda e: e.name.casefold())
        for entry in entries:
            name = prefix + entry.name
            info = entry.stat(follow_symlinks=False)
            if getattr(info, 'st_file_attributes', 0) & 0x400 or entry.is_symlink():
                raise ValueError('EXPORT_LINK: ' + name)
            category = group or entry.name
            if entry.is_dir(follow_symlinks=False):
                scan(entry.path, name + '/', category)
            else:
                row = groups.setdefault(category, {'files': 0, 'bytes': 0})
                row['files'] += 1
                row['bytes'] += info.st_size
                structure.update(name.encode('utf8') + b'\\0' + str(info.st_size).encode() + b'/' +
                                 str(info.st_mtime_ns).encode() + b'\\n')
    scan(folder)
    return dict(files=sum(v['files'] for v in groups.values()), bytes=sum(v['bytes'] for v in groups.values()),
                outputs=groups, path_size_mtime_sha256=structure.hexdigest())


def merge_outputs(origin, target, session, counts=None):
    """Rename disjoint trees on this volume. A replay can continue a partial merge."""
    origin = no_links(origin).resolve()
    target = no_links(target).resolve()
    if (not origin.is_relative_to(session) or not target.is_relative_to(session)
            or origin.is_relative_to(target) or target.is_relative_to(origin)):
        raise ValueError('INVALID_EXPORT_MERGE_PATHS')

    def merge(src, dst):
        if src.is_symlink() or src.is_junction() or dst.is_symlink() or dst.is_junction():
            raise ValueError('EXPORT_LINK: ' + str(src))
        if not dst.exists():
            src.rename(dst)
            if counts is not None:
                counts['renames'] += 1
        elif src.is_dir() and dst.is_dir():
            for child in src.iterdir():
                merge(child, dst / child.name)
            src.rmdir()
        elif src.is_file() and dst.is_file() and (size := src.stat().st_size) == dst.stat().st_size and sha(src) == sha(dst):
            src.unlink()
            if counts is not None:
                counts['duplicate_files'] += 1
                counts['duplicate_bytes'] += size
        else:
            raise ValueError('CONFLICTING_HUNTER_OUTPUT: ' + str(dst))
    merge(origin, target)


def commit_pass(row, session):
    attempt = row['attempts'][-1]['directory']
    output = relative(row['output'])
    if not re.fullmatch(r'attempt-\d+', attempt) or output not in (attempt+'/outputs', attempt+'/app/exported_files'):
        raise ValueError('INVALID_EXPORT_COMMIT_PATH')
    origin, target = session/output, session/'export'
    marker = '.hunter-commit-' + attempt
    if origin.exists():
        counts = dict(renames=0, duplicate_files=0, duplicate_bytes=0)
        merge_outputs(origin, target, session, counts)
        row['merge'] = counts
    if not (target/marker).is_file():
        raise ValueError('EXPORT_COMMIT_MARKER_MISSING')
    return target/marker


def daily_names(selection, required):
    for path in set(required) | {p + '/' for p in selection['discovery_directories']}:
        kind, name = path.casefold().split('/', 1)
        if kind == 'images':
            name = name.removesuffix('.png')
        if kind == 'raw_files':
            name = name.removesuffix('.decompiled')
        yield kind, name


def discovery_queries(selection, required, kinds):
    names = [name for kind, name in daily_names(selection, required) if kind in kinds]
    if not names:
        return []
    terms = [t for t in selection['export_terms'] if any(t in n for n in names)]
    for term in terms.copy():
        others = [t for t in terms if t != term]
        if all(any(t in n for t in others) for n in names if term in n):
            terms.remove(term)
    if any(not any(t in n for t in terms) for n in names):
        return ['']
    return terms or ['']


def recorded_passes(state):
    # Early single-filter receipts recorded the filter only in options.
    options = state['options']
    queries = options.get('queries', [options.get('query', '')])
    for row in state['passes']:
        if 'query' not in row:
            if len(queries) != 1:
                raise ValueError('MISSING_EXPORT_PASS_QUERY')
            row['query'] = queries[0]
    return state['passes']


def covers_daily(selection, required, kinds, passes):
    """Check each directory prefix and registered input against the actual type/filter pair."""
    needs = list(daily_names(selection, required))
    for kind in kinds:
        filters = []
        for row in passes:
            if kind in row['types']:
                query = row['query']
                if row.get('status') == 'committed' and row.get('attempts'):
                    query = row['attempts'][-1].get('applied_query', query)
                filters.append(query.casefold())
        if '' in filters:
            continue
        for resource_type, name in needs:
            if resource_type != kind:
                continue
            if not any(q in name for q in filters):
                return False
    return True


def run(args):
    args.session = no_links(args.session).resolve()
    args.index = no_links(args.index).resolve()
    args.hunter = no_links(args.hunter).resolve()
    if args.profile == 'daily' and args.cpu_limit is None:
        args.cpu_limit = 8
    if args.poll is None:
        args.poll = 1 if args.profile == 'daily' else 3
    if not any(args.session.is_relative_to(ROOT / area) and args.session != ROOT/area
               for area in ('incoming/game-update', 'dist')):
        raise ValueError('USE_A_NEW_SESSION_UNDER_INCOMING_OR_DIST')
    if args.timeout <= 0 or args.poll < .2 or args.retries < 0 or (args.cpu_limit is not None and args.cpu_limit < 1):
        raise ValueError('INVALID_TIMEOUT_OR_RETRIES')
    if args.query and (args.profile == 'daily' or not SEARCH_TEXT.fullmatch(args.query)):
        raise ValueError('EXPLICIT_QUERY_REQUIRES_FULL_PROFILE_AND_SUPPORTED_TEXT')
    if not args.resume:
        args.session.mkdir(parents=True, exist_ok=False)
    elif not (args.session / 'export.json').is_file():
        raise ValueError('NO_RESUMABLE_EXPORT')
    session = args.session
    status = session / 'export.json'
    from tools.process_metrics import snapshot, difference
    with locked(session):
        started = time.monotonic()
        metrics = snapshot()
        invocation = dict(started=now(),resume=args.resume,status='failed')
        try:
            result = run_locked(args,session,status)
            invocation['status'] = 'completed'
            return result
        except Exception as error:
            invocation['error'] = str(error)
            raise
        except KeyboardInterrupt:
            invocation['status'] = 'interrupted'
            raise
        finally:
            invocation.update(finished=now(),seconds=round(time.monotonic()-started,3),
                              process=difference(metrics,snapshot()))
            with (session/'invocations.jsonl').open('a',encoding='utf8') as stream:
                stream.write(json.dumps(invocation)+'\n')


def run_locked(args,session,status):
    from .display import compile_reader
    spec = source(args.index, args.hunter, args.build)
    kinds = [k for k in KINDS if k in args.types]
    queries = [args.query or '']
    if args.profile == 'daily':
        from tools.game_resources.selection import load_selection, dependencies
        selection = load_selection(ROOT, 'daily')
        required = set()
        dependencies(ROOT, selection, required_output=required)
        queries = discovery_queries(selection, required, kinds)
        if not queries:
            raise ValueError('NO_DAILY_DISCOVERY_OR_REGISTRATION_FOR_SELECTED_TYPES')
    options = dict(types=kinds, queries=queries, profile=args.profile, separate_types=args.separate_types)
    if args.resume:
        state = read_json(status)
        recorded_passes(state)
        if 'query' in state['options']:
            state['options']['queries'] = [state['options'].pop('query')]
        saved = state['options']
        if args.profile == saved.get('profile') == 'daily':
            if not covers_daily(selection,required,kinds,state['passes']):
                raise ValueError('RESUME_DAILY_COVERAGE_CHANGED')
            options['queries'] = saved['queries']
        if (state['source'],saved) != (spec,options):
            raise ValueError('RESUME_INPUT_OR_OPTIONS_CHANGED')
        if state['status']=='completed':
            if inventory(session/'export') != state['statistics']:
                raise ValueError('COMMITTED_EXPORT_INVENTORY_CHANGED')
            if conflicts := known_image_collisions(spec['index']['sha256'], session/'export'):
                state['known_image_collisions'] = conflicts
            return state
        (session/'cancel').unlink(missing_ok=True)
    else:
        if args.profile == 'daily' and args.separate_types:
            passes = [([kind],q) for kind in kinds for q in discovery_queries(selection,required,[kind])]
        else:
            batches = [[k] for k in kinds] if args.separate_types else [kinds]
            passes = [(batch,q) for batch in batches for q in queries]
        state = dict(schema_version=1, source=spec, options=options, started=now(), status='running',
                     passes=[dict(types=subset,query=q,status='pending',attempts=[]) for subset,q in passes])
    write_json(status,state)
    program = compile_reader(session)
    pool = SessionPool(args,program)
    with ExitStack() as cleanup, Timings('hunter-export') as timing:
        cleanup.push(pool.close)
        for row in state['passes']:
            if row['status']=='committed':
                attempt_dir = row['attempts'][-1]['directory']
                if not re.fullmatch(r'attempt-\d+',attempt_dir):
                    raise ValueError('INVALID_EXPORT_COMMIT_PATH')
                marker = session/'export'/('.hunter-commit-'+attempt_dir)
                marker.unlink(missing_ok=True)
                continue
            if row['status']!='exported':
                for retry in range(args.retries+1):
                    job = session / ('attempt-' + str(time.time_ns()))
                    job.mkdir()
                    attempt = dict(directory=job.name, types=row['types'], started=now())
                    row['attempts'].append(attempt)
                    row['status']='running'
                    state['status']='running'
                    write_json(status,state)
                    try:
                        output_name = timing.call('hunter_pass',pool.export,job,attempt,row['query'])
                        if timing.call('check_source_metadata',source,args.index,args.hunter,args.build,spec)!=spec:
                            raise ValueError('HUNTER_INPUT_CHANGED_DURING_EXPORT')
                        (session/output_name/('.hunter-commit-'+job.name)).touch(exist_ok=False)
                        row.update(status='exported', output=output_name)
                        attempt.update(status='succeeded',finished=now())
                        write_json(status,state)
                        break
                    except (Exception, KeyboardInterrupt) as error:
                        observation = pool.failure_observation()
                        if observation:
                            attempt['failure_process'] = observation
                        pool.close(*sys.exc_info())
                        attempt.update(status='interrupted' if isinstance(error,KeyboardInterrupt) else 'failed',
                                       error=str(error) or type(error).__name__,finished=now())
                        row['status']=attempt['status']
                        state['status']=row['status']
                        write_json(status,state)
                        if isinstance(error,(KeyboardInterrupt,ValueError)) or retry==args.retries:
                            raise
            marker = timing.call('commit_output',commit_pass,row,session)
            row['status']='committed'
            write_json(status,state)
            marker.unlink()
        if timing.call('verify_complete_source',source,args.index,args.hunter,args.build)!=spec:
            raise ValueError('HUNTER_INPUT_CHANGED_DURING_EXPORT')
        stats=timing.call('count_exported_files',inventory,session/'export')
        timing.stages['count_exported_files'].update(files=stats['files'],bytes=stats['bytes'])
        if not stats['files']:
            raise RuntimeError('HUNTER_PRODUCED_NO_FILES')
    source_id='hunter-'+session.name
    metadata=dict(source_id=source_id,origin='HUNTER_CLI',game_build=spec['game_build'],
                  source_container_sha256=spec['index']['sha256'],coverage=options,
                  export_receipt=str(status),depot_manifest=spec['depot_manifest'])
    collisions = known_image_collisions(spec['index']['sha256'], session/'export')
    if collisions:
        state['known_image_collisions'] = metadata['known_image_collisions'] = collisions
    write_json(session/'source.json',metadata)
    hosts = {p.parent.name:read_json(p) for p in sorted(session.glob('host-*/child-process.json'))}
    state.update(status='completed',finished=now(),statistics=stats,timings=timing.result(),hunter_processes=hosts,
                 source_directory=str(session/'export'),source_metadata=str(session/'source.json'))
    write_json(status,state)
    return state


def arguments(sub):
    p=sub.add_parser('bulk',help='Export all selected Hunter asset types in one local session')
    p.add_argument('--index',type=Path,required=True)
    p.add_argument('--session',type=Path,required=True)
    p.add_argument('--hunter',type=Path,default=ROOT/'tools/hunter.exe')
    p.add_argument('--types',nargs='+',choices=KINDS,default=KINDS)
    p.add_argument('--profile',choices=('full','daily'),default='full')
    p.add_argument('--query',help='Optional short native Hunter name filter')
    p.add_argument('--separate-types',action='store_true',help='Checkpoint each asset type separately')
    p.add_argument('--build')
    p.add_argument('--resume',action='store_true')
    p.add_argument('--retries',type=int,default=1)
    p.add_argument('--timeout',type=float,default=7200)
    p.add_argument('--cpu-limit',type=int,help='Maximum logical processors used by Hunter (daily default: 8)')
    p.add_argument('--poll',type=float,help='Busy progress interval in seconds (daily: 1, full: 3)')

