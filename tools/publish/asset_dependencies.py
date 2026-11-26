"""Resolve publication prerequisites from the same bytes that a reader will consume."""
from graphlib import CycleError, TopologicalSorter
from pathlib import Path
import re

from tools.brand_sets.dependencies import active_wikitext
from . import PublishError, normalized_title_name, require


FILE_LINK = re.compile(r'\[\[\s*:?\s*([^:{}|\[\]\s]+)\s*:\s*([^{}|\[\]\n]+?)(?=\||\]\])')
ASSET_CALL = re.compile(r'\{\{\s*(?:(?:Template|模板):\s*)?TD2资产\s*\|\s*(?:1\s*=\s*)?([^{}|\r\n]+?)\s*\}\}', re.I)
EXTENSIONS = r'png|jpe?g|gif|webp|svg|ogg|mp3|mp4|pdf'
# The address and logo resolvers emit bare filenames as switch results.
FILE_VALUE = re.compile(r'=\s*([^=<>\[\]{}|\r\n]+?\.(?:' + EXTENSIONS + r'))\s*(?=\||\}\})', re.I)
# catalog.cjs serializes each registered weapon or skin filename in this Lua field.
EQUIPMENT_IMAGE = re.compile(r'\["image"\]\s*=\s*"([^"\r\n]*)"')


class AssetDependencies:
    def __init__(self, entries, read_text):
        self.entries = {row['id']: row for row in entries}
        self.assets = {row['id']: row for row in entries if row['kind'] == 'assets'}
        self.names = {normalized_title_name(row['title'].split(':', 1)[1]): row['id']
                      for row in self.assets.values()}
        self.prefixes = {'file', 'image', '文件', '檔案', '图片', '圖片', '图像', '圖像'}
        self.prefixes.update(row['title'].split(':', 1)[0].casefold() for row in self.assets.values())
        self.read_text = read_text
        self.direct = {}

    def literal_assets(self, row):
        entry_id = row['id']
        if entry_id in self.direct:
            return self.direct[entry_id]
        result = set()
        suffix = Path(row['source']).suffix.lower()
        if suffix in ('.wiki', '.wikitext', '.lua') and row['kind'] != 'assets':
            text = active_wikitext(self.read_text(row))
            for prefix, filename in FILE_LINK.findall(text):
                if prefix.casefold() not in self.prefixes:
                    continue
                # A Lua concatenation supplies its filename from other registered data.
                if suffix == '.lua' and re.search(r"""['"]\s*\.\.|\.\.\s*['"]""", filename):
                    continue
                name = normalized_title_name(filename.split('#', 1)[0])
                require(name in self.names, '未登记的文件引用: ' + entry_id)
                result.add(self.names[name])
            result.update(value.strip() for value in ASSET_CALL.findall(text))
            if entry_id == 'equipment-mapping-data' and suffix == '.lua':
                for filename in EQUIPMENT_IMAGE.findall(text):
                    name = normalized_title_name(filename)
                    require(name in self.names, '未登记的装备图片: ' + filename)
                    result.add(self.names[name])
            if suffix != '.lua':
                for value in FILE_VALUE.findall(text):
                    name = normalized_title_name(value)
                    if name in self.names:
                        result.add(self.names[name])
                    elif name.startswith('td2-'):
                        raise PublishError('未登记的 Wiki 资产地址: ' + entry_id)
        require(result.issubset(self.assets), '资产引用指向未登记的资产: ' + entry_id)
        self.direct[entry_id] = result
        return result

    def resolve(self, row):
        extra = row.get('asset_relationships')
        require(isinstance(extra, list) and all(isinstance(key, str) and key in self.assets for key in extra),
                '资产关系必须引用已登记的资产: ' + row['id'])
        ids = set(extra) | self.literal_assets(row)
        if 'asset_relationship_source' in row:
            source = row['asset_relationship_source']
            if source == 'registry-assets':
                ids.update(self.assets)
            else:
                provider = self.entries.get(source) if isinstance(source, str) else None
                require(provider and provider['kind'] == 'templates' and source != row['id'],
                        '无效的资产地址提供模板: ' + row['id'])
                ids.update(self.literal_assets(provider))
        return sorted(ids)


def publication_order(rows):
    """Put files in dependency order, then the Wiki modules, templates and pages that use them."""
    assets = {row['id']: row for row in rows if row['kind'] == 'assets'}
    graph = TopologicalSorter({key: assets[key]['asset_relationships'] for key in sorted(assets)})
    try:
        ordered = [assets[key] for key in graph.static_order()]
    except CycleError as error:
        raise PublishError('资产依赖形成循环: ' + ' → '.join(error.args[1])) from None
    ranks = {'modules': 0, 'templates': 1, 'categories': 2, 'pages': 3, 'redirects': 4}
    return ordered + sorted((row for row in rows if row['kind'] != 'assets'),
                            key=lambda row: (ranks[row['kind']], row['id']))
