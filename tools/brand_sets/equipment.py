from tools.identity import read_json
"""普通金装共同规则；品牌仅覆盖主属性，具名装备逐项显式覆盖。

集中事实全部在 canonical 部位 ID 索引的 JSON，维护数值不需要修改本文件。
"""

import copy
import re
import unicodedata

from tools.publish.bundle import require
from .model import EQUIPMENT_SLOTS, plain
from .knowledge import COLORS, raster
from .icons import ROW_KEYS, STATE_KEYS, OPTIONAL_STATE_KEYS

SLOT_VISUAL_KEYS = {slot: slot for slot in EQUIPMENT_SLOTS}

COUNT_FIELDS = {"major_core_slots": "主属性槽数", "minor_attribute_slots": "次属性槽数", "talent_slot_count": "天赋位数", "mod_slot_count": "插件槽数"}
EXCEPTION_FLAGS = {"minor_attribute_slots": "次属性槽例外", "talent_slot_count": "天赋位例外", "mod_slot_count": "插件槽例外"}
EQUIPMENT_FIELDS = ("装备名称", "英文原名", "简介", "所属品牌", "stable_id", "固定次属性", "装备部位", "天赋引用", "talent_mode", "具名图纸名称", "允许主核心", "主核心组合") + tuple(field for key in COUNT_FIELDS if key not in ("talent_slot_count", "major_core_slots") for field in (EXCEPTION_FLAGS[key], COUNT_FIELDS[key]))


def count(value):
    require(value is None or (type(value) is int and value >= 0), "槽数／数量须为 null 或非负整数，不能用布尔值")
    return value


def amount(value):
    require(isinstance(value, dict) and set(value) == {"min", "max"}, "材料数量使用 min / max，未知两项都为 null")
    low, high = count(value["min"]), count(value["max"])
    require((low is None and high is None) or (low is not None and high is not None and low <= high), "数量范围须完整且 min 不大于 max")
    return value


def amount_text(value):
    if value["min"] is None:
        return "数量待核实"
    return str(value["min"]) if value["min"] == value["max"] else f'{value["min"]}–{value["max"]}'


def dismantle_amount_text(material):
    if "amount_values" in material:
        values = material["amount_values"]
        if material.get("chance_percent", 100) < 100 and values[0] != 0:
            values = [0] + values
        return ' / '.join(str(value) for value in values)
    value = amount_text(material["amount"])
    return '0 / ' + value if material.get("chance_percent", 100) < 100 and material["amount"]["min"] is not None else value


def dismantle_probability_text(base, material):
    extra = material.get("use_extra_quantity_bonus", False)
    chance = base["dismantle_profile"]["extra_quantity_chance_percent"] if extra else material.get("chance_percent", 100)
    if chance == 100:
        return ''
    return f'{chance}%'


def dismantle_note(base, material):
    notes = []
    if material.get("chance_percent", 100) < 100:
        notes.append(f'产出概率{material["chance_percent"]}%。')
    if material.get("use_extra_quantity_bonus"):
        chance = base["dismantle_profile"]["extra_quantity_chance_percent"]
        notes.append(f'额外产出概率{chance}%。')
    return ''.join(notes)


