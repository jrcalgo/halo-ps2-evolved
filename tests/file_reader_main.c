#include "stream/file.h"
#include "stream/ctag_map_source.h"

#include <assert.h>
#include <stdint.h>
#include <string.h>

static uint8_t arena_bytes[4096] __attribute__((aligned(64)));
static uint8_t data[64];

int main(int argc, char **argv)
{
	file_reader_t reader = { -1, 0 };
	ctag_map_source source;
	arena_t arena;
	size_t size = 0, baseline;
	uint8_t *loaded;
	assert(argc == 3);
	assert(file_size_of(argv[1]) == 2048);
	assert(file_reader_open(&reader, argv[1]) == 0 && reader.size == 2048);
	assert(file_reader_read_at(&reader, 1984, data, sizeof(data)) == 0);
	for (unsigned i = 0; i < sizeof(data); i++)
		assert(data[i] == (uint8_t)((1984 + i) * 13u + 7u));
	assert(file_reader_read_at(&reader, 2040, data, sizeof(data)) != 0);
	file_reader_close(&reader);
	assert(file_reader_read_at(&reader, 0, data, 1) != 0);

	assert(ctag_map_source_open(&source, argv[1], 2048) == 0);
	assert(ctag_map_source_read(&source, 7, 64, sizeof(data), data, 0));
	for (unsigned i = 0; i < sizeof(data); i++)
		assert(data[i] == (uint8_t)((64 + i) * 13u + 7u));
	assert(!ctag_map_source_read(&source, 7, 2040, sizeof(data), data, 0));
	ctag_map_source_close(&source);
	assert(!ctag_map_source_read(&source, 7, 64, 1, data, 1));
	assert(ctag_map_source_open(&source, argv[1], 2047) != 0);

	assert(file_set_default_root(argv[2]));
	assert(file_reader_open(&reader, "source.bin") == 0 && reader.size == 2048);
	file_reader_close(&reader);

	arena_init(&arena, "file test", arena_bytes, sizeof(arena_bytes));
	baseline = arena.used;
	loaded = file_load(&arena, argv[1], &size);
	assert(loaded && size == 2048 && memcmp(loaded, data, sizeof(data)) != 0);
	assert(arena.used > baseline);
	arena_release(&arena, baseline);
	loaded = file_load(&arena, argv[1], &size);
	assert(loaded && size == 2048);
	return 0;
}
