"""Build tiny, valid PDFs for extraction tests (SYNTHETIC FIXTURE text only; no real reports)."""

from __future__ import annotations

import io


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def text_pdf(pages: list[list[str]], *, title: str | None = None) -> bytes:
    """One page per entry, each a list of text lines (Helvetica). An empty list is a page with no text."""
    n = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, lines in enumerate(pages):
        ops = "q Q" if not lines else "BT /F1 12 Tf 72 720 Td 14 TL " + " T* ".join(
            f"({_escape(line)}) Tj" for line in lines
        ) + " ET"  # fmt: skip
        stream = ops.encode("latin-1")
        objects.append(
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 3 0 R >> >>"
            f" /Contents {5 + 2 * i} 0 R >>".encode()
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    info_ref = b""
    if title is not None:
        objects.append(f"<< /Title ({_escape(title)}) >>".encode("latin-1"))
        info_ref = f" /Info {len(objects)} 0 R".encode()
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
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R".encode() + info_ref
        + f" >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )  # fmt: skip
    return out.getvalue()


def encrypted_pdf(pages: list[list[str]]) -> bytes:
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(text_pdf(pages))))
    writer.encrypt("secret", algorithm="RC4-128")
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
