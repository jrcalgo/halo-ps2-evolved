#ifndef HALO_STREAM_SHA256_H
#define HALO_STREAM_SHA256_H

#include <stddef.h>
#include <stdint.h>

typedef struct {
	uint32_t state[8];
	uint64_t bit_count;
	uint8_t block[64];
	size_t block_size;
} sha256_context;

void sha256_init(sha256_context *context);
void sha256_update(sha256_context *context, const void *bytes, size_t size);
void sha256_final(sha256_context *context, uint8_t digest[32]);

#endif
