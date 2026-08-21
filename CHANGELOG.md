# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions carry the date of the FCC source revision they were built from, since
that matters more to a consumer than the code version.

## [Unreleased]

## [0.1.0] - 2026-08-21

Built from the FCC Online Table of Frequency Allocations revised 3 April 2026.

### Added

- Allocation layer: 2,666 bands covering 0 Hz to 275 GHz across ITU Regions 1,
  2 and 3, the US Federal table and the US non-Federal table.
- All 973 footnotes with full text, in four classes (ITU `5.x`, `US`, `NG`, `G`).
- 594 links from frequency ranges to the FCC rule part governing them.
- Curated layer: 368 channel entries, 238 for the United States and 130 for
  Europe. US coverage includes NOAA Weather Radio, marine VHF, FRS/GMRS/MURS,
  aviation, amateur, GNSS, broadcast, land mobile and cellular. European
  coverage includes PMR446, the DAB Band III block raster, 868 MHz SRD and
  LoRaWAN EU868, TETRA, GSM-R, DCF77 and MSF.
- Artifacts: `rfalloc.sqlite`, `rfalloc.json`, `rfalloc.min.json` and a 135 KB
  flat `rfalloc.bin`.
- C99 reader with no dependencies, and a Swift package wrapping it.
- 41 tests across Python, C and Swift.

### Known limitations

- Footnotes `5.372` and `5.415` are cited by the table but never defined in it.
  Stored with null text. This is a gap in the FCC document.
- Footnote attachment is conservative: a trailing run of footnote-only lines is
  treated as band-level, which can attach a footnote to a band that the printed
  table pinned to one service. It never drops one.
- Footnote sub-tables (state lists, hydro channel plans, observatory
  coordinates) are marked rather than extracted.
- Europe has the international allocation layer only, meaning ITU Region 1. No
  national statutory table is parsed; that would need the CEPT ECC European
  Common Allocation Table.
- `sources/fahf.docx` is committed but unread. It would supply a `last_amended`
  date per band.

[Unreleased]: https://github.com/ibelinp/rfalloc/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ibelinp/rfalloc/releases/tag/v0.1.0
