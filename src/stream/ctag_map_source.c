#include "stream/ctag_map_source.h"
#include "stream/hcu_loading_screen.h"
#include "stream/hmap.h"
#include "stream/sha256.h"

#include <string.h>

static const char *canonical_leaf(const char *map_name)
{
	const char *leaf = map_name;
	if (!map_name || !map_name[0]) return NULL;
	while (*map_name) {
		if (*map_name == '\\' || *map_name == '/') leaf = map_name + 1;
		map_name++;
	}
	return leaf[0] ? leaf : NULL;
}

static int section_owned_since(const arena_t *owner, size_t mark,
	const uint8_t *payload, size_t size)
{
	uintptr_t base, start, first, end;
	if (!owner || !owner->base || !payload || owner->used > owner->cap ||
		mark > owner->used)
		return 0;
	base = (uintptr_t)owner->base;
	first = (uintptr_t)payload;
	if (owner->cap > UINTPTR_MAX - base || mark > UINTPTR_MAX - base ||
		owner->used > UINTPTR_MAX - base)
		return 0;
	start = base + mark;
	end = base + owner->used;
	return first >= start && first <= end && size <= end - first;
}

int ctag_mount_hp2_file(ctag_mount *mount, arena_t *owner,
	const char *pack_path, const char *map_name,
	uint32_t tag_data_offset, uint32_t tag_data_size, uint32_t file_length,
	const char *resource_map_path, ctag_map_source *source,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context)
{
	if (!source || ctag_map_source_open(source, resource_map_path, file_length))
		return -1;
	if (ctag_mount_hp2(mount, owner, pack_path, map_name, tag_data_offset,
		tag_data_size, file_length, ctag_map_source_read, source, backend,
		load_section, load_context) != 0) {
		ctag_map_source_close(source);
		return -1;
	}
	mount->close_read_context = ctag_map_source_close_context;
	return 0;
}

int ctag_mount_hp2_file_with_bsp_catalog(ctag_mount *mount, arena_t *owner,
	arena_t *bsp_scratch, const char *pack_path, const char *map_name,
	uint32_t tag_data_offset, uint32_t tag_data_size, uint32_t file_length,
	const char *resource_map_path, ctag_map_source *source,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context)
{
	if (!source || ctag_map_source_open(source, resource_map_path, file_length))
		return -1;
	if (ctag_mount_hp2_with_bsp_catalog(mount, owner, bsp_scratch, pack_path,
		map_name, tag_data_offset, tag_data_size, file_length,
		ctag_map_source_read, source, backend, load_section, load_context) != 0) {
		ctag_map_source_close(source);
		return -1;
	}
	mount->close_read_context = ctag_map_source_close_context;
	return 0;
}

int ctag_mount_hp2_file_discover(ctag_mount *mount, arena_t *owner,
	const char *pack_path, const char *map_name,
	const char *resource_map_path, ctag_map_source *source,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context)
{
	if (!source || ctag_map_source_open_any(source, resource_map_path))
		return -1;
	if (ctag_mount_hp2_discover(mount, owner, pack_path, map_name,
		source->reader.size, ctag_map_source_read, source, backend,
		load_section, load_context) != 0) {
		ctag_map_source_close(source);
		return -1;
	}
	mount->close_read_context = ctag_map_source_close_context;
	return 0;
}

static int mount_file_verified_discover(ctag_mount *mount, arena_t *owner,
	arena_t *bsp_scratch, const char *pack_path, const char *map_name,
	const char *resource_map_path, ctag_map_source *source,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context)
{
	hmap_identity identity;
	const char *leaf = canonical_leaf(map_name);
	size_t mark, hmap_size = 0;
	uint8_t *hmap_bytes;
	int preflight_ok;
	if (!owner || !leaf || !load_section || !source ||
		ctag_map_source_open_any(source, resource_map_path))
		return -1;
	mark = arena_mark(owner);
	hmap_bytes = load_section(load_context, owner, pack_path, "HMAP",
		&hmap_size, 0);
	preflight_ok = hmap_bytes && hmap_size &&
		section_owned_since(owner, mark, hmap_bytes, hmap_size) &&
		hmap_open(&identity, hmap_bytes, hmap_size, leaf) &&
		identity.file_length == source->reader.size &&
		ctag_map_source_matches_sha256(source, identity.source_sha256);
	arena_release(owner, mark);
	if (!preflight_ok) {
		ctag_map_source_close(source);
		return -1;
	}
	if (ctag_mount_hp2_verified_source_discover(mount, owner, bsp_scratch,
		pack_path, map_name, source, &identity, backend, load_section,
		load_context) != 0) {
		ctag_map_source_close(source);
		return -1;
	}
	return 0;
}

int ctag_mount_hp2_verified_source_discover(ctag_mount *mount,
	arena_t *owner, arena_t *bsp_scratch, const char *pack_path,
	const char *map_name, ctag_map_source *source,
	const hmap_identity *identity, const ctag_mount_backend *backend,
	ctag_section_load_fn load_section, void *load_context)
{
	if (!source || !source->active || !identity || !pack_path || !map_name ||
		identity->file_length != source->reader.size)
		return -1;
	if ((bsp_scratch ?
		ctag_mount_hp2_discover_with_bsp_catalog(mount, owner, bsp_scratch,
			pack_path, map_name, source->reader.size, ctag_map_source_read,
			source, backend, load_section, load_context) :
		ctag_mount_hp2_discover(mount, owner, pack_path, map_name,
			source->reader.size, ctag_map_source_read, source, backend,
			load_section, load_context)) != 0) {
		ctag_map_source_close(source);
		return -1;
	}
	if (mount->resource_index.tag_data_offset != identity->tag_data_offset ||
		mount->resource_index.tag_data_size != identity->tag_data_size) {
		ctag_mount_unload(mount);
		ctag_map_source_close(source);
		return -1;
	}
	mount->close_read_context = ctag_map_source_close_context;
	return 0;
}

