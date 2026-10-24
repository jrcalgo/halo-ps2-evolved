#include "stream/ctag_mount.h"

#include <stdint.h>
#include <stdio.h>
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

static int visit_bsp_extent(void *context, uint32_t file_offset,
	uint32_t file_size, ctag_bsp_sink_fn sink, void *sink_context,
	size_t *raw_size)
{
	ctag_mount *mount = (ctag_mount *)context;
	cbsp_catalog_entry entry;
	uint64_t bsp_end, tag_end;
	if (raw_size) *raw_size = 0;
	if (!mount || !mount->active || !mount->visit_section || !sink ||
		!raw_size ||
		!cbsp_catalog_find(&mount->bsp_catalog, file_offset, file_size, &entry))
	{
		printf("HALO_PS2_LOCAL cbsp-visit reject=catalog offset=%u size=%u active=%d visitor=%d\n",
			(unsigned)file_offset, (unsigned)file_size,
			mount ? mount->active : 0, mount && mount->visit_section != NULL);
		return 0;
	}
	bsp_end = (uint64_t)file_offset + file_size;
	tag_end = (uint64_t)mount->resource_index.tag_data_offset +
		mount->resource_index.tag_data_size;
	if (((uint64_t)file_offset < tag_end &&
		(uint64_t)mount->resource_index.tag_data_offset < bsp_end) ||
		ctag_resource_index_overlaps(&mount->resource_index, file_offset,
			file_size))
	{
		printf("HALO_PS2_LOCAL cbsp-visit reject=overlap offset=%u size=%u tag=%u/%u\n",
			(unsigned)file_offset, (unsigned)file_size,
			(unsigned)mount->resource_index.tag_data_offset,
			(unsigned)mount->resource_index.tag_data_size);
		return 0;
	}
	/* The visitor completes (including outer HP2 CRC) before the cache adapter
	 * can publish CE's completion flag. The callback bytes are transient. */
	printf("HALO_PS2_LOCAL cbsp-visit begin tag=%s offset=%u size=%u\n",
		entry.section_tag, (unsigned)file_offset, (unsigned)file_size);
	return mount->visit_section(mount->load_context, mount->pack_path,
		entry.section_tag, sink, sink_context, raw_size);
}

