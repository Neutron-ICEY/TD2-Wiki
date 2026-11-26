"""Evidence-gated normalization and private local review/staging, never upload."""
import argparse
from collections import Counter, defaultdict
from html import escape
import io
import json
from pathlib import Path, PurePosixPath

from .contract import compatible_brand_filename, compatible_filename, detect_contract, match_wiki, read
from .investigate import dump, investigate, resolve_inputs
from .locations import SourceLocations
from .mapping import app_bindings, duplicate_groups
from .static_formats import claim_filename, image_metadata, safe_relative, sha256, write_source


def normalize_bytes(data, filename):
    from PIL import Image
    source = image_metadata(data)
    extension = PurePosixPath(filename).suffix.lower()
    compatible = {'.png': 'PNG', '.webp': 'WEBP', '.jpg': 'JPEG', '.jpeg': 'JPEG', '.gif': 'GIF', '.bmp': 'BMP'}
    if source['source_format'] == compatible.get(extension):
        return data, 'none; source bytes preserved'
    if extension != '.png' or source['source_format'] != 'WEBP' or source['frame_count'] != 1:
        raise ValueError('UNSUPPORTED_LOSSLESS_CONVERSION')
    buffer = io.BytesIO()
    with Image.open(io.BytesIO(data)) as image:
        image.load(); image.save(buffer, format='PNG')
    result = buffer.getvalue(); metadata = image_metadata(result)
    if any(metadata[k] != source[k] for k in ('width', 'height', 'alpha', 'transparency', 'pixel_hash')):
        raise ValueError('CONVERSION_CHANGED_PIXELS_OR_ALPHA')
    return result, 'WebP -> lossless PNG; dimensions, RGBA8 pixels and alpha verified'


def stage_plan(root, out, manifest, contract, source_root=None, resolver_sources=None):
    source_root = source_root or out
    locations = SourceLocations(root)
    rows = []; payloads = {}
    evidence_file = out / 'mapping-evidence.json'
    proof_index = {r['evidence_id']: r for r in read(out, 'mapping-evidence.json')['mappings']} if evidence_file.is_file() else {}
    for asset in manifest:
        if asset['status'] != 'approved':
            continue
        if asset['confidence'] != 'exact' or not asset['stable_id'] or not asset['icon_key']:
            raise ValueError('APPROVAL_GATE_FAILED')
        brand = asset.get('resolver_contract') == 'brand_image'
        if brand:
            from tools.brand_sets.brands import by_key, load_catalog
            entity = by_key(load_catalog(root)).get(asset['stable_id'])
            if (not entity or asset.get('publication_status') != 'READY_TO_UPLOAD'
                    or not entity.get('publication_ready') or entity.get('publication_status') != 'READY_TO_UPLOAD'
                    or asset['source_sha256'] != entity['asset_mapping']['selected_source_sha256']
                    or asset['asset_id'] != entity['asset_mapping']['selected_asset_id']
                    or locations.resolve(source_root / asset['raw_path']) != locations.resolve(root / entity['asset_mapping']['selected_raw_path'])
                    or asset['icon_key'] != 'TD2品牌图片|品牌=' + entity['entity_ref']):
                raise ValueError('BRAND_PUBLICATION_GATE_FAILED')
        else:
            category, key = asset['icon_key'].split('/', 1)
        filename = asset['normalized_filename']
        safe_relative(filename)
        if not filename or len(PurePosixPath(filename).parts) != 1 or filename != asset['intended_wiki_filename']:
            raise ValueError('INVALID_NORMALIZED_FILENAME')
        compatible = (compatible_brand_filename(root, asset['stable_id'], filename, resolver_sources) if brand
                      else compatible_filename(root, category, key, filename, contract, resolver_sources))
        if not compatible:
            raise ValueError('NAMING_CONTRACT_GATE_FAILED')
        if not asset['evidence'] or not asset['normalized_sha256'] or not asset['raw_path']:
            raise ValueError('INCOMPLETE_PROVENANCE')
        proofs = [proof_index.get(key) for key in asset['evidence']]
        if (len(proofs) != 1 or proofs[0] is None or proofs[0]['confidence'] != 'exact'
                or proofs[0]['candidate_stable_id'] != asset['stable_id'] or proofs[0]['candidate_icon_key'] != asset['icon_key']
                or proofs[0]['source_asset_id'] != asset['asset_id'] or proofs[0]['source_path'] != asset['raw_path']
                or len(asset.get('game_entities', [])) != 1 or proofs[0]['candidate_game_entity'] != asset['game_entities'][0]):
            raise ValueError('ENTITY_OR_PROVENANCE_GATE_FAILED')
        safe_relative(asset['raw_path'])
        if sha256(locations.resolve(source_root / asset['raw_path']).read_bytes()) != asset['source_sha256']:
            raise ValueError('RAW_SOURCE_CHANGED')
        data = (out / 'normalized' / filename).read_bytes()
        if sha256(data) != asset['normalized_sha256'] or image_metadata(data)['pixel_hash'] != asset['pixel_hash']:
            raise ValueError('NORMALIZED_CHANGED')
        folded = filename.casefold()
        if folded in payloads and payloads[folded][0] != data:
            raise ValueError('NORMALIZED_FILENAME_COLLISION')
        if folded in payloads and payloads[folded][1] != filename:
            raise ValueError('NORMALIZED_FILENAME_CASE_COLLISION')
        payloads[folded] = (data, filename)
        rows.append(dict(local_filename=filename, intended_wiki_filename=filename, source_asset_id=asset['asset_id'],
            category=asset['category'], stable_id=asset['stable_id'], icon_key=asset['icon_key'], sha256=sha256(data)))
    return rows, payloads


