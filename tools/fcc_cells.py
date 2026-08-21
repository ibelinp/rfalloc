"""Stage 2: parse the text of one Allocation Table cell into structured data.

A cell looks like this (each line is a separate Word paragraph -- the document
contains no line-break elements at all, so the print layout's hard wraps are
indistinguishable from meaningful line breaks by structure alone):

    148-149.9
    FIXED
    MOBILE
    MOBILE-SATELLITE
    (Earth-to-space)  US319
    US320  US323  US325
    5.218  5.219  G30

which means: band 148-149.9 MHz, three primary services, the third being
"MOBILE-SATELLITE (Earth-to-space)" qualified by footnotes US319/US320/US323/
US325, with 5.218/5.219/G30 applying to the band as a whole.

Two conventions of the printed table do the work:

  * **Case marks precedence.**  A service whose first word is set in capitals is
    a *primary* allocation; mixed case is *secondary*.  Lowercase words after
    the name ("MOBILE except aeronautical mobile") are qualifiers, not a case
    change, so only the first word is tested.
  * **Wrapped lines start lowercase or with a parenthesis**, or follow a line
    ending in a hyphen.  Real service names always begin with a capital, so this
    reconstructs the original lines unambiguously.

Footnote attachment is the one place the source is genuinely ambiguous: a
footnote-only line may either continue the footnote run of the service above it
or open the band-level block.  Nothing in the file distinguishes the two -- not
paragraph structure, not indentation, not style.  We therefore treat the whole
trailing run of footnote-only lines as band-level.  This never drops a footnote;
it can only attach one to the band that the printed table pinned to a single
service.  `raw_text` is retained on every record so the choice can be revisited
without reparsing the document.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 5.123 / 5.123A -> ITU; US123 -> both tables; NG123 -> non-Federal; G123 -> Federal.
FOOTNOTE_RE = re.compile(r"\b(?:5\.\d+[A-Z]*|US\d+[A-Z]*|NG\d+[A-Z]*|G\d+[A-Z]*)\b")

_RANGE_RE = re.compile(r"^(?P<lo>[\d][\d\s.]*)-(?P<hi>[\d][\d\s.]*)$")
_BELOW_RE = re.compile(r"^Below\s+(?P<hi>[\d][\d\s.]*)$")

UNIT_HZ = {"kHz": 1_000, "MHz": 1_000_000, "GHz": 1_000_000_000}


@dataclass
class Service:
    name: str
    primary: bool
    footnotes: list[str] = field(default_factory=list)


@dataclass
class ParsedCell:
    lo_hz: int | None
    hi_hz: int | None
    services: list[Service] = field(default_factory=list)
    footnotes: list[str] = field(default_factory=list)  # band-level
    not_allocated: bool = False
    raw_text: str = ""


def _num(text: str) -> float:
    # The table uses a thin space as a thousands separator in a few places.
    return float(text.replace(" ", "").replace(" ", ""))


def parse_range(line: str, unit: str) -> tuple[int | None, int | None, bool]:
    """Parse a cell's leading band-range line into integer hertz.

    Returns (lo, hi, matched).  Frequencies are stored as integers so that
    boundary comparisons are exact; the table's finest step is 100 Hz, well
    inside the range where scaling by the unit stays exact.
    """
    scale = UNIT_HZ[unit]
    text = line.replace("(Not Allocated)", "").strip()

    m = _BELOW_RE.match(text)
    if m:
        return 0, round(_num(m.group("hi")) * scale), True

    m = _RANGE_RE.match(text)
    if m:
        return (
            round(_num(m.group("lo")) * scale),
            round(_num(m.group("hi")) * scale),
            True,
        )
    return None, None, False


def _is_footnote_only(line: str) -> bool:
    return bool(line) and not FOOTNOTE_RE.sub("", line).strip()


def _rejoin(lines: list[str]) -> list[str]:
    """Undo the print layout's hard wrapping."""
    out: list[str] = []
    for line in lines:
        if out:
            prev = out[-1]
            if prev.endswith("-"):
                # Hyphenated wrap, e.g. "EARTH EXPLORATION-" + "SATELLITE".
                out[-1] = prev + line
                continue
            if line[:1] == "(" or (line[:1].isalpha() and line[:1].islower()):
                # Qualifier or lowercase continuation of the name above.
                out[-1] = prev + " " + line
                continue
        out.append(line)
    return out


def _is_primary(name: str) -> bool:
    """Capitalised first word => primary allocation."""
    first = next((w for w in name.split() if w[:1].isalpha()), "")
    letters = [c for c in first if c.isalpha()]
    return len(letters) >= 2 and all(c.isupper() for c in letters)


_SEE_PREV_RE = re.compile(r"see previous page|\(see previous page\)", re.I)


def is_pointer(text: str) -> bool:
    """True for the table's cross-page pointers, which carry no allocation."""
    return bool(_SEE_PREV_RE.search(text))


def split_cell(text: str, unit: str) -> list[ParsedCell]:
    """Split a cell that holds more than one band.

    Page layout occasionally packs two consecutive bands into a single Word
    cell (17.8-18.142 GHz and 18.142-18.3 GHz share one), which would otherwise
    silently drop the second band and open a gap in the spectrum.
    """
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    starts = [i for i, ln in enumerate(lines) if parse_range(ln, unit)[2]]
    if len(starts) <= 1:
        return [parse_cell(text, unit)]
    chunks = []
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(lines)
        chunks.append(parse_cell("\n".join(lines[start:end]), unit))
    return chunks


def parse_cell(text: str, unit: str) -> ParsedCell:
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    if not lines:
        return ParsedCell(None, None, raw_text=text)

    lo, hi, matched = parse_range(lines[0], unit)
    body = lines[1:] if matched else lines
    cell = ParsedCell(
        lo_hz=lo,
        hi_hz=hi,
        not_allocated="Not Allocated" in lines[0],
        raw_text=text,
    )

    body = _rejoin(body)

    # Split off the trailing run of footnote-only lines: the band-level block.
    tail = len(body)
    while tail > 0 and _is_footnote_only(body[tail - 1]):
        tail -= 1
    for line in body[tail:]:
        cell.footnotes.extend(FOOTNOTE_RE.findall(line))

    for line in body[:tail]:
        if _is_footnote_only(line):
            # An interior footnote-only line belongs to the service above it.
            if cell.services:
                cell.services[-1].footnotes.extend(FOOTNOTE_RE.findall(line))
            else:
                cell.footnotes.extend(FOOTNOTE_RE.findall(line))
            continue
        notes = FOOTNOTE_RE.findall(line)
        name = FOOTNOTE_RE.sub("", line)
        name = re.sub(r"\s{2,}", " ", name).strip(" \t.,")
        if not name:
            continue
        cell.services.append(Service(name=name, primary=_is_primary(name), footnotes=notes))

    return cell
