"""Photo evidence crops the normalized region and preserves the full-page view."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image

from ema.core.photo import render_photo_png
from ema.core.review.models import Photo


def test_region_crop_and_page_png(tmp_path: Path) -> None:
    source = tmp_path / "synthetic.png"
    Image.new("RGB", (100, 100), "white").save(source)
    locator = Photo(region=(0.2, 0.3, 0.6, 0.7))
    with Image.open(BytesIO(render_photo_png(source, locator, highlight=True))) as snippet:
        assert 44 <= snippet.width <= 45 and 44 <= snippet.height <= 45
        assert (217, 54, 54) in snippet.get_flattened_data()
    with Image.open(BytesIO(render_photo_png(source, locator, mode="page"))) as page:
        assert page.size == (100, 100)
