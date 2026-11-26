"""集中规则投影成小型 #switch 模板；不把业务逻辑塞入页面调用。"""

from .knowledge import COLORS
from .icons import call


def talent_detail(title, description, icon):
    return '<div class="td2-talent-detail"><div class="td2-talent-copy"><span class="td2-talent-title">' + title + '</span>' + description + '</div>' + ('<div class="td2-talent-icon">' + icon + '</div>' if icon else '') + '</div>'


def knowledge_sources():
    from .build import GENERATED, HEADER, switch_template
    content = talent_detail('{{{名称|}}}', '{{#if:{{{描述|}}}|<div class="td2-talent-description">{{{描述}}}</div>}}', '{{{图标内容|}}}')
    content = content.replace('<div class="td2-talent-icon">{{{图标内容|}}}</div>', '{{#if:{{{图标内容|}}}|<div class="td2-talent-icon">{{{图标内容}}}</div>}}')
    talent_source = '<noinclude>' + HEADER + '</noinclude><includeonly>{{#if:{{{名称|}}}|' + content + '}}</includeonly>'
    return {
        GENERATED["brand-talent-data"]: talent_source,
        GENERATED["brand-core-color"]: switch_template(COLORS, "待核实"),
        GENERATED["brand-core-icon"]: switch_template({kind + "/" + c: call('core_' + kind, c) + label for kind in ("major", "minor") for c, label in COLORS.items()}, "待核实").replace("{{{1|}}}", "{{{类型|}}}/{{{颜色|}}}"),
    }
