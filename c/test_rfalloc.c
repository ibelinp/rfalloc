/* Smoke test for the C reader: verifies the header, the ranked point lookup,
 * the span query a spectrum display would use, and rejection of bad files. */
#include "rfalloc.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int failures = 0;

static void check(int cond, const char *what)
{
    printf("  [%s] %s\n", cond ? "pass" : "FAIL", what);
    if (!cond) failures++;
}

int main(int argc, char **argv)
{
    const char *path = (argc > 1) ? argv[1] : "build/rfalloc.bin";
    FILE *fh = fopen(path, "rb");
    if (!fh) { fprintf(stderr, "cannot open %s\n", path); return 2; }
    fseek(fh, 0, SEEK_END);
    long size = ftell(fh);
    fseek(fh, 0, SEEK_SET);
    uint8_t *buf = malloc((size_t)size);
    if (fread(buf, 1, (size_t)size, fh) != (size_t)size) return 2;
    fclose(fh);

    rfalloc_db db;
    int rc = rfalloc_open(&db, buf, (size_t)size);
    printf("open: %s (%u bands, %u channels)\n", rfalloc_strerror(rc),
           db.band_count, db.channel_count);
    check(rc == RFALLOC_OK, "opens a valid file");

    rfalloc_channel ch[8];
    int n = rfalloc_channels_at(&db, 162550000ULL, ch, 8);
    printf("\n162.550 MHz -> %d channel(s)\n", n);
    for (int i = 0; i < n; i++)
        printf("   %s [%s]\n", ch[i].name, ch[i].service);
    check(n >= 1 && strstr(ch[0].name, "NOAA") != NULL,
          "162.550 MHz resolves to NOAA Weather Radio");

    rfalloc_band bands[8];
    n = rfalloc_bands_at(&db, 162550000ULL, bands, 8);
    printf("\n162.550 MHz -> %d band(s)\n", n);
    for (int i = 0; i < n; i++)
        printf("   %-28s %s\n", rfalloc_jurisdiction_name(bands[i].jurisdiction),
               bands[i].services);
    check(n >= 2, "point lookup finds both US tables plus ITU");

    /* Narrowest first: Channel 16 must outrank the wide land-mobile block. */
    n = rfalloc_channels_at(&db, 156800000ULL, ch, 8);
    printf("\n156.800 MHz -> %d channel(s), narrowest first\n", n);
    for (int i = 0; i < n; i++)
        printf("   %s\n", ch[i].name);
    check(n >= 1 && strstr(ch[0].name, "Channel 16") != NULL,
          "narrowest match is ranked first");

    /* A waterfall spanning 2 m: every amateur entry in view. */
    int count = rfalloc_channels_in(&db, 144000000ULL, 148000000ULL, NULL, 0);
    printf("\n144-148 MHz span -> %d channel(s) overlapping\n", count);
    check(count >= 3, "span query returns everything in view");

    /* Truncation and corruption must be refused, not walked off the end of. */
    rfalloc_db bad;
    check(rfalloc_open(&bad, buf, 8) == RFALLOC_ERR_TRUNCATED, "rejects a truncated file");
    uint8_t *corrupt = malloc((size_t)size);
    memcpy(corrupt, buf, (size_t)size);
    corrupt[0] = 'X';
    check(rfalloc_open(&bad, corrupt, (size_t)size) == RFALLOC_ERR_MAGIC,
          "rejects a bad magic number");
    memcpy(corrupt, buf, (size_t)size);
    corrupt[8] = 0xFF; corrupt[9] = 0xFF; corrupt[10] = 0xFF; corrupt[11] = 0xFF;
    check(rfalloc_open(&bad, corrupt, (size_t)size) == RFALLOC_ERR_LAYOUT,
          "rejects an impossible band count");

    free(corrupt);
    free(buf);
    printf("\n%s\n", failures ? "FAILURES" : "all checks passed");
    return failures ? 1 : 0;
}
