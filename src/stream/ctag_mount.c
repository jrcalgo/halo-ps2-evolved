#include "stream/ctag_mount.h"

#include <stdint.h>
#include <string.h>

/* HCU's PS2 cache adapter stores one process-global mounted map. */
static ctag_mount *s_active_mount;

static int mount_read_at(void *context, int32_t tag_index, uint32_t file_offset,
	uint32_t size, void *buffer, int blocking)
{
	ctag_mount *mount = (ctag_mount *)context;
	if (!mount || !mount->source_read) return 0;
	return ctag_resource_index_read(&mount->resource_index,
		mount->source_read, mount->read_context, tag_index, file_offset,
		size, buffer, blocking);
}

static int payload_owned_by_transaction(const arena_t *owner, size_t mark,
	const uint8_t *payload, size_t payload_size)
{
	uintptr_t arena_start, payload_start, transaction_start, allocation_end;
	if (!owner || !owner->base || !payload || owner->used > owner->cap ||
		mark > owner->used)
		return 0;
	arena_start = (uintptr_t)owner->base;
	payload_start = (uintptr_t)payload;
	if (owner->cap > UINTPTR_MAX - arena_start ||
		mark > UINTPTR_MAX - arena_start ||
		owner->used > UINTPTR_MAX - arena_start)
		return 0;
	transaction_start = arena_start + mark;
	allocation_end = arena_start + owner->used;
	return payload_start >= transaction_start && payload_start <= allocation_end &&
		payload_size <= allocation_end - payload_start;
}

static int arenas_disjoint(const arena_t *left, const arena_t *right)
{
	uintptr_t left_start, right_start, left_end, right_end;
	if (!left || !right || !left->base || !right->base ||
		left == right)
		return 0;
	left_start = (uintptr_t)left->base;
	right_start = (uintptr_t)right->base;
	if (left->cap > UINTPTR_MAX - left_start ||
		right->cap > UINTPTR_MAX - right_start)
		return 0;
	left_end = left_start + left->cap;
	right_end = right_start + right->cap;
	return left_end <= right_start || right_end <= left_start;
}

static void release_mounted_bsp(ctag_mount *mount)
{
	if (!mount || !mount->bsp_active) return;
	mount->backend->unmount_bsp(mount->backend->context);
	arena_release(mount->bsp_scratch, mount->bsp_scratch_mark);
	mount->bsp_active = 0;
}

static void release_bsp_callback(void *context)
{
	release_mounted_bsp((ctag_mount *)context);
}

static int load_bsp_extent(void *context, uint32_t file_offset,
	uint32_t file_size)
{
	ctag_mount *mount = (ctag_mount *)context;
	cbsp_catalog_entry entry;
	uint8_t *payload;
	size_t payload_size = 0, mark;
	uint64_t bsp_end, tag_end;
	if (!mount || !mount->active || !mount->bsp_scratch ||
		!mount->load_section || !mount->backend->mount_bsp ||
		!cbsp_catalog_find(&mount->bsp_catalog, file_offset, file_size, &entry))
		return 0;
	bsp_end = (uint64_t)file_offset + file_size;
	tag_end = (uint64_t)mount->resource_index.tag_data_offset +
		mount->resource_index.tag_data_size;
	if (((uint64_t)file_offset < tag_end &&
		(uint64_t)mount->resource_index.tag_data_offset < bsp_end) ||
		ctag_resource_index_overlaps(&mount->resource_index, file_offset,
			file_size))
		return 0;
	release_mounted_bsp(mount);
	mark = arena_mark(mount->bsp_scratch);
	payload = mount->load_section(mount->load_context, mount->bsp_scratch,
		mount->pack_path, entry.section_tag, &payload_size, 0);
	if (!payload || !payload_size ||
		!payload_owned_by_transaction(mount->bsp_scratch, mark, payload,
			payload_size)) {
		arena_release(mount->bsp_scratch, mark);
		return 0;
	}
	if (!mount->backend->mount_bsp(mount->backend->context, payload,
		payload_size, entry.file_offset, entry.file_size)) {
		arena_release(mount->bsp_scratch, mark);
		return 0;
	}
	mount->bsp_scratch_mark = mark;
	mount->bsp_active = 1;
	return 1;
}

void ctag_mount_init(ctag_mount *mount)
{
	if (mount) memset(mount, 0, sizeof(*mount));
}

static int ctag_mount_hp2_internal(ctag_mount *mount, arena_t *owner,
	const char *pack_path,
	const char *map_name, uint32_t tag_data_offset, uint32_t tag_data_size,
	uint32_t file_length, int discover_tag_extent,
	ctag_read_at_fn read_at, void *read_context,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context)
{
	size_t mark, payload_size = 0, resource_index_size = 0;
	uint8_t *payload, *resource_index_bytes;

	if (!mount || mount->active || s_active_mount || !owner || !owner->base ||
		!pack_path || !map_name ||
		!read_at || !backend || !backend->mount || !backend->unmount ||
		!load_section)
		return -1;
	mark = arena_mark(owner);
	payload = load_section(load_context, owner, pack_path, "CTAG",
		&payload_size, 0);
	if (!payload || !payload_size) {
		arena_release(owner, mark);
		return -1;
	}
	if (!payload_owned_by_transaction(owner, mark, payload, payload_size)) {
		arena_release(owner, mark);
		return -1;
	}
	resource_index_bytes = load_section(load_context, owner, pack_path, "CRNG",
		&resource_index_size, 0);
	if (!resource_index_bytes || !resource_index_size ||
		!payload_owned_by_transaction(owner, mark, resource_index_bytes,
			resource_index_size) ||
		!(discover_tag_extent ?
			ctag_resource_index_open_discover(&mount->resource_index,
				resource_index_bytes, resource_index_size, file_length) :
			ctag_resource_index_open(&mount->resource_index, resource_index_bytes,
				resource_index_size, file_length, tag_data_offset, tag_data_size))) {
		arena_release(owner, mark);
		return -1;
	}
	if (discover_tag_extent) {
		tag_data_offset = mount->resource_index.tag_data_offset;
		tag_data_size = mount->resource_index.tag_data_size;
	}
	mount->source_read = read_at;
	mount->read_context = read_context;
	if (!backend->mount(backend->context, map_name, payload, payload_size,
		tag_data_offset, file_length, mount_read_at, mount)) {
		memset(mount, 0, sizeof(*mount));
		arena_release(owner, mark);
		return -1;
	}
	mount->owner = owner;
	mount->arena_mark = mark;
	mount->backend = backend;
	mount->payload = payload;
	mount->payload_size = payload_size;
	mount->resource_index_bytes = resource_index_bytes;
	mount->resource_index_size = resource_index_size;
	mount->active = 1;
	s_active_mount = mount;
	return 0;
}

