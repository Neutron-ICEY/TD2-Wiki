"""Build and verify offline, reviewable MediaWiki publishing bundles."""

import argparse
import hashlib
import json
import re
import stat
from datetime import datetime, timezone
from pathlib import Path

from . import PublishError, normalized_title_name, require
from .asset_dependencies import AssetDependencies, publication_order

KINDS = {"pages", "templates", "modules", "categories", "redirects", "assets"}
EXPECTED_NS = {"templates": 10, "modules": 828, "categories": 14, "assets": 6}
HASH = re.compile(r"[0-9a-f]{64}")
ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*")


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_asset_digest(row, actual=None):
    expected = row.get("content_sha256")
    require(isinstance(expected, str) and HASH.fullmatch(expected),
            "ASSET_SHA256_REQUIRED: " + row["id"])
    if actual is not None:
        require(actual == expected, "ASSET_BYTES_CHANGED: " + row["id"])


def wiki_text(data, source):
    text = data.decode("utf-8")
    require(text.strip() and "\x00" not in text and not text.startswith("\ufeff"),
            "Wiki 源必须为非空 UTF-8 无 BOM 文本: " + source)
    require("\r" not in text, "Wiki 源必须采用 LF 换行以稳定 hash: " + source)
    return text


def is_within(path, root):
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def read_json(path, data=None):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            require(key not in obj, "存在重复 JSON 字段")
            obj[key] = value
        return obj

    text = path.read_text(encoding="utf-8-sig") if data is None else data.decode("utf-8-sig")
    return json.loads(text, object_pairs_hook=unique)


def safe_path(root, relative):
    from tools.asset_import.static_formats import safe_relative
    try:
        path = Path(safe_relative(relative))
    except ValueError:
        raise PublishError("路径不符合仓库与 Windows 安全文件名规则") from None
    resolved = (root / path).resolve()
    require(is_within(resolved, root.resolve()), "路径或符号链接逃逸根目录")
    return resolved


def title_key(title, namespace):
    require(type(namespace) is int and namespace >= 0, "namespace 必须是非负整数")
    require(isinstance(title, str) and title.strip() == title and title, "无效页面标题")
    require(not re.search(r"[\x00-\x1f\x7f#<>\[\]{}|]", title), "页面标题包含不支持的字符")
    # Conservative collision check. Live site title normalization remains preflight work.
    name = title.split(":", 1)[-1] if namespace else title
    require(bool(name.strip()), "页面名称不能为空")
    return namespace, normalized_title_name(name)


def validate_timestamp(value, field):
    message = field + " 必须为带时区的 ISO 时间"
    require(isinstance(value, str) and value.strip() == value and "T" in value, message)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise PublishError(message) from None
    require(parsed.utcoffset() is not None, message)


