"""Local template expansion boundary; Lua modules execute through LuaBoundary."""

import re
from functools import lru_cache
from datetime import date, datetime, timezone
from html import escape


@lru_cache(maxsize=4096)
def named_argument(part):
    # 只有参数顶层的=才分隔name/value。嵌套#switch/#if的=不把
    # TD2主属性列表的第1个位置参数错误变成具名参数。
    stack, pos = [], 0
    while pos < len(part):
        if part.startswith('{{', pos):
            width = 3 if part.startswith('{{{', pos) else 2
            stack.append(width); pos += width
        elif stack and part.startswith('}' * stack[-1], pos):
            pos += stack.pop()
        elif part.startswith('[[', pos):
            end = part.find(']]', pos)
            if end < 0: raise AssertionError('未闭合链接')
            pos = end + 2
        elif part[pos] == '=' and not stack:
            return part[:pos], part[pos+1:]
        else: pos += 1
    return None


@lru_cache(maxsize=1024)
def segments(source):
    """Cache syntax only. Arguments, Lua, references and selected branches are evaluated each time."""
    def node(pos, width):
        parts, begin = [], pos
        while pos < len(source):
            if source.startswith("}" * width, pos):
                parts.append(source[begin:pos])
                return parts, pos + width
            if source.startswith("{{", pos):
                _, pos = node(pos + (3 if source.startswith("{{{", pos) else 2), 3 if source.startswith("{{{", pos) else 2)
            elif source.startswith("[[", pos):
                end = source.find("]]", pos)
                if end < 0: raise AssertionError("未闭合链接")
                pos = end + 2
            elif source[pos] == "|":
                parts.append(source[begin:pos]); pos += 1; begin = pos
            else: pos += 1
        raise AssertionError("未闭合调用")

    chunks = []
    position = 0
    while position < len(source):
        opening = source.find('{{', position)
        if opening < 0:
            chunks.append(source[position:])
            break
        if opening > position:
            chunks.append(source[position:opening])
        width = 3 if source.startswith('{{{', opening) else 2
        parts, position = node(opening + width, width)
        chunks.append((tuple(parts), width))
    return tuple(chunks)