def stage_images(root, out, staging, manifest, contract, source_root=None, resolver_sources=None):
    rows, payloads = stage_plan(root, out, manifest, contract, source_root, resolver_sources)
    image_dir = staging / 'images'
    if image_dir.exists() and any(image_dir.iterdir()):
        raise ValueError('STAGING_NOT_FRESH')
    if (staging / 'image-manifest.json').exists():
        raise ValueError('STAGING_MANIFEST_EXISTS_USE_FRESH_DIRECTORY')
    # No interaction with the existing Sandbox directory or its manifest/README.
    image_dir.mkdir(parents=True, exist_ok=True)
    for data, name in payloads.values():
        write_source(image_dir, name, data)
    result = dict(schema_version=1, mode='MANUAL', local_staging_only=True, upload_executed=False,
                  approved_image_count=len(payloads), entries=rows,
                  empty_reason='没有同时通过确定性实体映射、现有 Wiki stable ID、实际文件名和当前解析器的资源。' if not rows else None)
    dump(staging / 'image-manifest.json', result)
    return result


def filename_hint(name):
    """Filename hints classify the review queue only; never confirm an entity."""
    stem = PurePosixPath(name).stem.lower()
    for prefix, category in (('brand', 'brand'), ('gearsettalent', 'talent'), ('gearset', 'gear_set'),
            ('backpacktalent', 'talent'), ('chesttalent', 'talent'), ('weapontalent', 'talent'),
            ('material', 'material'), ('mod', 'mod'), ('attri', 'attribute/state'), ('weaponattri', 'attribute/state'),
            ('gear', 'gear_slot'), ('skill', 'skill'), ('weapon', 'weapon'), ('specialization', 'specialization')):
        if stem.startswith(prefix):
            return category
    return 'unknown'


def make_evidence(root, images, bindings, groups):
    # Literal filenames resolve directly in Blazor wwwroot. Other encodings need
    # an exact file/pixel bridge; native-density filename similarity stays medium.
    by_filename = defaultdict(list); pixel_sources = defaultdict(list); sha_sources = defaultdict(list)
    for image in images:
        by_filename[(image['source_platform'], image['filename'])].append(image)
        pixel_sources[(image['source_platform'], image['pixel_hash'])].append(image)
        sha_sources[(image['source_platform'], image['sha256'])].append(image)
    evidence = []; comparisons = []
    for binding in bindings:
        wiki = match_wiki(root, binding)
        comparisons.append(dict(binding, wiki=wiki))
        direct = [i for i in by_filename[(binding['source_platform'], binding['source_filename'])]
                  if i['source_entry'] in ('wwwroot/' + binding['source_filename'], 'assets/wwwroot/' + binding['source_filename'])]
        candidates = {i['source_asset_id']: (i, 'exact', 'literal_filename_reference', []) for i in direct}
        for source in direct:
            for image in pixel_sources[(source['source_platform'], source['pixel_hash'])] + sha_sources[(source['source_platform'], source['sha256'])]:
                if image['source_asset_id'] not in candidates:
                    candidates[image['source_asset_id']] = (image, 'exact', 'decoded_pixel_bridge' if image['sha256'] != source['sha256'] else 'exact_sha256_bridge', [source['source_asset_id']])
        for image in by_filename[(binding['source_platform'], binding['source_filename'])]:
            if image['source_asset_id'] not in candidates:
                candidates[image['source_asset_id']] = (image, 'medium', 'filename_only_native_resource_candidate', [])
        for image, confidence, method, bridge in sorted(candidates.values(), key=lambda v: v[0]['source_asset_id']):
            evidence_id = 'mapping:' + sha256((image['source_asset_id'] + '\0' + binding['category'] + '\0' + binding['internal_key'] + '\0' + str(binding['internal_id'])).encode())[:24]
            evidence.append(dict(evidence_id=evidence_id, source_asset_id=image['source_asset_id'], source_platform=image['source_platform'],
                source_path=image['raw_path'], source_package=image['source_package'], source_entry=image['source_entry'], source_filename=image['filename'],
                internal_resource_id=image['android_resource_id'], internal_resource_key=binding['internal_key'], application_internal_id=binding['internal_id'],
                localization_key=binding['localization_key'], candidate_category=binding['category'], candidate_game_entity=binding['internal_key'],
                candidate_chinese_name=binding['chinese_name'], candidate_english_name=binding['english_name'],
                candidate_stable_id=wiki['stable_id'], candidate_icon_key=wiki['icon_key'], wiki_match=wiki,
                evidence_sources=[dict(file=binding['source_platform'] + '-managed-metadata.json', **e) for e in binding['evidence']],
                evidence_type=method, confidence=confidence, bridge_source_asset_ids=bridge,
                notes=wiki['notes'], status='needs_catalog_entry' if confidence == 'exact' and not wiki['stable_id'] else 'needs_review'))
    return sorted(evidence, key=lambda r: r['evidence_id']), comparisons


