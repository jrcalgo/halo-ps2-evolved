/* Transactional owner for a CTAG payload loaded from an HP2 pack. */
#ifndef HALO_CTAG_MOUNT_H
#define HALO_CTAG_MOUNT_H

#include "core/mem.h"
#include "stream/cbsp_catalog.h"
#include "stream/ctag_resource_index.h"

#include <stddef.h>
#include <stdint.h>

typedef int (*ctag_read_at_fn)(void *context, int32_t tag_index,
	uint32_t file_offset, uint32_t size, void *buffer, int blocking);
typedef uint8_t *(*ctag_section_load_fn)(void *context, arena_t *owner,
	const char *pack_path, const char *section_tag, size_t *raw_size,
	int optional);
typedef int (*ctag_bsp_load_fn)(void *context, uint32_t file_offset,
	uint32_t file_size);
typedef void (*ctag_bsp_release_fn)(void *context);

typedef struct {
	void *context;
	int (*mount)(void *context, const char *map_name,
		const uint8_t *payload, size_t payload_size,
		uint32_t tag_data_offset, uint32_t file_length,
		ctag_read_at_fn read_at, void *read_context);
	int (*mount_bsp)(void *context, const uint8_t *payload,
		size_t payload_size, uint32_t file_offset, uint32_t file_size);
	void (*unmount_bsp)(void *context);
	int (*register_bsp_loader)(void *context, ctag_bsp_load_fn load,
		ctag_bsp_release_fn release, void *loader_context);
	void (*unmount)(void *context);
} ctag_mount_backend;

typedef struct {
	arena_t *owner;
	size_t arena_mark;
	const ctag_mount_backend *backend;
	void *read_context;
	void (*close_read_context)(void *context);
	ctag_read_at_fn source_read;
	const uint8_t *payload;
	size_t payload_size;
	const uint8_t *resource_index_bytes;
	size_t resource_index_size;
	ctag_resource_index resource_index;
	cbsp_catalog bsp_catalog;
	arena_t *bsp_scratch;
	size_t bsp_scratch_mark;
	ctag_section_load_fn load_section;
	void *load_context;
	const char *pack_path;
	int bsp_active;
	int active;
} ctag_mount;

/* Initialize a fresh handle before its first use. */
void ctag_mount_init(ctag_mount *mount);

/* Decode the HP2 CTAG section into owner and mount it. `owner` must outlive
 * the map. `backend`, `read_at`, and `read_context` must remain valid until
 * ctag_mount_unload(). The section loader must return its decoded payload
 * inside `owner`. A backend mount failure must leave its backend unmounted.
 * Only one owner may be active because the PS2 cache adapter is a singleton.
 * Failure restores the arena mark and leaves the backend unmounted. */
int ctag_mount_hp2(ctag_mount *mount, arena_t *owner, const char *pack_path,
	const char *map_name, uint32_t tag_data_offset, uint32_t tag_data_size,
	uint32_t file_length,
	ctag_read_at_fn read_at, void *read_context,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context);

/* As above, but derive the original tag extent from the validated CRNG header.
 * The supplied file length must still match CRNG and the open source map. */
int ctag_mount_hp2_discover(ctag_mount *mount, arena_t *owner,
	const char *pack_path, const char *map_name, uint32_t file_length,
	ctag_read_at_fn read_at, void *read_context,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context);

/* Mount CTAG/CRNG and a compact CBIX directory. Each BSP is loaded lazily by
 * exact retail extent into `bsp_scratch`; only one encoded CBSP is resident at
 * a time, matching CE's single active BSP cache. */
int ctag_mount_hp2_with_bsp_catalog(ctag_mount *mount, arena_t *owner,
	arena_t *bsp_scratch, const char *pack_path, const char *map_name,
	uint32_t tag_data_offset, uint32_t tag_data_size, uint32_t file_length,
	ctag_read_at_fn read_at, void *read_context,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context);

/* Discovery variant for sources where the map file is opened first and CRNG
 * supplies the validated retail tag extent. */
int ctag_mount_hp2_discover_with_bsp_catalog(ctag_mount *mount,
	arena_t *owner, arena_t *bsp_scratch, const char *pack_path,
	const char *map_name, uint32_t file_length,
	ctag_read_at_fn read_at, void *read_context,
	const ctag_mount_backend *backend, ctag_section_load_fn load_section,
	void *load_context);

/* Unmount first (so CE releases every pointer into payload), then restore the
 * arena to its pre-load mark. Safe to call on an initialized inactive handle. */
void ctag_mount_unload(ctag_mount *mount);

#endif
