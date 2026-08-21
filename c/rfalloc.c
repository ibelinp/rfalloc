#include "rfalloc.h"

#include <string.h>

#define RFALLOC_MAGIC "RFAL"
#define RFALLOC_VERSION 1u
#define RFALLOC_HEADER_SIZE 64u

/* The file is little-endian by definition, so read scalars byte by byte rather
 * than casting.  This keeps the reader correct on a big-endian target and, more
 * importantly, avoids unaligned loads -- the record arrays are packed, so a
 * cast-and-dereference would be undefined behaviour on strict-alignment CPUs. */
static uint32_t rd32(const uint8_t *p)
{
    return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static uint64_t rd64(const uint8_t *p)
{
    return (uint64_t)rd32(p) | ((uint64_t)rd32(p + 4) << 32);
}

/* Bound a string-table offset so a corrupt or hostile file cannot walk us off
 * the end of the mapping.  The table always ends in a NUL, so any in-range
 * offset yields a terminated string. */
static const char *str_at(const rfalloc_db *db, uint32_t off)
{
    return (off < db->string_size) ? db->strings + off : "";
}

int rfalloc_open(rfalloc_db *db, const void *data, size_t size)
{
    const uint8_t *p = (const uint8_t *)data;

    if (db == NULL || p == NULL) return RFALLOC_ERR_TRUNCATED;
    memset(db, 0, sizeof(*db));
    if (size < RFALLOC_HEADER_SIZE) return RFALLOC_ERR_TRUNCATED;
    if (memcmp(p, RFALLOC_MAGIC, 4) != 0) return RFALLOC_ERR_MAGIC;
    if (rd32(p + 4) != RFALLOC_VERSION) return RFALLOC_ERR_VERSION;

    db->base = p;
    db->size = size;
    db->band_count = rd32(p + 8);
    db->channel_count = rd32(p + 12);

    uint32_t band_off = rd32(p + 16);
    uint32_t channel_off = rd32(p + 20);
    uint32_t string_off = rd32(p + 24);
    db->string_size = rd32(p + 28);
    db->max_band_span = rd64(p + 32);
    db->max_channel_span = rd64(p + 40);
    db->band_stride = rd32(p + 48);
    db->channel_stride = rd32(p + 52);

    if (db->band_stride == 0 || db->channel_stride == 0) return RFALLOC_ERR_LAYOUT;

    /* Verify every array fits inside the file before handing out pointers.
     * Each product is checked against the remaining size rather than summed,
     * so the arithmetic itself cannot overflow into a false pass. */
    if (band_off > size || channel_off > size || string_off > size)
        return RFALLOC_ERR_LAYOUT;
    if ((size_t)db->band_count > (size - band_off) / db->band_stride)
        return RFALLOC_ERR_LAYOUT;
    if ((size_t)db->channel_count > (size - channel_off) / db->channel_stride)
        return RFALLOC_ERR_LAYOUT;
    if ((size_t)db->string_size > size - string_off) return RFALLOC_ERR_LAYOUT;
    if (db->string_size == 0 || p[string_off + db->string_size - 1] != '\0')
        return RFALLOC_ERR_LAYOUT;

    db->bands = p + band_off;
    db->channels = p + channel_off;
    db->strings = (const char *)(p + string_off);
    return RFALLOC_OK;
}

/* Index of the first record whose lo_hz >= key. Records are sorted by lo_hz. */
static uint32_t lower_bound(const uint8_t *rows, uint32_t count, uint32_t stride,
                            uint64_t key)
{
    uint32_t lo = 0, hi = count;
    while (lo < hi) {
        uint32_t mid = lo + (hi - lo) / 2;
        if (rd64(rows + (size_t)mid * stride) < key) lo = mid + 1;
        else hi = mid;
    }
    return lo;
}

/* Records are sorted by lo_hz but their ranges nest, so the matches for a query
 * are not contiguous. Start from the first record that could still reach the
 * query -- no record starting before (query_lo - widest_span) can overlap it --
 * and test forward from there. */
static uint32_t scan_start(const uint8_t *rows, uint32_t count, uint32_t stride,
                           uint64_t lo_hz, uint64_t max_span)
{
    uint64_t floor_hz = (lo_hz > max_span) ? lo_hz - max_span : 0;
    return lower_bound(rows, count, stride, floor_hz);
}

/* Insert into an array kept sorted by ascending width, so the narrowest and
 * most specific match is always out[0]. The arrays are small (a handful of
 * entries), which is what makes an insertion sort the right choice here. */
#define RFALLOC_EMIT(TYPE, FIELD_LO, FIELD_HI, BUILD_EXPR)                     \
    do {                                                                       \
        TYPE item = BUILD_EXPR;                                                \
        uint64_t width = item.FIELD_HI - item.FIELD_LO;                        \
        if (out != NULL && max > 0) {                                          \
            int pos = (found < max) ? found : max - 1;                         \
            if (found >= max &&                                                \
                (out[max - 1].FIELD_HI - out[max - 1].FIELD_LO) <= width)      \
                pos = -1;                                                      \
            if (pos >= 0) {                                                    \
                while (pos > 0 &&                                              \
                       (out[pos - 1].FIELD_HI - out[pos - 1].FIELD_LO) > width) { \
                    out[pos] = out[pos - 1];                                   \
                    pos--;                                                     \
                }                                                              \
                out[pos] = item;                                               \
            }                                                                  \
        }                                                                      \
        found++;                                                               \
    } while (0)

int rfalloc_bands_in(const rfalloc_db *db, uint64_t lo_hz, uint64_t hi_hz,
                     rfalloc_band *out, int max)
{
    if (db == NULL || db->bands == NULL || hi_hz <= lo_hz) return 0;

    int found = 0;
    uint32_t stride = db->band_stride;
    for (uint32_t i = scan_start(db->bands, db->band_count, stride, lo_hz,
                                 db->max_band_span);
         i < db->band_count; i++) {
        const uint8_t *r = db->bands + (size_t)i * stride;
        uint64_t blo = rd64(r), bhi = rd64(r + 8);
        if (blo >= hi_hz) break; /* sorted by lo_hz: nothing further can match */
        if (bhi <= lo_hz) continue;

        rfalloc_band b;
        b.lo_hz = blo;
        b.hi_hz = bhi;
        b.services = str_at(db, rd32(r + 16));
        b.jurisdiction = r[20];
        b.not_allocated = r[21];
        RFALLOC_EMIT(rfalloc_band, lo_hz, hi_hz, b);
    }
    return (out != NULL && found > max) ? max : found;
}

int rfalloc_channels_in(const rfalloc_db *db, uint64_t lo_hz, uint64_t hi_hz,
                        rfalloc_channel *out, int max)
{
    if (db == NULL || db->channels == NULL || hi_hz <= lo_hz) return 0;

    int found = 0;
    uint32_t stride = db->channel_stride;
    for (uint32_t i = scan_start(db->channels, db->channel_count, stride, lo_hz,
                                 db->max_channel_span);
         i < db->channel_count; i++) {
        const uint8_t *r = db->channels + (size_t)i * stride;
        uint64_t clo = rd64(r), chi = rd64(r + 8);
        if (clo >= hi_hz) break;
        if (chi <= lo_hz) continue;

        rfalloc_channel c;
        c.lo_hz = clo;
        c.hi_hz = chi;
        c.name = str_at(db, rd32(r + 16));
        c.service = str_at(db, rd32(r + 20));
        c.description = str_at(db, rd32(r + 24));
        c.mode = str_at(db, rd32(r + 28));
        RFALLOC_EMIT(rfalloc_channel, lo_hz, hi_hz, c);
    }
    return (out != NULL && found > max) ? max : found;
}

int rfalloc_bands_at(const rfalloc_db *db, uint64_t hz, rfalloc_band *out, int max)
{
    return rfalloc_bands_in(db, hz, hz + 1, out, max);
}

int rfalloc_channels_at(const rfalloc_db *db, uint64_t hz, rfalloc_channel *out, int max)
{
    return rfalloc_channels_in(db, hz, hz + 1, out, max);
}

const char *rfalloc_jurisdiction_name(uint8_t code)
{
    switch (code) {
    case RFALLOC_ITU_R1: return "ITU Region 1";
    case RFALLOC_ITU_R2: return "ITU Region 2";
    case RFALLOC_ITU_R3: return "ITU Region 3";
    case RFALLOC_US_FEDERAL: return "United States (Federal)";
    case RFALLOC_US_NON_FEDERAL: return "United States (non-Federal)";
    case RFALLOC_US: return "United States";
    case RFALLOC_EU: return "Europe (CEPT)";
    default: return "unknown";
    }
}

const char *rfalloc_strerror(int err)
{
    switch (err) {
    case RFALLOC_OK: return "ok";
    case RFALLOC_ERR_MAGIC: return "not an rfalloc file";
    case RFALLOC_ERR_VERSION: return "unsupported rfalloc format version";
    case RFALLOC_ERR_TRUNCATED: return "file truncated";
    case RFALLOC_ERR_LAYOUT: return "inconsistent header layout";
    default: return "unknown error";
    }
}
