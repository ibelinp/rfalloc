# Schema

Full DDL: [`tools/schema.sql`](../tools/schema.sql). Conventions that apply
everywhere:

- **Frequencies are `INTEGER` hertz.** Never floating-point megahertz.
- **Ranges are half-open, `[lo_hz, hi_hz)`.**
- **Nothing is lossy.** `band.raw_text` keeps the verbatim source cell.

## Tables

| Table | Rows | Purpose |
|---|---|---|
| `jurisdiction` | 7 | ITU regions, US Federal/non-Federal, plus `us` and `eu` used by curated entries |
| `band` | 2,666 | one allocation per (jurisdiction, range) |
| `service` | — | services within a band, ordered as printed, with primary/secondary |
| `footnote` | 975 | all four classes; `text` is NULL when the source omits it |
| `band_footnote` | — | links footnotes to a band or to one service within it |
| `rule_part` | 594 | which FCC rule part governs a range |
| `channel` | 368 | the curated layer: 238 US, 130 European |
| `meta` | — | source document, revision date, conventions |

## Primary versus secondary

The printed table encodes precedence typographically: a service set in capitals
is **primary**, mixed case is **secondary**. Lowercase words after the name are
qualifiers, not a case change — `MOBILE except aeronautical mobile` is primary —
so only the first word is tested. This is stored as `service.is_primary`.

## A ranked lookup

Ordering by width puts the narrowest, most specific match first:

```sql
SELECT 'channel' AS layer, name, lo_hz, hi_hz FROM channel
 WHERE lo_hz <= :hz AND hi_hz > :hz
UNION ALL
SELECT 'band', COALESCE(
         (SELECT group_concat(name, ', ') FROM service s WHERE s.band_id = b.id),
         '(no service listed)'),
       lo_hz, hi_hz
  FROM band b
 WHERE lo_hz <= :hz AND hi_hz > :hz AND jurisdiction LIKE 'us%'
 ORDER BY (hi_hz - lo_hz) ASC;
```

Because `band` covers 0 Hz to 275 GHz with no gaps, this never returns empty for
a frequency in range.

## Overlap queries

A spectrum display needs everything across the visible span, not one point:

```sql
SELECT * FROM channel WHERE lo_hz < :span_hi AND hi_hz > :span_lo
 ORDER BY lo_hz;
```

Note the strict inequalities — that is the half-open convention, and it is what
stops a band edge matching two adjacent bands.

## Jurisdictions

| id | Meaning |
|---|---|
| `itu-r1` | ITU Region 1 — Europe, Africa, the Middle East, former USSR |
| `itu-r2` | ITU Region 2 — the Americas |
| `itu-r3` | ITU Region 3 — Asia-Pacific |
| `us-federal` / `us-non-federal` | the two columns of the US table |
| `us` / `eu` | curated layers |

Curated rows take their jurisdiction from the directory holding their CSV
(`data/curated/us/`, `data/curated/eu/`), so the CSV columns never change.

To add another: insert a row in `jurisdiction`, register it in `JURISDICTIONS` in
`tools/build_db.py`, create the directory, and — if it should reach the C reader
— give it a code in `JURISDICTION_CODE` in `tools/build_binary.py`. No migration
is needed; nothing in the schema assumes the United States.
