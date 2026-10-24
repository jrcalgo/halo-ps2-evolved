#include "stream/hp2.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t *read_file(const char *path, size_t *size)
{
	FILE *file = fopen(path, "rb");
	if (!file) return NULL;
	if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return NULL; }
	long length = ftell(file);
	if (length < 0 || fseek(file, 0, SEEK_SET) != 0) { fclose(file); return NULL; }
	uint8_t *bytes = malloc((size_t)length ? (size_t)length : 1);
	if (!bytes) { fclose(file); return NULL; }
	if (fread(bytes, 1, (size_t)length, file) != (size_t)length) {
		free(bytes);
		fclose(file);
		return NULL;
	}
	fclose(file);
	*size = (size_t)length;
	return bytes;
}

static int check_section(const hp2_pack *pack, const char *tag, const char *expected_path)
{
	const hp2_section *section = hp2_find(pack, tag);
	if (!section) return 10;
	size_t expected_size = 0;
	uint8_t *expected = read_file(expected_path, &expected_size);
	if (!expected) return 11;
	if (section->raw_size != expected_size) { free(expected); return 12; }
	uint8_t *decoded = malloc(expected_size ? expected_size : 1);
	if (!decoded) { free(expected); return 12; }
	hp2_status status = hp2_load(pack, section, decoded, expected_size);
	int result = status == HP2_OK &&
		memcmp(expected, decoded, expected_size) == 0 ? 0 : 13;
	free(decoded);
	free(expected);
	return result;
}

int main(int argc, char **argv)
{
	if (argc != 5) return 2;
	size_t pack_size = 0;
	uint8_t *image = read_file(argv[1], &pack_size);
	if (!image) return 3;
	hp2_pack pack;
	hp2_status status = hp2_open(&pack, image, pack_size);
	if (status != HP2_OK) { free(image); return 4; }
	int result = check_section(&pack, "CTAG", argv[2]);
	if (!result) result = check_section(&pack, "SCEN", argv[3]);
	if (!result) result = check_section(&pack, "BSP0", argv[4]);
	free(image);
	return result;
}