class WikiSubset:
    def __init__(self, root, existing_files=(), sources=None, acquisition=None, projection_modules=("TD2品牌投影",), *, today=None):
        self.root = root
        self.existing_files = set(existing_files)
        self.sources = sources or {}
        self._disk_templates = {}
        self.acquisition = acquisition or {"methods": []}
        self.projection_modules = projection_modules
        self.infobox_calls = []
        self.ref_calls = []
        self.template_frames = []
        self.today = today or datetime.now(timezone.utc)

    def template(self, name, params):
        name = re.sub(r'^(?:模板|Template):', '', name)
        if name == 'Infobox':
            # 站点基础是外部边界：断言分支参数即可，实际空行/表格由站点重测。
            self.infobox_calls.append(dict(params))
            numbered = sorted((key for key in params if re.fullmatch(r'data\d+', key)), key=lambda key:int(key[4:]))
            return '\n'.join(params.get(key, '') for key in ('title', 'subheader', 'image', *numbered) if params.get(key, ''))
        relative = "wiki/templates/" + name + ".wiki"
        source = self.sources.get(relative)
        if source is None:
            if relative not in self._disk_templates:
                self._disk_templates[relative] = (self.root / relative).read_text(encoding="utf-8")
            source = self._disk_templates[relative]
        source = re.sub(r"<noinclude>.*?</noinclude>", "", source, flags=re.S)
        source = re.sub(r"<!--.*?-->", "", source, flags=re.S)
        source = source.replace("<includeonly>", "").replace("</includeonly>", "")
        self.template_frames.append((name, params))
        try:
            return self.expand(source, params)
        finally:
            self.template_frames.pop()

    def expand(self, source, params):
        if '{{' not in source:
            return source

        def evaluate(parts, width):
            expand = lambda x: self.expand(x, params)
            head = expand(parts[0]).strip()
            branch = lambda n: expand(parts[n]) if len(parts) > n else ""
            if width == 3:
                return params[head] if head in params else branch(1)
            if head == "PAGENAME": return "试验品牌"
            if head == "#time:U":
                if len(parts) > 1:
                    try:
                        instant = datetime.fromisoformat(branch(1).strip())
                    except ValueError:
                        return "无效时间"
                else:
                    instant = self.today if isinstance(self.today, datetime) else datetime.combine(self.today, datetime.min.time())
                if instant.tzinfo is None:
                    instant = instant.replace(tzinfo=timezone.utc)
                return str(int(instant.timestamp()))
            if head in ("#time:Ymd", "#time:n月j日"):
                day = date.fromisoformat(branch(1).strip()) if len(parts) > 1 else self.today
                return day.strftime("%Y%m%d") if head == "#time:Ymd" else f"{day.month}月{day.day}日"
            if head == '#tag:ref':
                attributes = {}
                for part in parts[2:]:
                    argument = named_argument(part)
                    if argument is None or argument[0].strip() != 'name':
                        raise AssertionError('未声明的 ref 属性边界')
                    attributes['name'] = expand(argument[1]).strip()
                body = expand(branch(1))
                self.ref_calls.append(dict(body=body, attributes=attributes))
                name = ' name="' + escape(attributes['name'], quote=True) + '"' if attributes.get('name') else ''
                return '<ref' + name + '>' + body + '</ref>'
            if head.startswith("#if:"):
                return branch(1 if head[4:].strip() else 2)
            if head.startswith("#ifexist:"):
                return branch(1 if head[9:] in self.existing_files else 2)
            if head.startswith("#switch:"):
                matched, fallback = False, ''
                for part in parts[1:]:
                    case = named_argument(part)
                    if case:
                        key, value = case
                        if matched or expand(key).strip() == head[8:].strip(): return expand(value).strip()
                        if key.strip() == '#default': fallback = value
                    else:
                        matched = matched or expand(part).strip() == head[8:].strip()
                return expand(fallback).strip()
            if head.startswith("#arraymap:"):
                return (branch(4) if len(parts) > 4 else ", ").join(expand(parts[3].replace(parts[2], v.strip())) for v in head[10:].split(branch(1)) if v.strip())
            if head.startswith("#expr:"):
                expression = head[6:]
                if not re.fullmatch(r"[0-9 *+()-]+", expression): raise AssertionError("不支持的表达式")
                return str(eval(expression, {"__builtins__": {}}, {}))
            if head.startswith("#ifexpr:"):
                left, right = head[8:].split(">")
                return branch(1 if int(left) > int(right) else 2)
            if head.startswith("padleft:"):
                text, size, pad = head[8:], min(500, int(branch(1))), branch(2) or "0"
                return (pad * (size // len(pad) + 1))[:max(0, size-len(text))] + text
            if head.startswith('#invoke:'):
                args, ordinal = {}, 1
                for part in parts[2:]:
                    named = named_argument(part)
                    if named:
                        key, value = named; args[key.strip()] = expand(value).strip()
                    else:
                        args[str(ordinal)] = expand(part).strip(); ordinal += 1
                if not hasattr(self,'lua_boundary'):
                    from tools.equipment.lua import LuaBoundary
                    self.lua_boundary=LuaBoundary(self)
                parent=self.template_frames[-1][1] if self.template_frames else args
                return self.lua_boundary.invoke(head[8:],branch(1),args,parent)
            nested, ordinal = {}, 1
            for part in parts[1:]:
                named = named_argument(part)
                if named:
                    key, value = named; nested[key.strip()] = expand(value).strip()
                else:
                    nested[str(ordinal)] = expand(part).strip(); ordinal += 1
            return self.template(head, nested)

        return ''.join(item if isinstance(item, str) else evaluate(*item) for item in segments(source))
