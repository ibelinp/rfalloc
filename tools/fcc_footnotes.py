"""Extract the four classes of footnote that the Allocation Table refers to.

The footnotes are where the table's real meaning lives -- a band row says
"MOBILE", and the footnote hanging off it says who may actually transmit there,
at what power, and in which states.  All four classes are carried in the same
document as the table, laid out as prose after it:

    (b) International footnotes  ->  5.53, 5.54A, ...   (ITU, all regions)
    (c) United States Footnotes  ->  US1, US2, ...      (both US tables)
    (d) Non-Federal Government   ->  NG1, NG7, ...      (non-Federal only)
    (e) Federal Government       ->  G2, G5, ...        (Federal only)

Each entry opens with a numbering marker and its own identifier -- "(53)  5.53
Administrations authorizing..." -- and runs on across as many paragraphs as it
needs, including lettered sub-items that carry no identifier of their own.  A
paragraph therefore starts a new footnote only when it leads with an identifier;
everything else continues the one in progress.
"""

from __future__ import annotations

import pathlib

# Resolve the source document relative to this file rather than the working
# directory, so the tools run correctly from anywhere.
SOURCE_DOC = str(
    pathlib.Path(__file__).resolve().parent.parent / "sources" / "fcctable.docx"
)

import re
from dataclasses import dataclass, field

from docx_grid import read_body

# Where the Allocation Table stops and the notes begin.
NOTES_START_MARKER = "(a) Allocation Table."

_CLASS_HEADINGS = [
    ("itu", "International footnotes."),
    ("us", "United States Footnotes."),
    ("ng", "Non-Federal Government (NG) Footnotes."),
    ("g", "Federal Government (G) footnotes."),
]

# "(53)  5.53  text" / "(2)  US2  text" / "(i)  5.54A  text".  A few entries
# carry a compound marker -- "(260)(i)  5.260A ..." -- so the marker repeats.
_ENTRY_RE = re.compile(
    r"^(?:\(\s*[0-9ivxlcIVXLC]+\s*\)\s*)+"
    r"(?P<id>5\.\d+[A-Z]*|US\d+[A-Z]*|NG\d+[A-Z]*|G\d+[A-Z]*)"
    r"(?![\w.])\s*(?P<text>.*)$"
)
_RESERVED_RE = re.compile(r"^\(\s*[\d\s\-()]+\s*\)\s*\[Reserved\]", re.I)


@dataclass
class Footnote:
    id: str
    footnote_class: str  # itu | us | ng | g
    text: str = ""
    paragraphs: list[str] = field(default_factory=list)

    def finish(self) -> None:
        self.text = "\n".join(p for p in self.paragraphs if p).strip()


def parse_footnotes(path: str = SOURCE_DOC) -> dict[str, Footnote]:
    blocks = read_body(path).blocks

    start = next(
        (i for i, (kind, v) in enumerate(blocks) if kind == "p" and NOTES_START_MARKER in v),
        None,
    )
    if start is None:
        raise ValueError("could not locate the start of the notes section")

    notes: dict[str, Footnote] = {}
    current: Footnote | None = None
    klass: str | None = None

    for kind, value in blocks[start:]:
        if kind != "p":
            # Footnote sub-tables (station lists, channel plans) are recorded as
            # a marker rather than inlined; they are structured data of their own.
            if current is not None:
                current.paragraphs.append("[table omitted -- see source document]")
            continue

        text = value.strip()
        if not text:
            continue

        heading = next((k for k, h in _CLASS_HEADINGS if h in text[:80]), None)
        if heading:
            klass = heading
            if current:
                current.finish()
                current = None
            continue

        if klass is None:
            continue

        m = _ENTRY_RE.match(text)
        if m:
            if current:
                current.finish()
            current = Footnote(id=m.group("id"), footnote_class=klass)
            current.paragraphs.append(m.group("text").strip())
            notes[current.id] = current
            continue

        if _RESERVED_RE.match(text):
            if current:
                current.finish()
                current = None
            continue

        if current is not None:
            current.paragraphs.append(text)

    if current:
        current.finish()
    return notes


if __name__ == "__main__":
    notes = parse_footnotes()
    from collections import Counter

    print(f"{len(notes)} footnotes", Counter(n.footnote_class for n in notes.values()))
    for fid in ("5.226", "US52", "NG124", "G5", "US266", "5.111"):
        n = notes.get(fid)
        print(f"\n[{fid}] {'MISSING' if not n else n.text[:220]}")
