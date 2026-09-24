"""Synthetic workspace for frontend contract development."""

from __future__ import annotations

import base64
from datetime import UTC, datetime

from ema.core.jobs import create_job
from ema.core.review import propose
from ema.core.review.models import Evidence, PdfText
from ema.core.workspace import Workspace

_ONE_PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/h9sAAAAASUVORK5CYII="
)


def snippet_png() -> bytes:
    return _ONE_PIXEL_PNG


def preview_pdf() -> bytes:
    """A one-page synthetic PDF for pdf.js smoke checks."""
    stream = b"BT /F1 18 Tf 72 720 Td (Synthetic preview) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for number, body in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    start = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode()
    )
    return bytes(output)


def seed(ws: Workspace) -> None:
    """Populate a disposable mock workspace with no reference-library values."""
    if ws.root.joinpath(".mock-seeded").exists():
        return
    for kind in ("audit", "piee", "invoices", "reporting"):
        job = create_job(ws, kind, "exemplu", 2026)
        source = Evidence(
            id=f"{kind}-example",
            provenance="document",
            file_sha="synthetic",
            locator=PdfText(page=2, span="Consum anual estimat"),
            method="questionnaire",
            retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
            quote="Consum anual estimat: 120 MWh.",
            highlight="exact",
        )
        propose(ws, job, "consum_anual", 120, [source], state="extracted")
    ws.root.joinpath(".mock-seeded").touch()
