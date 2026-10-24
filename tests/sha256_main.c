#include "stream/sha256.h"

#include <assert.h>
#include <string.h>

static int hex_value(char value)
{
	if (value >= '0' && value <= '9') return value - '0';
	if (value >= 'a' && value <= 'f') return value - 'a' + 10;
	return -1;
}

int main(void)
{
	static const char expected[] =
		"ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad";
	uint8_t digest[32];
	unsigned i;
	sha256_context context;
	sha256_init(&context);
	sha256_update(&context, "a", 1);
	sha256_update(&context, "bc", 2);
	sha256_final(&context, digest);
	for (i = 0; i < sizeof(digest); i++) {
		int high = hex_value(expected[i * 2]);
		int low = hex_value(expected[i * 2 + 1]);
		assert(high >= 0 && low >= 0);
		assert(digest[i] == (uint8_t)((high << 4) | low));
	}
	return 0;
}
