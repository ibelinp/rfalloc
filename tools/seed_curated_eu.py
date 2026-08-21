"""One-time seed for the European regular channel grids (data/curated/eu/).

Same rule as the US seed: the CSVs are the source of truth once written, and
this script exists only so the systematic grids -- PMR446 and the DAB Band III
block raster -- are generated rather than transcribed by hand.

Jurisdiction is the containing directory, so nothing here names it.
"""

from __future__ import annotations

import pathlib
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from seed_curated import FIELDS, ch, write as _write  # noqa: E402

OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated" / "eu"


def write(filename: str, rows: list[dict]) -> None:
    import csv

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"{path.parent.name}/{path.name:26} {len(rows):4} rows")


# --------------------------------------------------------------- PMR446 ----
# 16 analogue channels, 12.5 kHz spacing, 446.00625 upward.  Licence-exempt
# across CEPT at 500 mW ERP; the direct European counterpart to FRS.
pmr = []
base = Decimal("446.00625")
for n in range(1, 17):
    freq = base + Decimal("0.0125") * (n - 1)
    pmr.append(ch(
        f"pmr446-{n:02d}", freq, 12.5, f"PMR446 Channel {n}", "Personal Radio",
        "Licence-exempt CEPT PMR446; 500 mW ERP, integral antenna only."
        + (" Also used by dPMR446/DMR446 digital sets." if n >= 9 else ""),
        "NFM", "pmr446;personal;cept", "ECC/DEC/(15)05 / ETSI EN 300 296",
    ))
write("personal-radio.csv", pmr)

# ------------------------------------------------------------- DAB Band III --
# The ETSI Band III block raster.  Each block is 1.536 MHz wide inside a
# 1.712 MHz raster step; the centre frequencies are fixed Europe-wide, while
# which blocks are actually in use is a national matter.
DAB_BLOCKS = [
    ("5A", "174.928"), ("5B", "176.640"), ("5C", "178.352"), ("5D", "180.064"),
    ("6A", "181.936"), ("6B", "183.648"), ("6C", "185.360"), ("6D", "187.072"),
    ("7A", "188.928"), ("7B", "190.640"), ("7C", "192.352"), ("7D", "194.064"),
    ("8A", "195.936"), ("8B", "197.648"), ("8C", "199.360"), ("8D", "201.072"),
    ("9A", "202.928"), ("9B", "204.640"), ("9C", "206.352"), ("9D", "208.064"),
    ("10A", "209.936"), ("10B", "211.648"), ("10C", "213.360"), ("10D", "215.072"),
    ("11A", "216.928"), ("11B", "218.640"), ("11C", "220.352"), ("11D", "222.064"),
    ("12A", "223.936"), ("12B", "225.648"), ("12C", "227.360"), ("12D", "229.072"),
    ("13A", "230.784"), ("13B", "232.496"), ("13C", "234.208"), ("13D", "235.776"),
    ("13E", "237.488"), ("13F", "239.200"),
]
write("dab.csv", [
    ch(f"dab-{blk.lower()}", f, 1536, f"DAB Block {blk}", "Broadcast",
       "DAB/DAB+ digital radio multiplex block; national use varies by country.",
       "OFDM", "dab;broadcast;digital", "ETSI EN 300 401 / ECC")
    for blk, f in DAB_BLOCKS
])