def validate_base(data):
    require(data.get("schema_version") == 2 and set(data.get("部位", {})) == set(EQUIPMENT_SLOTS), "普通装备规则必须明确列出六个 canonical 部位 ID")
    if "dismantle_profile" in data:
        profile = data["dismantle_profile"]
        require(set(profile) == {"item_level", "quality", "perk_level", "event_multiplier", "extra_quantity_chance_percent", "display"}, "分解适用条件字段不完整")
        require(all(type(profile[key]) is int for key in ("item_level", "perk_level", "event_multiplier")), "分解等级、专长及倍率须为整数，不能用布尔值")
        require(profile["item_level"] == 40 and profile["quality"] == "Orange" and profile["perk_level"] == 2 and profile["event_multiplier"] == 1, "当前分解规则仅核对40级金装、满级拆解专长和无活动倍率")
        require(type(profile["extra_quantity_chance_percent"]) is int and 0 <= profile["extra_quantity_chance_percent"] <= 100, "额外数量概率须为0至100的整数")
        require(plain(profile["display"], "分解适用条件").strip(), "分解适用条件不能为空")
    if "major_display_values" in data:
        values = data["major_display_values"]
        require(isinstance(values, dict) and set(values) == set(COLORS), "主属性展示值须对应三种既有核心")
        for value in values.values():
            require(plain(value, "主属性展示值").strip(), "主属性展示值不能为空")
    # Legacy rule documents may omit expertise; never infer numbers from slot notes.
    if "expertise" in data:
        expertise = data["expertise"]
        require(isinstance(expertise, dict) and set(expertise) == {"armor_bonus_per_level_percent", "max_level"}, "expertise 必须完整包含每级基础装甲百分比与等级上限")
        for key, value in expertise.items():
            require(type(value) is int and value > 0, "expertise." + key + " 必须为正整数，不能为布尔值")
    fields = set(COUNT_FIELDS) | {"base_armor", "talent_description", "specialization_note", "dismantle", "verification", "sources"}
    for slot, rule in data["部位"].items():
        require(set(rule) in (fields, fields | {'talent_pool'}), slot + "规则字段缺失或拼写错误")
        require(rule.get('talent_pool') in (None, 'chest', 'backpack'), '普通随机天赋池须为 chest/backpack 或 null')
        require(not rule.get('talent_pool') or rule['talent_slot_count'] not in (None, 0), '天赋池必须有普通天赋槽；不约束具名固定天赋引用')
        for key in tuple(COUNT_FIELDS) + ("base_armor",):
            count(rule[key])
        for key in ("talent_description", "specialization_note"):
            require(rule[key] is None or isinstance(rule[key], str), "规则说明用文本或 null")
            if rule[key] is not None:
                plain(rule[key], "规则说明")
        dismantle = rule["dismantle"]
        require(set(dismantle) in ({"brand_material_amount", "fixed_materials"}, {"brand_material_amount", "fixed_materials", "chance_materials"}), "分解规则字段不完整")
        amount(dismantle["brand_material_amount"])
        require(dismantle["fixed_materials"] is None or isinstance(dismantle["fixed_materials"], list), "固定材料未知为 null，确认无材料为 []")
        chance_materials = dismantle.get("chance_materials", [])
        require(isinstance(chance_materials, list), "概率材料须为列表")
        for material in list(dismantle["fixed_materials"] or []) + chance_materials:
            require({"name", "amount"} <= set(material) <= {"id", "name", "amount", "chance_percent", "requires_perk_level", "base_amount", "use_extra_quantity_bonus", "amount_values"} and plain(material["name"], "材料名").strip(), "材料字段无效或名称为空")
            if 'id' in material:
                require(isinstance(material['id'], str) and re.fullmatch(r'[a-z][a-z0-9_]*', material['id']), '材料 ID 必须是稳定英文键，不以中文名猜图标')
            amount(material["amount"])
            if "amount_values" in material:
                values = material["amount_values"]
                require(isinstance(values, list) and values and all(type(value) is int and value >= 0 for value in values), "离散产出数量须为非空非负整数列表")
                require(values == sorted(set(values)) and material["amount"] == {"min": values[0], "max": values[-1]}, "离散产出数量须升序且不重复，min/max与首尾值一致")
            chance = material.get("chance_percent", 100)
            require(type(chance) is int and 0 < chance <= 100, "材料概率须为1至100的整数")
            require((material in chance_materials) == (chance < 100), "概率材料与固定材料须分别维护")
            require(type(material.get("requires_perk_level", 0)) is int and 0 <= material.get("requires_perk_level", 0) <= 2, "材料专长条件须为0至2级")
            if "use_extra_quantity_bonus" in material:
                require(type(material["use_extra_quantity_bonus"]) is bool, "额外数量开关须为布尔值")
            if "base_amount" in material:
                count(material["base_amount"])
                require(material["base_amount"] is not None, "原生基础数量不能为null")
            if material.get("use_extra_quantity_bonus"):
                require("dismantle_profile" in data and "base_amount" in material, "额外数量规则须有基础数量及专长条件")
        require(rule["verification"] in ("NEEDS GAME-DATA VERIFICATION", "待核实", "已核实"), "请填写规则内部核实状态")
        require(isinstance(rule["sources"], list) and all(isinstance(s, str) and s.startswith("https://") for s in rule["sources"]), "规则来源使用 HTTPS 列表")
        require(rule["verification"] != "已核实" or rule["sources"], "已核实规则必须有来源")
    return data


