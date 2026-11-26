import atexit
from functools import cache
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
import zipfile


@cache
def corpus_root():
    """Restore the pinned regression inputs without borrowing a developer's raw exports."""
    fixtures = Path(__file__).parent / 'fixtures'
    manifest = json.loads((fixtures / 'resource-corpus.json').read_text('utf8'))
    archive = fixtures / manifest['archive']
    with archive.open('rb') as stream:
        if hashlib.file_digest(stream, 'sha256').hexdigest() != manifest['archive_sha256']:
            raise AssertionError('Regression corpus archive SHA256 mismatch')
    temporary = tempfile.TemporaryDirectory(prefix='td2-corpus-')
    root = Path(temporary.name).resolve()
    try:
        with zipfile.ZipFile(archive) as bundle:
            expected = {row['source']: row for row in manifest['files']}
            if len(expected) != len(manifest['files']) or set(bundle.namelist()) != set(expected):
                raise AssertionError('Regression corpus inventory mismatch')
            for name, row in expected.items():
                parts = PurePosixPath(name)
                if parts.is_absolute() or ':' in name or '\\' in name or any(p in ('.', '..') for p in parts.parts):
                    raise AssertionError('Unsafe regression corpus path')
                target = root.joinpath(*parts.parts)
                if not target.resolve().is_relative_to(root):
                    raise AssertionError('Regression corpus escapes its temporary directory')
                data = bundle.read(name)
                if len(data) != row['bytes'] or hashlib.sha256(data).hexdigest() != row['sha256']:
                    raise AssertionError('Regression corpus input SHA256 mismatch: ' + name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
    except BaseException:
        temporary.cleanup()
        raise
    atexit.register(temporary.cleanup)
    return root


def corpus_path(relative):
    """Resolve one recorded test input within the verified fixture archive."""
    root = corpus_root()
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Regression input escapes fixture root')
    return path