int ctag_mount_hp2_file_verified_discover(ctag_mount *mount, arena_t *owner,
	const char *pack_path, const char *map_name,
	const char *resource_map_path, ctag_map_source *source,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context)
{
	return mount_file_verified_discover(mount, owner, NULL, pack_path,
		map_name, resource_map_path, source, backend, load_section,
		load_context);
}

int ctag_mount_hp2_file_verified_discover_with_bsp_catalog(
	ctag_mount *mount, arena_t *owner, arena_t *bsp_scratch,
	const char *pack_path, const char *map_name,
	const char *resource_map_path, ctag_map_source *source,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context)
{
	if (!bsp_scratch) return -1;
	return mount_file_verified_discover(mount, owner, bsp_scratch, pack_path,
		map_name, resource_map_path, source, backend, load_section,
		load_context);
}

int ctag_mount_hp2_file_discover_with_bsp_catalog(ctag_mount *mount,
	arena_t *owner, arena_t *bsp_scratch, const char *pack_path,
	const char *map_name, const char *resource_map_path,
	ctag_map_source *source, const ctag_mount_backend *backend,
	ctag_section_load_fn load_section, void *load_context)
{
	if (!source || ctag_map_source_open_any(source, resource_map_path))
		return -1;
	if (ctag_mount_hp2_discover_with_bsp_catalog(mount, owner, bsp_scratch,
		pack_path, map_name, source->reader.size, ctag_map_source_read,
		source, backend, load_section, load_context) != 0) {
		ctag_map_source_close(source);
		return -1;
	}
	mount->close_read_context = ctag_map_source_close_context;
	return 0;
}

int ctag_map_source_open(ctag_map_source *source, const char *path,
	uint32_t expected_file_length)
{
	if (!source) return -1;
	memset(source, 0, sizeof(*source));
	source->reader.descriptor = -1;
	if (file_reader_open(&source->reader, path) != 0) return -1;
	if (source->reader.size != expected_file_length) {
		file_reader_close(&source->reader);
		return -1;
	}
	source->active = 1;
	return 0;
}

int ctag_map_source_open_any(ctag_map_source *source, const char *path)
{
	if (!source || !path) return -1;
	memset(source, 0, sizeof(*source));
	source->reader.descriptor = -1;
	if (file_reader_open(&source->reader, path) != 0) return -1;
	if (source->reader.size == 0) {
		file_reader_close(&source->reader);
		return -1;
	}
	source->active = 1;
	return 0;
}

int ctag_map_source_read(void *context, int32_t tag_index,
	uint32_t file_offset, uint32_t size, void *buffer, int blocking)
{
	ctag_map_source *source = (ctag_map_source *)context;
	uint32_t offset = 0;
	(void)tag_index;
	(void)blocking;
	if (!source || !source->active) return 0;
	/* Keep optical reads bounded so the progress presentation can yield between
	 * IOP transactions instead of waiting for an entire large tag section. */
	while (offset < size) {
		size_t chunk = (size_t)(size - offset);
		if (chunk > 32768u) chunk = 32768u;
		if (file_reader_read_at(&source->reader, file_offset + offset,
			(uint8_t *)buffer + offset, chunk) != 0)
			return 0;
		offset += (uint32_t)chunk;
		hcu_loading_screen_file_read((uint32_t)chunk);
	}
	return 1;
}

void ctag_map_source_close(ctag_map_source *source)
{
	if (!source) return;
	file_reader_close(&source->reader);
	source->active = 0;
}

int ctag_map_source_sha256(ctag_map_source *source, uint8_t digest[32])
{
	/* Keep this fixed and stack-bounded, but large enough to avoid thousands
	 * of tiny FileXio RPC reads while verifying a retail cache on DVD. */
	uint8_t buffer[16384];
	return ctag_map_source_sha256_with_buffer(source, digest, buffer,
		sizeof(buffer));
}

int ctag_map_source_sha256_with_buffer(ctag_map_source *source,
	uint8_t digest[32], void *buffer, size_t buffer_size)
{
	sha256_context hash;
	uint32_t offset = 0;
	if (!source || !source->active || !digest || !buffer || !buffer_size)
		return 0;
	sha256_init(&hash);
	while (offset < source->reader.size) {
		size_t count = source->reader.size - offset;
		if (count > buffer_size) count = buffer_size;
		if (file_reader_read_at(&source->reader, offset, buffer, count) != 0)
			return 0;
		sha256_update(&hash, buffer, count);
		hcu_loading_screen_file_read((uint32_t)count);
		offset += (uint32_t)count;
	}
	sha256_final(&hash, digest);
	return 1;
}

int ctag_map_source_matches_sha256(ctag_map_source *source,
	const uint8_t expected_digest[32])
{
	uint8_t buffer[16384];
	return ctag_map_source_matches_sha256_with_buffer(source,
		expected_digest, buffer, sizeof(buffer));
}

int ctag_map_source_matches_sha256_with_buffer(ctag_map_source *source,
	const uint8_t expected_digest[32], void *buffer, size_t buffer_size)
{
	uint8_t actual[32];
	uint8_t difference = 0;
	unsigned i;
	if (!expected_digest || !ctag_map_source_sha256_with_buffer(source,
		actual, buffer, buffer_size)) return 0;
	for (i = 0; i < sizeof(actual); i++)
		difference |= actual[i] ^ expected_digest[i];
	return difference == 0;
}

void ctag_map_source_close_context(void *context)
{
	ctag_map_source_close((ctag_map_source *)context);
}
