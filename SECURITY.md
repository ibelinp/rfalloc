# Security

This project ships data and a small read-only parser. The realistic risk is not
a compromised service but a malformed file.

## The C reader

`c/rfalloc.c` is the only component that reads untrusted bytes. It is written to
survive them:

- Every header offset is validated against the file size before anything is
  dereferenced, and the arithmetic is written so that it cannot overflow into a
  false pass.
- String-table offsets are bounds-checked on every access, and the table is
  required to end in a NUL, so any in-range offset yields a terminated string.
- Scalars are read byte by byte rather than cast, so unaligned loads and byte
  order are non-issues.
- It allocates nothing and holds no state beyond the pointers in `rfalloc_db`.

`c/test_rfalloc.c` exercises truncated files, a bad magic number and an
impossible record count.

If you find a way to make it read out of bounds, that is a bug worth reporting.

## Reporting

Open a [security advisory](https://github.com/ibelinp/rfalloc/security/advisories/new)
rather than a public issue. Expect a reply within a week.

## Data integrity

Release artifacts ship with `SHA256SUMS.txt`, which is what you want for
verifying a download arrived intact.

The allocation layer is generated from `sources/fcctable.docx`, which is
committed, so any published artifact can be rebuilt with `make all` and
compared. `rfalloc.json`, `rfalloc.min.json` and `rfalloc.bin` come out
bit-identical to the published files.

`rfalloc.sqlite` will not. SQLite records the version of the library that wrote
the file in its header, so a build on a machine with a different SQLite version
produces different bytes from identical content. Compare the content instead:

```bash
sqlite3 yours.sqlite .dump > a.sql
sqlite3 theirs.sqlite .dump > b.sql
diff a.sql b.sql
```

That comparison was run against the v0.1.0 release and matched exactly.
