"""Validate the small descriptors of explicitly excluded map settings layers."""
import hashlib
import json
import os
from pathlib import Path
import re

from . import child, linked, require


TOKENS = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/|#[0-9a-fA-F]{32}\b|[a-zA-Z_]\w*|[^\s]')


def header_identity(blob):
    """Read only root.header.type/uid; nested or quoted headers cannot authorize pruning.

    Layer descriptors use Hunter's brace/assignment text, not JSON or Fruit.
    Tokenizing strings/comments avoids interpreting braces inside them as scopes.
    """
    tokens = (m.group() for m in TOKENS.finditer(blob.decode('utf-8-sig'))
              if not m.group().startswith(('//', '/*')))
    depth = headers = 0
    in_header = False
    fields = {}
    require(next(tokens, None) == '{', 'INVALID_LAYER_DESCRIPTOR')
    depth = 1
    for token in tokens:
        require(depth > 0 and token not in ('"', '/'), 'INVALID_LAYER_DESCRIPTOR')
        if depth == 1 and token == 'header':
            require(next(tokens, None) == '=' and next(tokens, None) == '{', 'INVALID_LAYER_HEADER')
            headers += 1
            require(headers == 1, 'AMBIGUOUS_LAYER_HEADER')
            depth += 1
            in_header = True
        elif in_header and depth == 2 and token in ('type', 'uid'):
            require(token not in fields and next(tokens, None) == '=', 'AMBIGUOUS_LAYER_FIELD')
            value = next(tokens, '')
            if token == 'type':
                require(value.startswith('"'), 'INVALID_LAYER_TYPE')
                fields[token] = json.loads(value)
            else:
                require(re.fullmatch(r'#[0-9a-fA-F]{32}', value), 'INVALID_LAYER_UID')
                fields[token] = value[1:].lower()
        elif token == '{':
            depth += 1
        elif token == '}':
            depth -= 1
            if depth == 1:
                in_header = False
    require(depth == 0 and headers == 1 and set(fields) == {'type', 'uid'}, 'INCOMPLETE_LAYER_HEADER')
    return fields


def inspect_layers(source, selection):
    """No traversal: check each configured layer path and at most one file in it.

    Missing layers are frozen as absent. A later appearance, disappearance or
    descriptor change invalidates the plan even though its payload is excluded.
    """
    result = {}
    for name, kind in selection.get('layer_types', {}).items():
        directory = child(source, name)
        if not directory.exists():
            result[name] = None
            continue
        require(directory.is_dir(), 'LAYER_PATH_KIND_CHANGED: ' + name)
        path = child(source, name + '/layerdata.mlayer')
        require(path.is_file(), 'LAYER_DESCRIPTOR_MISSING: ' + name)
        before = path.stat(follow_symlinks=False)
        with path.open('rb') as stream:
            opened = os.fstat(stream.fileno())
            blob = stream.read()
            closed = os.fstat(stream.fileno())
        after = path.stat(follow_symlinks=False)
        identity = lambda info: (info.st_size, info.st_mtime_ns, info.st_ino)
        require(not linked(after) and identity(before) == identity(opened) == identity(closed) == identity(after)
                and len(blob) == after.st_size, 'LAYER_CHANGED_DURING_READ: ' + name)
        header = header_identity(blob)
        require(header['type'] == kind, 'LAYER_TYPE_MISMATCH: ' + name)
        require(header['uid'] == Path(name).name.casefold(), 'LAYER_UID_MISMATCH: ' + name)
        result[name] = {**header, 'sha256': hashlib.sha256(blob).hexdigest()}
    return result
