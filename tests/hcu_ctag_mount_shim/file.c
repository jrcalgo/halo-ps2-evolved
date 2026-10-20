#include "stream/file.h"
#include <stdio.h>
#include <string.h>

static const char *host_path(const char *path)
{
	return strncmp(path, "host:/", 6) == 0 ? path + 6 : path;
}

uint8_t *file_load(arena_t *a, const char *path, size_t *size_out)
{
	(void)a; (void)path; (void)size_out;
	return NULL;
}

long file_size_of(const char *path)
{
	FILE *file = fopen(host_path(path), "rb");
	long size;
	if (!file) return -1;
	if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return -1; }
	size = ftell(file);
	fclose(file);
	return size;
}

int file_read_at(const char *path, long offset, void *dst, size_t size)
{
	FILE *file = fopen(host_path(path), "rb");
	int result = -1;
	if (!file) return -1;
	if (offset >= 0 && fseek(file, offset, SEEK_SET) == 0 &&
		fread(dst, 1, size, file) == size)
		result = 0;
	fclose(file);
	return result;
}