def validate_confirmation(row, target, root):
    """Validate an explicitly unknown publication time against one immutable verified receipt entry."""
    require(root is not None, "baseline confirmation 必须显式指定工程 root")
    confirmation = row.get("confirmation")
    require(isinstance(confirmation, dict) and set(confirmation) == {"observed_at", "receipt", "receipt_sha256"},
            "baseline confirmation 必须完整记录 observed_at、receipt、receipt_sha256")
    for field in ("observed_at", "receipt"):
        require(field not in row or row[field] == confirmation[field],
                "baseline 与 confirmation 的 " + field + " 不一致")
    observed = confirmation["observed_at"]
    validate_timestamp(observed, "confirmation observed_at")
    require(isinstance(confirmation["receipt_sha256"], str) and HASH.fullmatch(confirmation["receipt_sha256"]),
            "confirmation 缺少 receipt SHA-256")
    receipt_name = confirmation["receipt"]
    root = Path(root).resolve()
    receipt_path = safe_path(root, receipt_name)
    parts = Path(receipt_name).parts
    require(len(parts) >= 3 and parts[:2] == ("publishing", "history") and receipt_path.suffix == ".json",
            "confirmation receipt 必须位于 publishing/history")
    cursor = root
    for part in parts:
        cursor = cursor / part
        info = cursor.lstat()
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400,
                "confirmation receipt 路径不允许符号链接或 junction")
    require(receipt_path.is_file() and is_within(receipt_path, root / "publishing/history"),
            "confirmation receipt 必须是 publishing/history 内的文件")
    raw = receipt_path.read_bytes()
    require(digest(raw) == confirmation["receipt_sha256"], "confirmation receipt SHA-256 不匹配")
    receipt = read_json(receipt_path, data=raw)
    require(receipt.get("schema_version") == 1 and receipt.get("target") == target
            and receipt.get("status") == "PUBLISHED_VERIFIED", "confirmation receipt 未确认发布或目标不匹配")
    records = []
    for field in ("entries", "completed"):
        if field in receipt:
            require(isinstance(receipt[field], list) and all(isinstance(item, dict) for item in receipt[field]),
                    "confirmation receipt 条目格式无效")
            records.extend(receipt[field])
    key = title_key(row["title"], row["namespace"])
    matching = [item for item in records if title_key(item.get("title"), item.get("namespace")) == key]
    require(len(matching) == 1, "confirmation receipt 必须唯一匹配目标标题")
    confirmed = matching[0]
    require(confirmed.get("status") == "PUBLISHED_VERIFIED", "confirmation receipt 条目未确认发布")
    require(type(confirmed.get("revision_id")) is int and confirmed["revision_id"] > 0,
            "confirmation receipt 缺少实际 revision_id")
    require(isinstance(confirmed.get("content_hash"), str) and HASH.fullmatch(confirmed["content_hash"]),
            "confirmation receipt 缺少 SHA-256")
    require(all(confirmed.get(field) == row.get(field) for field in
                ("title", "namespace", "revision_id", "content_hash"))
            and confirmed.get("observed_at") == observed, "confirmation receipt 与 baseline 确认内容不匹配")
    if row["namespace"] == 6:
        require(confirmed.get("file_revision") == row.get("file_revision"),
                "confirmation receipt 资产版本不匹配")


def load_state(path, target, snapshot=False, root=None):
    if path is None:
        return {}
    state = read_json(path)
    require(state.get("schema_version") == 1 and state.get("target") == target,
            "state 版本或目标 Wiki 不匹配")
    require(isinstance(state.get("entries"), list), "state.entries 必须为数组")
    result = {}
    for row in state["entries"]:
        key = title_key(row["title"], row["namespace"])
        require(key not in result, "state 中存在重复标题")
        if snapshot:
            require(type(row.get("exists")) is bool, "快照必须记录 exists")
            require(bool(row.get("observed_at")), "快照缺少 observed_at")
        else:
            require(row.get("exists", True) is True, "baseline 只能记录已发布内容")
            require(isinstance(row.get("reviewed_by"), str) and row["reviewed_by"].strip(),
                    "baseline 缺少人工审核记录: " + row["title"])
            if "published_at" in row and row["published_at"] is None:
                validate_confirmation(row, target, root)
            else:
                require(bool(row.get("published_at")), "baseline 缺少人工审核记录")
                validate_timestamp(row["published_at"], "baseline published_at")
        if row.get("exists", True):
            require(HASH.fullmatch(row.get("content_hash", "")), "state 缺少 SHA-256")
            require(type(row.get("revision_id")) is int and row["revision_id"] > 0,
                    "state 缺少正整数 revision_id")
            if row["namespace"] == 6:
                require(isinstance(row.get("file_revision"), str) and row["file_revision"],
                        "资产 state 必须记录 file_revision（实际上传版本标识）")
        result[key] = row
    return result


def assess_remote(baseline, remote):
    if remote is None:
        return "REMOTE_UNVERIFIED"
    if baseline is None:
        return "REMOTE_EXISTS_WITHOUT_BASELINE" if remote["exists"] else None
    if not remote["exists"]:
        return "REMOTE_DELETED"
    if (remote["revision_id"] != baseline["revision_id"]
            or remote["content_hash"] != baseline["content_hash"]
            or remote.get("file_revision") != baseline.get("file_revision")):
        return "REMOTE_DRIFT"
    return None


def md(value):
    return str(value).replace("\n", " ").replace("\r", " ").replace("|", "\\|").replace("`", "'")


