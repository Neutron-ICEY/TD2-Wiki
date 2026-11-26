"""Fixed Minor Preset domain: identity references Minor; values belong here only."""
from decimal import Decimal, InvalidOperation
import re

from tools.publish.bundle import read_json, require
from .minor import by_id as minor_by_id
from .knowledge import aliases, search_key

EMPTY = {"schema_version": 1, "presets": []}
ID = re.compile(r"(?:fixed_minor_|ordinary_minor_)[a-z][a-z0-9_]*$")


def decimal_text(value):
    require(isinstance(value, str) and re.fullmatch(r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)", value),
            "固定预设数值必须是十进制字符串")
    try:
        number = Decimal(value)
    except InvalidOperation:
        raise ValueError("固定预设数值不合法")
    require(number.is_finite(), "固定预设数值必须有限")
    if number == 0:
        return "0"
    result = format(number, "f")
    return result.rstrip("0").rstrip(".") if "." in result else result


def validate_catalog(data, minor_catalog):
    require(set(data) == {"schema_version", "presets"} and data["schema_version"] == 1,
            "固定预设目录结构不合法")
    require(isinstance(data["presets"], list), "固定预设必须是列表")
    minor = minor_by_id(minor_catalog)
    seen, facts = set(), set()
    for row in data["presets"]:
        require(isinstance(row, dict) and set(row) == {
            "id", "minor_attribute_id", "value", "search_aliases", "verification", "sources", "active"
        }, "固定预设字段不完整或存在未知字段")
        key = row["id"]
        require(isinstance(key, str) and re.fullmatch(r"fixed_minor_[a-z][a-z0-9_]*", key) and key not in seen,
                "固定预设 ID 领域错误或重复")
        seen.add(key)
        require(row["minor_attribute_id"] in minor, "固定预设必须引用 Minor Attribute")
        value = decimal_text(row["value"])
        require(re.fullmatch(r"-?(?:0|[1-9]\d*)(?:\.\d+)?", row["value"]) is not None, "固定预设数值须使用十进制文本，可保留显示精度")
        require(type(row["active"]) is bool, "active 必须是布尔值")
        aliases(row)
        require(isinstance(row["verification"], str) and row["verification"].strip(), "请填写核实状态")
        require(isinstance(row["sources"], list) and all(isinstance(s, str) and s.startswith("https://") for s in row["sources"]), "来源必须为 HTTPS 列表")
        fact = (row["minor_attribute_id"], value)
        if row["active"]:
            require(fact not in facts, "同属性同数值的 active 固定预设重复")
            facts.add(fact)
    return data


def load_catalog(root, minor_catalog):
    return validate_catalog(read_json(root / "data/brand-sets/fixed-minor-presets.json"), minor_catalog)


def resolve(data, minor_catalog, preset_id, ordinary=None):
    validate_catalog(data, minor_catalog)
    if preset_id.startswith('ordinary_minor_'):
        from tools.equipment_attributes.catalog import ordinary_rows
        rows = {p['id']: p for p in ordinary_rows(minor_catalog, ordinary or {'rules': []})}
        require(preset_id in rows, "未找到普通次属性规则")
        return rows[preset_id]
    rows = {p["id"]: p for p in data["presets"]}
    require(preset_id in rows, "未找到固定词条预设，请重新选择")
    preset = rows[preset_id]
    attribute = minor_by_id(minor_catalog)[preset["minor_attribute_id"]]
    return dict(preset, zh_name=attribute["zh_name"], en_name=attribute["en_name"],
                category=attribute["category"], unit=attribute["unit_type"])


def decode(value, data, minor_catalog, ordinary=None):
    require(isinstance(value, str), "固定次属性必须是预设 ID 列表")
    ids = value.split(";") if value else []
    require(len(ids) == len(set(ids)), "同一装备不能重复选择相同固定词条预设")
    for key in ids:
        require(ID.fullmatch(key), "固定次属性只接受预设 ID，不接受旧数值格式")
        resolve(data, minor_catalog, key, ordinary)
    return ids


def encode(ids, data, minor_catalog, ordinary=None):
    require(isinstance(ids, list) and all(isinstance(i, str) for i in ids), "固定预设引用必须是有序列表")
    text = ";".join(ids)
    require(decode(text, data, minor_catalog, ordinary) == ids, "固定预设引用列表不合法")
    return text


def search_records(data, minor_catalog, ordinary=None):
    validate_catalog(data, minor_catalog)
    minor = minor_by_id(minor_catalog)
    result = []
    for preset in sorted(data["presets"], key=lambda p: p["id"]):
        row = resolve(data, minor_catalog, preset["id"])
        attribute = minor[preset["minor_attribute_id"]]
        row["keys"] = sorted({search_key(s) for s in [row["zh_name"], row["en_name"]] + aliases(attribute) + aliases(preset) if s})
        result.append(row)
    from tools.equipment_attributes.catalog import ordinary_rows
    return result + ordinary_rows(minor_catalog, ordinary or {'rules': []})


def candidates(data, minor_catalog, ordinary=None):
    """New selections only; complete metadata still resolves inactive saved IDs."""
    return [row for row in search_records(data, minor_catalog, ordinary) if row["active"]]


def display_value(value, unit):
    if unit != "number" or not value:
        return value
    integer, dot, fraction = value.partition(".")
    return re.sub(r"(?<=\d)(?=(?:\d{3})+$)", ",", integer) + dot + fraction
