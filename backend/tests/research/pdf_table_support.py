"""Build tiny PDFs whose text sits at explicit coordinates (SYNTHETIC FIXTURE text only; no real reports).

Each item is drawn as its own text-showing operation at (x_left, y), so a test controls the exact table layout.
"""

from __future__ import annotations

import io

from .pdf_support import _escape

Item = tuple[float, float, str]


def table_pdf(pages: list[list[Item]], *, size: float = 10) -> bytes:
    """One page per entry; an empty page has no text. Coordinates are PDF points from the bottom-left."""
    n = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, items in enumerate(pages):
        ops = (
            "q Q"
            if not items
            else " ".join(
                f"BT /F1 {size} Tf {x:.2f} {y:.2f} Td ({_escape(text)}) Tj ET"
                for x, y, text in items
            )
        )
        stream = ops.encode("latin-1")
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >>"
            + f" /Contents {5 + 2 * i} 0 R >>".encode()
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n% SYNTHETIC FIXTURE\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(out.tell())
        out.write(f"{number} 0 obj\n".encode() + body + b"\nendobj\n")
    xref = out.tell()
    out.write(f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n".encode())
    for offset in offsets:
        out.write(f"{offset:010d} 00000 n \n".encode())
    out.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    return out.getvalue()
