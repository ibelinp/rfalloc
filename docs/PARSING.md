# How the source is parsed, and what is imperfect about it

The input is `fcctable.docx` — the FCC Online Table of Frequency Allocations,
47 CFR 2.106. It is a Word document laid out for print, not a data file, and
almost every difficulty below follows from that one fact.

## Why not the eCFR API or the PDF

The eCFR serves 47 CFR Part 2 as XML, which sounds like the better source. It
isn't: the same print layout is preserved there, so the hard problems are
identical, and the Word file additionally carries exact cell geometry that turns
out to be the key to recovering column identity. The PDF is worse again — the
column structure exists only as ink positions.

The Word document also carries the footnotes and the rule-part index in the same
file, so one input yields the whole database.

## The four problems

### 1. Column identity is not in the file

The table has six logical columns — ITU Regions 1/2/3, US Federal, US
non-Federal, FCC Rule Parts — but Word re-autofits the grid on every page. Grid
*indices* are meaningless across tables: table widths range from 2 to 10 columns
for the same six-column layout, and the fractional position of the Region 1/2
boundary varies from 0.131 to 0.190 across pages.

So column identity is reconstructed per row from three signals, combined in a
single dynamic-programming assignment over `(cell, column)` in
`tools/fcc_rows.py`:

**Geometry.** Each column contributes `2 × overlap − 1`, so covering more than
half of a column pays and covering less costs. Calibrated against the
"Region 1 Table / Region 2 Table / …" header row and inherited by the
continuation pages of that section.

**Footnote class.** The decisive content signal, because the printed table uses
each class in exactly one place:

| Class | Appears in |
|---|---|
| `G nnn` | Federal table only |
| `NG nnn` | non-Federal table only |
| `US nnn` | the US table, either side, never international |
| `Name (99)` | the FCC Rule Part column only |

**Continuity.** The sharpest signal of all. The table partitions the spectrum, so
within a column each band begins exactly where its predecessor ended. A cell
offering `430-432` is therefore almost certainly not in a column whose last band
ended at 450 MHz, whatever the geometry suggests. Page breaks legitimately
restate an open band, so a repeat scores neutral rather than negative.

Solving the row as a whole, rather than each cell independently, is what lets a
content constraint on one cell correct the placement of its neighbours.

### 2. Rows that disagree with their own header

Some pages lay a row out on a narrower grid than the section header declares,
shifting every cell. Two traps here:

- **Hairline cells** a thousandth of the table wide look like layout noise but
  act as column placeholders. Dropping them shifts every remaining cell one
  column left. They are kept deliberately.
- **Malformed header rows.** On page 27 the "Region 1 Table" label sits in a cell
  0.4% of the table wide, disagreeing with its own data rows. Header rows whose
  narrowest column falls below 4% of the width are rejected, and the previous
  section's geometry is used instead.

### 3. The print layout hard-wraps everything

Every line in a cell is a separate Word paragraph — the document contains no
line-break elements at all. So paragraph structure cannot distinguish a wrapped
line from a meaningful one, and neither can indentation or style (both are
uniform within a cell).

Wrapped lines are rejoined on the observation that real service names always
begin with a capital: a line starting lowercase or with `(` continues the line
above, as does any line following one that ends in a hyphen. This recovers
`MOBILE-SATELLITE` + `(Earth-to-space)` and `EARTH EXPLORATION-` + `SATELLITE
(active)`.

One related trap: the document uses **non-breaking hyphens** inside band ranges.
A naive tag-strip silently welds `172.2-172.8` into `172.2172.8`, producing a
plausible-looking wrong number. `w:noBreakHyphen` is mapped explicitly.

### 4. Cells holding more than one band

Occasionally one Word cell packs two consecutive bands — 17.8–18.142 GHz and
18.142–18.3 GHz share a cell. Cells are split at every line that parses as a
band range, which would otherwise silently drop the second band.

## Verification

The parse is checked structurally, not by inspection, because a mis-parse of a
print layout looks exactly like a correct one at a glance. The Allocation Table
partitions the spectrum, so within each jurisdiction the bands must tile it
exactly. They do — 0 gaps and 0 overlaps in all five jurisdictions from 0 Hz to
275 GHz. `make test-python` enforces this, plus spot checks against
independently verifiable allocations (FM broadcast, the 2 m amateur band, marine
Channel 16, AIS 1 and 2, GPS L1, ADS-B).

## Known limitations

**Footnote attachment is deliberately conservative.** A footnote-only line may
either continue the run belonging to the service above it or open the
band-level block, and nothing in the file distinguishes the two — not paragraph
structure, not indentation, not style. The whole trailing run is therefore
treated as band-level. This never drops a footnote; it can attach one to the
band that the printed table pinned to a single service. Inline footnotes, the
majority case, stay correctly attached to their service. Every band keeps its
verbatim `raw_text`, so this can be refined later without reparsing.

**Two footnotes are cited but never defined.** `5.372` and `5.415` are
referenced by the table 15 and 14 times respectively and appear nowhere as
definitions. This is a gap in the FCC document, not in the parser. They are
stored with `text = NULL` and pinned by a test.

**Footnote sub-tables are not inlined.** Some footnotes carry their own tables —
state lists, hydro channel plans, observatory coordinates. These are marked in
the footnote text with `[table omitted — see source document]` rather than
flattened into prose. Extracting them is worthwhile future work.

**275 GHz is the ceiling.** Not a parser limit: the Radio Regulations allocate
nothing above it, and footnote 5.565 merely *identifies* parts of 275–1000 GHz
for passive and active use.

**`fahf.docx` is unused.** The FCC Allocation History File would support a
`last_amended` field per band and per-proceeding provenance. Not yet wired in.