int ctag_mount_hp2(ctag_mount *mount, arena_t *owner, const char *pack_path,
	const char *map_name, uint32_t tag_data_offset, uint32_t tag_data_size,
	uint32_t file_length,
	ctag_read_at_fn read_at, void *read_context,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context)
{
	return ctag_mount_hp2_internal(mount, owner, pack_path, map_name,
		tag_data_offset, tag_data_size, file_length, 0, read_at, read_context,
		backend, load_section, load_context);
}

int ctag_mount_hp2_discover(ctag_mount *mount, arena_t *owner,
	const char *pack_path, const char *map_name, uint32_t file_length,
	ctag_read_at_fn read_at, void *read_context,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context)
{
	return ctag_mount_hp2_internal(mount, owner, pack_path, map_name,
		0, 0, file_length, 1, read_at, read_context, backend, load_section,
		load_context);
}

int ctag_mount_hp2_with_bsp_catalog(ctag_mount *mount, arena_t *owner,
	arena_t *bsp_scratch, const char *pack_path, const char *map_name,
	uint32_t tag_data_offset, uint32_t tag_data_size, uint32_t file_length,
	ctag_read_at_fn read_at, void *read_context,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context)
{
	size_t catalog_size = 0;
	uint8_t *catalog_bytes;
	if (!bsp_scratch || !backend || !backend->mount_bsp ||
		!backend->unmount_bsp || !backend->register_bsp_loader ||
		!arenas_disjoint(owner, bsp_scratch) || !pack_path)
		return -1;
	if (ctag_mount_hp2(mount, owner, pack_path, map_name,
		tag_data_offset, tag_data_size, file_length, read_at, read_context,
		backend, load_section, load_context) != 0)
		return -1;
	catalog_bytes = load_section(load_context, owner, pack_path, "CBIX",
		&catalog_size, 0);
	if (!catalog_bytes || !catalog_size ||
		!payload_owned_by_transaction(owner, mount->arena_mark, catalog_bytes,
			catalog_size) ||
		!cbsp_catalog_open(&mount->bsp_catalog, catalog_bytes, catalog_size,
			file_length)) {
		ctag_mount_unload(mount);
		return -1;
	}
	mount->bsp_scratch = bsp_scratch;
	mount->load_section = load_section;
	mount->load_context = load_context;
	mount->pack_path = pack_path;
	if (!backend->register_bsp_loader(backend->context, load_bsp_extent,
		release_bsp_callback, mount)) {
		ctag_mount_unload(mount);
		return -1;
	}
	return 0;
}

int ctag_mount_hp2_discover_with_bsp_catalog(ctag_mount *mount,
	arena_t *owner, arena_t *bsp_scratch, const char *pack_path,
	const char *map_name, uint32_t file_length,
	ctag_read_at_fn read_at, void *read_context,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context)
{
	size_t catalog_size = 0;
	uint8_t *catalog_bytes;
	if (!bsp_scratch || !backend || !backend->mount_bsp ||
		!backend->unmount_bsp || !backend->register_bsp_loader ||
		!arenas_disjoint(owner, bsp_scratch) || !pack_path)
		return -1;
	if (ctag_mount_hp2_discover(mount, owner, pack_path, map_name,
		file_length, read_at, read_context, backend, load_section,
		load_context) != 0)
		return -1;
	catalog_bytes = load_section(load_context, owner, pack_path, "CBIX",
		&catalog_size, 0);
	if (!catalog_bytes || !catalog_size ||
		!payload_owned_by_transaction(owner, mount->arena_mark, catalog_bytes,
			catalog_size) ||
		!cbsp_catalog_open(&mount->bsp_catalog, catalog_bytes, catalog_size,
			file_length)) {
		ctag_mount_unload(mount);
		return -1;
	}
	mount->bsp_scratch = bsp_scratch;
	mount->load_section = load_section;
	mount->load_context = load_context;
	mount->pack_path = pack_path;
	if (!backend->register_bsp_loader(backend->context, load_bsp_extent,
		release_bsp_callback, mount)) {
		ctag_mount_unload(mount);
		return -1;
	}
	return 0;
}

void ctag_mount_unload(ctag_mount *mount)
{
	if (!mount || !mount->active) return;
	release_mounted_bsp(mount);
	/* The backend must clear CE's mounted cache before its bytes are released. */
	mount->backend->unmount(mount->backend->context);
	/* A file-backed resource source must remain open until CE has released its
	 * cache callbacks; close it only after backend unmount succeeds. */
	if (mount->close_read_context)
		mount->close_read_context(mount->read_context);
	if (s_active_mount == mount) s_active_mount = NULL;
	arena_release(mount->owner, mount->arena_mark);
	memset(mount, 0, sizeof(*mount));
}