def ui_raster(icon, allow_local=False):
    # Local readiness never means Wiki publication; all other roles keep raster().
    if 'local_asset' not in icon:
        return raster(icon)
    require(allow_local and set(icon) == {'wiki_file', 'confirmed_on_wiki', 'local_asset'}, 'LOCAL_ICON_SCOPE')
    require(type(icon['confirmed_on_wiki']) is bool, 'LOCAL_ICON_PUBLICATION_STATE')
    validate_image_filename(icon['wiki_file'])
    asset = icon['local_asset']
    require(isinstance(asset, dict) and set(asset) == {'source', 'sha256'}, 'LOCAL_ICON_METADATA')
    require(asset['source'] == 'assets/' + icon['wiki_file'], 'LOCAL_ICON_SOURCE')
    require(isinstance(asset['sha256'], str) and re.fullmatch(r'[0-9a-f]{64}', asset['sha256']), 'LOCAL_ICON_HASH')


def validate_ui(data):
    require(data.get("schema_version") == 2 and set(data.get("major_names", {})) == set(COLORS), "主属性中文名称映射须完整")
    for name in data["major_names"].values():
        require(plain(name, "主属性名称").strip(), "主属性中文名称不能为空")
    require(set(data.get("icons", {})) == set(ROW_KEYS), "装备行图标入口须完整")
    for key, icon in data["icons"].items():
        ui_raster(icon, allow_local=key == "major_attribute")
    if 'state_icons' in data:
        require(set(STATE_KEYS) <= set(data['state_icons']) <= set(STATE_KEYS + OPTIONAL_STATE_KEYS), '状态图标须包含五种原状态，其他状态须为已登记的专用键')
        for key, icon in data['state_icons'].items(): ui_raster(icon, allow_local=key in OPTIONAL_STATE_KEYS or key == 'none')
    for key, icon in data.get('weapon_icons', {}).items():
        require(key in {'core_attribute','attribute','muzzle','optics','underbarrel','magazine',
                        'ammo_ar','ammo_rifle','ammo_marksman','ammo_smg','ammo_lmg','ammo_shotgun','ammo_pistol',
                        'ammo_signature_gl','ammo_signature_flamethrower','ammo_signature_gunner',
                        'ammo_signature_marksman','ammo_signature_crossbow','ammo_signature_technician'},
                '武器图标须使用已登记的 UI 角色')
        raster(icon)
    for key, icon in data.get('material_icons', {}).items():
        require(isinstance(key, str) and re.fullmatch(r'[a-z][a-z0-9_]*', key), '材料图标必须用稳定键')
        raster(icon)
    for name, info in data.get('material_display', {}).items():
        require(plain(name, '材料展示名称').strip() and set(info) - {'native','page_ref','name','aliases'} in ({'icon_key', 'quality', 'quality_evidence'}, {'icon_key', 'quality', 'quality_evidence', 'brand_ref'}), '材料展示映射字段不完整')
        if 'brand_ref' in info:
            require(plain(info['brand_ref'], '材料关联品牌').strip(), '材料关联品牌不能为空')
        if 'native' in info:
            require('brand_ref' in info and set(info['native']) == {'currency_uid', 'name_guid', 'gearbrand_uid'}, '品牌材料原生关联字段不完整')
            require(all(isinstance(value, str) and re.fullmatch(r'[0-9A-F]{32}', value) for value in info['native'].values()), '品牌材料原生ID无效')
        require(info['icon_key'] in data.get('material_icons', {}), '材料展示图标键不存在')
        require(info['quality'] in {'gray', 'green', 'blue', 'high_end'} and isinstance(info['quality_evidence'], str) and info['quality_evidence'], '材料展示品质须有依据')
    if 'talent_pools' in data:
        require(set(data['talent_pools']) == {'chest', 'backpack'}, '普通天赋池配置须包含胸甲与背包')
        for info in data['talent_pools'].values():
            require(set(info) == {'label', 'target'} and plain(info['label'], '天赋池显示名').strip(), '天赋池只维护显示名和可选页面/章节目标')
            target = plain(info['target'], '天赋池目标')
            require(not target or (target == target.strip() and not target.startswith(('#', 'http:', 'https:')) and target.count('#') <= 1 and not target.endswith('#')), '天赋池目标填写 Wiki 页面或页面#章节，不填外部 URL')
    require(set(data.get("slot_visuals", {})) == set(SLOT_VISUAL_KEYS.values()), "六张通用部位图片映射须完整")
    for icon in data["slot_visuals"].values():
        raster(icon)
    return data


