"""Replace a cloned figure's image while preserving its displayed width."""

# pyright: reportPrivateUsage=false

from __future__ import annotations

import hashlib
import io
import posixpath
from pathlib import Path

from lxml import etree
from PIL import Image, UnidentifiedImageError

from ema.core.office.package import P, R, encoded, rels_path, xml

A = "http://schemas.openxmlformats.org/drawingml/2006/main"
WP = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
REL_IMAGE = f"{R}/image"
MIME = {"JPEG": ("jpeg", "image/jpeg"), "PNG": ("png", "image/png"), "GIF": ("gif", "image/gif")}


def replace_picture(parts: dict[str, bytes], paragraph: etree._Element, image: Path) -> None:
    blips = list(paragraph.iter(f"{{{A}}}blip"))
    extents = list(paragraph.iter(f"{{{WP}}}extent"))
    if len(blips) != 1 or len(extents) != 1:
        raise ValueError("figure prototype needs exactly one inline picture")
    raw = image.read_bytes()
    try:
        with Image.open(io.BytesIO(raw)) as picture:
            extension, media_type = MIME[picture.format or ""]
            aspect = picture.height / picture.width
    except (OSError, KeyError, ZeroDivisionError, UnidentifiedImageError) as exc:
        raise ValueError("unsupported figure image") from exc
    name = f"ema-{hashlib.sha256(raw).hexdigest()[:16]}.{extension}"
    media = f"word/media/{name}"
    parts[media] = raw
    owner = "word/document.xml"
    rel_path = rels_path(owner)
    rels = xml(parts, rel_path)
    used = {rel.get("Id") for rel in rels}
    rid = next(f"rId{index}" for index in range(1, 100000) if f"rId{index}" not in used)
    etree.SubElement(
        rels,
        f"{{{P}}}Relationship",
        Id=rid,
        Type=REL_IMAGE,
        Target=posixpath.relpath(media, posixpath.dirname(owner)),
    )
    parts[rel_path] = encoded(rels)
    blips[0].set(f"{{{R}}}embed", rid)
    width = int(extents[0].get("cx", "0"))
    height = round(width * aspect)
    extents[0].set("cy", str(height))
    for transform in paragraph.iter(f"{{{A}}}ext"):
        if transform.get("cx") is not None and transform.get("cy") is not None:
            transform.set("cy", str(height))
    types = xml(parts, "[Content_Types].xml")
    if not any(node.get("Extension") == extension for node in types):
        etree.SubElement(types, f"{{{CT}}}Default", Extension=extension, ContentType=media_type)
        parts["[Content_Types].xml"] = encoded(types)
