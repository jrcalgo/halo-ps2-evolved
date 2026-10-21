#define NEWLIB_PORT_AWARE
#include <assert.h>
#include <fileXio_rpc.h>
#include <io_common.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "stream/file.h"
#include "stream/hcu_file_bridge.h"

enum { HANDLE_COUNT = 16, FILE_BYTES = 256 };
static uint8_t s_file[FILE_BYTES];
static int s_open[HANDLE_COUNT];
static int s_position[HANDLE_COUNT];
static int s_open_calls;
static int s_close_calls;
static int s_active_descriptors;
static int s_high_descriptors;
static unsigned s_heap_alloc_calls;
static int s_fail_read;
static char s_last_path[128];

void *__real_malloc(size_t size);
void *__wrap_malloc(size_t size)
{
	++s_heap_alloc_calls;
	return __real_malloc(size);
}
void *__real_calloc(size_t count, size_t size);
void *__wrap_calloc(size_t count, size_t size)
{
	++s_heap_alloc_calls;
	return __real_calloc(count, size);
}
void *__real_realloc(void *pointer, size_t size);
void *__wrap_realloc(void *pointer, size_t size)
{
	++s_heap_alloc_calls;
	return __real_realloc(pointer, size);
}

int fileXioInit(void) { return 0; }

int fileXioOpen(const char *path, int flags, ...)
{
	int i;
	assert(flags == FIO_O_RDONLY);
	assert(strlen(path) < sizeof(s_last_path));
	strcpy(s_last_path, path);
	for (i = 0; i < HANDLE_COUNT; ++i)
		if (!s_open[i]) break;
	if (i == HANDLE_COUNT) return -1;
	s_open[i] = 1;
	s_position[i] = 0;
	s_open_calls++;
	s_active_descriptors++;
	if (s_active_descriptors > s_high_descriptors)
		s_high_descriptors = s_active_descriptors;
	return i + 3;
}

int fileXioClose(int fd)
{
	int i = fd - 3;
	assert(i >= 0 && i < HANDLE_COUNT && s_open[i]);
	s_open[i] = 0;
	s_active_descriptors--;
	s_close_calls++;
	return 0;
}

int fileXioRead(int fd, void *buffer, int size)
{
	int i = fd - 3;
	int remaining;
	assert(i >= 0 && i < HANDLE_COUNT && s_open[i]);
	if (s_fail_read) return -1;
	remaining = FILE_BYTES - s_position[i];
	if (size > remaining) size = remaining;
	if (size <= 0) return 0;
	memcpy(buffer, s_file + s_position[i], (size_t)size);
	s_position[i] += size;
	return size;
}

int fileXioLseek(int fd, int offset, int whence)
{
	int i = fd - 3;
	int position;
	assert(i >= 0 && i < HANDLE_COUNT && s_open[i]);
	if (whence == FIO_SEEK_SET) position = offset;
	else if (whence == FIO_SEEK_CUR) position = s_position[i] + offset;
	else if (whence == FIO_SEEK_END) position = FILE_BYTES + offset;
	else return -1;
	if (position < 0 || position > FILE_BYTES) return -1;
	s_position[i] = position;
	return position;
}

int fileXioGetStat(const char *path, iox_stat_t *info)
{
	memset(info, 0, sizeof(*info));
	if (strcmp(path, "cdrom:\\MAPS") == 0) {
		info->mode = FIO_S_IFDIR;
		return 0;
	}
	if (strcmp(path, "cdrom:\\MAPS\\UI.MAP") == 0) {
		info->mode = FIO_S_IFREG;
		info->size = FILE_BYTES;
		return 0;
	}
	return -1;
}

