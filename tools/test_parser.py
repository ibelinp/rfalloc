"""Regression tests for the source parse.

A mis-parse of a print layout looks exactly like a correct one unless you check,
so these tests assert the structural invariants that a wrong column assignment
or a dropped cell would violate -- above all that each jurisdiction's bands
still tile the spectrum without a gap or an overlap.

    python3 tools/test_parser.py
"""

from __future__ import annotations

import sys
import unittest

from build_allocations import build
from fcc_cells import parse_cell
from fcc_footnotes import parse_footnotes

BANDS, PARTS, PROBLEMS = build()
NOTES = parse_footnotes()
JURISDICTIONS = ("itu-r1", "itu-r2", "itu-r3", "us-federal", "us-non-federal")


def unique_bands(jurisdiction: str):
    seen, out = set(), []
    group = [b for b in BANDS if b.jurisdiction == jurisdiction]
    for b in sorted(group, key=lambda b: (b.lo_hz, b.hi_hz)):
        if (b.lo_hz, b.hi_hz) in seen:
            continue  # the same band restated at a page break
        seen.add((b.lo_hz, b.hi_hz))
        out.append(b)
    return out


class TestStructure(unittest.TestCase):
    def test_no_parse_problems(self):
        self.assertEqual(PROBLEMS, [])

    def test_every_jurisdiction_is_populated(self):
        for j in JURISDICTIONS:
            self.assertGreater(len(unique_bands(j)), 400, j)

    def test_bands_tile_the_spectrum(self):
        """The Allocation Table partitions the spectrum: no gaps, no overlaps.

        This is the single most informative check in the suite. Almost any
        column mis-assignment shows up here, because a cell placed in the wrong
        column both leaves a hole where it belonged and collides where it landed.
        """
        for j in JURISDICTIONS:
            bands = unique_bands(j)
            for prev, cur in zip(bands, bands[1:]):
                self.assertEqual(
                    cur.lo_hz, prev.hi_hz,
                    f"{j}: {prev.lo_hz}-{prev.hi_hz} then {cur.lo_hz}-{cur.hi_hz} "
                    f"({prev.source} -> {cur.source})",
                )

    def test_spectrum_is_covered_end_to_end(self):
        """Coverage runs from 0 Hz to 275 GHz in every column.

        275 GHz is where the table stops, not an artefact of the parse: above it
        the Radio Regulations allocate nothing, and footnote 5.565 merely
        *identifies* parts of 275-1000 GHz for passive and active use.
        """
        for j in JURISDICTIONS:
            bands = unique_bands(j)
            self.assertEqual(bands[0].lo_hz, 0, j)
            self.assertEqual(bands[-1].hi_hz, 275_000_000_000, j)

    def test_ranges_are_well_formed(self):
        for b in BANDS:
            self.assertLess(b.lo_hz, b.hi_hz, b.source)


class TestFootnotes(unittest.TestCase):
    def test_every_reference_resolves(self):
        """5.372 and 5.415 are cited by the table but never defined in it.

        That is a gap in the FCC document, not in this parser, so it is pinned
        here: if the list changes, the source changed or the parser broke.
        """
        refs = {f for b in BANDS for f in b.footnotes}
        refs |= {f for b in BANDS for s in b.services for f in s["footnotes"]}
        self.assertEqual(sorted(refs - set(NOTES)), ["5.372", "5.415"])

    def test_classes_are_assigned_consistently(self):
        for fid, note in NOTES.items():
            expected = {"5": "itu", "U": "us", "N": "ng", "G": "g"}[fid[0]]
            self.assertEqual(note.footnote_class, expected, fid)

    def test_known_footnote_text(self):
        self.assertIn("distress", NOTES["5.226"].text.lower())
        self.assertIn("VHF maritime mobile", NOTES["US52"].text)


class TestCellParsing(unittest.TestCase):
    def test_case_marks_primary_and_secondary(self):
        cell = parse_cell("2400-2417\nAMATEUR\nRadiolocation\n5.150", "MHz")
        self.assertEqual([s.primary for s in cell.services], [True, False])

    def test_lowercase_qualifier_stays_primary(self):
        cell = parse_cell("156.8375-157.1875\nMOBILE except aeronautical mobile", "MHz")
        self.assertTrue(cell.services[0].primary)

    def test_hyphenated_wrap_is_rejoined(self):
        cell = parse_cell("10-10.4\nEARTH EXPLORATION-\nSATELLITE (active)", "GHz")
        self.assertEqual(cell.services[0].name, "EARTH EXPLORATION-SATELLITE (active)")

    def test_parenthesised_wrap_is_rejoined(self):
        cell = parse_cell("148-149.9\nMOBILE-SATELLITE\n(Earth-to-space) US319", "MHz")
        self.assertEqual(cell.services[0].name, "MOBILE-SATELLITE (Earth-to-space)")
        self.assertEqual(cell.services[0].footnotes, ["US319"])

    def test_frequencies_are_exact_integers(self):
        cell = parse_cell("156.2475-156.5125\nMARITIME MOBILE", "MHz")
        self.assertEqual((cell.lo_hz, cell.hi_hz), (156_247_500, 156_512_500))


