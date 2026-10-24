#ifndef HALO_STREAM_HCU_ASSET_PROFILE_H
#define HALO_STREAM_HCU_ASSET_PROFILE_H

#include <stddef.h>
#include <stdint.h>

enum { HCU_ASSET_CHUNK_CE = 1, HCU_ASSET_CHUNK_MEDIA = 2,
	HCU_ASSET_CHUNK_SOUND_META = 3, HCU_ASSET_PROFILE_MAX_CHUNKS = 65536 };
enum { HCU_ASSET_LIFETIME_MAP_UNLOAD = 1, HCU_ASSET_LIFETIME_REQUEST = 2 };
enum { HCU_ASSET_PROFILE_OK = 0, HCU_ASSET_PROFILE_E_ARGUMENT = -1,
	HCU_ASSET_PROFILE_E_FORMAT = -2, HCU_ASSET_PROFILE_E_PROFILE = -3,
	HCU_ASSET_PROFILE_E_BOUNDS = -4, HCU_ASSET_PROFILE_E_HASH = -5,
	HCU_ASSET_PROFILE_E_MEMORY = -6 };

typedef int (*hcu_asset_profile_read_at)(void *context, uint32_t offset,
	void *destination, uint32_t size);
typedef struct { uint32_t type, chunk_id, offset, size; uint8_t sha256[32]; } hcu_asset_chunk_view;
typedef struct {
	uint32_t profile_id;
	uint32_t total_bytes, chunk_count, directory_bytes;
	hcu_asset_profile_read_at read_at;
	void *reader_context;
	const uint8_t *memory_image;
} hcu_asset_profile_view;

/* Validate the whole envelope and every chunk hash before any live map teardown. */
int hcu_asset_profile_preflight_reader(hcu_asset_profile_read_at read_at,
	void *reader_context, uint32_t image_size,
	uint32_t expected_profile_id, hcu_asset_profile_view *view);
int hcu_asset_profile_preflight(const void *image, size_t image_size,
	uint32_t expected_profile_id, hcu_asset_profile_view *view);
int hcu_asset_profile_lookup(const hcu_asset_profile_view *view, uint32_t type,
	uint32_t chunk_id, hcu_asset_chunk_view *chunk);
/* Verify current backing bytes before copying a chunk into caller-owned storage. */
int hcu_asset_profile_read_chunk(const hcu_asset_profile_view *view,
	uint32_t type, uint32_t chunk_id, void *destination, uint32_t capacity);
int hcu_asset_profile_lifetime(uint32_t type, uint32_t *lifetime);
/* Capacity of one aligned decode target. The streamed directory is not a
 * resident allocation. Count the view and caller-owned source once separately. */
int hcu_asset_profile_accounting(const hcu_asset_profile_view *view,
	uint32_t type, uint32_t chunk_id, uint32_t *resident_bytes);

#endif
