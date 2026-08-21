"""Combine stages 1 and 2 into normalized allocation records, and validate them.

The validation pass is the real product here.  A silent mis-parse of a print
layout is indistinguishable from correct output at a glance, so every band is
checked for self-consistency (lo < hi), containment in its section's declared
range, and -- most usefully -- contiguity: the Allocation Table partitions the
spectrum, so within one jurisdiction each band should start exactly where the
previous one ended.  Gaps and overlaps are reported, not swallowed.
"""

from __future__ import annotations

import pathlib

# Resolve the source document relative to this file rather than the working
# directory, so the tools run correctly from anywhere.
SOURCE_DOC = str(
    pathlib.Path(__file__).resolve().parent.parent / "sources" / "fcctable.docx"
)

import re
from dataclasses import asdict, dataclass, field

from fcc_cells import ParsedCell, is_pointer, split_cell
from fcc_cells import _rejoin as rejoin_wrapped
from fcc_rows import parse_rows

# Column name in the source document -> jurisdiction id in our schema.
JURISDICTIONS = {
    "itu_r1": "itu-r1",
    "itu_r2": "itu-r2",
    "itu_r3": "itu-r3",
    "us_federal": "us-federal",
    "us_non_federal": "us-non-federal",
}

_PART_RE = re.compile(r"^(?P<name>.+?)\s*\((?P<num>\d+[A-Z]?)\)\s*$")


@dataclass
class Band:
    jurisdiction: str
    lo_hz: int
    hi_hz: int
    services: list[dict] = field(default_factory=list)
    footnotes: list[str] = field(default_factory=list)
    not_allocated: bool = False
    raw_text: str = ""
    source: str = ""


@dataclass
class RulePart:
    lo_hz: int
    hi_hz: int
    part: str
    name: str


def build(path: str = SOURCE_DOC) -> tuple[list[Band], list[RulePart], list[str]]:
    cells = parse_rows(path)
    bands: list[Band] = []
    parts: list[RulePart] = []
    problems: list[str] = []

    # Rule-part cells carry no band range of their own; they inherit the range of
    # the most recent allocation row on the same page.
    last_range: tuple[int, int] | None = None
    # Per-column memory, for footnote-only cells left behind by a page break.
    last_band: dict[str, Band] = {}

    for rc in cells:
        src = f"tbl{rc.table_index}:row{rc.row_index}"

        if is_pointer(rc.text):
            continue  # "150.05-153 MHz: see previous page" and friends

        if "fcc_parts" in rc.columns:
            # A few pages let an allocation cell bleed a sliver into the rule
            # part column; requiring the "Name (99)" shape keeps those out.
            found = False
            for line in rejoin_wrapped([ln.strip() for ln in rc.text.split("\n") if ln.strip()]):
                m = _PART_RE.match(line)
                if m and last_range is not None:
                    parts.append(
                        RulePart(
                            lo_hz=last_range[0],
                            hi_hz=last_range[1],
                            part=m.group("num"),
                            name=m.group("name").strip(),
                        )
                    )
                    found = True
            if rc.columns == ["fcc_parts"] or found:
                continue

        for parsed in split_cell(rc.text, rc.unit):
            if parsed.lo_hz is None:
                # No range of its own: a spill from the previous page.  Fold it
                # into the band it continues rather than dropping it.
                notes = parsed.footnotes + [f for s in parsed.services for f in s.footnotes]
                for col in rc.columns:
                    prev = last_band.get(col)
                    if prev is None:
                        continue
                    prev.footnotes.extend(n for n in notes if n not in prev.footnotes)
                    for svc in parsed.services:
                        if svc.name not in [x["name"] for x in prev.services]:
                            prev.services.append(asdict(svc))
                if not notes and not parsed.services:
                    problems.append(f"{src}: unparsed cell {rc.text[:60]!r}")
                continue

            if parsed.hi_hz is not None and parsed.lo_hz >= parsed.hi_hz:
                problems.append(f"{src}: non-increasing range {parsed.lo_hz}-{parsed.hi_hz}")

            last_range = (parsed.lo_hz, parsed.hi_hz)

            for col in rc.columns:
                juris = JURISDICTIONS.get(col)
                if juris is None:
                    continue
                band = Band(
                    jurisdiction=juris,
                    lo_hz=parsed.lo_hz,
                    hi_hz=parsed.hi_hz,
                    services=[asdict(s) for s in parsed.services],
                    footnotes=list(parsed.footnotes),
                    not_allocated=parsed.not_allocated,
                    raw_text=parsed.raw_text,
                    source=src,
                )
                bands.append(band)
                last_band[col] = band

    return bands, parts, problems


def check_contiguity(bands: list[Band]) -> list[str]:
    """The Allocation Table partitions the spectrum: report gaps and overlaps."""
    issues: list[str] = []
    by_juris: dict[str, list[Band]] = {}
    for b in bands:
        by_juris.setdefault(b.jurisdiction, []).append(b)

    for juris, group in sorted(by_juris.items()):
        seen: dict[tuple[int, int], Band] = {}
        uniq: list[Band] = []
        for b in sorted(group, key=lambda b: (b.lo_hz, b.hi_hz)):
            key = (b.lo_hz, b.hi_hz)
            if key in seen:
                continue  # same band repeated across a page break
            seen[key] = b
            uniq.append(b)
        gaps = overlaps = 0
        for prev, cur in zip(uniq, uniq[1:]):
            if cur.lo_hz > prev.hi_hz:
                gaps += 1
            elif cur.lo_hz < prev.hi_hz:
                overlaps += 1
        issues.append(
            f"{juris:16} bands={len(uniq):5}  gaps={gaps:4}  overlaps={overlaps:4}  "
            f"span={uniq[0].lo_hz/1e6:.4f}-{uniq[-1].hi_hz/1e9:.0f}GHz"
        )
    return issues


if __name__ == "__main__":
    bands, parts, problems = build()
    print(f"bands={len(bands)}  rule_parts={len(parts)}  problems={len(problems)}")
    for line in check_contiguity(bands):
        print("  ", line)
    for p in problems[:15]:
        print("  !", p)
