# Contributing

## Adding a known use — no code required

This is the most valuable contribution and the easiest. The allocation layer is
already complete and machine-generated; the curated layer is what makes a
tooltip readable, and it is hand-built.

Add a row to the right CSV under `data/curated/<jurisdiction>/` — `us/` and
`eu/` exist today. **The directory name is the jurisdiction**, which is why the
CSV columns are identical everywhere:

```csv
id,lo_mhz,hi_mhz,name,service,description,mode,tags,source
noaa-wx1,162.5375,162.5625,NOAA Weather Radio WX1,Weather,NOAA All Hazards …,NFM,weather;noaa,NWS / NTIA Redbook
```

Rules:

- **`id` must be unique** across every file, in every jurisdiction. The build
  fails on duplicates. Prefix non-US ids (`eu-ham-2m`) to keep them distinct.
- **Frequencies are decimal megahertz**, converted to exact integer hertz at
  build time. Give the channel's full occupied width, not its centre — for a
  25 kHz channel at 162.550 that is `162.5375` to `162.5625`.
- **`source` is required and must be public.** A rule part (`47 CFR 80.371`), a
  standard (`ICAO Annex 10`), or an agency (`NWS`). "I heard it" is not a source;
  neither is a subscription database.
- **Never copy from RadioReference or any commercial directory.** See
  [LICENSE-DATA](LICENSE-DATA) — one such import would make the whole database
  undistributable.
- Quote any field containing a comma.

Then `make` and check your entry:

```bash
make && make lookup FREQ=162.55
```

## Adding a jurisdiction

Two levels, and the easy one needs no code.

**A curated layer** for a new administration: create `data/curated/<id>/`, add a
row for `<id>` to `JURISDICTIONS` in `tools/build_db.py`, and start adding CSVs.
If it should also reach the C reader, give it a code in `JURISDICTION_CODE` in
`tools/build_binary.py` and a case in `rfalloc_jurisdiction_name`.

**An allocation layer** — the statutory table for that country — means writing a
parser under `tools/` that emits the same `Band` records. For Europe the source
would be the CEPT ECC European Common Allocation Table; today the ITU Region 1
column of the FCC document is what stands in for it, which is correct as far as
it goes but carries no national detail.

Nothing in the schema assumes the United States, and the binary format and both
readers are already jurisdiction-agnostic.

## Changing the parser

`make test-python` asserts the structural invariants — above all that every
jurisdiction's bands still tile the spectrum with no gap and no overlap. That
check is the reason the parse can be trusted, because a mis-parse of a print
layout is invisible to a spot check but always breaks the tiling.

If you change column assignment, run the full suite and report the gap/overlap
counts in your PR. They should be zero. `tools/report_issues.py` prints any that
appear, with the source cell text and a `tblN:rowN` locator into the document.

See [docs/PARSING.md](docs/PARSING.md) for how the parse works and what is
already known to be imperfect.
