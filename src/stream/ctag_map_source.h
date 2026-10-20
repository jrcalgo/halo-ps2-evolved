#ifndef HALO_CTAG_MAP_SOURCE_H
#define HALO_CTAG_MAP_SOURCE_H

#include "stream/ctag_mount.h"
#include "stream/file.h"
#include "stream/hmap.h"

typedef struct {
	file_reader_t reader;
	int active;
} ctag_map_source;

/* Keep the decompressed retail map open for the lifetime of its mounted CTAG
 * image. The exact size must match the CRNG metadata. */
int ctag_map_source_open(ctag_map_source *source, const char *path,
	uint32_t expected_file_length);
/* Open a nonempty source map and use its actual measured length for CRNG
 * validation; metadata still has to agree exactly with the packaged index. */
int ctag_map_source_open_any(ctag_map_source *source, const char *path);
/* Stream the complete opened map through bounded caller-owned scratch. The
 * default wrapper uses a 16 KiB stack buffer; startup can use its arena. */
int ctag_map_source_sha256(ctag_map_source *source, uint8_t digest[32]);
int ctag_map_source_sha256_with_buffer(ctag_map_source *source,
	uint8_t digest[32], void *buffer, size_t buffer_size);
int ctag_map_source_matches_sha256(ctag_map_source *source,
	const uint8_t expected_digest[32]);
int ctag_map_source_matches_sha256_with_buffer(ctag_map_source *source,
	const uint8_t expected_digest[32], void *buffer, size_t buffer_size);
/* Close callback suitable for ctag_mount's post-unmount source cleanup. */
void ctag_map_source_close_context(void *context);
int ctag_map_source_read(void *context, int32_t tag_index,
	uint32_t file_offset, uint32_t size, void *buffer, int blocking);
void ctag_map_source_close(ctag_map_source *source);

/* Open the exact-size retail resource map, mount CTAG/CRNG from HP2, and tie
 * source lifetime to the mount so unload closes it after cache unpublication. */
int ctag_mount_hp2_file(ctag_mount *mount, arena_t *owner,
	const char *pack_path, const char *map_name,
	uint32_t tag_data_offset, uint32_t tag_data_size, uint32_t file_length,
	const char *resource_map_path, ctag_map_source *source,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context);

int ctag_mount_hp2_file_with_bsp_catalog(ctag_mount *mount, arena_t *owner,
	arena_t *bsp_scratch, const char *pack_path, const char *map_name,
	uint32_t tag_data_offset, uint32_t tag_data_size, uint32_t file_length,
	const char *resource_map_path, ctag_map_source *source,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context);

/* Derive retail file and tag extents from the opened map plus validated CRNG. */
int ctag_mount_hp2_file_discover(ctag_mount *mount, arena_t *owner,
	const char *pack_path, const char *map_name,
	const char *resource_map_path, ctag_map_source *source,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context);

/* Preflight HMAP v1 identity (canonical leaf, exact length and full SHA-256)
 * before loading/mounting CTAG and CRNG. Failed preflight releases both the
 * source descriptor and its temporary arena span. */
int ctag_mount_hp2_file_verified_discover(ctag_mount *mount, arena_t *owner,
	const char *pack_path, const char *map_name,
	const char *resource_map_path, ctag_map_source *source,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context);
int ctag_mount_hp2_file_verified_discover_with_bsp_catalog(
	ctag_mount *mount, arena_t *owner, arena_t *bsp_scratch,
	const char *pack_path, const char *map_name,
	const char *resource_map_path, ctag_map_source *source,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context);

/* Commit the mount after an external non-mutating preflight has already
 * opened, length-checked and SHA-256-verified `source` against `identity`.
 * On success, mount owns source closure at unmount. */
int ctag_mount_hp2_verified_source_discover(ctag_mount *mount,
	arena_t *owner, arena_t *bsp_scratch, const char *pack_path,
	const char *map_name, ctag_map_source *source,
	const hmap_identity *identity, const ctag_mount_backend *backend,
	ctag_section_load_fn load_section, void *load_context);

/* Production-oriented discovery path: open the actual map, validate its
 * length against CRNG, derive the tag extent, then attach the BSP catalog. */
int ctag_mount_hp2_file_discover_with_bsp_catalog(ctag_mount *mount,
	arena_t *owner, arena_t *bsp_scratch, const char *pack_path,
	const char *map_name, const char *resource_map_path,
	ctag_map_source *source, const ctag_mount_backend *backend,
	ctag_section_load_fn load_section, void *load_context);

#endif