def load_equipment(root):
    import hashlib
    from tools.publish.bundle import is_within
    ui = read_json(root / "data/brand-sets/equipment-ui.json")
    if (root / 'data/equipment/attributes.json').is_file():
        shared=read_json(root / 'data/equipment/attributes.json')
        for rule in shared.get('rules', []):
            identity=shared.get('identities', {}).get(rule['attribute_id'])
            if rule['kind']=='core' and identity:ui['major_names'][rule['core_type']]=identity.get('display_alias') or identity['zh_name']
    ui = validate_ui(ui)
    for group in ('icons', 'state_icons'):
        for icon in ui.get(group, {}).values():
            if 'local_asset' in icon:
                asset = icon['local_asset']
                path = root / asset['source']
                require(is_within(path, root / 'assets') and path.is_file() and not path.is_symlink(), 'LOCAL_ICON_MISSING_OR_UNSAFE')
                require(hashlib.sha256(path.read_bytes()).hexdigest() == asset['sha256'], 'LOCAL_ICON_BYTES_CHANGED')
    return (validate_base(read_json(root / "data/brand-sets/equipment-base-rules.json")), ui)


IMAGE_CATEGORIES = {'Brand','GearSet','Talent','Attribute','Weapon','Gear','Skill','Material','UI','Status'}
IMAGE_PURPOSES = {'Logo', 'Icon', 'Background', 'Pattern'}
IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif'}


def image_label(name):
    plain(name, "批准的图片命名标签")
    require(not any(unicodedata.category(c) in ('Cc', 'Cf') for c in name), 'IMAGE_LABEL_CONTROL')
    require(not re.search(r'[\\/:*?"%#<>\[\]{}|]', name), 'IMAGE_LABEL_INVALID_CHARACTER')
    label = ' '.join(unicodedata.normalize('NFC', name).replace('_', ' ').split())
    require(not re.search(r'\.(png|jpe?g|webp|gif|bmp|svg|ico)$', label, re.I), 'IMAGE_LABEL_ALREADY_HAS_EXTENSION')
    return label


def validate_image_filename(filename):
    from tools.asset_import.static_formats import safe_relative
    require(isinstance(filename, str) and filename == unicodedata.normalize('NFC', filename), 'IMAGE_FILENAME_NFC')
    require(len(safe_relative(filename).parts) == 1 and filename == filename.strip(), 'IMAGE_FILENAME_PATH')
    stem, dot, extension = filename.rpartition('.')
    require(dot and extension in IMAGE_EXTENSIONS and stem, 'IMAGE_FILENAME_EXTENSION')
    require(image_label(stem) == stem, 'IMAGE_FILENAME_NORMALIZATION')
    require(len(filename.encode('utf-8')) <= 240, 'IMAGE_FILENAME_TOO_LONG')
    return filename


def asset_image_name(category, approved_label, purpose, extension='png', *, subtype='', owner=''):
    """Generate a candidate from verified English; never infer a game identity."""
    require(category in IMAGE_CATEGORIES and purpose in IMAGE_PURPOSES and extension in IMAGE_EXTENSIONS, 'IMAGE_NAMING_CATEGORY_OR_PURPOSE')
    def token(value):
        require(isinstance(value, str), 'IMAGE_LABEL_TEXT_REQUIRED')
        # Native color markup affects presentation, never the visible name.
        value=re.sub(r'''<color\s+name\s*=\s*["“”'][A-Za-z0-9_]+(?: +[A-Za-z0-9_]+)*["“”']\s*>|</color\s*>''', '', value, flags=re.I)
        # Both punctuation marks separate words in the game's English labels.
        value=image_label(value.replace(':', ' ').replace('–', '-'))
        # Possessives and contractions stay one word; preserve their letter case.
        value=value.translate(str.maketrans('', '', "'‘’ʼ"))
        value=unicodedata.normalize('NFKD',value)
        value=''.join(c for c in value if not unicodedata.combining(c))
        require(value.isascii() and value.strip(), 'IMAGE_ENGLISH_LABEL_REQUIRED')
        words=re.findall(r'[A-Za-z0-9]+',value.replace('&',' And '))
        require(words,'IMAGE_LABEL_EMPTY')
        return ''.join(w[0].upper()+w[1:] for w in words)
    fields=[category]+([token(subtype)] if subtype else [])+([token(owner)] if owner else [])+[token(approved_label),purpose]
    return validate_image_filename('TD2-'+'-'.join(fields)+'.'+extension)


