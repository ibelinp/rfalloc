"""Assemble the parsed sources into the shipped artifacts.

Outputs, all written to build/:
  rfalloc.sqlite  the full database, including footnote text and raw source cells
  rfalloc.json    the same content as JSON, for consumers without SQLite
  rfalloc.min.json  the lookup-only subset: bands, services and channels

Run:  python3 tools/build_db.py
"""

from __future__ import annotations

import csv
import json
import pathlib
import re
import sqlite3
import sys
from decimal import Decimal

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from build_allocations import build, check_contiguity  # noqa: E402
from docx_grid import read_body  # noqa: E402
from fcc_footnotes import parse_footnotes  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"
CURATED = ROOT / "data" / "curated"
SOURCE_DOC = ROOT / "sources" / "fcctable.docx"

JURISDICTIONS = [
    ("itu-r1", "ITU Region 1", "ITU", None, 1),
    ("itu-r2", "ITU Region 2", "ITU", None, 2),
    ("itu-r3", "ITU Region 3", "ITU", None, 3),
    ("us-federal", "United States (Federal)", "FCC/NTIA", "US", 2),
    ("us-non-federal", "United States (non-Federal)", "FCC", "US", 2),
    ("us", "United States (general)", "FCC", "US", 2),
    ("eu", "Europe (CEPT)", "CEPT/ECC", None, 1),
]

FOOTNOTE_CLASS_OF = {"5": "itu", "U": "us", "N": "ng", "G": "g"}


def source_revision() -> str:
    """The "Revised on ..." date the FCC stamps on the document."""
    for kind, value in read_body(str(SOURCE_DOC)).blocks[:40]:
        if kind == "p":
            m = re.search(r"Revised on\s+(.+?)\s*$", value)
            if m:
                return m.group(1)
    return "unknown"


def hz(value: str) -> int:
    """Decimal megahertz -> integer hertz, without going through binary floats."""
    return int((Decimal(value.strip()) * 1_000_000).to_integral_value())


def load_curated() -> list[dict]:
    """Read data/curated/<jurisdiction>/*.csv.

    The directory name is the jurisdiction, which keeps the CSV columns
    identical for every administration and makes adding one a matter of
    creating a folder.
    """
    known = {j[0] for j in JURISDICTIONS}
    rows: list[dict] = []
    seen: set[str] = set()
    for path in sorted(CURATED.glob("*/*.csv")):
        jurisdiction = path.parent.name
        if jurisdiction not in known:
            raise ValueError(
                f"{path}: '{jurisdiction}' is not a known jurisdiction; "
                f"add it to JURISDICTIONS first"
            )
        with path.open() as fh:
            for line_no, row in enumerate(csv.DictReader(fh), start=2):
                cid = row["id"].strip()
                if not cid:
                    continue
                if cid in seen:
                    raise ValueError(f"{path.name}:{line_no}: duplicate channel id {cid!r}")
                seen.add(cid)
                lo, hi = hz(row["lo_mhz"]), hz(row["hi_mhz"])
                if lo >= hi:
                    raise ValueError(f"{path.name}:{line_no}: {cid} has lo >= hi")
                rows.append(
                    {
                        "id": cid,
                        "jurisdiction": jurisdiction,
                        "lo_hz": lo,
                        "hi_hz": hi,
                        "name": row["name"].strip(),
                        "service": row["service"].strip(),
                        "description": row["description"].strip(),
                        "mode": row["mode"].strip(),
                        "tags": row["tags"].strip(),
                        "source": row["source"].strip(),
                    }
                )
    return rows


