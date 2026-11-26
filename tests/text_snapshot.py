from tools.asset_import.text_library import TextError, TextLibrary, sha256
from fixture_corpus import corpus_root


SNAPSHOT_INDEX = 'dist/text-library-20261018-002/text-sources.review.json'
SNAPSHOT_SHA256 = 'cc940e9e2d2ec47cdfccfe8a46578b68f711d453e6220cc0230851975f084525'
ARCHIVED_INPUTS = {
    'data/brand-sets/brands.json':
        'dist/reader-editor-production-20261018-work/before/data/brand-sets/brands.json',
    'data/brand-sets/bonuses.json':
        'dist/brand-page-pilot-20261021-002/before/data/brand-sets/bonuses.json',
}


class HistoricalTextLibrary(TextLibrary):
    def __init__(self, root=None):
        root = corpus_root() if root is None else root
        if sha256((root / SNAPSHOT_INDEX).read_bytes()) != SNAPSHOT_SHA256:
            raise TextError('INPUT_HASH_MISMATCH', SNAPSHOT_INDEX)
        super().__init__(root=root, index=SNAPSHOT_INDEX)

    def _read(self, spec):
        """Read exact archived bytes without changing the historical source identity."""
        original = spec.get('file') if isinstance(spec, dict) else None
        if original not in ARCHIVED_INPUTS:
            return super()._read(spec)
        blob, text, info = super()._read({**spec, 'file': ARCHIVED_INPUTS[original]})
        return blob, text, {**info, 'file': original}
