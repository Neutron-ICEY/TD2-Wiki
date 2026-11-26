"""Rebuild gallery swatches from the game's weapon skin textures and palettes."""
import argparse
from io import BytesIO
import json
from pathlib import Path

from PIL import Image

from tools.identity import registry
from .weapons_native import ROOT, WeaponNative


IMAGES = Path('resources/game/current/images')


def linear_sample(value):
    channel = value / 255
    linear = channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4
    return round(linear * 255)


def render_swatch(native, item):
    """Apply the three ItemSkin shader channels with a neutral UI tint."""
    if item['resource_type'] != 'WeaponSkinItem':
        raise ValueError('Expected a WeaponSkinItem')
    if any((native.scalar(item, field) or '').strip('"') for field in ('myCustomPreviewTexture', 'myIcon')):
        raise ValueError('Use the existing native preview for ' + item['resource_uid'])
    texture = (native.scalar(item, 'mySkinTexture') or '').strip('"')
    relative = Path(texture.lower())
    if relative.suffix != '.dds' or relative.is_absolute() or '..' in relative.parts:
        raise ValueError('Invalid skin texture: ' + texture)
    image_source = IMAGES / relative.with_suffix('.png')
    palette = [native.scalar(item, 'myColor' + str(i)) for i in (1, 2, 3)]
    colors = [int(color, 16) for color in palette]
    matrix = []
    for shift in (16, 8, 0):
        matrix.extend(((color >> shift) & 255) / 255 for color in colors)
        matrix.append(0)
    with Image.open(ROOT / image_source) as source:
        rgb = source.convert('RGB').point([linear_sample(i) for i in range(256)] * 3)
        width = min(source.width, source.height * 2)
        height = min(source.height, source.width / 2)
        left, top = (source.width - width) / 2, (source.height - height) / 2
        cropped = rgb.crop((left, top, left + width, top + height))
        swatch = cropped.convert('RGB', matrix).resize((256, 128), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    swatch.save(buffer, 'PNG')
    return buffer.getvalue(), dict(image_method='texture_cover', native_texture=texture,
                                    image_source=image_source.as_posix(), palette=palette)


def build(directory):
    if directory.exists():
        raise ValueError('Use a fresh output directory')
    catalog = json.loads((ROOT / 'data/equipment/weapon-skins.json').read_bytes())
    files = {r['id']: Path(r['source']).name for r in registry(ROOT) if r['kind'] == 'assets'}
    native = WeaponNative(ROOT / 'resources/game/current/raw_files')
    outputs = {}
    for skin in catalog['skins']:
        if skin.get('image_method') == 'texture_cover':
            filename = files[skin['asset_ref']]
            if filename in outputs:
                raise ValueError('Duplicate swatch target: ' + filename)
            item = native.record(skin['source'], skin['uid'])
            outputs[filename], _ = render_swatch(native, item)
    directory.mkdir(parents=True)
    for filename, payload in outputs.items():
        (directory / filename).write_bytes(payload)
    print(f'{len(outputs)} swatches in {directory}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    build(parser.parse_args().directory)
