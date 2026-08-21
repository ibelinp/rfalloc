"""Reverse lookup: frequency in, plain-language answer out.

    python3 tools/lookup.py 162.55
    python3 tools/lookup.py 1090 --footnotes
    python3 tools/lookup.py 156.8 157.1 --span

Results are ranked by specificity, narrowest first, so the curated channel a
person would recognise leads and the statutory allocation backs it up.
"""

from __future__ import annotations

import argparse
import pathlib
import sqlite3

DB = pathlib.Path(__file__).resolve().parent.parent / "build" / "rfalloc.sqlite"


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def lookup(con: sqlite3.Connection, lo_hz: int, hi_hz: int | None = None) -> dict:
    """Everything known about a frequency, or about a span of them."""
    hi_hz = hi_hz if hi_hz is not None else lo_hz + 1

    channels = con.execute(
        "SELECT * FROM channel WHERE lo_hz < ? AND hi_hz > ? "
        "ORDER BY (hi_hz - lo_hz) ASC",
        (hi_hz, lo_hz),
    ).fetchall()

    bands = con.execute(
        "SELECT b.*, j.name AS jname FROM band b JOIN jurisdiction j "
        "ON j.id = b.jurisdiction WHERE b.lo_hz < ? AND b.hi_hz > ? "
        "ORDER BY (b.hi_hz - b.lo_hz) ASC",
        (hi_hz, lo_hz),
    ).fetchall()

    out: dict = {"channels": [dict(c) for c in channels], "bands": []}
    for b in bands:
        services = con.execute(
            "SELECT name, is_primary FROM service WHERE band_id = ? ORDER BY ordinal",
            (b["id"],),
        ).fetchall()
        notes = con.execute(
            "SELECT DISTINCT f.id, f.class, f.text FROM band_footnote bf "
            "JOIN footnote f ON f.id = bf.footnote_id WHERE bf.band_id = ?",
            (b["id"],),
        ).fetchall()
        out["bands"].append(
            {
                "jurisdiction": b["jurisdiction"], "jname": b["jname"],
                "lo_hz": b["lo_hz"], "hi_hz": b["hi_hz"],
                "services": [dict(s) for s in services],
                "footnotes": [dict(n) for n in notes],
            }
        )

    out["rule_parts"] = [
        dict(r) for r in con.execute(
            "SELECT DISTINCT part, name FROM rule_part WHERE lo_hz < ? AND hi_hz > ? "
            "ORDER BY CAST(part AS INTEGER)",
            (hi_hz, lo_hz),
        )
    ]
    return out


def fmt_hz(v: int) -> str:
    for scale, unit in ((1e9, "GHz"), (1e6, "MHz"), (1e3, "kHz")):
        if abs(v) >= scale:
            return f"{v / scale:g} {unit}"
    return f"{v} Hz"


ITU_LABEL = {"itu-r1": "1", "itu-r2": "2", "itu-r3": "3"}
JURISDICTION_LABEL = {"us": "US", "eu": "EU"}


def _collapse_itu(bands: list[dict]) -> list[tuple[str, dict]]:
    """Merge the ITU regions that say the same thing.

    All three regions agree far more often than not, and printing three
    identical lines buries the cases where they genuinely differ -- which is
    exactly what a European user needs to see. Region 1 is Europe, Africa and
    the Middle East; Region 2 the Americas; Region 3 Asia-Pacific.
    """
    groups: dict[tuple, list[str]] = {}
    for b in bands:
        if b["jurisdiction"] not in ITU_LABEL:
            continue
        key = (b["lo_hz"], b["hi_hz"],
               tuple((s["name"], s["is_primary"]) for s in b["services"]))
        groups.setdefault(key, []).append(ITU_LABEL[b["jurisdiction"]])

    out = []
    for b in bands:
        if b["jurisdiction"] not in ITU_LABEL:
            continue
        key = (b["lo_hz"], b["hi_hz"],
               tuple((s["name"], s["is_primary"]) for s in b["services"]))
        regions = groups.pop(key, None)
        if regions is None:
            continue
        label = ("ITU Regions " + "\u2013".join([regions[0], regions[-1]])
                 if len(regions) > 1 else f"ITU Region {regions[0]}")
        out.append((label, b))
    return out