def manifests(root, out, images, evidence, groups, contract):
    by_asset = defaultdict(list); memberships = defaultdict(list)
    for row in evidence:
        by_asset[row['source_asset_id']].append(row)
    for group in groups:
        for key in group['members']:
            memberships[key].append(group['duplicate_group'])
    result = []; occupied = {}
    for image in images:
        rows = by_asset[image['source_asset_id']]
        exact = [row for row in rows if row['confidence'] == 'exact']
        confirmed = [row for row in exact if row['candidate_stable_id']]
        categories = {row['candidate_category'] for row in rows}
        category = next(iter(categories)) if len(categories) == 1 else 'shared_icon' if categories else filename_hint(image['filename'])
        confidence = next((level for level in ('exact', 'high', 'medium', 'low') if any(r['confidence'] == level for r in rows)), 'unknown')
        status = 'needs_review' if confirmed else 'needs_catalog_entry' if exact else 'high_confidence' if confidence == 'high' else 'needs_review' if rows else 'unmatched'
        stable_ids = {r['candidate_stable_id'] for r in confirmed}
        icon_keys = {r['candidate_icon_key'] for r in confirmed if r['candidate_icon_key']}
        asset = dict(asset_id=image['source_asset_id'], category=category, stable_id=next(iter(stable_ids)) if len(stable_ids) == 1 else None,
            icon_key=next(iter(icon_keys)) if len(icon_keys) == 1 else None, source_platform=image['source_platform'],
            source_package=image['source_package'], source_entry=image['source_entry'], source_filename=image['filename'],
            source_sha256=image['sha256'], pixel_hash=image['pixel_hash'], width=image['width'], height=image['height'],
            source_format=image['source_format'], alpha=image['alpha'], transparency=image['transparency'],
            raw_path=image['raw_path'], normalized_filename=None, normalized_sha256=None, intended_wiki_filename=None,
            conversion=None, match_method=sorted({r['evidence_type'] for r in rows}), evidence=[r['evidence_id'] for r in rows],
            confidence=confidence, status=status, duplicate_group=sorted(memberships[image['source_asset_id']]),
            game_entities=sorted({r['candidate_game_entity'] for r in exact}), chinese_names=sorted({r['candidate_chinese_name'] for r in exact if r['candidate_chinese_name']}),
            english_names=sorted({r['candidate_english_name'] for r in exact if r['candidate_english_name']}),
            proposed_game_entities=sorted({r['candidate_game_entity'] for r in rows}),
            proposed_chinese_names=sorted({r['candidate_chinese_name'] for r in rows if r['candidate_chinese_name']}),
            proposed_english_names=sorted({r['candidate_english_name'] for r in rows if r['candidate_english_name']}),
            notes=['应用内映射证据与 Wiki 命名/解析门禁分别核验。'] if rows else ['只有源路径/文件名；未用外观或 OCR 猜实体。'], naming_gate='CLOSED')
        if len(exact) == 1 and len(confirmed) == 1 and asset['icon_key']:
            lookup_category, key = asset['icon_key'].split('/', 1)
            entry = contract['small_icon_entries'].get(asset['icon_key'], {})
            filename = entry.get('wiki_file')
            if filename and compatible_filename(root, lookup_category, key, filename, contract):
                claim_filename(filename, asset['pixel_hash'], occupied)
                data, conversion = normalize_bytes((out / asset['raw_path']).read_bytes(), filename)
                write_source(out / 'normalized', filename, data)
                asset.update(normalized_filename=filename, normalized_sha256=sha256(data), intended_wiki_filename=filename,
                             conversion=conversion, status='approved', naming_gate='PASS')
        result.append(asset)
    (out / 'normalized').mkdir(exist_ok=True)
    return result