def move_options(namespace):
    """Native moves preserve history; only File moves suppress the old redirect."""
    return {"method": "native_move", "noredirect": namespace == 6,
            "preserve_history": True, "reason": ""}


def file_write_policy():
    return {"summary": "", "new_description": "", "existing_description": "PRESERVE",
            "rename_existing": "NATIVE_MOVE_ONLY", "runtime_address": "REGISTRY_ONLY"}


def address_action(move):
    source, target = move.get("source_observation"), move.get("target_observation")
    if source is None or target is None:
        return "HOLD_ADDRESS_PREFLIGHT"
    if target["exists"]:
        return "HOLD_TARGET_OCCUPIED"
    old = move["source_baseline"]
    if old is not None and assess_remote(old, source):
        return "HOLD_SOURCE_DRIFT"
    if not source["exists"]:
        return "FIRST_UPLOAD_REQUIRES_APPROVAL" if move["namespace"] == 6 else "CREATE_PAGE_REQUIRES_APPROVAL"
    return "MOVE_FILE_NO_REDIRECT_KEEP_HISTORY" if move["namespace"] == 6 else "MOVE_PAGE_KEEP_REDIRECT"


def report_for(manifest):
    lines = ["# HuijiWiki 人工发布报告", "", f"目标：`{md(manifest['target'])}`",
             "", "模式：MANUAL。此报告不执行任何线上写入。",
             "操作是相对最后一次确认发布的 baseline 计算的本地意图；不是线上状态结论。",
             "远端快照仅供审核，可能过期。编辑前必须再次检查实际 revision / 文件版本。", ""]
    lines.extend(["## 资产依赖顺序", "",
                  "manifest.json 的 entries 按资产前置关系排序。以下列出本批需变更或移动的前置文件及其消费者。操作分类见后文。", ""])
    changed_assets = {r["id"] for r in manifest["entries"] if r["kind"] == "assets"
                      and (r["operation"] != "unchanged" or r.get("pending_move_from"))}
    referenced = {asset_id for r in manifest["entries"] for asset_id in r["asset_relationships"]
                  if asset_id in changed_assets}
    for row in manifest["entries"]:
        waits = referenced.intersection(row["asset_relationships"])
        if row["id"] in referenced or waits:
            note = f"核实 {len(waits)} 项前置文件后核对引用" if waits else "先核实文件版本及目标地址"
            lines.append(f"1. `{md(row['title'])}`（`{md(row['id'])}`）— {note}")
    if not referenced:
        lines.append("本批无需要先变更的前置文件。")
    lines.append("")
    for section in ("CREATE", "UPDATE", "UPLOAD", "UNCHANGED", "CONFLICT", "DELETE"):
        lines.extend([f"## {section}", ""])
        if section == "DELETE":
            rows = manifest["delete_candidates"]
            lines.append("自动删除禁止。以下仅为未在当前维护映射中登记的候选项，必须单独人工确认。")
            lines.extend(f"- `{md(r['title'])}` (namespace {r['namespace']})" for r in rows)
        else:
            rows = [r for r in manifest["entries"] if (
                bool(r["conflicts"]) if section == "CONFLICT" else
                not r.get("pending_move_from") and (r["kind"] == "assets" and r["operation"] != "unchanged" if section == "UPLOAD" else
                r["operation"] == section.lower() and (section == "UNCHANGED" or r["kind"] != "assets")))]
            for row in rows:
                conflicts = ", ".join(row["conflicts"]) or "快照与 baseline 一致；仍需写入前复查"
                lines.append(f"- `{md(row['title'])}` ← `{md(row['file'])}` — {md(row['ownership'])}; "
                             f"{md(row['operation'])}; {md(row['change_reason'])}; {conflicts}")
        if not rows:
            lines.append("无。")
        lines.append("")
    if manifest.get('address_moves'):
        lines.extend(['## 待审核的地址迁移', '', '正文原生 Move 保留重定向；File 原生 MOVE 不创建重定向，均保留历史。File 原因留空，禁止复制上传替代移动。源不存在才列首次创建待批；未知或目标占用必须停止。',
                      '无文件重定向期间会有短暂引用失效：按消费者依赖切换并逐项核验；文件回退先按成功回执逆向无重定向移动，再恢复对应消费者备份，不能先假定旧地址可用。'])
        lines.extend('- `' + md(m['from_title']) + '` → `' + md(m['to_title']) + '`（' + md(m['id']) + '）— ' + md(m['execution_action']) + '; noredirect=' + str(m['move_options']['noredirect']).lower() + '; NOT_EXECUTED' for m in manifest['address_moves'])
        lines.append('')
    lines.extend(["## 人工审核和发布步骤", "",
                  "1. 检查 Git diff、修改原因、entity 映射、资产授权、模板/Lua 依赖及页面预览。",
                  "2. 读取线上当前内容及 revision。无 baseline 的现有页面先人工对账；有 drift 时先将人工修改回收到 Git，再重建审核包。",
                  "3. 解决本批冲突，按依赖先发布资产、数据、模块和模板，再发布引用页面。",
                  "4. 按已审核的操作保存文本或首次上传图片；图片摘要、原因和新文件简介留空，不额外填说明。移动保留原有文件简介与历史，不复制上传已有图片替代移动。删除走独立人工流程。",
                  "5. 核对实际保存结果并更新成功项的 baseline 和回执；文本记录实际内容与 revision，文件以浏览器上传成功状态及必要轻量确认为准。",
                  "6. 部分失败只记录已验证成功的项，停止并重新核对其余项。", ""])
    return "\n".join(lines)


