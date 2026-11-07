#include "stream/hcu_irx_unpack.h"
#include "stream/hp2.h"
#include <stdint.h>
#include <string.h>
/* Charged to resident_gameplay NOBITS by the existing static ledger. */
static uint8_t s_irx_scratch[16384] __attribute__((aligned(64)));
const void *hcu_irx_unpack(const void *packed, size_t bytes, size_t raw_bytes)
{
    size_t padded = (raw_bytes + 15u) & ~(size_t)15u;
    if (!packed || !raw_bytes || raw_bytes > sizeof(s_irx_scratch) ||
        padded > sizeof(s_irx_scratch)) return NULL;
    if (lz4_decode(packed, bytes, s_irx_scratch, raw_bytes) != (long)raw_bytes)
        return NULL;
    memset(s_irx_scratch + raw_bytes, 0, padded - raw_bytes);
    return s_irx_scratch;
}
