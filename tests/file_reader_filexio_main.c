#define NEWLIB_PORT_AWARE
#include <io_common.h>
#include <fileXio_rpc.h>

#include "stream/file.h"

#include <assert.h>
#include <stdarg.h>
#include <stdint.h>
#include <string.h>

static uint8_t source_bytes[1024];
static int source_position;
static int init_calls;
static int fail_init;
static int open_calls;
static int read_calls;
static int close_calls;
static int fail_reads;
static char last_path[128];
static char last_stat_path[128];

int fileXioInit(void)
{
	init_calls++;
	return fail_init ? -1 : 0;
}

int fileXioOpen(const char *source, int flags, ...)
{
	va_list args;
	int mode;
	va_start(args, flags);
	mode = va_arg(args, int);
	va_end(args);
	assert(flags == FIO_O_RDONLY && mode == 0);
	assert(strlen(source) < sizeof(last_path));
	strcpy(last_path, source);
	open_calls++;
	return 7;
}

int fileXioClose(int fd)
{
	assert(fd == 7);
	close_calls++;
	return 0;
}

int fileXioRead(int fd, void *buffer, int size)
{
	int available;
	assert(fd == 7 && size > 0);
	read_calls++;
	if (fail_reads) return 0;
	available = (int)sizeof(source_bytes) - source_position;
	if (size > available) size = available;
	if (size <= 0) return 0;
	memcpy(buffer, source_bytes + source_position, (size_t)size);
	source_position += size;
	return size;
}

int fileXioLseek(int fd, int offset, int whence)
{
	int next;
	assert(fd == 7);
	if (whence == FIO_SEEK_SET) next = offset;
	else if (whence == FIO_SEEK_CUR) next = source_position + offset;
	else if (whence == FIO_SEEK_END) next = (int)sizeof(source_bytes) + offset;
	else return -1;
	if (next < 0 || next > (int)sizeof(source_bytes)) return -1;
	source_position = next;
	return next;
}

int fileXioGetStat(const char *path, iox_stat_t *info)
{
	assert(strlen(path) < sizeof(last_stat_path));
	strcpy(last_stat_path, path);
	memset(info, 0, sizeof(*info));
	if (strcmp(path, "cdrom:\\MAPS") == 0) {
		info->mode = FIO_S_IFDIR;
		return 0;
	}
	if (strcmp(path, "cdrom:\\MAPS\\UI.MAP") == 0) {
		info->mode = FIO_S_IFREG;
		info->size = sizeof(source_bytes);
		return 0;
	}
	if (strcmp(path, "mass:/maps/ui.hp2") == 0 ||
		strcmp(path, "smb0:/maps/ui.hp2") == 0 ||
		strcmp(path, "pfs0:/maps/ui.hp2") == 0) {
		info->mode = FIO_S_IFREG;
		info->size = sizeof(source_bytes);
		return 0;
	}
	return -1;
}

int main(void)
{
	file_reader_t reader = { -1, 0 };
	uint8_t actual[32];
	int calls_before;
	unsigned i;
	for (i = 0; i < sizeof(source_bytes); i++)
		source_bytes[i] = (uint8_t)(i * 17u + 3u);

	/* Fail closed until startup has loaded/confirmed the IOP service. */
	assert(file_reader_open(&reader, "host:/ui.map") != 0);
	assert(open_calls == 0 && reader.descriptor == -1);
	fail_init = 1;
	assert(file_reader_filexio_init() != 0 && init_calls == 1);
	assert(file_reader_open(&reader, "host:/ui.map") != 0 && open_calls == 0);
	fail_init = 0;
	assert(file_reader_filexio_init() == 0 && init_calls == 2);
	assert(file_reader_filexio_init() == 0 && init_calls == 2);
	assert(file_reader_open(&reader, "host:/ui.map") == 0);
	assert(open_calls == 1 && strcmp(last_path, "host:/ui.map") == 0);
	assert(reader.descriptor == 7 && reader.size == sizeof(source_bytes));
	assert(file_reader_read_at(&reader, 9, actual, 17) == 0);
	assert(memcmp(actual, source_bytes + 9, 17) == 0);
	calls_before = read_calls;
	memset(actual, 0xCC, sizeof(actual));
	assert(file_reader_read_at(&reader, reader.size - 4, actual, 8) != 0);
	assert(read_calls == calls_before);
	for (i = 0; i < sizeof(actual); i++) assert(actual[i] == 0xCC);
	fail_reads = 1;
	assert(file_reader_read_at(&reader, 0, actual, 8) != 0);
	fail_reads = 0;
	file_reader_close(&reader);
	assert(close_calls == 1 && reader.descriptor == -1 && reader.size == 0);
	file_reader_close(&reader);
	assert(close_calls == 1);

	/* Device selection remains explicit and does not require libc open(). */
	assert(file_set_default_root("cdrom:/"));
	assert(file_reader_open(&reader, "maps/ui.hp2") == 0);
	assert(strcmp(last_path, "cdrom:\\MAPS\\UI.HP2") == 0);
	file_reader_close(&reader);
	assert(close_calls == 2);
	assert(file_reader_open(&reader, "cdrom:/maps/ui.map") == 0);
	assert(strcmp(last_path, "cdrom:\\MAPS\\UI.MAP") == 0);
	file_reader_close(&reader);
	assert(close_calls == 3);
	{
		uint32_t size = 0;
		assert(file_reader_path_info("maps", &size) == 2);
		assert(strcmp(last_stat_path, "cdrom:\\MAPS") == 0);
		assert(file_reader_path_info("maps/ui.map", &size) == 1);
		assert(size == sizeof(source_bytes));
		assert(strcmp(last_stat_path, "cdrom:\\MAPS\\UI.MAP") == 0);
	}
	/* OPL profiles are explicit roots. The prefixes are passed through as-is;
	 * this fixture does not pretend to mount the underlying devices. */
	{
		static const char *const roots[] = {
			"mass:/", "smb0:/", "pfs0:/"
		};
		static const char *const expected[] = {
			"mass:/maps/ui.hp2", "smb0:/maps/ui.hp2", "pfs0:/maps/ui.hp2"
		};
		for (i = 0; i < sizeof(roots) / sizeof(roots[0]); ++i) {
			uint32_t size = 0;
			assert(file_set_default_root(roots[i]));
			assert(file_reader_open(&reader, "maps/ui.hp2") == 0);
			assert(strcmp(last_path, expected[i]) == 0);
			file_reader_close(&reader);
			assert(file_reader_path_info("maps/ui.hp2", &size) == 1);
			assert(size == sizeof(source_bytes));
			assert(strcmp(last_stat_path, expected[i]) == 0);
		}
	}
	return 0;
}
