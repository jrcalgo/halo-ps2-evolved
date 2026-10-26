#ifndef HALO_STREAM_HCU_ASSET_PROFILE_H
#define HALO_STREAM_HCU_ASSET_PROFILE_H

#include <stddef.h>
#include <stdint.h>

enum { HCU_ASSET_CHUNK_CE = 1, HCU_ASSET_CHUNK_MEDIA = 2,
	HCU_ASSET_CHUNK_SOUND_META = 3, HCU_ASSET_PROFILE_MAX_CHUNKS = 65536 };
/* C3 render chunks (opt-in producer: tools/hcu_render_media.py). Keyed by the
 * structure BSP index: BSPS v2 section, TEXS shader pack and LMn lightmap pages. */
enum { HCU_ASSET_CHUNK_BSPS = 4, HCU_ASSET_CHUNK_TEXS = 5,
	HCU_ASSET_CHUNK_LIGHTMAP = 6 };
/* Independently decoded MEDIA resources have a persistent chunk cap. This is
 * separate from HP2's 64 KiB LZ4 history window. */
#define HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES 65536u
enum { HCU_ASSET_LIFETIME_MAP_UNLOAD = 1, HCU_ASSET_LIFETIME_REQUEST = 2 };
enum { HCU_ASSET_PROFILE_OK = 0, HCU_ASSET_PROFILE_E_ARGUMENT = -1,
	HCU_ASSET_PROFILE_E_FORMAT = -2, HCU_ASSET_PROFILE_E_PROFILE = -3,
	HCU_ASSET_PROFILE_E_BOUNDS = -4, HCU_ASSET_PROFILE_E_HASH = -5,
	HCU_ASSET_PROFILE_E_MEMORY = -6, HCU_ASSET_PROFILE_E_BUSY = -7,
	HCU_ASSET_PROFILE_E_STATE = -8 };

typedef int (*hcu_asset_profile_read_at)(void *context, uint32_t offset,
	void *destination, uint32_t size);
typedef struct { uint32_t type, chunk_id, offset, size, first_segment, segment_count; uint8_t sha256[32]; } hcu_asset_chunk_view;
typedef struct {
	uint32_t profile_id;
	uint32_t total_bytes, chunk_count, directory_bytes, version, record_bytes;
	hcu_asset_profile_read_at read_at;
	void *reader_context;
	const uint8_t *memory_image;
} hcu_asset_profile_view;

/* Validate the whole envelope and every chunk hash before any live map teardown. */
int hcu_asset_profile_preflight_reader(hcu_asset_profile_read_at read_at,
	void *reader_context, uint32_t image_size,
	uint32_t expected_profile_id, hcu_asset_profile_view *view);
int hcu_asset_profile_preflight_reader_scratch(hcu_asset_profile_read_at read_at,
	void *reader_context, uint32_t image_size, uint32_t expected_profile_id,
	hcu_asset_profile_view *view, uint8_t *scratch, uint32_t scratch_bytes);
int hcu_asset_profile_preflight(const void *image, size_t image_size,
	uint32_t expected_profile_id, hcu_asset_profile_view *view);
int hcu_asset_profile_lookup(const hcu_asset_profile_view *view, uint32_t type,
	uint32_t chunk_id, hcu_asset_chunk_view *chunk);
/* Verify current backing bytes before copying a chunk into caller-owned storage. */
int hcu_asset_profile_read_chunk(const hcu_asset_profile_view *view,
	uint32_t type, uint32_t chunk_id, void *destination, uint32_t capacity);
/* Read and verify a chunk in one sequential payload pass. After lookup and
 * capacity validation, any read, metadata, or hash failure zeros chunk size
 * bytes. Argument, lookup, and capacity errors leave destination untouched. */
int hcu_asset_profile_read_chunk_staged(const hcu_asset_profile_view *view,
	uint32_t type, uint32_t chunk_id, void *destination, uint32_t capacity);
typedef struct {
	uint32_t payload_read_calls, payload_read_bytes;
	uint32_t read_cycles, hash_cycles, metadata_cycles;
} hcu_asset_profile_staged_stats;
int hcu_asset_profile_read_chunk_staged_profiled(const hcu_asset_profile_view *view,
	uint32_t type, uint32_t chunk_id, void *destination, uint32_t capacity,
	hcu_asset_profile_staged_stats *stats);
