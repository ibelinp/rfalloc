"""Stage 1: turn the FCC Online Table of Frequency Allocations into flat rows.

The source document (fcctable.docx) is a print layout, not a data file.  Three
properties of it drive the design here:

  * It is split into ~31 *sections* ("Table of Frequency Allocations 150.8-162.0375
    MHz (VHF)"), each spanning several Word tables because of page breaks.  The
    unit (kHz/MHz/GHz) is stated only in the section heading, never in the cells.
  * Word re-autofits the column widths on every page, so grid column *indices*
    mean nothing across tables.  Column identity has to come from the horizontal
    extent of each cell, calibrated against the "Region 1 Table / Region 2 Table
    / ..." header row and inherited by the continuation pages of that section.
  * Every cell restates its own band range, which makes each cell independently
    parseable and lets us recover from page breaks that split a band.

Output is one record per (band, column) cell, still carrying raw text.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from docx_grid import Cell, Table, read_body

# The six logical columns of the Allocation Table, left to right.
COLUMNS = ["itu_r1", "itu_r2", "itu_r3", "us_federal", "us_non_federal", "fcc_parts"]

# Number of Word tables at the head of the document that make up the Allocation
# Table itself; everything after is the notes/footnote prose and its own tables.
ALLOCATION_TABLE_COUNT = 61

_UNIT_HZ = {"kHz": 1_000, "MHz": 1_000_000, "GHz": 1_000_000_000}

_SECTION_RE = re.compile(
    r"Table of Frequency Allocations\s+"
    r"(?P<lo>[\d.]+)\s*-\s*(?P<hi>[\d.]+)\s*(?P<unit>kHz|MHz|GHz)"
    r"(?:\s*\((?P<label>[^)]*)\))?"
)

_HEADER_TOKENS = (
    "Region 1 Table",
    "Region 2 Table",
    "Region 3 Table",
    "International Table",
    "United States Table",
    "Federal Table",
    "Non-Federal Table",
    "FCC Rule Part(s)",
)


@dataclass
class Section:
    lo_hz: int
    hi_hz: int
    unit: str
    label: str  # e.g. "VHF", "SHF/EHF"
    bounds: list[float] = field(default_factory=list)  # 7 fractional column edges


@dataclass
class RawCell:
    """One cell of the Allocation Table, tagged with the column(s) it covers."""

    columns: list[str]
    text: str
    section_label: str
    unit: str
    table_index: int
    row_index: int


def _is_header_row(row: list[Cell]) -> bool:
    joined = " ".join(c.text for c in row)
    return any(tok in joined for tok in _HEADER_TOKENS)


MIN_COLUMN_WIDTH = 0.04

_COLUMN_LABELS = [
    "Region 1 Table",
    "Region 2 Table",
    "Region 3 Table",
    "Federal Table",
    "Non-Federal Table",
    "FCC Rule Part(s)",
]


def _column_bounds(row: list[Cell]) -> list[float] | None:
    """Recover the six column edges from a "Region 1 Table ..." header row.

    Read the edges off the *labelled* cells rather than off every cell in the
    row.  Several header rows carry a hairline spacer cell, and taking every
    edge lets that spacer shift the whole boundary list one place -- which then
    mis-columns every data row on the pages that inherit these bounds.  A few
    header rows are also laid out on a narrower grid than the page, so the
    result is rescaled to span the full width.
    """
    found: dict[str, Cell] = {}
    for cell in row:
        for label in _COLUMN_LABELS:
            if label in cell.text and label not in found:
                found[label] = cell

    if not all(label in found for label in _COLUMN_LABELS[:5]):
        return None

    edges = [found[label].x0 for label in _COLUMN_LABELS[:5]]
    last = found.get(_COLUMN_LABELS[5])
    if last is not None:
        edges.append(last.x0)
        right = last.x1
    else:
        # No rule-part header on this row; the non-Federal cell ends the table.
        edges.append(found["Non-Federal Table"].x1)
        right = edges[-1]
    edges.append(right)

    edges[0] = 0.0
    if right <= 0:
        return None
    edges = [round(e / right, 4) for e in edges]

    if len(edges) != 7 or any(b <= a for a, b in zip(edges, edges[1:])):
        return None

    # A handful of pages carry a header block laid out on a different grid than
    # the body underneath it -- on page 27 "Region 1 Table" sits in a cell four
    # thousandths of the table wide, and trusting it mis-columns the whole page.
    # Every real column is a substantial fraction of the width, so an implausibly
    # narrow one means the header is unusable; the previous section's geometry is
    # a better guide than a broken one.
    if min(b - a for a, b in zip(edges, edges[1:])) < MIN_COLUMN_WIDTH:
        return None
    return edges


def _cell_span_hz(text: str, unit: str) -> tuple[int, int] | None:
    """The full band range this cell declares, used to advance column state."""
    from fcc_cells import parse_range

    spans = [parse_range(ln.strip(), unit) for ln in text.split("\n") if ln.strip()]
    spans = [(lo, hi) for lo, hi, ok in spans if ok]
    return (spans[0][0], spans[-1][1]) if spans else None


def _cell_lo_hz(text: str, unit: str) -> int | None:
    """The lower edge of the band this cell declares, if it declares one."""
    from fcc_cells import parse_range

    first = next((ln.strip() for ln in text.split("\n") if ln.strip()), "")
    lo, _hi, ok = parse_range(first, unit)
    return lo if ok else None


_G_RE = re.compile(r"\bG\d+[A-Z]*\b")
_NG_RE = re.compile(r"\bNG\d+[A-Z]*\b")
_US_RE = re.compile(r"\bUS\d+[A-Z]*\b")
_PART_RE = re.compile(r"^.+?\s*\(\d+[A-Z]?\)\s*$", re.M)

_VIOLATION = -100.0
_SATISFIED = 2.0


def _content_score(text: str, cols: set[str]) -> float:
    """Score a candidate column assignment against the cell's own content.

    Geometry alone is not enough: a handful of continuation pages lay their rows
    out on a different grid than the section header declares, which shifts every
    cell in the row by one column.  The footnote classes pin them back down,
    because the printed table uses each class in exactly one place:

        G nnn   Federal table only
        NG nnn  non-Federal table only
        US nnn  the US table (either side), never the international columns
        "Name (99)"  the FCC Rule Part column only
    """
    score = 0.0
    us_side = cols & {"us_federal", "us_non_federal"}

    if _G_RE.search(text):
        score += _SATISFIED if "us_federal" in cols else _VIOLATION
    if _NG_RE.search(text):
        score += _SATISFIED if "us_non_federal" in cols else _VIOLATION
    if _US_RE.search(text):
        score += _SATISFIED if us_side else _VIOLATION
    if _PART_RE.match(text.strip()) and "\n" not in text.strip():
        score += _SATISFIED if "fcc_parts" in cols else _VIOLATION
    return score


def _geometry_score(cell: Cell, bounds: list[float], j: int, e: int) -> float:
    """How well does spanning columns j..e match where this cell actually sits?

    Each column contributes ``2 * overlap - 1``, so covering more than half of a
    column pays and covering less costs.  Without the penalty term a cell could
    claim every column it barely grazes at no cost, since raw overlap is never
    negative.
    """
    total = 0.0
    for c in range(j, e + 1):
        lo, hi = bounds[c], bounds[c + 1]
        width = hi - lo
        if width <= 0:
            continue
        overlap = max(0.0, min(cell.x1, hi) - max(cell.x0, lo))
        total += 2.0 * (overlap / width) - 1.0
    return total


def _continuity_score(
    lo_hz: int | None,
    cols: range,
    state: dict[str, tuple[int, int]],
) -> float:
    """Reward a placement that continues the column where it left off.

    This is the sharpest signal in the whole document.  The Allocation Table
    partitions the spectrum, so within any one column each band begins exactly
    where its predecessor ended.  A cell offering "430-432" is therefore almost
    certainly *not* in a column whose last band ended at 450 MHz, no matter what
    the page geometry suggests.  Page breaks legitimately restate the band that
    is already open, so a repeat is treated as neutral rather than punished.
    """
    if lo_hz is None:
        return 0.0
    score = 0.0
    for c in cols:
        prev = state.get(COLUMNS[c])
        if prev is None:
            continue
        last_lo, last_hi = prev
        if lo_hz == last_hi:
            score += 3.0
        elif lo_hz == last_lo:
            score += 1.0
        else:
            score -= 2.0
    return score


def assign_row(
    cells: list[Cell],
    bounds: list[float],
    unit: str = "MHz",
    state: dict[str, tuple[int, int]] | None = None,
) -> list[list[str]]:
    """Assign each cell in a row to a run of logical columns.

    Columns run strictly left to right and a cell may span several of them, so
    this is a shortest-path problem over (cell, column) rather than an
    independent choice per cell.  Solving the row as a whole is what lets a
    content constraint on one cell correct the placement of its neighbours.
    """
    # Hairline cells (a thousandth of the table width) are kept deliberately.
    # They look like layout noise but act as column placeholders: on the pages
    # where a row is laid out on its own narrower grid, dropping them shifts
    # every remaining cell one column to the left.
    cells = [c for c in cells if c.text]
    n = len(cells)
    if n == 0:
        return []
    state = state or {}
    los = [_cell_lo_hz(c.text, unit) for c in cells]

    NEG = float("-inf")
    # best[i][j]: best achievable score placing cells[i:] into columns[j:].
    best = [[NEG] * (len(COLUMNS) + 1) for _ in range(n + 1)]
    choice: dict[tuple[int, int], tuple[int, int]] = {}
    for j in range(len(COLUMNS) + 1):
        best[n][j] = 0.0

    for i in range(n - 1, -1, -1):
        for j in range(len(COLUMNS) - 1, -1, -1):
            # Option A: leave column j unused (the row omits it).
            if best[i][j + 1] > best[i][j]:
                best[i][j] = best[i][j + 1]
                choice[(i, j)] = (-1, j + 1)
            # Option B: cell i spans columns j..e.
            for e in range(j, len(COLUMNS)):
                nxt = best[i + 1][e + 1]
                if nxt == NEG:
                    continue
                cols = {COLUMNS[c] for c in range(j, e + 1)}
                score = (
                    _geometry_score(cells[i], bounds, j, e)
                    + _content_score(cells[i].text, cols)
                    + _continuity_score(los[i], range(j, e + 1), state)
                    + nxt
                )
                if score > best[i][j]:
                    best[i][j] = score
                    choice[(i, j)] = (e, e + 1)

    out: list[list[str]] = [[] for _ in range(n)]
    i, j = 0, 0
    while i < n and j < len(COLUMNS):
        step = choice.get((i, j))
        if step is None:
            break
        e, j_next = step
        if e >= 0:
            out[i] = [COLUMNS[c] for c in range(j, e + 1)]
            i += 1
        j = j_next
    return out


def parse_rows(path: str) -> list[RawCell]:
    tables: list[Table] = read_body(path).tables()[:ALLOCATION_TABLE_COUNT]

    out: list[RawCell] = []
    section: Section | None = None
    # Per-column (last_lo, last_hi) in hertz, driving the continuity score.
    column_state: dict[str, tuple[int, int]] = {}
    # Default geometry, used only if a continuation page appears before any
    # header row has been seen.
    bounds = [0.0, 0.148, 0.317, 0.503, 0.702, 0.88, 1.0]

    for t_idx, table in enumerate(tables):
        for r_idx, row in enumerate(table.rows):
            joined = "\n".join(c.text for c in row)

            m = _SECTION_RE.search(joined)
            if m:
                scale = _UNIT_HZ[m.group("unit")]
                section = Section(
                    lo_hz=round(float(m.group("lo")) * scale),
                    hi_hz=round(float(m.group("hi")) * scale),
                    unit=m.group("unit"),
                    label=m.group("label") or "",
                )
                continue

            new_bounds = _column_bounds(row)
            if new_bounds:
                bounds = new_bounds
                if section:
                    section.bounds = new_bounds
                continue

            if _is_header_row(row):
                continue

            usable = [c for c in row if c.text and not c.merged_up]
            unit = section.unit if section else "kHz"
            assigned = assign_row(usable, bounds, unit, column_state)
            for cell, cols in zip(usable, assigned):
                if not cols:
                    continue
                lo_hi = _cell_span_hz(cell.text, unit)
                if lo_hi is not None:
                    for col in cols:
                        column_state[col] = lo_hi
                out.append(
                    RawCell(
                        columns=cols,
                        text=cell.text,
                        section_label=section.label if section else "",
                        unit=section.unit if section else "kHz",
                        table_index=t_idx,
                        row_index=r_idx,
                    )
                )
    return out


if __name__ == "__main__":
    import sys

    from build_allocations import SOURCE_DOC

    cells = parse_rows(sys.argv[1] if len(sys.argv) > 1 else SOURCE_DOC)
    print(f"{len(cells)} cells")
