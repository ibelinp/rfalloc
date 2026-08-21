"""One-time seed for the US curated channel layer (data/curated/us/*.csv).

The CSVs are the source of truth once written; this script exists to generate
the regular channel grids (marine VHF, FRS/GMRS, weather radio) without hand
transcription errors, and to document where each block came from.  Re-running it
overwrites the seed files, so edit the CSVs, not this script, unless you are
adding a whole new regular grid.

Frequencies are written as decimal megahertz for legibility and converted to
integer hertz at build time.
"""

from __future__ import annotations

import csv
import pathlib
from decimal import Decimal

OUT = pathlib.Path(__file__).resolve().parent.parent / "data" / "curated" / "us"
FIELDS = ["id", "lo_mhz", "hi_mhz", "name", "service", "description", "mode", "tags", "source"]


def ch(cid, center, bw_khz, name, service, desc, mode, tags, source):
    """A channel centred on `center` MHz with `bw_khz` of channel spacing."""
    half = Decimal(bw_khz) / Decimal(2000)
    c = Decimal(str(center))
    return dict(
        id=cid, lo_mhz=c - half, hi_mhz=c + half, name=name, service=service,
        description=desc, mode=mode, tags=tags, source=source,
    )


def band(cid, lo, hi, name, service, desc, mode, tags, source):
    return dict(
        id=cid, lo_mhz=Decimal(str(lo)), hi_mhz=Decimal(str(hi)), name=name,
        service=service, description=desc, mode=mode, tags=tags, source=source,
    )


def write(filename: str, rows: list[dict]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / filename
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"{path.name:28} {len(rows):4} rows")