class TestKnownFrequencies(unittest.TestCase):
    """Spot checks against allocations that can be verified independently."""

    def assert_band(self, mhz, jurisdiction, lo_mhz, hi_mhz, contains):
        hz = round(mhz * 1e6)
        hit = next(
            b for b in BANDS
            if b.jurisdiction == jurisdiction and b.lo_hz <= hz < b.hi_hz
        )
        self.assertEqual((hit.lo_hz, hit.hi_hz), (round(lo_mhz * 1e6), round(hi_mhz * 1e6)))
        names = " ".join(s["name"] for s in hit.services)
        self.assertIn(contains, names)

    def test_fm_broadcast(self):
        self.assert_band(98.5, "us-non-federal", 88, 108, "BROADCASTING")

    def test_two_metre_amateur(self):
        self.assert_band(146.52, "us-non-federal", 146, 148, "AMATEUR")

    def test_marine_channel_16(self):
        self.assert_band(156.8, "us-non-federal", 156.7875, 156.8125, "MARITIME MOBILE")

    def test_ais_channels(self):
        self.assert_band(161.975, "us-non-federal", 161.9625, 161.9875, "AIS 1")
        self.assert_band(162.025, "us-non-federal", 162.0125, 162.0375, "AIS 2")

    def test_gps_l1(self):
        self.assert_band(1575.42, "us-federal", 1559, 1610, "RADIONAVIGATION-SATELLITE")

    def test_adsb(self):
        self.assert_band(1090, "us-federal", 960, 1164, "AERONAUTICAL RADIONAVIGATION")

    def test_rule_parts_are_linked(self):
        hz = round(462.5625 * 1e6)
        parts = {p.part for p in PARTS if p.lo_hz <= hz < p.hi_hz}
        self.assertIn("95", parts)  # FRS/GMRS live in Part 95


class TestCuratedLayer(unittest.TestCase):
    """The curated CSVs are hand-maintained, so they get their own checks."""

    @classmethod
    def setUpClass(cls):
        from build_db import load_curated

        cls.channels = load_curated()

    def test_both_jurisdictions_are_present(self):
        by_j = {}
        for c in self.channels:
            by_j[c["jurisdiction"]] = by_j.get(c["jurisdiction"], 0) + 1
        self.assertGreater(by_j.get("us", 0), 100)
        self.assertGreater(by_j.get("eu", 0), 100)

    def test_every_entry_cites_a_source(self):
        for c in self.channels:
            self.assertTrue(c["source"], c["id"])

    def test_ranges_are_well_formed(self):
        for c in self.channels:
            self.assertLess(c["lo_hz"], c["hi_hz"], c["id"])

    def test_regional_amateur_edges_differ(self):
        """The 2 m band ends at 146 MHz in Region 1 and 148 MHz in the US.

        Getting this backwards is the classic bug in a US-authored database, so
        it is pinned rather than assumed.
        """
        eu = next(c for c in self.channels if c["id"] == "eu-ham-2m")
        us = next(c for c in self.channels if c["id"] == "ham-2m")
        self.assertEqual(eu["hi_hz"], 146_000_000)
        self.assertEqual(us["hi_hz"], 148_000_000)

    def test_pmr446_grid(self):
        pmr = sorted(
            (c for c in self.channels if c["id"].startswith("pmr446-")),
            key=lambda c: c["lo_hz"],
        )
        self.assertEqual(len(pmr), 16)
        # 12.5 kHz raster, first channel centred on 446.00625 MHz
        centres = [(c["lo_hz"] + c["hi_hz"]) // 2 for c in pmr]
        self.assertEqual(centres[0], 446_006_250)
        self.assertTrue(all(b - a == 12_500 for a, b in zip(centres, centres[1:])))


if __name__ == "__main__":
    sys.exit(0 if unittest.main(exit=False, verbosity=2).result.wasSuccessful() else 1)