def _services_of(band: dict) -> str:
    return ", ".join(
        s["name"] + ("" if s["is_primary"] else " (secondary)") for s in band["services"]
    ) or "no service listed"


def render(result: dict, freq_label: str, show_footnotes: bool,
           jurisdiction: str = "all") -> str:
    lines = [f"\u2500\u2500 {freq_label} " + "\u2500" * max(0, 60 - len(freq_label))]

    channels = [
        c for c in result["channels"]
        if jurisdiction == "all" or c["jurisdiction"] == jurisdiction
    ]
    if channels:
        lines.append("\nKnown use")
        for c in channels:
            tag = JURISDICTION_LABEL.get(c["jurisdiction"], c["jurisdiction"])
            lines.append(f"  \u2022 [{tag}] {c['name']}  [{c['service']}]")
            lines.append(f"    {fmt_hz(c['lo_hz'])} \u2013 {fmt_hz(c['hi_hz'])}"
                         + (f"   {c['mode']}" if c["mode"] else ""))
            if c["description"]:
                lines.append(f"    {c['description']}")
            lines.append(f"    source: {c['source']}")
    else:
        lines.append("\nKnown use\n  (nothing curated here yet)")

    lines.append("\nUnited States allocation")
    for b in result["bands"]:
        if not b["jurisdiction"].startswith("us"):
            continue
        lines.append(f"  {b['jname']}")
        lines.append(f"    {fmt_hz(b['lo_hz'])} \u2013 {fmt_hz(b['hi_hz'])}: {_services_of(b)}")
        ids = ", ".join(n["id"] for n in b["footnotes"])
        if ids:
            lines.append(f"    footnotes: {ids}")

    itu = _collapse_itu(result["bands"])
    if itu:
        lines.append("\nInternational allocation  (Region 1 = Europe, Africa, Middle East)")
        for label, b in itu:
            lines.append(f"  {label}")
            lines.append(f"    {fmt_hz(b['lo_hz'])} \u2013 {fmt_hz(b['hi_hz'])}: {_services_of(b)}")

    if result["rule_parts"]:
        lines.append("\nFCC rule parts")
        for r in result["rule_parts"]:
            lines.append(f"  Part {r['part']} \u2014 {r['name']}")

    if show_footnotes:
        seen = {}
        for b in result["bands"]:
            for n in b["footnotes"]:
                seen.setdefault(n["id"], n)
        if seen:
            lines.append("\nFootnote text")
            for fid, n in sorted(seen.items()):
                body = n["text"] or "(not reproduced in the FCC source document)"
                lines.append(f"  [{fid}] {body}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Reverse-look-up a frequency.")
    ap.add_argument("freq", nargs="+", help="frequency in MHz (two values with --span)")
    ap.add_argument("--span", action="store_true", help="treat the two values as a range")
    ap.add_argument("--footnotes", action="store_true", help="print full footnote text")
    ap.add_argument("--jurisdiction", default="all", choices=["all", "us", "eu"],
                    help="restrict the curated layer to one jurisdiction")
    args = ap.parse_args()

    con = connect()
    if args.span:
        if len(args.freq) != 2:
            ap.error("--span needs exactly two frequencies")
        lo, hi = (round(float(f) * 1e6) for f in args.freq)
        print(render(lookup(con, lo, hi), f"{args.freq[0]}–{args.freq[1]} MHz", args.footnotes))
        return
    for f in args.freq:
        hz = round(float(f) * 1e6)
        print(render(lookup(con, hz), f"{f} MHz", args.footnotes, args.jurisdiction))
        print()


if __name__ == "__main__":
    main()
