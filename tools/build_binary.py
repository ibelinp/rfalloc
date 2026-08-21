"""Emit build/rfalloc.bin: a flat, mmap-able table for the C99 reader.

The format is deliberately dull -- a header, two sorted fixed-size record
arrays, and one string blob -- so that a consumer can mmap the file and binary
search it with no parsing, no allocation, and no dependencies.  Everything is
little-endian; every offset is a byte offset from the start of the file.

  header    64 bytes
  bands     24 bytes each, sorted by lo_hz
  channels  32 bytes each, sorted by lo_hz
  strings   NUL-terminated UTF-8

Ranges nest and overlap (a channel sits inside a band, and curated channels
overlap each other), so a lookup binary searches for the last record whose
lo_hz <= f and then walks backwards.  The header carries the widest span in
each array, which bounds that walk instead of leaving it open-ended.
"""

from __future__ import annotations

import pathlib
import sqlite3
import struct

ROOT = pathlib.Path(__file__).resolve().parent.parent
BUILD = ROOT / "build"

MAGIC = b"RFAL"
VERSION = 1
HEADER = struct.Struct("<4sIIIIIIIQQII")  # see write_binary() for field order
HEADER_SIZE = 64  # header padded out, leaving room for later fields
BAND = struct.Struct("<QQIBBH")
CHANNEL = struct.Struct("<QQIIII")

JURISDICTION_CODE = {
    "itu-r1": 0, "itu-r2": 1, "itu-r3": 2,
    "us-federal": 3, "us-non-federal": 4, "us": 5, "eu": 6,
}


class Strings:
    """Deduplicating string blob; offset 0 is always the empty string."""

    def __init__(self) -> None:
        self.blob = bytearray(b"\0")
        self.offsets: dict[str, int] = {"": 0}

    def add(self, text: str | None) -> int:
        text = text or ""
        if text not in self.offsets:
            self.offsets[text] = len(self.blob)
            self.blob += text.encode("utf-8") + b"\0"
        return self.offsets[text]


def write_binary() -> pathlib.Path:
    con = sqlite3.connect(f"file:{BUILD / 'rfalloc.sqlite'}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    strings = Strings()

    bands = []
    for b in con.execute("SELECT * FROM band ORDER BY lo_hz, hi_hz"):
        services = con.execute(
            "SELECT name, is_primary FROM service WHERE band_id=? ORDER BY ordinal",
            (b["id"],),
        ).fetchall()
        desc = ", ".join(
            s["name"] + ("" if s["is_primary"] else " (secondary)") for s in services
        )
        bands.append(
            (b["lo_hz"], b["hi_hz"], strings.add(desc),
             JURISDICTION_CODE[b["jurisdiction"]], 1 if b["not_allocated"] else 0)
        )

    channels = []
    for c in con.execute("SELECT * FROM channel ORDER BY lo_hz, hi_hz"):
        channels.append(
            (c["lo_hz"], c["hi_hz"], strings.add(c["name"]),
             strings.add(c["service"]), strings.add(c["description"]),
             strings.add(c["mode"]))
        )

    max_band_span = max((hi - lo for lo, hi, *_ in bands), default=0)
    max_channel_span = max((hi - lo for lo, hi, *_ in channels), default=0)

    band_off = HEADER_SIZE
    channel_off = band_off + BAND.size * len(bands)
    string_off = channel_off + CHANNEL.size * len(channels)

    header = HEADER.pack(
        MAGIC, VERSION,
        len(bands), len(channels),
        band_off, channel_off,
        string_off, len(strings.blob),
        max_band_span, max_channel_span,
        BAND.size, CHANNEL.size,
    )
    out = bytearray(header.ljust(HEADER_SIZE, b"\0"))
    for lo, hi, desc, juris, flags in bands:
        out += BAND.pack(lo, hi, desc, juris, flags, 0)
    for lo, hi, name, service, desc, mode in channels:
        out += CHANNEL.pack(lo, hi, name, service, desc, mode)
    out += strings.blob

    path = BUILD / "rfalloc.bin"
    path.write_bytes(out)
    print(f"  {path.name:22} {len(out)/1024:8.1f} KB  "
          f"({len(bands)} bands, {len(channels)} channels, "
          f"{len(strings.blob)/1024:.0f} KB strings)")
    return path


if __name__ == "__main__":
    write_binary()
