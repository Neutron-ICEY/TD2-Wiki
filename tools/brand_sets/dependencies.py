"""Literal Template and Lua dependencies for offline review plans."""
import re

CALL = re.compile(r'(?<!\{)\{\{(?!\{)(\s*)([^{}\n|]+?)(?=\s*(?:\||\}\}))')
LUA_TEMPLATE = re.compile(r"(\bexpandTemplate\s*\{\s*title\s*=\s*)(['\"])([^'\"]+)\2")


def active_wikitext(text):
    return re.sub(r'<!--.*?-->|<(?:nowiki|pre|syntaxhighlight|source)\b[^>]*?/\s*>'
                  r'|<(nowiki|pre|syntaxhighlight|source)\b[^>]*>.*?</\1\s*>', '', text, flags=re.S | re.I)


def dependencies(text):
    """Return literal dependencies without treating displayed examples as calls."""
    text = active_wikitext(text)
    result = set()
    for match in CALL.finditer(text):
        name = match[2].strip()
        if name.startswith('#invoke:'):
            result.add(('module', name.split(':', 1)[1].strip()))
        elif not (name.startswith('#') or name.startswith('padleft:') or name in ('PAGENAME', '!')):
            result.add(('template', re.sub(r'^(?:模板|Template):', '', name)))
    result.update(('module', name) for name in re.findall(r"mw\.loadData\(['\"](?:Module|模块):([^'\"]+)['\"]\)", text))
    result.update(('module', name) for name in re.findall(r"\brequire\s*(?:\(\s*)?['\"](?:Module|模块):([^'\"]+)['\"]", text))
    result.update(('template', m[3]) for m in LUA_TEMPLATE.finditer(text))
    return result