/* Read a bounded logical byte range from its verified segments. Callers must
 * verify the returned range's full logical checksum before publishing it. */
int hcu_asset_profile_read_range(const hcu_asset_profile_view *view,
	uint32_t type, uint32_t chunk_id, uint32_t logical_offset,
	void *destination, uint32_t size);
int hcu_asset_profile_lifetime(uint32_t type, uint32_t *lifetime);
/* Chunk-kind table. Kinds 1 and 3 are unkeyed (id 0); kinds 2, 4, 5 and 6 are
 * keyed by chunk id. Unknown kinds are refused by every format check. */
typedef struct { uint32_t type; const char *name; uint32_t lifetime; int keyed; } hcu_asset_chunk_kind;
int hcu_asset_chunk_kind_lookup(uint32_t type, hcu_asset_chunk_kind *kind);
/* Nonzero when (type, chunk_id) is a known kind with a legal id. */
int hcu_asset_chunk_id_valid(uint32_t type, uint32_t chunk_id);
/* Capacity of one aligned decode target. The streamed directory is not a
 * resident allocation. Count the view and caller-owned source once separately. */
int hcu_asset_profile_accounting(const hcu_asset_profile_view *view,
	uint32_t type, uint32_t chunk_id, uint32_t *resident_bytes);

/* Segment bounds of one verified HCP2 logical chunk: the stored size and the
 * logical offset of a segment, read from its own directory row. */
int hcu_asset_profile_segment_info(const hcu_asset_profile_view *view,
	uint32_t type, uint32_t chunk_id, uint32_t segment,
	uint32_t *bytes, uint32_t *logical_offset);
/* Read one segment and verify its own SHA-256 before returning. The segment is
 * at most HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES, and dst is zeroed on failure. */
int hcu_asset_profile_read_segment(const hcu_asset_profile_view *view,
	uint32_t type, uint32_t chunk_id, uint32_t segment, void *destination, uint32_t capacity);

/* Bounded residency table for verified HCP2 segments. The residency unit is one
 * segment (logical chunk, segment index), so a resident buffer never exceeds
 * HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES. Each resident segment is backed by
 * caller storage. Three independent counts keep bytes alive: CE pins
 * (tag/BSP/source readers), DMA/GS leases (renderer uploads), and gameplay
 * references (live pointers into the segment). Eviction is refused while any
 * count is nonzero, and the storage is returned only on success. The table has
 * a fixed slot count; a pin that finds no free slot is refused and counted. */
typedef struct {
	uint32_t type, chunk_id, segment;
	uint32_t pin_count, lease_count, gameplay_refs;
	uint32_t bytes, resident;
	void *storage;
} hcu_asset_residency_entry;
typedef struct {
	hcu_asset_residency_entry *entries;
	uint32_t capacity, count;
	uint32_t resident_bytes, resident_high_water;
	uint32_t evictions, refused_evictions, refused_pins, verify_failures;
} hcu_asset_residency;

int hcu_asset_residency_init(hcu_asset_residency *table,
	hcu_asset_residency_entry *entries, uint32_t capacity);
/* Verify and copy one segment into storage on first pin; later pins only count. */
int hcu_asset_residency_pin(hcu_asset_residency *table,
	const hcu_asset_profile_view *view, uint32_t type, uint32_t chunk_id, uint32_t segment,
	void *storage, uint32_t capacity);
int hcu_asset_residency_unpin(hcu_asset_residency *table, uint32_t type, uint32_t chunk_id, uint32_t segment);
int hcu_asset_residency_lease(hcu_asset_residency *table, uint32_t type, uint32_t chunk_id, uint32_t segment);
int hcu_asset_residency_release_lease(hcu_asset_residency *table, uint32_t type, uint32_t chunk_id, uint32_t segment);
int hcu_asset_residency_gameplay_ref(hcu_asset_residency *table, uint32_t type, uint32_t chunk_id, uint32_t segment, int delta);
/* On success returns the released storage pointer (caller may free it). Busy
 * segments return HCU_ASSET_PROFILE_E_BUSY and stay resident. */
int hcu_asset_residency_evict(hcu_asset_residency *table, uint32_t type,
	uint32_t chunk_id, uint32_t segment, void **storage_out);
int hcu_asset_residency_state(const hcu_asset_residency *table, uint32_t type,
	uint32_t chunk_id, uint32_t segment, const hcu_asset_residency_entry **entry);

#endif