def main() -> None:
    BUILD.mkdir(exist_ok=True)
    bands, parts, problems = build()
    notes = parse_footnotes()
    channels = load_curated()
    revision = source_revision()

    contiguity = check_contiguity(bands)
    print(f"revision: {revision}")
    for line in contiguity:
        print("  ", line)
    if problems:
        print(f"  {len(problems)} parse problems")

    db_path = BUILD / "rfalloc.sqlite"
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    con.executescript((ROOT / "tools" / "schema.sql").read_text())

    con.executemany("INSERT INTO jurisdiction VALUES (?,?,?,?,?)", JURISDICTIONS)

    # Any footnote the table cites gets a row, even when the FCC document does
    # not reproduce its text -- a dangling reference is information too.
    referenced = {f for b in bands for f in b.footnotes}
    referenced |= {f for b in bands for s in b.services for f in s["footnotes"]}
    for fid in sorted(referenced | set(notes)):
        note = notes.get(fid)
        con.execute(
            "INSERT INTO footnote VALUES (?,?,?)",
            (fid, note.footnote_class if note else FOOTNOTE_CLASS_OF.get(fid[0], "itu"),
             note.text if note else None),
        )

    for band_id, b in enumerate(bands, start=1):
        con.execute(
            "INSERT INTO band VALUES (?,?,?,?,?,?,?)",
            (band_id, b.jurisdiction, b.lo_hz, b.hi_hz, int(b.not_allocated),
             b.raw_text, b.source),
        )
        for ordinal, svc in enumerate(b.services):
            con.execute(
                "INSERT INTO service VALUES (?,?,?,?)",
                (band_id, ordinal, svc["name"], int(svc["primary"])),
            )
            for fid in svc["footnotes"]:
                con.execute(
                    "INSERT INTO band_footnote VALUES (?,?,?,?)",
                    (band_id, fid, "service", ordinal),
                )
        for fid in b.footnotes:
            con.execute(
                "INSERT INTO band_footnote VALUES (?,?,?,?)", (band_id, fid, "band", None)
            )

    con.executemany(
        "INSERT INTO rule_part VALUES (?,?,?,?)",
        [(p.lo_hz, p.hi_hz, p.part, p.name) for p in parts],
    )
    con.executemany(
        "INSERT INTO channel VALUES (:id,:jurisdiction,:lo_hz,:hi_hz,:name,:service,"
        ":description,:mode,:tags,:source)",
        channels,
    )
    con.executemany(
        "INSERT INTO meta VALUES (?,?)",
        [
            ("source_document", "FCC Online Table of Frequency Allocations, 47 CFR 2.106"),
            ("source_revision", revision),
            ("band_count", str(len(bands))),
            ("channel_count", str(len(channels))),
            ("footnote_count", str(len(notes))),
            ("rule_part_count", str(len(parts))),
            ("frequency_unit", "hertz"),
            ("interval_convention", "half-open [lo_hz, hi_hz)"),
        ],
    )
    con.commit()

    full = {
        "meta": dict(con.execute("SELECT key, value FROM meta")),
        "jurisdictions": [
            dict(zip(("id", "name", "authority", "country", "itu_region"), j))
            for j in JURISDICTIONS
        ],
        "bands": [
            {
                "jurisdiction": b.jurisdiction, "lo_hz": b.lo_hz, "hi_hz": b.hi_hz,
                "not_allocated": b.not_allocated,
                "services": [
                    {"name": s["name"], "primary": s["primary"], "footnotes": s["footnotes"]}
                    for s in b.services
                ],
                "footnotes": b.footnotes,
            }
            for b in bands
        ],
        "footnotes": [
            {"id": fid, "class": (notes[fid].footnote_class if fid in notes
                                  else FOOTNOTE_CLASS_OF.get(fid[0], "itu")),
             "text": notes[fid].text if fid in notes else None}
            for fid in sorted(referenced | set(notes))
        ],
        "rule_parts": [
            {"lo_hz": p.lo_hz, "hi_hz": p.hi_hz, "part": p.part, "name": p.name}
            for p in parts
        ],
        "channels": channels,
    }
    (BUILD / "rfalloc.json").write_text(json.dumps(full, indent=1))

    minimal = {
        "meta": full["meta"],
        "bands": [
            {"j": b["jurisdiction"], "lo": b["lo_hz"], "hi": b["hi_hz"],
             "s": [[s["name"], 1 if s["primary"] else 0] for s in b["services"]]}
            for b in full["bands"]
        ],
        "channels": [
            {"lo": c["lo_hz"], "hi": c["hi_hz"], "n": c["name"],
             "sv": c["service"], "d": c["description"]}
            for c in channels
        ],
    }
    (BUILD / "rfalloc.min.json").write_text(json.dumps(minimal, separators=(",", ":")))

    con.close()
    for f in sorted(BUILD.iterdir()):
        print(f"  {f.name:22} {f.stat().st_size/1024:8.1f} KB")


if __name__ == "__main__":
    main()