def brand_image_name(name, ui):
    return asset_image_name('Brand',name,'Logo') if name.strip() else ''


def blueprints(value):
    """tokens 的分号序列或离线逐条列表；只 trim、过滤空项，不猜关系或 ID。"""
    require(isinstance(value, (str, list)), "图纸必须是文本列表")
    if isinstance(value, str) and value.strip() == "无制作图纸": return []
    values = value.split(";") if isinstance(value, str) else value
    result = []
    for entry in values:
        require(isinstance(entry, str), "图纸名称须为文本")
        entry = entry.strip()
        if entry:
            plain(entry, "图纸名称")
            result.append(entry)
    return result


def colors(value):
    values = value.split(";") if isinstance(value, str) and value else []
    require(len(set(values)) == len(values) and all(v in COLORS for v in values), "主属性只能选择不重复的红／蓝／黄；空选为未知")
    return values


def enabled(params, name):
    require(params.get(name, "") in ("", "是", "否"), "例外须明确为是／否")
    return params.get(name) == "是"


ALL_MAJOR_CORES = ('red', 'blue', 'yellow')
MAJOR_MODES = ('使用部位设置', '单核心', '同时拥有三种主核心')


def brand_triple(params):
    require(not any(slot + '同时拥有主核心' in params for slot in EQUIPMENT_SLOTS if slot != 'backpack'), '同时三核心仅适用于已登记的背包')
    triple = enabled(params, 'backpack同时拥有主核心')
    require(not triple or (enabled(params, '部分部位主属性不同') and enabled(params, 'backpack使用不同规则')), '关闭背包例外前，请先恢复单核心')
    return triple


def brand_major(params, slot):
    require(slot in EQUIPMENT_SLOTS, "部位不合法")
    if brand_triple(params) and slot == "backpack":
        colors(params.get("backpack允许主核心", ""))  # 保留非活动选择，但不能保存未知/重复类型。
        return list(ALL_MAJOR_CORES)
    if enabled(params, slot + "使用不同规则"):
        require(enabled(params, "部分部位主属性不同"), "先启用部分部位主属性不同")
        result = colors(params.get(slot + "允许主核心", ""))
        require(result, "请选择该装备允许的主属性。")
        return result
    require(not params.get(slot + "允许主核心", ""), "未启用部位例外却填写主属性")
    return colors(params.get("默认允许主核心", ""))


def is_unbranded(params):
    require(params.get("资料类型", "") in ("", "brand", "unbranded"), "资料类型不合法")
    return params.get("资料类型") == "unbranded"


def validate_brand_fields(params):
    enabled(params, "部分部位主属性不同")
    require(colors(params.get("默认允许主核心", "")), "请选择该装备允许的主属性。")
    for slot in EQUIPMENT_SLOTS:
        brand_major(params, slot)
        blueprints(params.get(slot + "图纸", ""))
        mod_count = params.get(slot + "插件槽数", "")
        require(not mod_count or re.fullmatch(r"[0-9]+", mod_count), "普通装备插件槽数须为非负整数，0 合法")
        require(not is_unbranded(params) or mod_count != "", "无品牌装备须明确六部位插件槽数")
    plain(params.get("品牌分解材料", ""), "品牌分解材料")
    if is_unbranded(params):
        require(not params.get("品牌分解材料", ""), "无品牌装备不使用品牌分解材料")
        require(not params.get("具名装备资料", "").strip(), "无品牌装备资料不包含具名装备")
        for count in (1, 2, 3):
            for mode in ("PvE", "PvP"):
                prefix = f"{count}件{mode}"
                require(not any(params.get(prefix + field, "") for field in ("词条", "数值", "单位", "特殊说明", "特殊原因"))
                        and params.get(prefix + "使用特殊数值", "") in ("", "否")
                        and params.get(prefix + "状态", "") in ("", "暂无数据", "不适用"), "无品牌装备不使用套装加成")


