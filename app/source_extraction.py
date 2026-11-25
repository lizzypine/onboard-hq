"""Extract bounded passages and exact character spans from retained source bytes."""

import re
from html.parser import HTMLParser
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.knowledge_models import Extraction, Media, Passage

MAX_BYTES = 16 * 1024 * 1024
MAX_TEXT = 2_000_000
CHUNK_SIZE = 1400


class SourceError(ValueError):
    pass


class Headings(HTMLParser):
    """Retain visible text and its enclosing HTML heading."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[tuple[str, str]] = []
        self.buffer: list[str] = []
        self.heading = "Document"
        self.heading_tag = ""
        self.hidden = 0

    def flush(self) -> None:
        value = " ".join("".join(self.buffer).split())
        if value:
            self.parts.append((self.heading, value))
        self.buffer = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "nav", "noscript", "svg", "footer", "header"}:
            self.hidden += 1
        elif not self.hidden and tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self.flush()
            self.heading_tag = tag
        elif not self.hidden and tag in {"p", "div", "li", "br", "tr", "td"}:
            self.buffer.append(" ")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "noscript", "svg", "footer", "header"}:
            self.hidden = max(0, self.hidden - 1)
        elif not self.hidden and tag == self.heading_tag:
            self.heading = " ".join("".join(self.buffer).split()) or "Document"
            self.heading_tag = ""
            self.buffer = []
        elif not self.hidden and tag in {"p", "div", "li", "tr", "td"}:
            self.buffer.append(" ")

    def handle_data(self, data):
        if not self.hidden:
            self.buffer.append(data)


def _chunks(
    text: str, section: str, page: int | None, start: int, end: int
) -> list[Passage]:
    result = []
    while start < end:
        stop = min(start + CHUNK_SIZE, end)
        if stop < end:
            boundary = max(
                text.rfind("\n", start + CHUNK_SIZE // 2, stop),
                text.rfind(" ", start + CHUNK_SIZE // 2, stop),
            )
            if boundary > start:
                stop = boundary
        part = text[start:stop]
        if part.strip():
            left = start + len(part) - len(part.lstrip())
            right = start + len(part.rstrip())
            result.append(
                Passage(
                    text=text[left:right],
                    section=section,
                    page=page,
                    char_start=left,
                    char_end=right,
                )
            )
        start = stop
    return result


def _plain(text: str) -> Extraction:
    section = "Document"
    start = 0
    chunks = []
    for heading in re.finditer(r"^#{1,6}[ \t]+(.+)$", text, re.MULTILINE):
        chunks.extend(_chunks(text, section, None, start, heading.start()))
        section = heading.group(1).strip()
        start = heading.end()
    chunks.extend(_chunks(text, section, None, start, len(text)))
    return Extraction(text=text, chunks=chunks)


# Legal headings include a rule number followed by a title. A bare rule
# number is often a running page header and does not start a new section.
PDF_HEADING = re.compile(
    r"^[ \t]*(?:(?P<rule>§[ \t]*\d+[A-Z]?(?:-\d+)+(?:\.\d+)?)(?=[ \t]+[A-Z])"
    r"|(?P<title>(?i:section|chapter|subchapter)[ \t]+(?:[IVXLCDM]+|\d+)"
    r"[ \t]*[-–—:][ \t]*[^\n]{1,160})$)",
    re.MULTILINE,
)


def _pdf(raw: bytes) -> Extraction:
    try:
        reader = PdfReader(BytesIO(raw))
        if reader.is_encrypted and not reader.decrypt(""):
            raise SourceError("The configured PDF requires a password.")
        if len(reader.pages) > 500:
            raise SourceError("Source exceeds the page limit.")
        pages = [(page.extract_text() or "").strip() for page in reader.pages]
    except (PyPdfError, OSError, ValueError) as exc:
        raise SourceError("Could not extract the configured PDF.") from exc

    text = "\n\n".join(pages)
    chunks = []
    section = "Document"
    page_start = 0
    for page_number, page_text in enumerate(pages, 1):
        start = page_start
        for match in PDF_HEADING.finditer(page_text):
            boundary = page_start + match.start()
            chunks.extend(_chunks(text, section, page_number, start, boundary))
            section = (match.group("rule") or match.group("title")).strip()
            start = boundary
        end = page_start + len(page_text)
        chunks.extend(_chunks(text, section, page_number, start, end))
        page_start = end + 2
    return Extraction(text=text, chunks=chunks)


def _html_text(raw: bytes) -> str:
    declared = re.search(
        rb"""<meta\b[^>]*?charset\s*=\s*['"]?([a-z0-9_-]+)""", raw[:4096], re.IGNORECASE
    )
    encoding = declared.group(1).lower() if declared else b"utf-8"
    supported = {
        b"utf-8": "utf-8-sig",
        b"utf8": "utf-8-sig",
        b"windows-1252": "cp1252",
        b"iso-8859-1": "cp1252",
        b"us-ascii": "ascii",
    }
    if encoding not in supported:
        raise SourceError("Unsupported encoding in configured HTML source.")
    try:
        return raw.decode(supported[encoding])
    except UnicodeDecodeError:
        raise SourceError("HTML source does not match its declared encoding.") from None


def extract_source(raw: bytes, media_type: Media) -> Extraction:
    if not 0 < len(raw) <= MAX_BYTES:
        raise SourceError("Source size is outside the supported range.")
    if media_type == "text/plain":
        result = _plain(raw.decode("utf-8-sig"))
    elif media_type == "application/pdf":
        result = _pdf(raw)
    else:
        parser = Headings()
        parser.feed(_html_text(raw))
        parser.close()
        parser.flush()
        parts = parser.parts
        text = "\n\n".join(body for _, body in parts)
        chunks = []
        pos = 0
        for section, body in parts:
            chunks.extend(_chunks(text, section, None, pos, pos + len(body)))
            pos += len(body) + 2
        result = Extraction(text=text, chunks=chunks)
    if not result.chunks or len(result.text) > MAX_TEXT:
        raise SourceError("Extraction is empty or exceeds the supported text size.")
    return result
