"""The invoice image previews a printed value at reading size."""

from io import BytesIO
from pathlib import Path

from PIL import Image

from ema.core.pdf import render_invoice_crop_png, render_page_png


def _invoice(path: Path) -> Path:
    stream = b"BT /F1 20 Tf 50 700 Td (Consum: 142.118 kWh) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(data))
        data.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    start = len(data)
    data.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode())
    data.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    path.write_bytes(data)
    return path


def test_crop_highlights_value_and_missing_text_keeps_full_page(tmp_path: Path) -> None:
    path = _invoice(tmp_path / "invoice.pdf")
    full = render_page_png(path, 1)
    crop = render_invoice_crop_png(path, 1, "142118", "Consum: 142.118 kWh")
    full_image = Image.open(BytesIO(full))
    crop_image = Image.open(BytesIO(crop))
    assert crop_image.width < full_image.width
    assert crop_image.height < full_image.height
    assert any(
        r > 130 and 60 < g < 190 and b < 90 for r, g, b in crop_image.convert("RGB").getdata()
    )
    assert render_invoice_crop_png(path, 1, "999", "Absent") == full
