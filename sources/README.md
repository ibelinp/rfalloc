# Source documents

Everything in `data/` and `build/` is derived from `fcctable.docx`. It is kept in
the repository so that a build is reproducible against a known revision rather
than against whatever the FCC is publishing today.

| File | What it is | Used by the build |
|---|---|---|
| `fcctable.docx` | FCC Online Table of Frequency Allocations, 47 CFR 2.106, revised 3 April 2026 | Yes, this is the sole input |
| `fahf.docx` | FCC Allocation History File, revised 3 April 2026 | No, see below |
| `*.pdf` | Same content as the `.docx` files, in a format that cannot be parsed reliably | No, and excluded from git |

## Where these come from

Both are published by the FCC Office of Engineering and Technology, Policy and
Rules Division, at <https://www.fcc.gov/engineering-technology/policy-and-rules-division/general/radio-spectrum-allocation>.
The documents name J.C. Montenegro (<Juan.Montenegro@fcc.gov>, +1 202 418 3619)
as the contact for questions about their content.

The legally operative text is the Table of Frequency Allocations as codified in
the Code of Federal Regulations. The Online Table may include amendments adopted
by the Commission that have not yet taken effect.

## Why the .docx and not the eCFR API or the PDF

The eCFR serves 47 CFR Part 2 as XML. The same print layout survives into it, so
the parsing problems are identical, and it lacks the cell geometry that turns out
to be the key to recovering column identity. See
[docs/PARSING.md](../docs/PARSING.md).

The PDFs carry no table structure at all, only ink positions.

## fahf.docx

The Allocation History File lists every amendment to the Allocation Table since
2000, with Federal Register and FCC Record citations. It would support a
`last_amended` date per band and per-proceeding provenance. Nothing reads it yet.

## Copyright

Works of the United States Government carry no copyright in the US under
[17 U.S.C. 105](https://www.law.cornell.edu/uscode/text/17/105). See
[LICENSE-DATA](../LICENSE-DATA).
