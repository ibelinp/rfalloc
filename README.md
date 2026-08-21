# rfalloc

[![CI](https://github.com/ibelinp/rfalloc/actions/workflows/ci.yml/badge.svg)](https://github.com/ibelinp/rfalloc/actions/workflows/ci.yml)
[![Code: MIT](https://img.shields.io/badge/code-MIT-blue.svg)](LICENSE)
[![Data: CC0](https://img.shields.io/badge/data-CC0--1.0-lightgrey.svg)](LICENSE-DATA)
[![Source revision](https://img.shields.io/badge/FCC%20table-3%20Apr%202026-green.svg)](sources/README.md)

Reverse frequency lookup for SDR. Click a signal, learn what it is.

Every authoritative source for spectrum allocation is a PDF, a wall chart, or a
Word document laid out for print. None of them can be queried by frequency. This
project parses them into a database that can, so a receiver can show something
useful when you tap a peak on the waterfall.

```
$ python3 tools/lookup.py 162.55

── 162.55 MHz ──────────────────────────────────────────────────

Known use
  • [US] NOAA Weather Radio WX1  [Weather]
    162.537 MHz – 162.562 MHz   NFM
    NOAA All Hazards continuous broadcast; NWS forecast and warning audio.
    source: NWS / NTIA Redbook
  • [EU] VHF PMR (CEPT)  [Land Mobile]
    146 MHz – 174 MHz   NFM/DMR
    European private mobile radio; 12.5 kHz narrowband. Note 2 m amateur ends at 146.
    source: ERC/REC 70-03 / national

United States allocation
  United States (Federal)
    162.037 MHz – 173.2 MHz: FIXED, MOBILE
    footnotes: US8, US11, US13, US55, US73, US300, US312, G5
  United States (non-Federal)
    162.037 MHz – 173.2 MHz: no service listed
    footnotes: US8, US11, US13, US55, US73, US300, US312

International allocation  (Region 1 = Europe, Africa, Middle East)
  ITU Region 1
    162.037 MHz – 174 MHz: FIXED, MOBILE except aeronautical mobile
  ITU Regions 2–3
    162.037 MHz – 174 MHz: FIXED, MOBILE

FCC rule parts
  Part 74D — Remote Pickup
  Part 90 — Private Land Mobile
```

Results are ranked narrowest first, so the recognisable name leads. Restrict the
curated layer with `--jurisdiction us` or `--jurisdiction eu`; add `--footnotes`
for the full text of every footnote that applies.

## Contents at a glance

| | |
|---|---|
| Allocation bands | 2,666 across 5 jurisdictions |
| Coverage | 0 Hz to 275 GHz, no gaps |
| Footnotes | 973, with full text |
| Rule part links | 594 |
| Curated channels | 368 (238 US, 130 European) |
| Source revision | FCC Online Table, 3 April 2026 |
| Largest artifact | 1.6 MB SQLite; 135 KB flat binary |
| Dependencies | none, at build time or runtime |

## Why there are two layers

The example above is the entire design argument. The statutory allocation table
answers 162.55 MHz with **FIXED, MOBILE**. That is correct, and it is worthless
to somebody staring at a waterfall. The name anybody actually wants, *NOAA
Weather Radio*, appears nowhere in the allocation table.

So the database carries two layers and ranks results by specificity.

| Layer | Question it answers | Where it comes from | Size |
|---|---|---|---|
| Allocation | Which service class owns this band? | [47 CFR 2.106](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-2/subpart-B/section-2.106), parsed | 2,666 bands |
| Known use | What would I actually hear here? | Curated per rule part and standard | 368 channels |

A lookup returns both, narrowest first, so the recognisable name leads and the
statutory allocation sits underneath it. Because the allocation layer has no
gaps, a query inside 0 Hz to 275 GHz can never come back empty.

There is deliberately no third layer for licensees. FCC ULS will tell you which
station holds 155.475 MHz in your county, but that is millions of rows, it
depends on location, and it would dominate the repository. It belongs in a
separate project.

## Jurisdictions

| id | Meaning | Layer |
|---|---|---|
| `itu-r1` | ITU Region 1: Europe, Africa, Middle East, former USSR | Allocation |
| `itu-r2` | ITU Region 2: the Americas | Allocation |
| `itu-r3` | ITU Region 3: Asia-Pacific | Allocation |
| `us-federal` | US Federal table, administered by NTIA | Allocation |
| `us-non-federal` | US non-Federal table, administered by the FCC | Allocation |
| `us` | Curated US channel plans | Known use |
| `eu` | Curated European (CEPT) channel plans | Known use |

Regional differences are real and routinely get flipped by US-authored data.
Several are pinned by tests.

| | Region 1 (Europe) | United States |
|---|---|---|
| 2 m amateur band | 144 to 146 MHz | 144 to 148 MHz |
| 70 cm amateur band | 430 to 440 MHz | 420 to 450 MHz |
| Amateur at 432–438 MHz | Primary | Secondary |
| 433 MHz | ISM band | Part 15 use inside the amateur band |
| FM broadcast | 87.5 to 108 MHz | 88 to 108 MHz |
| MW broadcast raster | 9 kHz | 10 kHz |
| VHF airband spacing | 8.33 kHz mandatory | 25 kHz |

European curated coverage: PMR446, the full DAB Band III block raster, 868 MHz
SRD and LoRaWAN EU868, 433 MHz SRD and LPD433, TETRA, GSM-R, wireless M-Bus,
Z-Wave EU, DCF77 and MSF, and the CEPT cellular band pairings.

Europe currently gets the international allocation layer, which is ITU Region 1,
rather than a national statutory table. Nothing here encodes a Dutch or German
licensing condition. Closing that would mean parsing the
[CEPT ECC European Common Allocation Table](https://efis.cept.org/), a separate
document of comparable size.

## How the parse is verified

A mis-parse of a print layout looks exactly like a correct one at a glance, so
correctness is checked structurally. The Allocation Table partitions the
spectrum: within any one jurisdiction, each band must begin precisely where its
predecessor ended.

```
itu-r1           bands=  543  gaps=   0  overlaps=   0  span=0 Hz-275 GHz
itu-r2           bands=  543  gaps=   0  overlaps=   0  span=0 Hz-275 GHz
itu-r3           bands=  537  gaps=   0  overlaps=   0  span=0 Hz-275 GHz
us-federal       bands=  501  gaps=   0  overlaps=   0  span=0 Hz-275 GHz
us-non-federal   bands=  542  gaps=   0  overlaps=   0  span=0 Hz-275 GHz
```

That single check catches almost any column misassignment, because a cell put in
the wrong column leaves a hole where it belonged and collides where it landed.
Alongside it sit spot checks against allocations verifiable from other sources:
FM broadcast, the 2 m amateur band, marine Channel 16, AIS 1 and 2, GPS L1,
ADS-B.

41 tests run across the three languages.

| Suite | Tests | Command |
|---|---|---|
| Parser invariants and known frequencies | 25 | `make test-python` |
| C reader, including malformed input | 8 | `make test-c` |
| Swift wrapper | 8 | `make test-swift` |

## Build

Python 3.11 or newer and a C99 compiler. Nothing else.

```bash
make                      # parse the source and build every artifact
make test                 # all three suites
make lookup FREQ=1090
```

Artifacts land in `build/`.

| File | Size | Use it when |
|---|---|---|
| `rfalloc.sqlite` | 1.6 MB | You want everything: footnote text, rule parts, raw source cells |
| `rfalloc.json` | 1.7 MB | Same content, no SQLite dependency |
| `rfalloc.min.json` | 351 KB | Lookup only, for a web front end |
| `rfalloc.bin` | 135 KB | Embedding in an app via the C or Swift reader |

## Swift

```swift
import RFAlloc

let db = try SpectrumDatabase(contentsOf: url)   // rfalloc.bin

db.summary(at: 162_550_000)                      // "NOAA Weather Radio WX1"
db.channels(at: 446_006_250).first?.name         // "PMR446 Channel 1"

// A waterfall wants everything across the visible span, not one point.
db.channels(in: 144_000_000 ..< 148_000_000)

// Region 1 is Europe. All three ITU regions are present.
db.allocations(at: 433_920_000).filter { $0.jurisdiction == .ituRegion1 }
```

Add it as a package dependency, or drag `c/rfalloc.c` and `c/rfalloc.h` straight
into an Xcode target.

Queries are local, read-only, and allocation-free inside the reader, so calling
them from a rendering path is fine. A tooltip never triggers a network request.

## C

```c
#include "rfalloc.h"

rfalloc_db db;
if (rfalloc_open(&db, bytes, len) != RFALLOC_OK) { /* ... */ }

rfalloc_channel hits[8];
int n = rfalloc_channels_at(&db, 162550000ULL, hits, 8);
printf("%s\n", hits[0].name);       /* NOAA Weather Radio WX1 */
```

`c/rfalloc.c` is 211 lines of C99 with no dependency beyond the standard
library. It allocates nothing, reads scalars byte by byte so that unaligned
loads and byte order are non-issues, and validates every header offset against
the file size before dereferencing anything. Vendor the two files anywhere.

## Design decisions worth knowing

**Frequencies are integer hertz.** Floating-point megahertz makes band-edge
comparison unreliable in precisely the place where correctness matters.

**Ranges are half-open, `[lo, hi)`.** Bands in the source abut exactly, as in
`148–149.9` followed by `149.9–150.05`. A closed upper bound would make every
boundary frequency match two bands at once.

**Jurisdiction is a table, never a column.** One source document already yields
five jurisdictions, so the schema was multi-national from the first commit.
Adding an administration to the curated layer means creating a directory under
`data/curated/`; the directory name is the jurisdiction.

**Lookups are range-overlap queries.** Hovering gives you a point, but a
spectrum display wants every allocation across the visible span so it can draw a
band ribbon beneath the trace.

**Nothing is lossy.** Every band keeps the verbatim source cell in `raw_text`,
so parsing choices can be revisited without going back to the document.

## Layout

```
sources/          FCC source documents, kept for reproducible builds
tools/            parser and build pipeline, Python 3.11+, no dependencies
data/curated/
    us/           US channel plans, one CSV per service
    eu/           European (CEPT) channel plans
c/                C99 reader
swift/            Swift wrapper around the C reader
docs/             parsing methodology, schema reference
```

## Releases

Prebuilt artifacts are attached to every [release](https://github.com/ibelinp/rfalloc/releases),
so you do not need Python or a compiler to use the data. Tagging `v*` builds and
publishes them automatically, with checksums.

## Licence

Code under MIT. Data under CC0, so the tables can be embedded in a commercial
product with no conditions attached.

The derived data is public domain because works of the United States Government
carry no copyright under
[17 U.S.C. 105](https://www.law.cornell.edu/uscode/text/17/105).
[LICENSE-DATA](LICENSE-DATA) sets out the reasoning and the one rule that must
never be broken: no imports from RadioReference or any other proprietary
frequency directory, not even partially. Those compilations are licensed, and a
single import would make the whole database undistributable.

## Contributing

The curated layer is where help is worth most, and it needs no code. Add a row
to a CSV under `data/curated/<jurisdiction>/` with a public source citation.
[CONTRIBUTING.md](CONTRIBUTING.md) has the rules; [docs/PARSING.md](docs/PARSING.md)
covers how the parse works and what is already known to be imperfect.

## Further reading

| Document | |
|---|---|
| [docs/PARSING.md](docs/PARSING.md) | How a print layout is turned into data, and the known limitations |
| [docs/SCHEMA.md](docs/SCHEMA.md) | Table reference and example queries |
| [sources/README.md](sources/README.md) | Provenance of the source documents |
| [FCC Online Table of Frequency Allocations](https://www.fcc.gov/engineering-technology/policy-and-rules-division/general/radio-spectrum-allocation) | Upstream source |
| [47 CFR 2.106 on eCFR](https://www.ecfr.gov/current/title-47/chapter-I/subchapter-A/part-2/subpart-B/section-2.106) | The codified table |
| [NTIA Redbook](https://www.ntia.gov/page/2011/manual-regulations-and-procedures-federal-radio-frequency-management-redbook) | Federal use, beyond what 2.106 records |
| [CEPT ECC EFIS](https://efis.cept.org/) | European allocation data |
