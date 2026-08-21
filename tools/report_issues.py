"""Print every gap and overlap with enough context to judge it by hand."""
import sys
from build_allocations import build

bands, parts, problems = build()
for juris in ("itu-r1", "itu-r2", "itu-r3", "us-federal", "us-non-federal"):
    group = [b for b in bands if b.jurisdiction == juris]
    seen, uniq = set(), []
    for b in sorted(group, key=lambda b: (b.lo_hz, b.hi_hz)):
        if (b.lo_hz, b.hi_hz) in seen:
            continue
        seen.add((b.lo_hz, b.hi_hz))
        uniq.append(b)
    for prev, cur in zip(uniq, uniq[1:]):
        if cur.lo_hz == prev.hi_hz:
            continue
        kind = "GAP    " if cur.lo_hz > prev.hi_hz else "OVERLAP"
        print(f"{kind} {juris}: {prev.lo_hz/1e6:.4f}-{prev.hi_hz/1e6:.4f} [{prev.source}]"
              f" -> {cur.lo_hz/1e6:.4f}-{cur.hi_hz/1e6:.4f} [{cur.source}]")
        print(f"        prev: {prev.raw_text[:80]!r}")
        print(f"        cur : {cur.raw_text[:80]!r}")
