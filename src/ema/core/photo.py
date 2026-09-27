"""Render a photo evidence page or a padded region crop as PNG."""

from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from ema.core.errors import EmaError
from ema.core.review.models import Photo


def render_photo_png(
    path: Path, locator: Photo, *, mode: str = "snippet", highlight: bool = False
) -> bytes:
    try:
        with Image.open(path) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
            if mode == "snippet" and locator.region is not None:
                width, height = image.size
                x0, y0, x1, y1 = locator.region
                pad_x, pad_y = (x1 - x0) * 0.05, (y1 - y0) * 0.05
                left = max(0, int((x0 - pad_x) * image.width))
                top = max(0, int((y0 - pad_y) * image.height))
                right = min(image.width, int((x1 + pad_x) * image.width + 0.999))
                bottom = min(image.height, int((y1 + pad_y) * image.height + 0.999))
                image = image.crop((left, top, right, bottom))
                if highlight:
                    ImageDraw.Draw(image).rectangle(
                        (
                            int(x0 * width) - left,
                            int(y0 * height) - top,
                            int(x1 * width) - left,
                            int(y1 * height) - top,
                        ),
                        outline="#d93636",
                        width=3,
                    )
            output = io.BytesIO()
            image.save(output, format="PNG")
            return output.getvalue()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise EmaError("file_type", "Fotografia este invalidă.", path.name) from exc