int main(void)
{
	uint8_t buffer[16];
	unsigned long size = 0, read_count = 0;
	const char *failed_stage = NULL;
	int tokens[HANDLE_COUNT];
	int i, cycle;
	unsigned heap_alloc_baseline;
	for (i = 0; i < FILE_BYTES; ++i) s_file[i] = (uint8_t)(i ^ 0xA5);
	assert(file_set_default_root("cdrom:/"));
	assert(hcu_file_bridge_open("maps/ui.map", &size) < 0);
	assert(file_reader_filexio_init() == 0);
	heap_alloc_baseline = s_heap_alloc_calls;
	assert(hcu_file_bridge_probe("D:\\maps\\ui.map", &size,
		&failed_stage));
	assert(size == FILE_BYTES && failed_stage == NULL);
	assert(s_active_descriptors == 0 && s_high_descriptors == 1);
	assert(!hcu_file_bridge_probe("D:\\maps\\missing.map", &size,
		&failed_stage));
	assert(size == 0 && strcmp(failed_stage, "stat") == 0);
	assert(!hcu_file_bridge_probe("D:\\maps", &size, &failed_stage));
	assert(strcmp(failed_stage, "validate-file") == 0);
	for (i = 0; i < HANDLE_COUNT; ++i) {
		tokens[i] = hcu_file_bridge_open("D:\\maps\\ui.map", &size);
		assert(tokens[i] == i && size == FILE_BYTES);
		assert(strcmp(s_last_path, "cdrom:\\MAPS\\UI.MAP") == 0);
	}
	assert(hcu_file_bridge_open("maps/ui.map", &size) < 0);
	assert(s_open_calls == HANDLE_COUNT + 1 && s_high_descriptors == HANDLE_COUNT);
	assert(hcu_file_bridge_size(tokens[0], &size) && size == FILE_BYTES);
	assert(hcu_file_bridge_read(tokens[0], buffer, 8, &read_count));
	assert(read_count == 8 && memcmp(buffer, s_file, 8) == 0);
	assert(hcu_file_bridge_seek(tokens[0], 20, 0) == 20);
	assert(hcu_file_bridge_seek(tokens[0], 4, 1) == 24);
	assert(hcu_file_bridge_seek(tokens[0], -4, 2) == FILE_BYTES - 4);
	assert(hcu_file_bridge_read(tokens[0], buffer, sizeof(buffer), &read_count));
	assert(read_count == 4 && memcmp(buffer, s_file + FILE_BYTES - 4, 4) == 0);
	assert(hcu_file_bridge_read(tokens[0], buffer, 1, &read_count));
	assert(read_count == 0);
	assert(hcu_file_bridge_seek(tokens[0], -1, 0) < 0);
	assert(hcu_file_bridge_seek(tokens[0], 0, 3) < 0);
	assert(!hcu_file_bridge_read(-1, buffer, 1, &read_count));
	assert(!hcu_file_bridge_size(tokens[0], NULL));
	s_fail_read = 1;
	assert(hcu_file_bridge_seek(tokens[0], 0, 0) == 0);
	assert(!hcu_file_bridge_read(tokens[0], buffer, 1, &read_count));
	assert(read_count == 0);
	s_fail_read = 0;
	assert(!hcu_file_bridge_probe("D:\\maps\\ui.map", &size,
		&failed_stage));
	assert(strcmp(failed_stage, "open") == 0);
	for (i = 0; i < HANDLE_COUNT; ++i)
		assert(hcu_file_bridge_close(tokens[i]));
	assert(!hcu_file_bridge_close(tokens[0]));
	assert(s_active_descriptors == 0 && s_close_calls == HANDLE_COUNT + 1);
	s_fail_read = 1;
	assert(!hcu_file_bridge_probe("D:\\maps\\ui.map", &size,
		&failed_stage));
	assert(strcmp(failed_stage, "read-first-byte") == 0);
	assert(s_active_descriptors == 0);
	s_fail_read = 0;
	for (cycle = 0; cycle < 100; ++cycle) {
		int token = hcu_file_bridge_open("maps/ui.map", &size);
		assert(token == 0 && size == FILE_BYTES);
		assert(hcu_file_bridge_close(token));
	}
	assert(s_active_descriptors == 0 && s_high_descriptors == HANDLE_COUNT);
	assert(s_open_calls == HANDLE_COUNT + 102);
	assert(s_close_calls == HANDLE_COUNT + 102);
	assert(s_heap_alloc_calls == heap_alloc_baseline);
	{
		int is_directory = 0;
		assert(hcu_file_bridge_stat("D:\\maps", &size, &is_directory));
		assert(is_directory && size == 0);
		assert(hcu_file_bridge_stat("D:\\maps\\ui.map", &size,
			&is_directory));
		assert(!is_directory && size == FILE_BYTES);
	}
	return 0;
}
