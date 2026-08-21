-- rfalloc: reverse-lookup schema for radio spectrum allocations.
--
-- Design notes
--   * Frequencies are INTEGER hertz everywhere.  Floating-point megahertz makes
--     band-edge comparisons unreliable exactly where correctness matters most.
--   * Ranges are half-open, [lo_hz, hi_hz).  The source table's bands abut
--     exactly (148-149.9 then 149.9-150.05), so a closed upper bound would make
--     every boundary frequency match two bands.
--   * `jurisdiction` is a first-class table, not a US-specific column, so other
--     administrations can be added without a migration.
--   * Layers are ranked by `specificity`: a lookup returns the narrowest,
--     most specific match first and the broad allocation last.

PRAGMA foreign_keys = ON;

CREATE TABLE jurisdiction (
    id          TEXT PRIMARY KEY,   -- 'us-federal', 'itu-r2'
    name        TEXT NOT NULL,
    authority   TEXT,               -- 'FCC', 'ITU'
    country     TEXT,               -- ISO 3166-1 alpha-2, NULL for international
    itu_region  INTEGER             -- 1, 2, 3, or NULL
);

-- Layer 1: the statutory allocation table.  Answers "what service class owns
-- this band", which is always available but often too coarse to be useful.
CREATE TABLE band (
    id            INTEGER PRIMARY KEY,
    jurisdiction  TEXT NOT NULL REFERENCES jurisdiction(id),
    lo_hz         INTEGER NOT NULL,
    hi_hz         INTEGER NOT NULL,
    not_allocated INTEGER NOT NULL DEFAULT 0,
    raw_text      TEXT,             -- verbatim source cell, so nothing is lost
    source        TEXT,             -- locator within the source document
    CHECK (lo_hz < hi_hz)
);
CREATE INDEX band_lookup ON band(lo_hz, hi_hz);
CREATE INDEX band_by_jurisdiction ON band(jurisdiction, lo_hz);

CREATE TABLE service (
    band_id    INTEGER NOT NULL REFERENCES band(id),
    ordinal    INTEGER NOT NULL,    -- order as printed
    name       TEXT NOT NULL,
    is_primary INTEGER NOT NULL,    -- capitalised in the source == primary
    PRIMARY KEY (band_id, ordinal)
);

CREATE TABLE footnote (
    id     TEXT PRIMARY KEY,        -- '5.226', 'US52', 'NG124', 'G5'
    class  TEXT NOT NULL,           -- itu | us | ng | g
    text   TEXT                     -- NULL when the source does not reproduce it
);

CREATE TABLE band_footnote (
    band_id         INTEGER NOT NULL REFERENCES band(id),
    footnote_id     TEXT NOT NULL REFERENCES footnote(id),
    scope           TEXT NOT NULL,  -- 'band' | 'service'
    service_ordinal INTEGER         -- set when scope = 'service'
);
CREATE INDEX band_footnote_by_band ON band_footnote(band_id);

-- Which FCC rule part governs a band; the bridge from allocation to the
-- service rules that actually define channels.
CREATE TABLE rule_part (
    lo_hz INTEGER NOT NULL,
    hi_hz INTEGER NOT NULL,
    part  TEXT NOT NULL,            -- '90', '95I', '74D'
    name  TEXT NOT NULL
);
CREATE INDEX rule_part_lookup ON rule_part(lo_hz, hi_hz);

-- Layer 2: curated, human-recognisable uses.  This is what makes a tooltip
-- useful -- the allocation table calls 162.55 MHz "FIXED, MOBILE"; this table
-- calls it NOAA Weather Radio channel WX7.
CREATE TABLE channel (
    id           TEXT PRIMARY KEY,
    jurisdiction TEXT REFERENCES jurisdiction(id),
    lo_hz        INTEGER NOT NULL,
    hi_hz        INTEGER NOT NULL,
    name         TEXT NOT NULL,     -- 'NOAA Weather Radio WX7'
    service      TEXT,              -- 'Weather', 'Marine', 'Amateur'
    description  TEXT,
    mode         TEXT,              -- 'NFM', 'AM', 'LSB', 'D-STAR', ...
    tags         TEXT,
    source       TEXT,              -- rule part or authority for the claim
    CHECK (lo_hz < hi_hz)
);
CREATE INDEX channel_lookup ON channel(lo_hz, hi_hz);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
