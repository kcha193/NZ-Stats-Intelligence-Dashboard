"""Build PDFs from raw content-stream operators, the way real reports draw text (SYNTHETIC FIXTURE text only).

`table_pdf` draws every cell in its own `BT..ET`. Real generators put a whole row (or page) in one block, position with `Tm`,
kern with `TJ` arrays, scale fonts through the matrix and rotate pages. These helpers let a test write the operators itself.
"""

from __future__ import annotations

import io

from .pdf_support import _escape


def raw_pdf(
    contents: list[str], *, rotate: int = 0, font_objects: dict[str, bytes] | None = None
) -> bytes:
    """One page per entry; each entry is the page's content stream, written by the test.

    /F1 is Helvetica and /F2 Helvetica-Bold (objects 3 and 4); pages are objects 5, 7, ... and their streams 6, 8, ...
    `font_objects` maps a font name (e.g. "F3") to a font dictionary, added after the pages.
    """
    font_objects = font_objects or {}
    first_font = 5 + 2 * len(contents)
    extra = "".join(f"/{name} {first_font + i} 0 R " for i, name in enumerate(font_objects))
    n = len(contents)
    kids = " ".join(f"{5 + 2 * i} 0 R" for i in range(n))
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>".encode(),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>",
    ]
    for i, content in enumerate(contents):
        stream = content.encode("cp1252")
        objects.append(
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792]"
            + (f" /Rotate {rotate}".encode() if rotate else b"")
            + b" /Resources << /Font << /F1 3 0 R /F2 4 0 R "
            + extra.encode()
            + b" >> >>"
            + f" /Contents {6 + 2 * i} 0 R >>".encode()
        )
        objects.append(
            b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream"
        )
    objects.extend(font_objects.values())
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


def row(y: float, cells: list[tuple[float, str]], *, size: float = 10, font: str = "F1") -> str:
    """One whole baseline in ONE `BT..ET`: each cell is positioned with a relative `Td` and drawn with `Tj`."""
    ops, last = [f"BT /{font} {size} Tf"], 0.0
    for n, (x, text) in enumerate(cells):
        ops.append(f"{x:.2f} {y:.2f} Td" if n == 0 else f"{x - last:.2f} 0 Td")
        ops.append(f"({_escape(text)}) Tj")
        last = x
    ops.append("ET")
    return " ".join(ops)


def page(*rows: str) -> str:
    return "\n".join(rows)


def nested_form_pdf(outer: str, inner: str, *, depth: int) -> bytes:
    """A page's shallow content plus text inside exactly `depth` nested Form XObjects."""
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import (
        ArrayObject,
        DecodedStreamObject,
        DictionaryObject,
        NameObject,
        NumberObject,
    )

    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(raw_pdf([outer]))))
    sheet = writer.pages[0]
    fonts = sheet["/Resources"]["/Font"]
    nested = None
    for _ in range(depth):
        resources = DictionaryObject({NameObject("/Font"): fonts})
        if nested is not None:
            resources[NameObject("/XObject")] = DictionaryObject({NameObject("/Nested"): nested})
        form = DecodedStreamObject()
        form.set_data((inner if nested is None else "/Nested Do").encode("cp1252"))
        form.update(
            {
                NameObject("/Type"): NameObject("/XObject"),
                NameObject("/Subtype"): NameObject("/Form"),
                NameObject("/BBox"): ArrayObject([NumberObject(n) for n in (0, 0, 612, 792)]),
                NameObject("/Resources"): resources,
            }
        )
        nested = writer._add_object(form)
    sheet["/Resources"][NameObject("/XObject")] = DictionaryObject({NameObject("/Nested"): nested})
    contents = DecodedStreamObject()
    contents.set_data(outer.encode("cp1252") + b"\n/Nested Do")
    sheet[NameObject("/Contents")] = writer._add_object(contents)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()