static int visit_ctag_payload(void *context, ctag_ctag_sink_fn sink,
	void *sink_context, size_t *raw_size)
{
	ctag_mount *mount = (ctag_mount *)context;
	if (raw_size) *raw_size = 0;
	if (!mount || !mount->active || !mount->visit_ctag_section ||
		!sink || !raw_size)
		return 0;
	return mount->visit_ctag_section(mount->load_context,
		mount->pack_path, "CTAG", sink, sink_context, raw_size);
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

int ctag_mount_set_bsp_section_visitor(ctag_mount *mount,
	ctag_section_visit_fn visit_section)
{
	if (!mount || !mount->active || !visit_section || !mount->backend ||
		!mount->backend->register_bsp_visitor ||
		!mount->backend->register_bsp_loader)
		return 0;
	mount->visit_section = visit_section;
	if (!mount->backend->register_bsp_visitor(mount->backend->context,
		visit_bsp_extent, mount)) {
		mount->visit_section = NULL;
		return 0;
	}
	if (!mount->backend->register_bsp_loader(mount->backend->context,
		NULL, NULL, NULL)) {
		mount->backend->register_bsp_visitor(mount->backend->context,
			NULL, NULL);
		mount->visit_section = NULL;
		return 0;
	}
	return 1;
}

int ctag_mount_hp2_stream_verified_source_discover(ctag_mount *mount,
	arena_t *owner, arena_t *bsp_scratch, const char *pack_path,
	const char *map_name, uint32_t tag_data_offset,
	uint32_t tag_data_size, uint32_t file_length,
	ctag_read_at_fn read_at, void *read_context,
	void (*close_read_context)(void *context),
	const hmap_identity *identity, const ctag_stream_info *ctag_info,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context)
{
	size_t mark, crng_size = 0, catalog_size = 0, relocation_bytes;
	uint8_t *crng_bytes, *catalog_bytes, *relocations = NULL;
	ctag_resource_index resource_index;
	cbsp_catalog bsp_catalog;
	if (!mount || mount->active || s_active_mount || !owner || !owner->base ||
		!pack_path || !map_name || !read_at || !identity || !ctag_info ||
		!backend || !backend->mount_stream || !backend->unmount ||
		!backend->register_ctag_visitor || !load_section ||
		identity->file_length != file_length || file_length == 0 ||
		tag_data_offset != identity->tag_data_offset ||
		tag_data_size != identity->tag_data_size ||
		ctag_info->image_size < 36u ||
		ctag_info->image_size > tag_data_size ||
		ctag_info->relocation_count == 0 ||
		ctag_info->relocation_count > UINT32_MAX / 4u ||
		(bsp_scratch && (!backend->mount_bsp || !backend->unmount_bsp ||
			!backend->register_bsp_loader || !backend->register_bsp_visitor ||
			!arenas_disjoint(owner, bsp_scratch))))
		return -1;
	relocation_bytes = (size_t)ctag_info->relocation_count * 4u;
	mark = arena_mark(owner);
	crng_bytes = load_section(load_context, owner, pack_path, "CRNG",
		&crng_size, 0);
	if (!crng_bytes || !crng_size ||
		!payload_owned_by_transaction(owner, mark, crng_bytes, crng_size) ||
		!ctag_resource_index_open(&resource_index, crng_bytes, crng_size,
			file_length, tag_data_offset, tag_data_size))
		goto fail;
	catalog_bytes = NULL;
	memset(&bsp_catalog, 0, sizeof(bsp_catalog));
	if (bsp_scratch) {
		catalog_bytes = load_section(load_context, owner, pack_path, "CBIX",
			&catalog_size, 0);
		if (!catalog_bytes || !catalog_size ||
			!payload_owned_by_transaction(owner, mark, catalog_bytes,
				catalog_size) ||
			!cbsp_catalog_open(&bsp_catalog, catalog_bytes, catalog_size,
				file_length))
			goto fail;
	}
	if (relocation_bytes) {
		relocations = (uint8_t *)arena_alloc(owner, relocation_bytes, 4u);
		if (!relocations) goto fail;
	}
	if (!backend->mount_stream(backend->context, map_name, ctag_info,
		relocations, relocation_bytes, tag_data_offset, file_length,
		read_at, read_context))
		goto fail;
	mount->owner = owner;
	mount->arena_mark = mark;
	mount->backend = backend;
	mount->read_context = read_context;
	mount->close_read_context = close_read_context;
	mount->source_read = read_at;
	mount->ctag_stream_info = *ctag_info;
	mount->ctag_relocations = relocations;
	mount->ctag_relocation_bytes = relocation_bytes;
	mount->resource_index_bytes = crng_bytes;
	mount->resource_index_size = crng_size;
	mount->resource_index = resource_index;
	mount->bsp_catalog = bsp_catalog;
	mount->bsp_scratch = bsp_scratch;
	mount->load_section = load_section;
	mount->load_context = load_context;
	mount->pack_path = pack_path;
	mount->active = 1;
	s_active_mount = mount;
	if (bsp_scratch && !backend->register_bsp_loader(backend->context,
		load_bsp_extent, release_bsp_callback, mount)) {
		ctag_mount_unload(mount);
		return -1;
	}
	return 0;

fail:
	arena_release(owner, mark);
	return -1;
}

int ctag_mount_set_ctag_section_visitor(ctag_mount *mount,
	ctag_ctag_visit_fn visit_section)
{
	if (!mount || !mount->active || !visit_section || !mount->backend ||
		!mount->backend->register_ctag_visitor)
		return 0;
	mount->visit_ctag_section = visit_section;
	if (!mount->backend->register_ctag_visitor(mount->backend->context,
		visit_ctag_payload, mount)) {
		mount->visit_ctag_section = NULL;
		return 0;
	}
	return 1;
}
