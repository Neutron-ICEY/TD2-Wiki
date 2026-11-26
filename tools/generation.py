"""Preflight generated source batches before any maintenance write."""
from tools.publish.bundle import require, safe_path, title_key


def plan(root, sources, registry, owners):
    """Resolve every target, owner and UTF-8 payload before the first write."""
    result, targets = [], set()
    for relative, text in sources.items():
        rows = [row for row in registry['entries'] if row['source'] == relative]
        require(len(rows) == 1 and rows[0]['ownership'] == 'generated'
                and rows[0].get('generator') == owners[relative], 'Generated ownership mismatch: ' + relative)
        row = rows[0]
        identity = title_key(row.get('title'), row.get('namespace'))
        require(sum(title_key(other.get('title'), other.get('namespace')) == identity
                    for other in registry['entries']) == 1, 'Duplicate generated Wiki target')
        target = safe_path(root, relative)
        require(not any(part.startswith('.') for part in relative.split('/')), 'Hidden generated target')
        original = root.resolve() / relative
        for current in (original, *original.parents):
            if current == root.resolve():
                break
            require(not current.is_symlink(), 'Symlink generated target: ' + relative)
        key = str(target).casefold()
        require(key not in targets, 'Duplicate generated target')
        targets.add(key)
        require(not target.exists() or target.is_file(), 'Generated target is not a file: ' + relative)
        for parent in target.parents:
            if parent == root.resolve():
                break
            require(not parent.exists() or parent.is_dir(), 'Generated parent is not a directory: ' + relative)
        data = text.encode('utf-8')
        result.append((relative, target, data, not target.is_file() or target.read_bytes() != data))
    return result


def apply(batch, check=False):
    """Validation is batch-wide; OS write failures may leave earlier targets updated."""
    changed = [relative for relative, _, _, stale in batch if stale]
    if check:
        require(not changed, '派生文件已过期，请运行 generate 并检查 diff')
    else:
        for _, target, data, stale in batch:
            if stale:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    return changed
