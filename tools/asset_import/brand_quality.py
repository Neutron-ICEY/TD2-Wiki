"""Read-only raster measurements for evidence-based brand source comparisons.

Metrics describe visible pixels; they do not establish identity or quality by
themselves. No resize, sharpening, recoloring or image output occurs here.
"""
import hashlib
import io
from PIL import Image


def raster_measurements(data):
    with Image.open(io.BytesIO(data)) as source:
        source.load()
        image = source.convert('RGBA')
        width, height = image.size
        alpha = image.getchannel('A')
        bbox = alpha.getbbox()
        substantial = alpha.point(lambda value: 255 if value >= 16 else 0).getbbox()
        occupied = sum(1 for value in alpha.getdata() if value > 0)
        solid = sum(1 for value in alpha.getdata() if value == 255)
        partial = occupied - solid
        region = image.crop(bbox) if bbox else image
        levels = len(set(alpha.getdata()))
        return dict(source_sha256=hashlib.sha256(data).hexdigest(), byte_size=len(data),
            image_width=width, image_height=height, pixel_count=width*height,
            alpha_channel='A' in source.getbands(), format=source.format, image_mode=source.mode,
            alpha_min=alpha.getextrema()[0], alpha_max=alpha.getextrema()[1], alpha_levels=levels,
            alpha_nonzero_pixels=occupied, alpha_solid_pixels=solid, alpha_partial_pixels=partial,
            effective_pattern_bbox=list(bbox) if bbox else None,
            effective_pattern_width=bbox[2]-bbox[0] if bbox else 0,
            effective_pattern_height=bbox[3]-bbox[1] if bbox else 0,
            substantial_alpha_bbox=list(substantial) if substantial else None,
            transparent_margin_fraction=round(1-occupied/(width*height),6),
            rgba_unique_colors=len(set(region.getdata())),
            icc_profile_present=bool(source.info.get('icc_profile')), gamma=source.info.get('gamma'),
            srgb_rendering_intent=source.info.get('srgb'),
            metric_limitation='Alpha occupancy/bounds are descriptive; canvas size, color count and margins do not prove extra detail or same identity/use.')
