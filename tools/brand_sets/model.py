from tools.identity import read_json
"""当前品牌资料的离线契约。PvE/PvP 数值独立；PvP 可仅复用 PvE 词条身份。"""

import re

from tools.publish.bundle import require
from .slots import SLOTS

CATEGORIES = {"offense": "攻击类", "defense": "防御类", "utility": "技能/功能类"}
UNITS = {"percent": "%", "number": "", "seconds": "秒"}


def bonus_value_text(value, attribute_id):
    from decimal import Decimal, ROUND_HALF_UP, localcontext
    number = Decimal(value)
    require(number.is_finite(), "数值必须有限")
    precision = Decimal("1") if attribute_id == "bonus_increased_threat" else Decimal("0.1")
    with localcontext() as context:
        context.prec = max(28, len(number.as_tuple().digits) + abs(number.adjusted()) + 3)
        rendered = format(number.quantize(precision, rounding=ROUND_HALF_UP), "f")
    return ("" if rendered.startswith("-") else "+") + rendered
SPECIAL_LABEL = "其他／特殊效果"
STATUSES = ("暂无数据", "未知", "待核实", "不适用", "已核实")
EQUIPMENT_SLOTS = SLOTS
NATIVE_LABELS = ("允许主核心", "允许小核心", "主核心槽数", "小属性槽数", "插件槽数")


def plain(value, label):
    require(isinstance(value, str), f"{label} 必须是文本")
    require(not re.search(r"[\x00-\x1f<>\[\]{}|]", value), f"{label} 含不支持的控制或 Wiki 字符")
    return value


def load_catalog(root):
    catalog = read_json(root / "data/brand-sets/bonuses.json")
    icons = read_json(root / "data/brand-sets/category-icons.json")
    validate_catalog(catalog, icons)
    return catalog, icons


def validate_catalog(catalog, icons):
    return validate_catalog_records(catalog, icons, "bonus_")


def validate_catalog_records(catalog, icons, prefix, distinct_units=False):
    require(catalog.get("schema_version") == 2, "词条配置版本不支持，请显式迁移旧 pilot")
    require(isinstance(catalog.get("attributes"), list), "attributes 必须是列表，可为空")
    ids, names, labels = set(), set(), set()
    for item in catalog["attributes"]:
        required = {"id", "zh_name", "en_name", "category", "unit_type", "active", "verification", "sources"}
        require(isinstance(item, dict) and required <= set(item) and not set(item) - required - {"search_aliases"}, "词条字段不完整或存在拼写错误，请复制完整条目")
        from .knowledge import aliases
        aliases(item)
        key = item.get("id", "")
        require(isinstance(key, str) and re.fullmatch(r"[a-z][a-z0-9_]*", key), "词条 id 应为可读英文标识")
        require(key.startswith(prefix) and key != "special" and key not in ids, "词条 ID 领域错误、重复或占用特殊标识")
        ids.add(key)
        name = plain(item.get("zh_name"), "中文名称")
        name_key = (name, item.get('unit_type')) if distinct_units else name
        require(name and name_key not in names and "," not in name, "中文名称为空、同单位重复或含列表分隔符")
        names.add(name_key)
        plain(item.get("en_name"), "英文名称")
        require(item.get("category") in CATEGORIES, "词条分类不合法")
        require(item.get("unit_type") in UNITS, "词条单位类型未登记")
        require(type(item.get("active")) is bool, "active 必须为 true 或 false")
        label = display_label(item)
        label_key = (label, item.get('unit_type')) if distinct_units else label
        require(name == name.strip() and ";" not in label and label != SPECIAL_LABEL and label_key not in labels,
                "PF 显示名称冲突、含首尾空白或分号；请使用唯一中文名，不占用特殊效果标签")
        labels.add(label_key)
        require(isinstance(item.get("verification"), str) and item["verification"], "请说明词条核实情况")
        require(isinstance(item.get("sources"), list), "sources 必须为列表")
        require(all(isinstance(s, str) and s.startswith("https://") for s in item["sources"]), "来源必须是 HTTPS 链接")
    require(icons.get("schema_version") == 1 and set(icons.get("icons", {})) == set(CATEGORIES), "图标分类映射不完整")
    for icon in icons["icons"].values():
        filename = plain(icon.get("wiki_file"), "图标文件名")
        require(type(icon.get("confirmed_on_wiki")) is bool, "图标确认状态必须是布尔值")
        if filename:
            require(":" not in filename and re.search(r"\.(png|jpe?g|webp|gif)$", filename, re.I), "图标须为不带命名空间的 raster 文件名")
            # Local registered assets may await a separately authorized File move.


def attributes_by_id(catalog):
    require(all(item["id"].startswith("bonus_") for item in catalog["attributes"]), "Bonus Catalog 不接受 Minor Attribute ID")
    return {item["id"]: item for item in catalog["attributes"]}


def display_label(item):
    """PF mapping 与元数据/条件匹配共用同一个标签，停用标记不能各写一份。"""
    return item["zh_name"] + ("（已停用）" if not item["active"] else "")


def relationship_values(value):
    """分号独立于中英文标点；禁止链接语法，避免拆分歧义。"""
    if value == "":
        return []
    values = [part.strip() for part in value.split(";")]
    require(all(values) and len(values) == len(set(values)), "列表存在空项或重复项")
    for title in values:
        plain(title, "关系页面名称")
        require("#" not in title, "关系指向页面，不使用段落锚点")
    return values