def formal_resource_titles(root):
    """Return titles maintained by the separate formal Reader / Editor build."""
    path = safe_path(root, "publishing/reader-editor-production.json")
    if not path.exists():
        return set()
    naming = read_json(path)["resource_naming"]
    titles = {title_key(row["title"], 2300) for row in naming["reader"]}
    titles.update(title_key(naming[role + "_title"], 2300) for role in ("runtime", "entry"))
    for gadget in naming["gadgets"]:
        titles.add(title_key("Gadget definition:" + gadget["name"], 2302))
        titles.add(title_key("MediaWiki:Gadget-" + gadget["name"], 8))
    return titles


def build(root, registry_path, baseline_path, output, snapshot_path=None):
    registry = read_json(registry_path)
    require(registry.get("schema_version") == 1, "不支持的 registry 版本")
    require(registry.get("mode") == "MANUAL", "当前仅实现 MANUAL，不支持生产 API 发布")
    target = registry.get("target")
    require(isinstance(target, str) and target, "缺少 target")
    require(isinstance(registry.get("entries"), list), "entries 必须为数组")
    baseline = load_state(baseline_path, target, root=root)
    remote = load_state(snapshot_path, target, snapshot=True)
    entries, blobs, titles, ids = [], {}, set(), set()
    prefixes = registry.get("namespace_prefixes", {})
    for source in registry["entries"]:
        entry_id, kind = source["id"], source["kind"]
        require(isinstance(entry_id, str) and ID.fullmatch(entry_id), "无效 entry id")
        require(entry_id.casefold() not in ids, "重复 entry id")
        ids.add(entry_id.casefold())
        require(kind in KINDS, "未知内容类型")
        title, namespace = source["title"], source["namespace"]
        key = title_key(title, namespace)
        require(key not in titles, "重复或冲突的 Wiki 标题映射")
        titles.add(key)
        allowed = prefixes.get(str(namespace))
        require(isinstance(allowed, list) and bool(allowed), "namespace 未配置")
        if namespace:
            require(":" in title and title.split(":", 1)[0].casefold() in [p.casefold() for p in allowed],
                    "标题前缀与 namespace 不匹配")
        else:
            # Disallow ambiguous namespace/interwiki-like titles in mainspace.
            require(":" not in title, "主命名空间标题暂不允许冒号")
        require(kind not in EXPECTED_NS or namespace == EXPECTED_NS[kind], "kind 与 namespace 不匹配")
        require(source.get("ownership") in ("generated", "manual"), "必须明确 generated/manual")
        require(isinstance(source.get("change_reason"), str) and source["change_reason"].strip(), "缺少修改原因: " + entry_id)
        require("related_entity" in source and (source["related_entity"] is None or
                isinstance(source["related_entity"], str)), "必须声明 related_entity，可为 null")
        if source["ownership"] == "generated":
            require(isinstance(source.get("generator"), str) and source["generator"].strip(), "generated 内容必须记录 generator")
        relationships = source.get("asset_relationships")
        require(isinstance(relationships, list) and all(isinstance(v, str) for v in relationships), "缺少资产关系数组")
        path = safe_path(root, source["source"])
        expected_root = (root / ("assets" if kind == "assets" else f"wiki/{kind}")).resolve()
        require(is_within(path, expected_root), "源文件不在对应 wiki/<kind> 或 assets 目录")
        require(path.is_file(), "源文件不存在")
        require(not any(part.startswith(".") for part in Path(source["source"]).parts), "不导出隐藏文件")
        data = path.read_bytes()
        if kind != "assets":
            content = wiki_text(data, source["source"])
            suffix = path.suffix.lower()
            if suffix in (".css", ".js"):
                model = "css" if suffix == ".css" else "javascript"
                require(kind == "pages" and namespace == 8 and
                        title == "MediaWiki:Common" + suffix and
                        source["ownership"] == "manual" and source.get("content_model") == model,
                        "仅支持明确登记的 manual MediaWiki:Common.css/Common.js")
            else:
                require(suffix in (".wiki", ".wikitext", ".lua", ".json"), "不支持的 Wiki 源扩展名")
            if path.suffix.lower() == ".json":
                read_json(path)
            if kind == "redirects":
                require(re.fullmatch(r"\s*#(?:REDIRECT|重定向|重新導向)\s*\[\[[^\]\r\n]+\]\]\s*", content, re.I), "redirect 必须是单一重定向指令")
        else:
            require(path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ogg", ".mp3", ".mp4", ".pdf"), "不支持的资产类型")
            require(bool(data), "资产不能为空")
        content_hash = digest(data)
        if kind == "assets":
            validate_asset_digest(source, content_hash)
        previous = baseline.get(key)
        operation = "create" if previous is None else "unchanged" if previous["content_hash"] == content_hash else "update"
        conflict = assess_remote(previous, remote.get(key))
        relative = f"{kind}/{entry_id}{path.suffix.lower()}"
        row = {field: source.get(field) for field in ("id", "source", "title", "namespace", "related_entity", "ownership", "generator", "change_reason", "asset_relationships")}
        if "asset_relationship_source" in source:
            row["asset_relationship_source"] = source["asset_relationship_source"]
        if path.suffix.lower() in (".css", ".js"):
            row["content_model"] = source["content_model"]
        row.update(kind=kind, file=relative, operation=operation, content_hash=content_hash,
                   baseline_revision=previous["revision_id"] if previous else None,
                   remote_observation=remote.get(key), conflicts=[conflict] if conflict else [])
        entries.append(row)
        blobs[relative] = data
    assets = AssetDependencies(entries, lambda row: blobs[row["file"]].decode("utf-8"))
    for row in entries:
        if row["asset_relationships"]:
            row["declared_asset_relationships"] = row["asset_relationships"]
        row["asset_relationships"] = assets.resolve(row)
    entries = publication_order(entries)
    moves_file = root / 'publishing/pending-moves.json'
    moves = read_json(moves_file) if moves_file.is_file() else {'schema_version':1,'status':'LOCAL_ONLY_NOT_PUBLISHED','entries':[]}
    require(moves.get('schema_version')==1 and moves.get('status')=='LOCAL_ONLY_NOT_PUBLISHED' and isinstance(moves.get('entries'),list), 'Invalid pending move transaction')
    pending_moves = moves['entries']
    current_by_id = {row['id']: row for row in entries}
    move_plan = []
    move_sources = set(); move_ids = set()
    for move in pending_moves:
        require(isinstance(move, dict) and set(move) == {'id', 'namespace', 'from_title', 'from_source'},
                'Pending move fields must not override the native move policy')
        require(move['id'] in current_by_id, 'Move references unknown registry ID')
        require(move['id'] not in move_ids, 'Duplicate move registration ID')
        move_ids.add(move['id'])
        row = current_by_id[move['id']]
        require(move['namespace'] == row['namespace'], 'Move crosses namespace')
        old_key = title_key(move['from_title'], move['namespace'])
        require(old_key != title_key(row['title'],row['namespace']), 'Move source equals target')
        safe_path(root,move['from_source'])
        require(old_key not in move_sources, 'Duplicate move source')
        move_sources.add(old_key)
        previous = baseline.get(old_key)
        row['pending_move_from'] = move['from_title']
        row['conflicts'].append('ADDRESS_MIGRATION_REQUIRES_REVIEW')
        source_baseline = None
        if previous:
            source_baseline = {key: previous[key] for key in ('revision_id', 'content_hash', 'file_revision')
                               if key in previous}
        planned = {
            **move, 'to_title': row['title'], 'to_source': row['source'],
            'baseline_revision': previous['revision_id'] if previous else None,
            'source_baseline': source_baseline, 'source_observation': remote.get(old_key),
            'target_observation': remote.get(title_key(row['title'], row['namespace'])),
            'move_options': move_options(row['namespace']), 'status': 'NOT_EXECUTED',
        }
        planned['execution_action'] = address_action(planned)
        if planned['execution_action'] == 'HOLD_SOURCE_DRIFT':
            row['conflicts'].append('MOVE_SOURCE_DRIFT')
        move_plan.append(planned)
    maintained_titles = titles | formal_resource_titles(root) | move_sources
    manifest = {"schema_version": 1, "mode": "MANUAL", "target": target,
                "built_at": datetime.now(timezone.utc).isoformat(), "hash_algorithm": "sha256",
                "address_moves": move_plan, "file_write_policy": file_write_policy(),
                "comparison": "last_confirmed_baseline", "entries": entries,
                "delete_candidates": [baseline[k] for k in sorted(baseline)
                                      if k not in maintained_titles and baseline[k].get("retired") is not True]}
    manifest_data = json_bytes(manifest)
    report_data = report_for(manifest).encode("utf-8")
    validation = {"schema_version": 1, "status": "passed", "scope": "offline_publish_contract",
                  "production_approved": False, "manifest_hash": digest(manifest_data),
                  "report_hash": digest(report_data), "entry_count": len(entries)}
    require(not output.exists(), "输出目录已存在；请使用新的审核包目录")
    output.mkdir(parents=True)
    for kind in sorted(KINDS):
        (output / kind).mkdir()
    for relative, data in blobs.items():
        (output / relative).write_bytes(data)
    (output / "manifest.json").write_bytes(manifest_data)
    (output / "publish-report.md").write_bytes(report_data)
    (output / "validation.json").write_bytes(json_bytes(validation))
    verify_bundle(output)
    return manifest


def verify_bundle(bundle):
    manifest = read_json(bundle / "manifest.json")
    validation = read_json(bundle / "validation.json")
    require(validation.get("status") == "passed" and validation.get("scope") == "offline_publish_contract",
            "发布包未通过离线 validation")
    require(validation.get("production_approved") is False, "离线 validation 的 production_approved 必须为 false")
    require(manifest.get("schema_version") == 1 and manifest.get("mode") == "MANUAL", "不支持的发布包")
    require(digest((bundle / "manifest.json").read_bytes()) == validation.get("manifest_hash"), "manifest 被修改")
    require(digest((bundle / "publish-report.md").read_bytes()) == validation.get("report_hash"), "report 被修改")
    require(manifest.get('file_write_policy') == file_write_policy(), 'File write policy is missing or unsafe')
    rows = {row['id']: row for row in manifest['entries']}
    require(len(rows) == len(manifest['entries']), '包内重复登记 ID')
    moves = manifest.get('address_moves')
    require(isinstance(moves, list), 'Missing address move contract')
    move_ids = set()
    for move in moves:
        entry_id = move['id']
        require(entry_id in rows and entry_id not in move_ids, 'Invalid or duplicate move ID')
        move_ids.add(entry_id)
        row = rows[entry_id]
        require(move['namespace'] == row['namespace'] and move['to_title'] == row['title']
                and move['to_source'] == row['source'] and move['from_title'] == row.get('pending_move_from'),
                'Move does not match the registered address')
        options = move.get('move_options')
        require(options == move_options(row['namespace']) and type(options.get('noredirect')) is bool,
                'Native move redirect/history/reason policy is missing or unsafe')
        require('source_baseline' in move, 'Missing move source baseline')
        old = move['source_baseline']
        if old is None:
            require(move['baseline_revision'] is None, 'Missing confirmed move source version')
        else:
            require(isinstance(old, dict) and type(old.get('revision_id')) is int
                    and old['revision_id'] > 0 and old['revision_id'] == move['baseline_revision']
                    and isinstance(old.get('content_hash'), str) and HASH.fullmatch(old['content_hash']),
                    'Invalid confirmed move source version')
            if move['namespace'] == 6:
                require(isinstance(old.get('file_revision'), str) and old['file_revision'], 'Missing confirmed move file revision')
        require(move.get('execution_action') == address_action(move) and move.get('status') == 'NOT_EXECUTED',
                'Move action or execution status is invalid')
        require(('MOVE_SOURCE_DRIFT' in row['conflicts']) == (move['execution_action'] == 'HOLD_SOURCE_DRIFT'),
                'Move source drift conflict does not match action')
    require(move_ids == {r['id'] for r in rows.values() if r.get('pending_move_from')}, 'Incomplete address move contract')
    expected = {"manifest.json", "validation.json", "publish-report.md"}
    texts = {}
    for row in manifest["entries"]:
        require(row["operation"] in ("create", "update", "unchanged"), "禁止自动删除或未知 operation")
        path = safe_path(bundle, row["file"])
        require(row["file"] not in expected, "重复产物路径")
        expected.add(row["file"])
        data = path.read_bytes()
        require(digest(data) == row["content_hash"], "产物 hash 不匹配")
        if row["kind"] != "assets":
            texts[row["id"]] = wiki_text(data, row["source"])
    assets = AssetDependencies(manifest["entries"], lambda row: texts[row["id"]])
    preceding = set()
    for row in manifest["entries"]:
        source = {**row, "asset_relationships": row.get("declared_asset_relationships", [])}
        deps = assets.resolve(source)
        require(row["asset_relationships"] == deps, "包内资产依赖与来源不符: " + row["id"])
        require(preceding.issuperset(deps), "包内资产依赖顺序错误: " + row["id"])
        preceding.add(row["id"])
    require((bundle / 'publish-report.md').read_bytes() == report_for(manifest).encode('utf-8'),
            'Report does not match the current operation contract')
    require(validation.get("entry_count") == len(manifest["entries"]), "条目数不匹配")
    actual = {p.relative_to(bundle).as_posix() for p in bundle.rglob("*") if p.is_file()}
    require(actual == expected, "包内存在未登记或缺失文件")
    return manifest


def main():
    parser = argparse.ArgumentParser(description="Offline HuijiWiki export / manual review")
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build")
    build_parser.add_argument("--root", type=Path, default=Path.cwd())
    build_parser.add_argument("--registry", default="publishing/registry.json")
    build_parser.add_argument("--baseline", default="publishing/baseline.json")
    build_parser.add_argument("--snapshot", help="人工采集的远端快照，仓库相对路径")
    build_parser.add_argument("--output", default="dist/current")
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--bundle", type=Path, required=True)
    prepare_parser.add_argument("--mode", choices=["MANUAL"], default="MANUAL")
    args = parser.parse_args()
    try:
        if args.command == "build":
            root = args.root.resolve()
            output = safe_path(root, args.output)
            require(is_within(output, root / "dist") and output != root / "dist", "输出必须位于 dist 的子目录")
            manifest = build(root, safe_path(root, args.registry), safe_path(root, args.baseline), output,
                             safe_path(root, args.snapshot) if args.snapshot else None)
            print(f"MANUAL: {len(manifest['entries'])} entries exported to {output}")
        else:
            from .publisher import ManualPublisher
            print(ManualPublisher().prepare(args.bundle.resolve()))
    except PublishError as error:
        parser.exit(1, f"发布流程失败：{error}\n")
    except (ValueError, OSError, KeyError, TypeError, AttributeError) as error:
        # Avoid echoing source content, credentials, or parser excerpts in logs.
        parser.exit(1, f"发布流程失败 ({type(error).__name__})。请检查路径、映射、状态文件和发布包完整性。\n")
