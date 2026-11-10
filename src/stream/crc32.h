#ifndef HALO_STREAM_CRC32_H
#define HALO_STREAM_CRC32_H

#include <stddef.h>
#include <stdint.h>

/* IEEE CRC-32 (zlib's crc32): the runtime's cheap integrity check. Header-only so every link recipe that already
 * builds the asset-profile reader gets it without a new object. Pass the previous result to continue a checksum. */
static inline uint32_t hcu_crc32_update(uint32_t crc, const void *data, size_t size)
{
	static uint32_t table[256];
	static int ready;
	const uint8_t *p = (const uint8_t *)data;
	if (!ready) {
		uint32_t n, k;
		for (n = 0; n < 256u; n++) {
			uint32_t c = n;
			for (k = 0; k < 8u; k++) c = (c & 1u) ? 0xEDB88320u ^ (c >> 1) : c >> 1;
			table[n] = c;
		}
		ready = 1;
	}
	crc = ~crc;
	while (size--) crc = table[(crc ^ *p++) & 0xFFu] ^ (crc >> 8);
	return ~crc;
}

#endif
