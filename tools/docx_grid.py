"""Dependency-free extraction of tables and body text from a .docx file.

We deliberately avoid python-docx so that contributors can run the build with a
bare Python 3 install.  The only thing we need out of WordprocessingML is:

  * the body in document order (paragraphs interleaved with tables), because the
    FCC table's units (kHz / MHz / GHz) live in the page heading *between*
    tables rather than inside them;
  * a rectangular grid per table, with `gridSpan` expanded and `vMerge`
    continuation cells resolved back to the cell that started the merge.

Everything else in the file is ignored.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _q(tag: str) -> str:
    return W + tag


@dataclass
class Cell:
    """One physical table cell, placed on the table's column grid."""

    text: str
    col: int  # first grid column occupied
    span: int  # number of grid columns occupied
    row: int
    # Horizontal extent as a fraction of the table width.  The FCC document
    # re-autofits every page, so grid *indices* are meaningless across tables
    # while these fractions stay stable within a section.
    x0: float = 0.0
    x1: float = 1.0
    # True when this cell is a vMerge continuation, i.e. visually part of the
    # cell above.  Its own text is normally empty.
    merged_up: bool = False


@dataclass
class Table:
    rows: list[list[Cell]] = field(default_factory=list)
    grid: list[int] = field(default_factory=list)  # w:tblGrid column widths, twips

    @property
    def width(self) -> int:
        return max((c.col + c.span for row in self.rows for c in row), default=0)


@dataclass
class Body:
    """Document body in reading order."""

    blocks: list[tuple[str, object]] = field(default_factory=list)  # ("p", str) | ("tbl", Table)

    def tables(self) -> list[Table]:
        return [b for kind, b in self.blocks if kind == "tbl"]


def _text_of(el: ET.Element) -> str:
    """Flatten a paragraph or cell to text.

    Word encodes several things as elements rather than characters.  The one
    that matters here is `noBreakHyphen`: the FCC table uses it inside every
    band range, so dropping it silently welds "172.2-172.8" into "172.2172.8".
    """
    out: list[str] = []
    for node in el.iter():
        tag = node.tag
        if tag == _q("t"):
            out.append(node.text or "")
        elif tag == _q("noBreakHyphen"):
            out.append("-")
        elif tag == _q("softHyphen"):
            pass  # discretionary hyphen: not part of the content
        elif tag == _q("tab"):
            out.append(" ")
        elif tag in (_q("br"), _q("cr")):
            out.append("\n")
        elif tag == _q("p"):
            if out and not out[-1].endswith("\n"):
                out.append("\n")
    return "".join(out)


def _normalize(text: str) -> str:
    """Collapse Word's layout padding into plain lines.

    Cells are padded with runs of tabs and empty paragraphs purely for print
    layout; none of it carries meaning.
    """
    lines = [re.sub(r"[ \u00a0]+", " ", ln).strip() for ln in text.split("\n")]
    return "\n".join(ln for ln in lines if ln)


def _cell_props(tc: ET.Element) -> tuple[int, str | None]:
    """Return (gridSpan, vMerge state) for a `w:tc`."""
    span, vmerge = 1, None
    pr = tc.find(_q("tcPr"))
    if pr is not None:
        gs = pr.find(_q("gridSpan"))
        if gs is not None:
            span = int(gs.get(_q("val"), "1"))
        vm = pr.find(_q("vMerge"))
        if vm is not None:
            # An omitted w:val defaults to "continue" per the spec.
            vmerge = vm.get(_q("val"), "continue")
    return span, vmerge


def _parse_table(tbl: ET.Element) -> Table:
    grid_el = tbl.find(_q("tblGrid"))
    grid = (
        [int(gc.get(_q("w"), "0")) for gc in grid_el.findall(_q("gridCol"))]
        if grid_el is not None
        else []
    )
    edges = [0]
    for w in grid:
        edges.append(edges[-1] + w)
    total = edges[-1] or 1

    table = Table(grid=grid)
    for r_idx, tr in enumerate(tbl.findall(_q("tr"))):
        row: list[Cell] = []
        col = 0
        for tc in tr.findall(_q("tc")):
            span, vmerge = _cell_props(tc)
            text = _normalize(_text_of(tc))
            merged_up = vmerge == "continue"
            if merged_up and not text:
                # Inherit from the cell that started the merge, so every row of
                # the grid is independently readable.
                for prev in reversed(table.rows):
                    match = next((c for c in prev if c.col == col and not c.merged_up), None)
                    if match is not None:
                        text = match.text
                        break
            lo = edges[min(col, len(edges) - 1)]
            hi = edges[min(col + span, len(edges) - 1)]
            row.append(
                Cell(
                    text=text,
                    col=col,
                    span=span,
                    row=r_idx,
                    x0=lo / total,
                    x1=hi / total,
                    merged_up=merged_up,
                )
            )
            col += span
        table.rows.append(row)
    return table


def read_body(path: str) -> Body:
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml")
    root = ET.fromstring(xml)
    body_el = root.find(_q("body"))
    if body_el is None:
        raise ValueError(f"{path}: no w:body")

    body = Body()
    for child in body_el:
        if child.tag == _q("p"):
            txt = _normalize(_text_of(child))
            if txt:
                body.blocks.append(("p", txt))
        elif child.tag == _q("tbl"):
            body.blocks.append(("tbl", _parse_table(child)))
    return body
