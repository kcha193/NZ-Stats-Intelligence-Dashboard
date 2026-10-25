"""Readable text and sections from a public HTML report page (stdlib `html.parser`, never rendered).

`<main>` is preferred, then `<article>`, then `<body>`. Scripts, styles, templates, forms, navigation,
page furniture and hidden elements are dropped. Sections start at h1-h3. Text that looks like
instructions is kept verbatim as data: nothing here interprets it.
"""

from __future__ import annotations

import codecs
import json
import re
from html.parser import HTMLParser
from typing import Any

from nzstats.domain import ErrorClass, IngestError
from nzstats.research.extract import Extracted, ExtractionLimits, build_sections, too_long

EXTRACTOR_VERSION = "html-1"

_SKIP = frozenset(
    "script style noscript template nav form aside svg math iframe object embed button select"
    " textarea canvas dialog menu head".split()
)
_FURNITURE = frozenset({"header", "footer"})  # dropped unless inside <main> or <article>
_VOID = frozenset("area base br col embed hr img input link meta param source track wbr".split())
_BLOCK = frozenset(
    "p div li ul ol tr td th table section blockquote pre h4 h5 h6 dt dd figure figcaption address"
    " hr br main article header footer".split()
)
_PARAGRAPH = frozenset("p h4 h5 h6 blockquote pre table figure section main article".split())
_AUTOCLOSE = frozenset("p li dt dd tr td th option".split())
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3}
_DATE_META = frozenset(
    "article:published_time date dc.date dcterms.issued dcterms.date citation_publication_date"
    " publication_date".split()
)
_CHARSET = re.compile(
    rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_.:-]{1,40})""", re.IGNORECASE
)
_MAX_HINT = 64
_MAX_LD_CHARS = 256 * 1024


def _hidden(attrs: dict[str, str | None]) -> bool:
    style = re.sub(r"\s+", "", (attrs.get("style") or "").lower())
    return (
        "hidden" in attrs
        or (attrs.get("aria-hidden") or "").lower() == "true"
        or "display:none" in style
        or "visibility:hidden" in style
    )


class _Parser(HTMLParser):
    def __init__(self, limits: ExtractionLimits) -> None:
        super().__init__(convert_charrefs=True)
        self.limits = limits
        # (tag, skip, in_main, in_article, heading_level)
        self.stack: list[tuple[str, bool, bool, bool, int]] = []
        self.events: list[
            tuple[str, str, bool, bool, int]
        ] = []  # (kind, text, main, article, level)
        self.heading: list[str] | None = None
        self.heading_level = 0
        self.title_tag: list[str] | None = None
        self.title_text: str | None = None
        self.og_title: str | None = None
        self.meta_date: str | None = None
        self.time_date: str | None = None
        self.ld: list[str] | None = None
        self.ld_blocks: list[str] = []
        self.raw_chars = 0

    def _top(self) -> tuple[bool, bool, bool, int]:
        return self.stack[-1][1:] if self.stack else (False, False, False, 0)

    def handle_starttag(self, tag: str, attr_list: list[tuple[str, str | None]]) -> None:
        attrs = {k.lower(): v for k, v in attr_list}
        if tag == "meta":
            self._meta(attrs)
        skip, main, article, level = self._top()
        if tag == "title" and self.title_text is None:
            self.title_tag = []
        if tag == "script" and "ld+json" in (attrs.get("type") or "").lower():
            self.ld = []
        if tag == "time" and not skip and self.time_date is None and attrs.get("datetime"):
            self.time_date = attrs["datetime"]
        if tag in _VOID:
            if tag in ("br", "hr") and not skip:
                self._emit("b", "1")
            return
        if self.stack and (
            (tag in _AUTOCLOSE and self.stack[-1][0] == tag)
            or (tag in _BLOCK and self.stack[-1][0] == "p")
        ):
            self._close(len(self.stack) - 1)
            skip, main, article, level = self._top()
        skip = (
            skip or tag in _SKIP or (tag in _FURNITURE and not (main or article)) or _hidden(attrs)
        )
        main = main or tag == "main" or (attrs.get("role") or "").lower() == "main"
        article = article or tag == "article"
        if tag in _HEADINGS and not skip:
            self._flush_heading()
            level = self.heading_level = _HEADINGS[tag]
            self.heading = []
        self.stack.append((tag, skip, main, article, level))
        if len(self.stack) > self.limits.max_depth:
            raise IngestError(ErrorClass.LAYOUT_CHANGED, "html nesting too deep")
        if tag in _BLOCK and not skip:
            self._emit("b", self._strength(tag))

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self.title_tag is not None:
            self.title_text, self.title_tag = "".join(self.title_tag), None
        if tag == "script" and self.ld is not None:
            self.ld_blocks.append("".join(self.ld))
            self.ld = None
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                self._close(i)
                return

    def _close(self, index: int) -> None:
        popped = self.stack[index:]
        del self.stack[index:]
        if any(entry[4] and not entry[1] for entry in popped) and not self._top()[3]:
            self._flush_heading()
        blocks = [entry[0] for entry in popped if entry[0] in _BLOCK and not entry[1]]
        if blocks:
            self._emit("b", max(self._strength(t) for t in blocks))

    @staticmethod
    def _strength(tag: str) -> str:
        return "2" if tag in _PARAGRAPH else "1"

    def handle_data(self, data: str) -> None:
        if self.title_tag is not None:
            self.title_tag.append(data)
            return
        if self.ld is not None:
            if sum(map(len, self.ld)) < _MAX_LD_CHARS:
                self.ld.append(data)
            return
        skip, _, _, level = self._top()
        if skip:
            return
        self.raw_chars += len(data)
        if self.raw_chars > 4 * self.limits.max_chars:  # bound memory before cleaning
            raise too_long(self.limits)
        if not any(entry[0] == "pre" for entry in self.stack):
            data = re.sub(r"\s+", " ", data)  # HTML whitespace is not layout
        if level and self.heading is not None:
            self.heading.append(data)
        else:
            self._emit("t", data)

    def _emit(self, kind: str, text: str, level: int = 0) -> None:
        _, main, article, _ = self._top()
        self.events.append((kind, text, main, article, level))

    def _flush_heading(self) -> None:
        if self.heading is not None:
            text = " ".join("".join(self.heading).split())
            level, self.heading = self.heading_level, None
            if text:
                self._emit("h", text, level)

    def _meta(self, attrs: dict[str, str | None]) -> None:
        name = (attrs.get("property") or attrs.get("name") or "").lower()
        content = attrs.get("content")
        if not content:
            return
        if name == "og:title" and self.og_title is None:
            self.og_title = content
        elif name in _DATE_META and self.meta_date is None:
            self.meta_date = content


def _decode(body: bytes, content_type: str) -> str:
    if body.startswith(codecs.BOM_UTF8):
        return body[3:].decode("utf-8", errors="replace")
    if body.startswith((codecs.BOM_UTF16_LE, codecs.BOM_UTF16_BE)):
        return body.decode("utf-16", errors="replace")
    header = re.search(r"charset\s*=\s*[\"']?([A-Za-z0-9_.:-]{1,40})", content_type or "", re.I)
    meta = _CHARSET.search(body[:4096])
    for name in (header and header.group(1), meta and meta.group(1).decode("ascii")):
        if not name:
            continue
        try:
            if codecs.lookup(name)._is_text_encoding:  # never base64/rot13-style codecs
                return body.decode(name, errors="replace")
        except LookupError:
            continue
    return body.decode("utf-8", errors="replace")


def _ld_date(node: Any, depth: int = 0) -> str | None:
    if depth > 20:
        return None
    if isinstance(node, dict):
        value = node.get("datePublished")
        if isinstance(value, str):
            return value
        children = node.values()
    elif isinstance(node, list):
        children = node
    else:
        return None
    for child in children:
        if (found := _ld_date(child, depth + 1)) is not None:
            return found
    return None


def _join(pieces: list[tuple[str, str]]) -> str:
    """Text and break markers -> text; consecutive breaks merge into the strongest one."""
    out: list[str] = []
    pending = 0
    for kind, text in pieces:
        if kind == "b":
            pending = max(pending, int(text))
        elif text.strip():
            if pending and out:
                out.append("\n" * pending)
            out.append(text)
            pending = 0
        elif not pending:
            out.append(text)
    return "".join(out)


def _hint(*candidates: str | None) -> str | None:
    for value in candidates:
        if value and 0 < len(value.strip()) <= _MAX_HINT:
            return value.strip()
    return None


def extract_html(body: bytes, content_type: str, limits: ExtractionLimits) -> Extracted:
    if len(body) > limits.max_html_bytes:
        raise IngestError(ErrorClass.VALIDATION_FAILED, "html too large")
    parser = _Parser(limits)
    parser.feed(_decode(body, content_type))
    parser.close()
    parser._flush_heading()
    events = parser.events
    if any(e[2] and e[0] == "t" and e[1].strip() for e in events):
        events = [e for e in events if e[2]]
    elif any(e[3] and e[0] == "t" and e[1].strip() for e in events):
        events = [e for e in events if e[3]]
    blocks: list[tuple[str | None, str, None, None]] = []
    heading: str | None = None
    pieces: list[str] = []
    for kind, text, *_ in events:
        if kind == "h":
            blocks.append((heading, _join(pieces), None, None))
            heading, pieces = text, []
        else:
            pieces.append((kind, text))
    blocks.append((heading, _join(pieces), None, None))
    sections, warnings = build_sections(blocks, limits)
    first_h1 = next((e[1] for e in events if e[0] == "h" and e[4] == 1), None)
    ld_date = None
    for block in parser.ld_blocks:
        try:
            ld_date = _ld_date(json.loads(block))
        except ValueError:
            continue
        if ld_date:
            break
    title = next(
        (
            " ".join(t.split())
            for t in (parser.og_title, parser.title_text, first_h1)
            if t and t.strip()
        ),
        None,
    )
    return Extracted(
        format="html",
        title=title[: limits.max_heading_chars] if title else None,
        sections=sections,
        published_hint=_hint(parser.meta_date, ld_date, parser.time_date),
        extractor_version=EXTRACTOR_VERSION,
        warnings=warnings,
    )
