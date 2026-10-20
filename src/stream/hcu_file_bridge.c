#include "stream/hcu_file_bridge.h"

#include "stream/file.h"

#include <stddef.h>
#include <stdint.h>
#include <string.h>

enum { HCU_FILE_SLOT_COUNT = 16 };

struct hcu_file_slot
{
	file_reader_t reader;
	uint32_t position;
	uint8_t active;
};

static struct hcu_file_slot s_slots[HCU_FILE_SLOT_COUNT];

static const char *relative_path(const char *path)
{
	if (!path) return NULL;
	if ((path[0] == 'd' || path[0] == 'D') && path[1] == ':' &&
		(path[2] == '\\' || path[2] == '/'))
		return path + 3;
	return path;
}

static struct hcu_file_slot *get_slot(int token)
{
	if (token < 0 || token >= HCU_FILE_SLOT_COUNT || !s_slots[token].active)
		return NULL;
	return &s_slots[token];
}

int hcu_file_bridge_open(const char *path, unsigned long *size_out)
{
	const char *relative = relative_path(path);
	int index;
	if (size_out) *size_out = 0;
	if (!relative || !relative[0]) return -1;
	for (index = 0; index < HCU_FILE_SLOT_COUNT; ++index)
		if (!s_slots[index].active) break;
	if (index == HCU_FILE_SLOT_COUNT) return -1;
	s_slots[index].reader.descriptor = -1;
	s_slots[index].reader.size = 0;
	if (file_reader_open(&s_slots[index].reader, relative) != 0) return -1;
	s_slots[index].position = 0;
	s_slots[index].active = 1;
	if (size_out) *size_out = s_slots[index].reader.size;
	return index;
}

int hcu_file_bridge_close(int token)
{
	struct hcu_file_slot *slot = get_slot(token);
	if (!slot) return 0;
	file_reader_close(&slot->reader);
	memset(slot, 0, sizeof(*slot));
	slot->reader.descriptor = -1;
	return 1;
}

int hcu_file_bridge_read(int token, void *buffer, unsigned long count,
	unsigned long *read_out)
{
	struct hcu_file_slot *slot = get_slot(token);
	uint32_t remaining;
	size_t amount;
	if (read_out) *read_out = 0;
	if (!slot || (!buffer && count)) return 0;
	if (slot->position >= slot->reader.size) return 1;
	remaining = slot->reader.size - slot->position;
	amount = count < remaining ? (size_t)count : remaining;
	if (file_reader_read_at(&slot->reader, slot->position, buffer, amount) != 0)
		return 0;
	slot->position += (uint32_t)amount;
	if (read_out) *read_out = (unsigned long)amount;
	return 1;
}

int hcu_file_bridge_size(int token, unsigned long *size_out)
{
	struct hcu_file_slot *slot = get_slot(token);
	if (!slot || !size_out) return 0;
	*size_out = slot->reader.size;
	return 1;
}

long hcu_file_bridge_seek(int token, long distance, unsigned long origin)
{
	struct hcu_file_slot *slot = get_slot(token);
	int64_t base, position;
	if (!slot) return -1;
	if (origin == 0) base = 0;
	else if (origin == 1) base = slot->position;
	else if (origin == 2) base = slot->reader.size;
	else return -1;
	position = base + distance;
	if (position < 0 || position > slot->reader.size || position > UINT32_MAX)
		return -1;
	slot->position = (uint32_t)position;
	return (long)slot->position;
}

int hcu_file_bridge_stat(const char *path, unsigned long *size_out,
	int *directory_out)
{
	const char *relative = relative_path(path);
	uint32_t size = 0;
	int kind;
	if (size_out) *size_out = 0;
	if (directory_out) *directory_out = 0;
	if (!relative) return 0;
	kind = file_reader_path_info(relative, &size);
	if (!kind) return 0;
	if (size_out) *size_out = size;
	if (directory_out) *directory_out = kind == 2;
	return 1;
}
