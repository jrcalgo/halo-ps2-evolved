#include "stream/ctag_ps2_backend.h"

#include "halo_ps2_cache.h"

static int mount_ctag(void *context, const char *map_name,
	const uint8_t *payload, size_t payload_size, uint32_t tag_data_offset,
	uint32_t file_length, ctag_read_at_fn read_at, void *read_context)
{
	(void)context;
	return ps2_cache_mount_ctag_with_file_source(map_name, payload,
		payload_size, tag_data_offset, file_length, read_at, read_context);
}

static int mount_cbsp(void *context, const uint8_t *payload,
	size_t payload_size, uint32_t file_offset, uint32_t file_size)
{
	(void)context;
	return ps2_cache_mount_cbsp_for_extent(payload, payload_size,
		file_offset, file_size);
}

static void unmount_cbsp(void *context)
{
	(void)context;
	ps2_cache_unmount_cbsp();
}

static int register_cbsp_loader(void *context, ctag_bsp_load_fn load,
	ctag_bsp_release_fn release, void *loader_context)
{
	(void)context;
	return ps2_cache_set_bsp_loader(load, release, loader_context);
}

static void unmount_ctag(void *context)
{
	(void)context;
	ps2_cache_unmount_ctag();
}

const ctag_mount_backend *ctag_ps2_cache_backend(void)
{
	static const ctag_mount_backend backend = {
		NULL,
		mount_ctag,
		mount_cbsp,
		unmount_cbsp,
		register_cbsp_loader,
		unmount_ctag
	};
	return &backend;
}
