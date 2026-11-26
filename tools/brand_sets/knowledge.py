from tools.identity import read_json
"""共享天赋与图标目录校验。"""

import re
import unicodedata

from tools.publish.bundle import require
from .model import EQUIPMENT_SLOTS, plain

MODES = ("PvE", "PvP")


def description_html(description, allowed_tones=('plain', 'gold', 'orange')):
    from html import escape
    require(isinstance(description, (str, list)), "天赋说明必须是纯文本或段落列表")
    paragraphs = description.split('\n') if isinstance(description, str) else description
    require(bool(paragraphs), "天赋说明为空时请用 null")
    output = []
    for paragraph in paragraphs:
        segments = [paragraph] if isinstance(paragraph, str) else paragraph
        require(isinstance(segments, list) and bool(segments), "天赋段落必须包含文本片段")
        parts = []
        for segment in segments:
            if isinstance(segment, str):
                text, tone = segment, 'plain'
            else:
                require(isinstance(segment, dict) and set(segment) == {'text', 'tone'}, "天赋片段仅允许 text/tone")
                text, tone = segment['text'], segment['tone']
            require(tone in allowed_tones, "天赋片段颜色无效")
            plain(text, '天赋片段')
            value = escape(text)
            parts.append(value if tone == 'plain' else '<span class="td2-text-' + tone + '">' + value + '</span>')
        output.append('<p>' + ''.join(parts) + '</p>')
    require(any(re.sub('<[^>]+>', '', p).strip() for p in output), "天赋说明为空时请用 null")
    return ''.join(output)
COLORS = {"red": "红", "blue": "蓝", "yellow": "黄"}
def aliases(item):
    result = item.get("search_aliases", [])
    require(isinstance(result, list), "search_aliases 必须为列表")
    for value in result:
        require(plain(value, "搜索别名").strip(), "搜索别名不能为空")
    return result


def evidence(item):
    require(item.get("verification") in ("已核实", "待核实", "有争议"), "核实状态无效")
    require(isinstance(item.get("sources"), list) and all(isinstance(s, str) and s.strip() for s in item["sources"]), "来源记录须为非空文本，可为空列表")
    require(item["verification"] != "已核实" or item["sources"], "已核实记录必须有来源")


def raster(icon):
    require(set(icon) - {"local_available"} == {"wiki_file", "confirmed_on_wiki"}, "图标须包含文件名和确认状态")
    filename = plain(icon["wiki_file"], "图标文件名")
    require(type(icon["confirmed_on_wiki"]) is bool, "图标确认状态须为布尔值")
    require(not filename or (":" not in filename and re.search(r"\.(png|jpe?g|webp|gif)$", filename, re.I)), "请填写登记的 raster 文件名，不带命名空间；发布状态独立核实")


def validate_talents(data):
    require(data.get("schema_version") == 1 and isinstance(data.get("talents"), list), "天赋资料结构不合法")
    seen = set()
    for item in data["talents"]:
        require(set(item) | {"modes"} == {"id", "zh_name", "en_name", "page_title", "icon", "modes", "search_aliases", "active", "verification", "sources"}, "天赋字段不完整或拼写错误")
        require(isinstance(item["id"], str) and re.fullmatch(r"[a-z][a-z0-9_]*", item["id"]) and item["id"] not in seen, "天赋 id 重复或不合法")
        seen.add(item["id"])
        require(plain(item["zh_name"], "天赋中文名").strip(), "天赋中文名不能为空")
        plain(item["en_name"], "天赋英文名")
        title = plain(item["page_title"], "天赋页面标题")
        require(not any(s in title for s in (":", "#", ";")), "天赋页面使用已确认的主命名空间标题，不猜命名空间")
        require(type(item["active"]) is bool, "天赋 active 必须是布尔值")
        aliases(item)
        from .equipment import ui_raster
        ui_raster(item["icon"], allow_local=True)
        require(set(item.get("modes", dict.fromkeys(MODES))) == set(MODES), "天赋必须独立声明 PvE 和 PvP，未知写 null")
        for record in item.get("modes", {}).values():
            if record is not None:
                require(set(record) == {"description", "verification", "sources"}, "天赋模式字段不完整")
                description_html(record["description"])
                evidence(record)
        evidence(item)
    return data


def validate_core_icons(data):
    require(data.get("schema_version") == 1 and set(data.get("icons", {})) == {"major", "minor"}, "主核心和小核心须分别映射")
    filenames = []
    for kind in ("major", "minor"):
        require(set(data["icons"][kind]) == set(COLORS), "核心图标需提供红蓝黄三个独立入口")
        for icon in data["icons"][kind].values():
            raster(icon)
            if icon["wiki_file"]:
                filenames.append(icon["wiki_file"].casefold())
    require(len(filenames) == len(set(filenames)), "六个主／小核心图标不可复用同一文件")
    return data


def search_key(value):
    # Same explicit whitespace set as the browser helper; Python/JS \s differ.
    value = unicodedata.normalize("NFKC", value).lower()
    return re.sub(r"[\u0009-\u000d\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000\ufeff]+", " ", value).strip(" ")


def load_knowledge(root, catalog):
    talents = validate_talents(read_json(root / "data/brand-sets/talents.json"))
    icons = validate_core_icons(read_json(root / "data/brand-sets/core-icons.json"))
    return None, talents, icons