def main() -> None:
    # --------------------------------------------------------------- weather ----
    # NOAA Weather Radio All Hazards, 25 kHz spacing.  Channel numbering is the
    # marine-radio WX convention, which is NOT in frequency order.
    WX = [("WX1", "162.550"), ("WX2", "162.400"), ("WX3", "162.475"), ("WX4", "162.425"),
          ("WX5", "162.450"), ("WX6", "162.500"), ("WX7", "162.525")]
    write("weather.csv", [
        ch(f"noaa-{n.lower()}", f, 25, f"NOAA Weather Radio {n}", "Weather",
           "NOAA All Hazards continuous broadcast; NWS forecast and warning audio.",
           "NFM", "weather;noaa;broadcast", "NWS / NTIA Redbook")
        for n, f in WX
    ])

    # ---------------------------------------------------------------- marine ----
    # US VHF marine channels, 25 kHz spacing.  "A" channels are the US simplex use
    # of the ship half of an international duplex pair.
    MARINE_SIMPLEX = [
        ("01A", "156.050", "Port operations / commercial (US)"),
        ("05A", "156.250", "Port operations; VTS in some ports"),
        ("06",  "156.300", "Intership safety; mandatory on all sets"),
        ("07A", "156.350", "Commercial"),
        ("08",  "156.400", "Commercial, intership only"),
        ("09",  "156.450", "Boater calling; recreational hailing"),
        ("10",  "156.500", "Commercial"),
        ("11",  "156.550", "Commercial; VTS in some ports"),
        ("12",  "156.600", "Port operations; VTS in some ports"),
        ("13",  "156.650", "Bridge-to-bridge navigation safety; 1 W limit"),
        ("14",  "156.700", "Port operations; VTS in some ports"),
        ("15",  "156.750", "Environmental; receive only"),
        ("16",  "156.800", "International distress, safety and calling"),
        ("17",  "156.850", "State control"),
        ("18A", "156.900", "Commercial"),
        ("19A", "156.950", "Commercial"),
        ("20",  "157.000", "Port operations (duplex)"),
        ("21A", "157.050", "US Coast Guard only"),
        ("22A", "157.100", "Coast Guard liaison and maritime safety broadcasts"),
        ("23A", "157.150", "US Coast Guard only"),
        ("63A", "156.175", "Port operations / commercial"),
        ("65A", "156.275", "Port operations"),
        ("66A", "156.325", "Port operations"),
        ("67",  "156.375", "Commercial; bridge-to-bridge in lower Mississippi"),
        ("68",  "156.425", "Non-commercial working (recreational)"),
        ("69",  "156.475", "Non-commercial working (recreational)"),
        ("70",  "156.525", "Digital selective calling (DSC) distress; no voice"),
        ("71",  "156.575", "Non-commercial working (recreational)"),
        ("72",  "156.625", "Non-commercial intership"),
        ("73",  "156.675", "Port operations"),
        ("74",  "156.725", "Port operations"),
        ("77",  "156.875", "Port operations, intership only"),
        ("78A", "156.925", "Non-commercial working"),
        ("79A", "156.975", "Commercial; non-commercial on Great Lakes"),
        ("80A", "157.025", "Commercial; non-commercial on Great Lakes"),
        ("81A", "157.075", "US government / environmental protection"),
        ("82A", "157.125", "US government"),
        ("83A", "157.175", "US Coast Guard only"),
        ("88A", "157.425", "Commercial, intership only"),
    ]
    marine = [
        ch(f"marine-vhf-{n.lower()}", f, 25, f"Marine VHF Channel {n}", "Marine",
           d, "DSC" if n == "70" else "NFM", "marine;vhf", "47 CFR 80.371 / USCG")
        for n, f, d in MARINE_SIMPLEX
    ]
    marine += [
        ch("marine-ais-1", "161.975", 25, "AIS 1 (Channel 87B)", "Marine",
           "Automatic Identification System channel A; ship position reporting.",
           "GMSK", "marine;ais;data", "47 CFR 80.393"),
        ch("marine-ais-2", "162.025", 25, "AIS 2 (Channel 88B)", "Marine",
           "Automatic Identification System channel B; ship position reporting.",
           "GMSK", "marine;ais;data", "47 CFR 80.393"),
        ch("marine-2182", "2.182", 6, "2182 kHz Distress", "Marine",
           "International MF radiotelephone distress and calling frequency.",
           "USB", "marine;distress;hf", "47 CFR 80.313"),
        ch("marine-dsc-2187", "2.1875", 6, "2187.5 kHz DSC Distress", "Marine",
           "MF digital selective calling distress and safety.",
           "DSC", "marine;distress;hf", "ITU-R M.541"),
    ]
    write("marine.csv", marine)

    # ------------------------------------------------------- personal radio ----
    FRS_GMRS = (
        [(i + 1, f"462.{n}") for i, n in enumerate(
            ["5625", "5875", "6125", "6375", "6625", "6875", "7125"])]
        + [(i + 8, f"467.{n}") for i, n in enumerate(
            ["5625", "5875", "6125", "6375", "6625", "6875", "7125"])]
        + [(i + 15, f"462.{n}") for i, n in enumerate(
            ["5500", "5750", "6000", "6250", "6500", "6750", "7000", "7250"])]
    )
    personal = []
    for num, freq in FRS_GMRS:
        if 1 <= num <= 7:
            desc = "FRS and GMRS shared interstitial channel; FRS 2 W, GMRS 5 W."
        elif 8 <= num <= 14:
            desc = "FRS only, 0.5 W limit; GMRS repeater inputs are not on these."
        else:
            desc = "GMRS main channel (FRS 2 W); GMRS repeater output, licence required."
        personal.append(ch(f"frs-gmrs-{num:02d}", freq, 12.5 if num <= 14 else 20,
                           f"FRS/GMRS Channel {num}", "Personal Radio", desc,
                           "NFM", "frs;gmrs;personal", "47 CFR Part 95 Subparts B/E"))
    MURS = [("1", "151.820"), ("2", "151.880"), ("3", "151.940"),
            ("4", "154.570"), ("5", "154.600")]
    personal += [
        ch(f"murs-{n}", f, 11.25 if f.startswith("151") else 20,
           f"MURS Channel {n}", "Personal Radio",
           "Multi-Use Radio Service; licence-free, 2 W limit.",
           "NFM", "murs;personal", "47 CFR Part 95 Subpart J")
        for n, f in MURS
    ]
    CB_NOTABLE = [("9", "27.065", "Emergency and traveller assistance"),
                  ("19", "27.185", "Highway / trucker calling channel"),
                  ("1", "26.965", "Lowest CB channel"),
                  ("40", "27.405", "Highest CB channel")]
    personal += [
        ch(f"cb-{n}", f, 10, f"CB Channel {n}", "Personal Radio", d, "AM/SSB",
           "cb;personal;hf", "47 CFR Part 95 Subpart D")
        for n, f, d in CB_NOTABLE
    ]
    personal.append(band("cb-band", 26.965, 27.405, "Citizens Band (CB)", "Personal Radio",
                         "40 channels, 4 W AM / 12 W PEP SSB, licence-free.",
                         "AM/SSB", "cb;personal;hf", "47 CFR Part 95 Subpart D"))
    write("personal-radio.csv", personal)


if __name__ == "__main__":
    main()