def validate_equipment_fields(params):
    mode = params.get("talent_mode", "none")
    require(mode in ("none", "random_chest", "random_backpack", "fixed"), "天赋位状态不合法")
    if mode in ("random_chest", "random_backpack"):
        require(params.get("装备部位") == mode.removeprefix("random_"), "随机天赋类型与装备部位不符")
    require(not any(k in params for k in ("天赋位数", "天赋位例外")), "具名天赋位使用 talent_mode，不使用结构例外")
    require(not any(k in params for k in ("主属性槽数", "主属性槽例外")), "主核心数量由类型与组合方式推导，不再手填")
    combination = params.get("主核心组合") or "使用部位设置"
    require(combination in MAJOR_MODES, "主核心组合无效")
    require(combination != "同时拥有三种主核心" or params.get("装备部位") == "backpack", "只有背包可设置主核心组合；更换部位前请恢复使用部位设置")
    if combination == "单核心":
        require(colors(params.get("允许主核心", "")), "请选择该装备允许的主属性。")
    for key, label in COUNT_FIELDS.items():
        if key in ("talent_slot_count", "major_core_slots"): continue
        value = params.get(label, "")
        if enabled(params, EXCEPTION_FLAGS[key]):
            require(isinstance(value, str) and re.fullmatch(r"\d+", value), "启用槽数例外后须填写非负整数，0 合法")
        else:
            require(value == "", "未启用槽数例外却填写数据")


def resolve_equipment(base, brand, slot, equipment=None):
    result = copy.deepcopy(base["部位"][slot])
    if is_unbranded(brand):
        result.update(talent_slot_count=0, talent_pool=None, talent_description="无天赋槽位")
    result["allowed_major_cores"] = brand_major(brand, slot)
    mod_count = brand.get(slot + "插件槽数", "")
    if mod_count != "":
        require(re.fullmatch(r"[0-9]+", mod_count), "普通装备插件槽数须为非负整数，0 合法")
        result["mod_slot_count"] = int(mod_count)
    simultaneous = slot == "backpack" and brand_triple(brand)
    if equipment:
        validate_equipment_fields(equipment)
        combination = equipment.get("主核心组合") or "使用部位设置"
        if combination != "使用部位设置": simultaneous = combination == "同时拥有三种主核心"
        require(not simultaneous or slot == "backpack", "三核心仅适用于背包")
        if simultaneous:
            result["allowed_major_cores"] = list(ALL_MAJOR_CORES)
        elif combination == "单核心":
            result["allowed_major_cores"] = colors(equipment.get("允许主核心", ""))
        mode = equipment.get("talent_mode", "none")
        result["talent_slot_count"] = 0 if mode == "none" else 1
        result["talent_description"] = {"none":"无天赋槽位", "random_chest":"随机胸甲天赋槽位", "random_backpack":"随机背包天赋槽位", "fixed":"固定天赋待选择"}[mode]
        result["talent_pool"] = {"random_chest":"chest", "random_backpack":"backpack"}.get(mode)
        for key, label in COUNT_FIELDS.items():
            if key in ("talent_slot_count", "major_core_slots"): continue
            if enabled(equipment, EXCEPTION_FLAGS[key]):
                result[key] = int(equipment[label])
    result["major_core_mode"] = "all" if simultaneous else "random_one"
    cores = result["allowed_major_cores"]
    require(not simultaneous or cores, "同时拥有主核心时须填写主核心类型")
    result["major_core_slots"] = (len(cores) if simultaneous else 1) if cores else None
    return result


def dismantle_entries(base, brand_material, slot, ui):
    rule = base["部位"][slot]["dismantle"]
    rows = list(rule["fixed_materials"] or []) + rule.get("chance_materials", [])
    if brand_material.strip(): rows.append({"name": brand_material.strip(), "amount": rule["brand_material_amount"], "brand": True})
    order = {quality: index for index, quality in enumerate(('gray', 'green', 'blue', 'high_end'))}
    return sorted(rows, key=lambda item: order.get('high_end' if item.get('brand') else ui.get('material_display', {}).get(item.get('id'), {}).get('quality'), len(order)))


def dismantle_materials(base, brand_material, slot, ui):
    rule = base["部位"][slot]["dismantle"]
    rows = [(item["name"], dismantle_amount_text(item)) for item in dismantle_entries(base, brand_material, slot, ui)]
    if rule["fixed_materials"] is None:
        rows.append(("固定分解材料", "待核实"))
    return rows


def craftable_slots(params):
    """只由过滤后的图纸派生，不读取旧制作布尔值或部位集合。"""
    return [slot for slot in EQUIPMENT_SLOTS if blueprints(params.get(slot + "图纸", ""))]
