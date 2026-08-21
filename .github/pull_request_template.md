## What this changes

<!-- One or two sentences. -->

## Checklist

- [ ] `make test` passes
- [ ] Any new curated row cites a public source in its `source` column
- [ ] No data imported from RadioReference or another proprietary directory

## If you touched the parser

Paste the gap and overlap counts from `make test-python`, or the output of
`python3 tools/report_issues.py`. Every jurisdiction should read zero. That
check is the reason the allocation layer can be trusted, because a mis-parse of
a print layout is invisible to a spot check while always breaking the tiling.
