"""Shared original-page crop coordinates for SVG and narrated video."""
from __future__ import annotations

import math
from PIL import Image

PREVIEW_CENTER = (-5.7, .25)
PREVIEW_SIZE = (2.0, 3.8)
DETAIL_CENTER = (.85, -.1)
DETAIL_SIZE = (9.2, 3.6)


def fit_size(size, bounds):
    scale = min(bounds[0] / size[0], bounds[1] / size[1])
    return size[0] * scale, size[1] * scale


def source_detail(diagram, focus):
    if not diagram.source_asset:
        return None
    for key in focus:
        rect = diagram.source_regions.get(str(key))
        if rect is None:
            continue
        if (len(rect) != 4 or not all(math.isfinite(v) and 0 <= v <= 1 for v in rect)
                or rect[0] >= rect[2] or rect[1] >= rect[3]):
            raise ValueError('原页放大区域坐标无效。')
        with Image.open(diagram.source_asset) as original:
            width, height = original.size
            box = (max(0, math.floor((rect[0] - .015) * width)),
                   max(0, math.floor((rect[1] - .012) * height)),
                   min(width, math.ceil((rect[2] + .015) * width)),
                   min(height, math.ceil((rect[3] + .012) * height)))
            image = original.crop(box).convert('RGB')
            bounds = (4.5, 2.8) if diagram.relations else DETAIL_SIZE
            center = (-4.65, -.75) if diagram.relations else DETAIL_CENTER
            size = fit_size(image.size, bounds)
            preview_size = fit_size(original.size, PREVIEW_SIZE)
            enlargement = size[0] / (image.width * preview_size[0] / width)
        return {'image': image, 'focus': key, 'pixel_box': box, 'source_region': rect,
                'size': size, 'center': center, 'enlargement': enlargement}
    return None  # Missing coordinates never produce a guessed crop.