def review_html(out, assets, evidence):
    evidence_index = {r['evidence_id']: r for r in evidence}
    cards = []
    for asset in sorted(assets, key=lambda r: (r['category'], r['status'], r['source_platform'], r['source_entry'])):
        def e(value):
            return escape(str(value) if value is not None else '—', quote=True)
        rows = [evidence_index[k] for k in asset['evidence']]
        details = [('来源', asset['source_platform'] + ' / ' + asset['source_entry']), ('原文件', asset['source_filename']),
            ('尺寸 / 格式', '%s × %s / %s' % (asset['width'], asset['height'], asset['source_format'])),
            ('分类', asset['category']), ('游戏实体', ' / '.join(asset['game_entities']) or (' / '.join(asset.get('proposed_game_entities', [])) + '（候选）' if asset.get('proposed_game_entities') else None)),
            ('中文名', ' / '.join(asset['chinese_names']) or (' / '.join(asset.get('proposed_chinese_names', [])) + '（候选关联）' if asset.get('proposed_chinese_names') else None)),
            ('英文名', ' / '.join(asset['english_names']) or (' / '.join(asset.get('proposed_english_names', [])) + '（候选关联）' if asset.get('proposed_english_names') else None)),
            ('Wiki stable ID', asset['stable_id']), ('Icon key', asset['icon_key']), ('标准文件名', asset['normalized_filename']),
            ('置信度', asset['confidence']), ('证据', '; '.join(asset['match_method']) or '无实体映射证据'),
            ('重复组', '; '.join(asset['duplicate_group']) or None), ('审核状态', asset['status']), ('命名门禁', asset['naming_gate'])]
        details.extend(asset.get('review_details', []))
        image = '<img loading="lazy" src="' + e(asset['raw_path']) + '" alt="资源预览">' if asset['source_format'] != 'DIB' else '<span>PE 原始 DIB：见 raw 与 inventory</span>'
        text = ' '.join(str(value) for _, value in details).casefold()
        preview = '<div class="thumb">' + image + '</div>'
        if asset.get('review_images'):
            views = []
            for view in asset['review_images']:
                # Only local artifact paths; labels and evidence remain escaped text.
                path = safe_relative(view['path']).as_posix()
                views.append('<figure><figcaption>' + e(view['label']) + '</figcaption><a href="' + e(path) + '"><div class="native-raster"><img loading="lazy" src="' + e(path) + '" alt="' + e(view['label']) + '"></div></a><small>' + e(view.get('note', '原始像素；点击打开原图')) + '</small></figure>')
            preview = '<div class="quality-views">' + ''.join(views) + '</div>'
        markup = '<article>' + preview + '<strong>' + e(asset['asset_id']) + '</strong><dl>' + ''.join('<dt>' + e(k) + '</dt><dd>' + e(v) + '</dd>' for k, v in details) + '</dl><details><summary>映射证据</summary><pre>' + e(json.dumps(rows, ensure_ascii=False, indent=2)) + '</pre></details></article>'
        cards.append(dict(category=asset['category'], status=asset['status'], platform=asset['source_platform'],
                          statuses=asset.get('review_statuses', [asset['status']]),
                          platforms=asset.get('review_platforms', [asset['source_platform']]), search=text, html=markup))
    statuses = ''.join('<option>' + escape(k) + '</option>' for k in sorted({s for a in assets for s in a.get('review_statuses', [a['status']])}))
    categories = ''.join('<option>' + escape(k) + '</option>' for k in sorted({a['category'] for a in assets}))
    document = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>TD2 授权素材批量审核</title>
