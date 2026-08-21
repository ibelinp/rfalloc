/* rfalloc -- reverse frequency lookup over a flat allocation table.
 *
 * Point the reader at the bytes of rfalloc.bin and ask what is at a frequency.
 * There is no parsing step, no allocation, and no dependency beyond the C
 * standard library: the file is used in place, so it can be mmap'd or simply
 * embedded in the binary as a static array.
 *
 *     rfalloc_db db;
 *     if (rfalloc_open(&db, bytes, len) != RFALLOC_OK) { ... }
 *
 *     rfalloc_channel ch[8];
 *     int n = rfalloc_channels_at(&db, 162550000ULL, ch, 8);
 *     for (int i = 0; i < n; i++) printf("%s\n", ch[i].name);
 *
 * Frequencies are unsigned hertz.  Ranges are half-open, [lo_hz, hi_hz), so a
 * frequency exactly on a band edge belongs to the upper band only.
 *
 * The reader is read-only and holds no state beyond the pointers in rfalloc_db,
 * so a single opened db may be shared across threads.
 */

#ifndef RFALLOC_H
#define RFALLOC_H

#include <stddef.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

enum {
    RFALLOC_OK = 0,
    RFALLOC_ERR_MAGIC = -1,   /* not an rfalloc file */
    RFALLOC_ERR_VERSION = -2, /* newer format than this reader understands */
    RFALLOC_ERR_TRUNCATED = -3,
    RFALLOC_ERR_LAYOUT = -4   /* header offsets inconsistent with the file size */
};

/* Jurisdiction codes, matching JURISDICTION_CODE in tools/build_binary.py. */
enum {
    RFALLOC_ITU_R1 = 0,
    RFALLOC_ITU_R2 = 1,
    RFALLOC_ITU_R3 = 2,
    RFALLOC_US_FEDERAL = 3,
    RFALLOC_US_NON_FEDERAL = 4,
    RFALLOC_US = 5,
    RFALLOC_EU = 6
};

typedef struct {
    const uint8_t *base;
    size_t size;
    const uint8_t *bands;
    const uint8_t *channels;
    const char *strings;
    uint32_t band_count;
    uint32_t channel_count;
    uint32_t string_size;
    uint64_t max_band_span;
    uint64_t max_channel_span;
    uint32_t band_stride;
    uint32_t channel_stride;
} rfalloc_db;

/* A statutory allocation: what service class owns this band. */
typedef struct {
    uint64_t lo_hz;
    uint64_t hi_hz;
    const char *services;   /* "FIXED, MOBILE"; never NULL, may be "" */
    uint8_t jurisdiction;   /* one of the RFALLOC_* jurisdiction codes */
    uint8_t not_allocated;
} rfalloc_band;

/* A curated, human-recognisable use: "NOAA Weather Radio WX1". */
typedef struct {
    uint64_t lo_hz;
    uint64_t hi_hz;
    const char *name;
    const char *service;
    const char *description;
    const char *mode;
} rfalloc_channel;

/* Validate and bind to the file's bytes.  `data` must outlive `db`; nothing is
 * copied.  Returns RFALLOC_OK or a negative RFALLOC_ERR_*. */
int rfalloc_open(rfalloc_db *db, const void *data, size_t size);

/* Fill `out` with the entries covering `hz`, narrowest first, and return how
 * many were written (never more than `max`).  Pass out=NULL, max=0 to count. */
int rfalloc_bands_at(const rfalloc_db *db, uint64_t hz, rfalloc_band *out, int max);
int rfalloc_channels_at(const rfalloc_db *db, uint64_t hz, rfalloc_channel *out, int max);

/* The same, for everything overlapping [lo_hz, hi_hz) -- what a spectrum
 * display needs to draw an allocation ribbon under the visible span. */
int rfalloc_bands_in(const rfalloc_db *db, uint64_t lo_hz, uint64_t hi_hz,
                     rfalloc_band *out, int max);
int rfalloc_channels_in(const rfalloc_db *db, uint64_t lo_hz, uint64_t hi_hz,
                        rfalloc_channel *out, int max);

const char *rfalloc_jurisdiction_name(uint8_t code);
const char *rfalloc_strerror(int err);

#ifdef __cplusplus
}
#endif
#endif /* RFALLOC_H */
