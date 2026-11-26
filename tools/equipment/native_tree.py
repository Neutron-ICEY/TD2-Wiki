"""Scoped Fruit blocks for UID-less crafting, reward and loot definitions.

This reader retains explicit fields and nested conditions. It does not evaluate
unknown game syntax or turn a loot tag into an availability assertion.
"""
import re


def parse(text):
    root={'header':'root','properties':[],'children':[],'line':0};stack=[root]
    for number,line in enumerate(text.splitlines(),1):
        value=line.strip()
        if not value or value.startswith('//'):continue
        if value=='{':
            if not stack[-1]['properties']:raise ValueError('Native block without header')
            header,location=stack[-1]['properties'].pop()
            node={'header':header,'line':location,'properties':[],'children':[]}
            stack[-1]['children'].append(node);stack.append(node)
        elif value=='}':
            if len(stack)==1:raise ValueError('Unbalanced native block')
            stack.pop()
        else:stack[-1]['properties'].append((value,number))
    if len(stack)!=1:raise ValueError('Unclosed native block')
    return root


def walk(node):
    for child in node['children']:
        yield child
        yield from walk(child)


def child(node,name):
    rows=[c for c in node['children'] if c['header']==name]
    if len(rows)>1:raise ValueError('Duplicate native member: '+name)
    return rows[0] if rows else None


def prop(node,name,default=None):
    values=[text[len(name)+1:] for text,_ in node['properties'] if text.startswith(name+' ')]
    if len(values)>1:raise ValueError('Duplicate native property: '+name)
    return values[0] if values else default


def reference(value):
    match=re.fullmatch(r'<\s*uid=[A-Fa-f0-9]{32}\s*>\s*=\s*(.+)\s+([A-Fa-f0-9]{32})',value or '')
    if not match:raise ValueError('Unsupported native reference: '+str(value))
    return {'name':match[1],'uid':match[2].upper()}


def tags(node,name):
    row=child(node,name)
    if row is None:return []
    result=[]
    for text,_ in row['properties']:
        match=re.fullmatch(r'ItemTag (?:"[^"]*"|\S+) (\S+)',text)
        if not match:raise ValueError('Unsupported native tag: '+text)
        result.append(match[1])
    return result


def semantic(node):
    """Locations and editor-only object labels do not affect rule fingerprints."""
    if '\ufffd' in node['header'] or any('\ufffd' in p for p,_ in node['properties']):raise ValueError('Invalid UTF-8 in native rule')
    return {'type':node['header'].split()[0], 'properties':[p for p,_ in node['properties']],
            'children':[semantic(c) for c in node['children']]}