<style>body{margin:0;font:14px/1.5 system-ui;background:#f2f4f6;color:#17202a}header{position:sticky;top:0;background:#fff;padding:20px 28px;border-bottom:1px solid #ccc;z-index:2}h1{font-size:24px;margin:0}h2{grid-column:1/-1;font-size:18px;margin:0}input,select,button{padding:8px;margin-right:12px}main{display:grid;grid-template-columns:repeat(auto-fill,minmax(320px,1fr));gap:18px;padding:28px}article{background:white;border:1px solid #d7dde3;border-radius:8px;padding:16px;overflow-wrap:anywhere}.thumb{height:150px;display:grid;place-items:center;background:repeating-conic-gradient(#303840 0% 25%,#404a55 0% 50%) 0/20px 20px;margin-bottom:14px}.thumb img{max-width:100%;max-height:140px;object-fit:contain}dl{display:grid;grid-template-columns:100px 1fr;font-size:12px}dt{color:#667}dd{margin:0 0 6px}pre{white-space:pre-wrap;font-size:11px}[hidden]{display:none}</style>
<header><h1>TD2 授权素材批量审核</h1><p>全部证据来自静态数据。预览供人工核对；视觉相似不能批准实体映射。当前筛选仅改变显示，不保存批准、不上传。</p><input id="query" placeholder="搜索文件、实体、stable ID"><select id="category"><option value="">全部分类</option>''' + categories + '''</select><select id="status"><option value="">全部状态</option>''' + statuses + '''</select><select id="platform"><option value="">全部来源</option><option value="apk">APK</option><option value="windows">Windows</option></select><button id="previous">上一批</button><button id="next">下一批</button><b id="count"></b></header><main></main><script type="application/json" id="records">''' + json.dumps(cards, ensure_ascii=False).replace('<', '\\u003c') + '''</script><script>
const records=JSON.parse(document.getElementById('records').textContent),query=document.getElementById('query'),category=document.getElementById('category'),status=document.getElementById('status'),platform=document.getElementById('platform');
let page=0;const pageSize=48;
function filter(){const selected=records.filter(r=>(!category.value||r.category===category.value)&&(!status.value||r.statuses.includes(status.value))&&(!platform.value||r.platforms.includes(platform.value))&&r.search.includes(query.value.toLowerCase()));page=Math.max(0,Math.min(page,Math.ceil(selected.length/pageSize)-1));const start=page*pageSize;let group='',markup='';for(const r of selected.slice(start,start+pageSize)){const key=r.category+' / '+r.status;if(group!==key){group=key;markup+='<h2>'+key+'</h2>';}markup+=r.html;}document.querySelector('main').innerHTML=markup;document.getElementById('count').textContent=(selected.length?start+1:0)+'–'+Math.min(start+pageSize,selected.length)+' / '+selected.length+'（总数 '+records.length+'）';document.getElementById('previous').disabled=page===0;document.getElementById('next').disabled=start+pageSize>=selected.length;}
for(const control of [query,category,status,platform])control.addEventListener('input',()=>{page=0;filter();});document.getElementById('previous').addEventListener('click',()=>{page--;filter();});document.getElementById('next').addEventListener('click',()=>{page++;filter();});filter();</script></html>'''
    # Optional quality views share the existing filtering/pagination engine.
    # Raster pixels are never fitted or smoothed; wider comparisons scroll.
    quality_css = '<style>.quality-views{display:flex;gap:14px;overflow-x:auto;margin-bottom:14px}.quality-views figure{flex:0 0 auto;margin:0;max-width:180px}.quality-views figcaption{font-weight:600;font-size:12px}.native-raster{background:repeating-conic-gradient(#303840 0% 25%,#404a55 0% 50%) 0/16px 16px;width:max-content;min-width:128px;min-height:128px}.native-raster img{display:block;max-width:none;max-height:none;image-rendering:pixelated}.quality-views small{display:block;font-size:10px;max-width:160px}</style>'
    if any(a.get('review_images') for a in assets): document = document.replace('</style>', '</style>'+quality_css, 1)
    if any('hunter' in a.get('review_platforms', [a['source_platform']]) for a in assets):
        document = document.replace('<option value="windows">Windows</option>', '<option value="windows">Windows</option><option value="hunter">Hunter</option>', 1)
    (out / 'review.html').write_text(document, encoding='utf-8')


def write_report(root, out, package, images, bindings, groups, correlations, evidence, assets, contract, staging, unresolved):
    counts = Counter(a['status'] for a in assets); source_counts = Counter(a['source_platform'] for a in assets)
    format_counts = Counter(a['source_format'] for a in assets)
    review = ['# TD2 素材人工审核队列', '', '状态计数按 source_asset_id；一张合法共享图可以关联多个实体，mapping-evidence 中每条关系单独保留。', '',
              '优先在 [review.html](review.html) 中按分类/状态筛选。确认实体及 current Wiki stable ID 后，另行确定已有 wiki_file 映射；本任务不修改 Catalog 或解析器。', '',
              '| source_asset_id | category | status | confidence | source | entities | Wiki stable ID |', '| --- | --- | --- | --- | --- | --- | --- |']
    for a in assets:
        if a['status'] != 'approved':
            entities = '; '.join(a['game_entities']) or ('; '.join(a['proposed_game_entities']) + ' (candidate)' if a['proposed_game_entities'] else '无确定映射')
            review.append('| ' + ' | '.join(str(v).replace('|', '&#124;') for v in [a['asset_id'], a['category'], a['status'], a['confidence'], a['source_entry'], entities, a['stable_id'] or '无']) + ' |')
    (out / 'NEEDS-REVIEW.md').write_text('\n'.join(review) + '\n', encoding='utf-8')
    lines = ['# TD2 Authorized Asset Import / Normalization', '', '授权素材静态分析与标准化阶段性完成。这里只构建本地私有审核资料；没有发布或上传授权。', '',
             '## 输入及版本', '', '- repository root：`' + str(root) + '`', '']
    for platform in ('apk', 'windows'):
        p = package[platform]
        lines += ['- ' + platform + ' path：`' + p['relative_path'] + '`', '- absolute path：`' + p['absolute_path'] + '`',
                  '- filename / size / signature：`%s` / %s bytes / %s' % (p['filename'], p['size'], p['file_signature']),
                  '- SHA-256：`' + p['sha256'] + '`', '']
    a = package['apk']; w = package['windows']
    lines += ['- APK package：`' + a['metadata']['package'] + '`', '- APK versionName / versionCode：`%s` / `%s`' % (a['metadata']['versionName'], a['metadata']['versionCode']),
              '- APK min SDK / target SDK：`%s` / `%s`' % (a['metadata']['minSdkVersion'], a['metadata']['targetSdkVersion']),
              '- Windows ProductName：`' + w['version_info']['ProductName'] + '`', '- Windows ProductVersion：`' + w['version_info']['ProductVersion'] + '`',
              '- Windows FileVersion / AssemblyVersion：`%s` / `%s`' % (w['version_info']['FileVersion'], w['assembly_version']),
              '- Windows type：%s / %s；native apphost，embedded application assembly 为 managed .NET。' % (w['pe']['type'], w['pe']['architecture']),
              '- .NET single-file bundle：' + str(w['bundle']['single_file']) + '；bundle v%s.%s，%s entries。' % (*w['bundle']['format_version'], w['bundle']['entry_count']),
              '- MAUI / self-contained：%s / %s；runtime config：`%s`。' % (w['maui'], w['self_contained'], json.dumps(w['runtime'], ensure_ascii=False)),
              '- APK / Windows version relationship：**' + package['version_relationship'] + '**（依据内部版本比较；平台 internal IDs 另行独立验证）。', '',
              '## 静态资源结构与方法', '', '- APK：`' + json.dumps(a['structure'], ensure_ascii=False) + '`；Android binary XML 和 resources.arsc 为只读解析。',
              '- APK assembly store：按实际 manifest 定位 app 与 en satellite；XALZ LZ4 在内存解压，从未加载目标程序集。',
              '- Windows：只读 bundle offsets/PE RVA；只保留图片，framework/runtime DLL 只登记 entry、SHA-256 和 metadata，未复制整个 runtime。',
              '- 用已安装的 PowerShell 7 + System.Reflection.Metadata 的 PEReader/MetadataReader 读取两个 app 和两个 en satellite；只检查指定模型构造器、AppData .cctor 和相关图标 helper。',
              '- .resources 只读取 String 类型；不调用 ResourceReader 对任意对象反序列化。localization 只导出游戏映射所用键；未保存程序集或完整资源流。',
              '- APK assets/assetbuild、sponsor 的内置配装/赞助者资料不属于实体图标任务，已跳过，未复制用户资料或输出值。',
              '- 服务类型与用户数据类型只做元数据标识，没有读取其 IL/值。',
              '- additional tooling：**不需要**；未安装或下载任何软件。',
              '- MISSING_EXTERNAL_DEPENDENCY：' + (', '.join(w['missing_external_dependencies']) or '无（仅核对 managed app 直接引用；不声称完成动态原生依赖/应用可启动性检查）'), '',
              '## Detected Naming Contract', '', contract['explanation'], '',
              '真实配置与当前生成的模板均保持原状。空文件名表示 contract 没有定义该文件，不能填入虚构的命名示例。品牌例子来自现有 NON-GAME-FACT fixture，仅证明 helper 语法。', '',
              '| category | stable_id | icon_key | normalized_filename | intended_wiki_filename | lookup/result | gate |',
              '| --- | --- | --- | --- | --- | --- | --- |']
    for row in contract['examples']:
        display = 'File:' + row['intended_wiki_filename'] if '[[File:' in row['lookup_result'] else '16px placeholder' if 'td2-icon-placeholder' in row['lookup_result'] else '无图片输出'
        cells = [row['category'], row['stable_id'], row['icon_key'], row['normalized_filename'], row['intended_wiki_filename'], row['lookup'] + ' → ' + display, row['gate']]
        lines.append('| ' + ' | '.join(str(v or 'null').replace('|', '&#124;') for v in cells) + ' |')
    lines += ['', '- gate：**' + contract['automatic_normalization_gate'] + '**',
              '- NAMING_CONTRACT_CONFLICT：' + str(len(contract['naming_contract_conflicts'])) + '。缺 mapping / 空 catalog / unsupported category 分别记录，未把缺项伪装为已证明的命名格式。',
              '- HuijiUpdater 原有 `_0_..._4_` helper 属于页面文本导出；不用于图标实体命名，本次不执行现有 Sandbox exporter。', '',
              '## Inventory、duplicates 与 correlation', '', '- 图片资源总数：**%s**；APK：%s；Windows：%s（包括 bundle PNG/ICO 和 %s 个 PE 原始 icon resources）。' % (len(images), source_counts['apk'], source_counts['windows'], w['pe_image_resource_count']),
              '- 各格式：`' + json.dumps(format_counts, ensure_ascii=False) + '`',
              '- exact_file_duplicate：%s groups / %s redundant files。' % (sum(g['type'] == 'exact_file_duplicate' for g in groups), sum(len(g['members']) - 1 for g in groups if g['type'] == 'exact_file_duplicate')),
              '- pixel_duplicate：%s groups（包含 exact file groups；同 pixels 不同 compression/encoding 另有 %s groups）。' % (sum(g['type'] == 'pixel_duplicate' for g in groups), sum(g['type'] == 'pixel_duplicate' and len(g['source_sha256s']) > 1 for g in groups)),
              '- cross-platform shared assets：%s distinct pixel groups；exact correlation pairs：%s。' % (sum(g['type'] == 'pixel_duplicate' and g['cross_platform'] for g in groups), sum(c['confidence'] == 'exact' for c in correlations)),
              '- legitimate_shared_icon：%s pixel groups；从直接构造器绑定证明多个实体共享图片，保留多条映射，不创建无解释的 normalized 副本。' % sum(g['type'] == 'pixel_duplicate' and g['legitimate_shared_icon'] for g in groups),
              '- pixel hash：TD2-RGBA8-v1，dimensions/frame count + 完整 RGBA8 frames + animated duration；不 resize、不 premultiply、不改 RGB/alpha、不执行 EXIF 旋转。', '',
              '## 应用映射与当前 Wiki Catalog', '',
              '- 明确 resource mapping table：**有**，AppData .cctor 中的 literal constructor records；两平台各独立恢复并逐条验证 Name/Image 参数流。',
              '- internal ID ↔ image：Talent 的 Save 字段直接绑定；brand/gear_set 用 app Name/localization key，未从数字文件名推导实体 ID。',
              '- Wiki 匹配：只使用已有 catalog 的唯一中文/英文精确匹配；共享图片关系保留，不把 app ID 变成 Wiki ID。',
              '- 未修改任何 base/Perfect canonical Talent 关系；NamedTalent 与普通 Talent 共享资源只作为应用证据。', '',
              '| category | APK exact app bindings | Windows exact app bindings | Wiki condition |', '| --- | --- | --- | --- |']
    conditions = {'talent': 'talents.json 为空；全部 app Talent 进入 needs_catalog_entry。', 'brand': '无真实 brand stable ID catalog；只证明现有 display-name helper。',
                  'gear_set': '当前没有该 Catalog/resolver 类别。', 'attribute': '有真实词条 catalog；特定词条图片不能自动等同 attribute_category 分类图。',
                  'mod': '当前只有 equipment_row/mod_slot；mod 实体图不自动等同槽行图。', 'material': '只有 brand_material/unverified 空入口；未发现直接材料实体绑定。',
                  'gear_slot': '六个 canonical slot 已有，但 slot_visuals 全空；未证明 slot 唯一图标绑定。',
                  'attribute/state': 'red/blue/yellow/random/none 全为空；不以图片颜色/文件名猜状态。',
                  'equipment row type': '四种既有 row key 全为空；没有已验证 source ↔ row-key 绑定。'}
    for category, condition in conditions.items():
        lines.append('| %s | %s | %s | %s |' % (category, sum(b['category'] == category and b['source_platform'] == 'apk' for b in bindings), sum(b['category'] == category and b['source_platform'] == 'windows' for b in bindings), condition))
    if package['skipped_unrelated_strings']:
        lines += ['', '发现与任务无关的敏感配置，已跳过。']
    lines += ['', '- 详细 Talent/Wiki exact/high/missing/ambiguous、Brand/Gear Set/Material 对照见 `catalog-comparison.json`；当前无 Wiki Talent，exact/high/missing 三个 Wiki Talent 数量均为 0，app 侧缺项单独列出。',
              '- 其它 blueprint/weapon/skill/specialization/named/exotic/unknown 仅 inventory / filename-hint review；没有通过外观推导实体。',
              '- 无法恢复的受选构造器表达式：%s；未使用 unsupported 表达式补齐数据。' % sum(len(v) for v in unresolved.values()), '',
              '## EXACT / APPROVED', '', '- 应用内 exact entity/image 证据不等于 Wiki approved。',
              '- approved：**%s**；normalized 实际图片：%s；HuijiUpdater approved image count：**%s**。' % (counts['approved'], sum(bool(a['normalized_filename']) for a in assets), staging['approved_image_count']),
              '- 所有 approved 必须同时通过 exact、唯一游戏实体、已有 Wiki stable ID/icon key、无 filename collision、当前解析器实际解析及 provenance 检查。', '',
              '## NEEDS HUMAN REVIEW', '', '- source_asset_id 状态计数：`' + json.dumps({k: counts[k] for k in ('high_confidence', 'needs_review', 'unmatched', 'needs_catalog_entry')}, ensure_ascii=False) + '`',
              '- `NEEDS-REVIEW.md` 与 `review.html` 包含全部非 approved 资源。批量预览只用于人工核对，不能单独提升 exact/high。',
              '- `proposed-icon-mapping.json` 只列已有 Wiki ID 的确定性应用图片候选，文件名仍为 null；需要另轮人工配置，不修改 production facts。', '',
              '## 输出与安全', '', '- normalized directory：`dist/asset-import/normalized/`', '- asset manifest：`dist/asset-import/asset-manifest.json`',
              '- mapping evidence：`dist/asset-import/mapping-evidence.json`', '- contact sheet：`dist/asset-import/review.html`',
              '- human review：`dist/asset-import/NEEDS-REVIEW.md`', '- HuijiUpdater staging：`dist/huiji-updater/images/`；`dist/huiji-updater/image-manifest.json`',
              '- 本次输入由命令显式指定；原始包不执行，提取产物与正式 Wiki 源分开保存。',
              '- immutable input before/after：`' + json.dumps(package['immutable_verification'], ensure_ascii=False) + '`',
              '- 开始时的已有未提交变更单独保存在 repository-before.json；最终逐文件 hash 比较，不归入本任务修改。',
              '- validation/tests 详细结果见 `validation-results.json`；复核 determinism/normalized/staging/provenance 与边界后写出 `validation.json`。', '',
              '## 未解决项与下一步', '',
              '1. 人工先审 `needs_review` 中已有 Wiki attribute ID 的候选，确认分类图/具体词条图的语义，不直接复用角色。',
              '2. 在独立、获准的 Catalog 维护任务中补充真实 Talent/Brand/Gear Set stable IDs；本任务不会自动建实体。',
              '3. 人工确定现有 wiki_file 空入口应采用的准确名称及 source_asset_id，再以新的审核目录重跑 Naming Contract Gate。',
              '4. 只有 resolver 真正可解析的 exact 项才能进入 images/；上传继续保持独立人工步骤。本轮不检查或声称线上文件存在。', '',
              '## 静态格式依据', '',
              '- [.NET bundle manifest](https://github.com/dotnet/runtime/blob/main/src/installer/managed/Microsoft.NET.HostModel/Bundle/Manifest.cs)、[FileEntry](https://github.com/dotnet/runtime/blob/main/src/installer/managed/Microsoft.NET.HostModel/Bundle/FileEntry.cs)。',
              '- [AOSP ResourceTypes.h](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/libs/androidfw/include/androidfw/ResourceTypes.h)。', '',
              '授权素材静态分析与标准化阶段性完成；原 APK 与 Windows EXE 未被修改，未 commit、未 push、未 publish、未上传灰机。所有 approved 图片均通过现有 Wiki naming contract 与 Icon Resolver 兼容性检查；其余映射已进入人工审核队列。等待人工审核结果。']
    (out / 'ASSET-IMPORT-REPORT.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def run_import(root, out, staging, pwsh, inputs):
    if (out / 'validation.json').exists():
        raise ValueError('VALIDATED_BUNDLE_IMMUTABLE_USE_FRESH_OUTPUT')
    inputs = resolve_inputs(root, out, inputs)
    out.mkdir(parents=True, exist_ok=True)
    contract = detect_contract(root)
    dump(out / 'naming-contract.json', contract)
    # Write the gate before any normalization. Raw inventory is independent.
    (out / 'ASSET-IMPORT-REPORT.md').write_text('## Detected Naming Contract\n\n' + contract['explanation'] + '\n\nGate: ' + contract['automatic_normalization_gate'] + '\n', encoding='utf-8')
    package, inventories, managed, localizations = investigate(root, out, pwsh, inputs)
    bindings = []; unresolved = {}; contracts = {}
    for platform in ('apk', 'windows'):
        rows, constructor_rules, unsupported = app_bindings(platform, managed[platform], localizations)
        bindings += rows; unresolved[platform] = unsupported; contracts[platform] = constructor_rules
    images = sorted(inventories['apk'] + inventories['windows'], key=lambda r: r['source_asset_id'])
    groups, correlations = duplicate_groups(images, bindings)
    evidence, comparisons = make_evidence(root, images, bindings, groups)
    assets = manifests(root, out, images, evidence, groups, contract)
    dump(out / 'application-bindings.json', dict(schema_version=1, bindings=bindings, constructor_contracts=contracts, unresolved=unresolved))
    dump(out / 'mapping-evidence.json', dict(schema_version=1, mappings=evidence))
    dump(out / 'duplicate-groups.json', dict(schema_version=1, groups=groups))
    dump(out / 'cross-platform-correlation.json', dict(schema_version=1, correlations=correlations))
    dump(out / 'asset-manifest.json', dict(schema_version=1, assets=assets))
    wiki_talents = read(root, 'data/brand-sets/talents.json')['talents']
    matched = {c['wiki']['stable_id'] for c in comparisons if c['category'] == 'talent' and c['wiki']['unique']}
    dump(out / 'catalog-comparison.json', dict(schema_version=1, application_entities=comparisons,
        wiki_talent_exact=[t['id'] for t in wiki_talents if t['id'] in matched], wiki_talent_high=[],
        wiki_talent_without_app_icon=[t['id'] for t in wiki_talents if t['id'] not in matched],
        app_talent_missing_from_wiki=[c for c in comparisons if c['category'] == 'talent' and not c['wiki']['stable_id']],
        ambiguous_mappings=[c for c in comparisons if c['wiki']['method'] == 'ambiguous_catalog_name']))
    proposed = [dict(source_asset_id=r['source_asset_id'], evidence_id=r['evidence_id'], category=r['candidate_category'],
        stable_id=r['candidate_stable_id'], icon_key=r['candidate_icon_key'], normalized_filename=None, intended_wiki_filename=None,
        reason=r['wiki_match']['notes'] or 'current wiki_file mapping is empty; a filename cannot be invented')
        for r in evidence if r['candidate_stable_id'] and r['confidence'] == 'exact']
    if proposed:
        dump(out / 'proposed-icon-mapping.json', dict(schema_version=1, production_modified=False, proposals=proposed))
    used_keys = {b['localization_key'] for b in bindings} | {b['localization_key'] + 'FN' for b in bindings if b['category'] == 'brand'}
    dump(out / 'game-localization-evidence.json', {label: {k: v for k, v in values.items() if k in used_keys} for label, values in localizations.items()})
    staging_result = stage_images(root, out, staging, assets, contract)
    review_html(out, assets, evidence)
    write_report(root, out, package, images, bindings, groups, correlations, evidence, assets, contract, staging_result, unresolved)
    return dict(images=len(images), platforms={k: len(v) for k, v in inventories.items()},
                status_counts=dict(Counter(a['status'] for a in assets)), application_binding_count=len(bindings),
                mapping_count=len(evidence), normalized_count=sum(bool(a['normalized_filename']) for a in assets),
                staged_image_count=staging_result['approved_image_count'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='dist/asset-import')
    parser.add_argument('--staging', default='dist/huiji-updater')
    parser.add_argument('--pwsh', required=True)
    parser.add_argument('--apk', required=True)
    parser.add_argument('--windows', required=True)
    args = parser.parse_args(); root = Path.cwd(); out = root / args.output; staging = root / args.staging
    allowed_out = (root / 'dist/asset-import').resolve(); allowed_stage = (root / 'dist/huiji-updater').resolve()
    if allowed_out not in (out.resolve(), *out.resolve().parents) or allowed_stage not in (staging.resolve(), *staging.resolve().parents):
        raise ValueError('OUTPUT_BOUNDARY')
    print(json.dumps(run_import(root, out, staging, args.pwsh, {'apk': args.apk, 'windows': args.windows}), ensure_ascii=False))


if __name__ == '__main__':
    main()
