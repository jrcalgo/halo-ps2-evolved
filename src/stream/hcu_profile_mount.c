#include "stream/hcu_profile_mount.h"

#include <limits.h>
#include <string.h>
#include "ps2_ctag.h"
#include "stream/sha256.h"

#include <stdio.h>

#define HCU_PROFILE_MOUNT_SCRATCH_MIN 512u
#define HCU_PROFILE_MOUNT_MAX_BSPS 64u
#define HCU_PROFILE_MOUNT_MAX_RESOURCES 65536u

typedef struct {
	const hcu_asset_profile_view *profile;
	hcu_asset_chunk_view chunk;
	/* Optional read-ahead window: the CE tag validator reads in 256-byte steps and every
	 * read_range is a directory lookup plus file-bridge RPCs. */
	uint8_t *window;
	size_t window_cap, window_off, window_len;
} profile_chunk_reader_context;

static int add_size_ok(size_t left, size_t right, size_t *sum)
{
	if (right > SIZE_MAX - left) return 0;
	*sum = left + right;
	return 1;
}

static int span_overlap(const void *left, size_t left_size,
	const void *right, size_t right_size)
{
	uintptr_t a = (uintptr_t)left, b = (uintptr_t)right;
	uintptr_t ae, be;
	if (!left_size || !right_size) return 0;
	if (left_size > UINTPTR_MAX - a || right_size > UINTPTR_MAX - b) return 1;
	ae = a + left_size; be = b + right_size;
	return a < be && b < ae;
}

static int chunk_reader(void *context, size_t offset,
	uint8_t *destination, size_t size)
{
	profile_chunk_reader_context *reader =	(profile_chunk_reader_context *)context;
	size_t end;
	if (!reader || !reader->profile || !add_size_ok(offset, size, &end) ||
		end > reader->chunk.size || offset > UINT32_MAX || size > UINT32_MAX)
		return -1;
	if (reader->window && size <= reader->window_cap) {
		if (!(reader->window_len && offset >= reader->window_off &&
			end <= reader->window_off + reader->window_len)) {
			size_t fill = reader->chunk.size - offset;
			if (fill > reader->window_cap) fill = reader->window_cap;
			reader->window_len = 0;
			if (hcu_asset_profile_read_range(reader->profile, reader->chunk.type,
				reader->chunk.chunk_id, (uint32_t)offset, reader->window, (uint32_t)fill) !=
				HCU_ASSET_PROFILE_OK) return -1;
			reader->window_off = offset;
			reader->window_len = fill;
		}
		memcpy(destination, reader->window + (offset - reader->window_off), size);
		return 0;
	}
	return hcu_asset_profile_read_range(reader->profile, reader->chunk.type,
		reader->chunk.chunk_id, (uint32_t)offset, destination, (uint32_t)size) ==
		HCU_ASSET_PROFILE_OK ? 0 : -1;
}

static uint32_t read_u32_le(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
		(uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

static void sha_bytes(const void *bytes, size_t size, uint8_t digest[32])
{
	sha256_context sha;
	sha256_init(&sha);
	if (size) sha256_update(&sha, bytes, size);
	sha256_final(&sha, digest);
}

static int digest_profile_chunk(const hcu_asset_profile_view *profile,
	const hcu_asset_chunk_view *chunk, void *scratch, size_t scratch_size)
{
	sha256_context sha;
	uint8_t digest[32];
	uint32_t offset = 0;
	if (!profile || !chunk || !scratch || !scratch_size) return 0;
	sha256_init(&sha);
	while (offset < chunk->size) {
		uint32_t take = chunk->size - offset;
		if (take > scratch_size) take = (uint32_t)scratch_size;
		if (take > HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES)
			take = HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES;
		if (hcu_asset_profile_read_range(profile, chunk->type, chunk->chunk_id,
			offset, scratch, take) != HCU_ASSET_PROFILE_OK) return 0;
		sha256_update(&sha, scratch, take);
		offset += take;
	}
	sha256_final(&sha, digest);
	return memcmp(digest, chunk->sha256, sizeof(digest)) == 0;
}

static void digest_catalog_bsp(const hcu_map_bsp_entry *rows, uint16_t count,
	uint8_t digest[32])
{
	sha256_context sha;
	uint16_t i;
	sha256_init(&sha);
	for (i = 0; i < count; ++i) {
		sha256_update(&sha, &rows[i].file_offset, sizeof(rows[i].file_offset));
		sha256_update(&sha, &rows[i].file_size, sizeof(rows[i].file_size));
		sha256_update(&sha, rows[i].section_tag, sizeof(rows[i].section_tag));
		sha256_update(&sha, &rows[i].scenario_bsp_path,
			sizeof(rows[i].scenario_bsp_path));
	}
	sha256_final(&sha, digest);
}

static int profile_view_matches(const hcu_asset_profile_view *a,
	const hcu_asset_profile_view *b)
{
	return a && b && a->profile_id == b->profile_id &&
		a->total_bytes == b->total_bytes && a->chunk_count == b->chunk_count &&
		a->version == b->version && a->record_bytes == b->record_bytes &&
		a->directory_bytes == b->directory_bytes && a->read_at == b->read_at &&
		a->reader_context == b->reader_context && a->memory_image == b->memory_image;
}

static int prepared_inputs_match(const hcu_profile_mount *mount)
{
	uint8_t digest[32];
	if (!mount || !mount->profile || !mount->catalog_entry ||
		!profile_view_matches(mount->profile, &mount->profile_snapshot) ||
		memcmp(&mount->catalog_entry->identity, &mount->source_identity_snapshot,
			sizeof(mount->source_identity_snapshot)) != 0 ||
		mount->catalog_entry->bsp_catalog != mount->catalog_bsp ||
		mount->catalog_entry->bsp_count != mount->catalog_bsp_count)
		return 0;
	if (mount->catalog_bsp_count) {
		digest_catalog_bsp(mount->catalog_bsp, mount->catalog_bsp_count, digest);
		if (memcmp(digest, mount->catalog_bsp_sha256, sizeof(digest))) return 0;
	}
	if (mount->cbsp_binding_count) {
		sha_bytes(mount->cbsp_bindings,
			(size_t)mount->cbsp_binding_count * sizeof(*mount->cbsp_bindings), digest);
		if (memcmp(digest, mount->cbsp_bindings_sha256, sizeof(digest))) return 0;
	}
	if (mount->resource_range_count) {
		sha_bytes(mount->resource_ranges,
			(size_t)mount->resource_range_count * sizeof(*mount->resource_ranges), digest);
		if (memcmp(digest, mount->resource_ranges_sha256, sizeof(digest))) return 0;
	}
	return 1;
}

void hcu_profile_mount_init(hcu_profile_mount *mount)
{
	if (mount) memset(mount, 0, sizeof(*mount));
}

int hcu_profile_mount_bind_residency(hcu_profile_mount *mount,
	hcu_asset_residency_entry *entries, uint32_t entry_capacity,
	void *arena, size_t arena_bytes)
{
	if (!mount || !entries || !entry_capacity || !arena ||
		arena_bytes < HCU_PROFILE_MOUNT_RESIDENCY_SEGMENT_BYTES ||
		((uintptr_t)arena & 15u))
		return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (mount->prepared || mount->active || mount->backend_mounted || mount->callbacks_active)
		return HCU_PROFILE_MOUNT_E_BUSY;
	mount->residency_entries = entries;
	mount->residency_entry_capacity = entry_capacity;
	mount->residency_arena = (uint8_t *)arena;
	mount->residency_arena_bytes = arena_bytes;
	mount->residency_bound = 1;
	return HCU_PROFILE_MOUNT_OK;
}

int hcu_profile_mount_inputs_match(const hcu_profile_mount *mount)
{
	return mount && mount->prepared && !mount->callbacks_active &&
		prepared_inputs_match(mount);
}

static void profile_mount_residency_stats(const hcu_profile_mount *mount,
	hcu_profile_residency_stats *stats)
{
	memset(stats, 0, sizeof(*stats));
	if (!mount || !mount->prepared || !mount->residency_bound) return;
	stats->bound = 1;
	stats->capacity_bytes = mount->residency_arena_bytes;
	stats->current_bytes = mount->residency.resident_bytes;
	stats->high_water_bytes = mount->residency.resident_high_water;
	stats->evictions = mount->residency.evictions;
	stats->refused_evictions = mount->residency.refused_evictions;
	stats->refused_pins = mount->residency.refused_pins;
	stats->verify_failures = mount->residency.verify_failures;
}

int hcu_profile_mount_residency_snapshot(const hcu_profile_mount *mount,
	hcu_profile_residency_stats *stats)
{
	if (!mount || !stats) return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (!mount->prepared || !mount->residency_bound)
		return HCU_PROFILE_MOUNT_E_STATE;
	profile_mount_residency_stats(mount, stats);
	return HCU_PROFILE_MOUNT_OK;
}

static int resource_range_valid(const hmap_identity *identity,
	const hcu_map_catalog_entry *catalog,
	const hcu_profile_resource_range *range)
{
	uint64_t end, tag_end;
	uint16_t i;
	if (!range || range->output_datum > INT32_MAX || !range->size ||
		range->source_offset > identity->file_length ||
		range->size > identity->file_length - range->source_offset)
		return 0;
	end = (uint64_t)range->source_offset + range->size;
	tag_end = (uint64_t)identity->tag_data_offset + identity->tag_data_size;
	if ((uint64_t)range->source_offset < tag_end &&
		(uint64_t)identity->tag_data_offset < end)
		return 0;
	for (i = 0; i < catalog->bsp_count; ++i) {
		uint64_t bsp_end = (uint64_t)catalog->bsp_catalog[i].file_offset +
			catalog->bsp_catalog[i].file_size;
		if ((uint64_t)range->source_offset < bsp_end &&
			(uint64_t)catalog->bsp_catalog[i].file_offset < end)
			return 0;
	}
	return 1;
}

static int cbsp_binding_match_catalog(const hcu_profile_cbsp_binding *binding,
	const hcu_map_catalog_entry *catalog, const hmap_identity *identity)
{
	uint16_t i;
	if (memcmp(binding->source_map_sha256, identity->source_sha256, 32)) return 0;
	for (i = 0; i < catalog->bsp_count; ++i) {
		const hcu_map_bsp_entry *row = &catalog->bsp_catalog[i];
		if (row->file_offset == binding->source_file_offset &&
			row->file_size == binding->source_file_size)
			return 1;
	}
	return 0;
}

int hcu_profile_mount_prepare(hcu_profile_mount *mount,
	const hcu_asset_profile_view *profile, uint32_t expected_profile_id,
	const hcu_map_catalog_entry *catalog_entry,
	const hcu_profile_cbsp_binding *cbsp_bindings, uint16_t cbsp_binding_count,
	const hcu_profile_resource_range *resource_ranges, uint32_t resource_range_count,
	hcu_profile_source_read_fn source_read, void *source_context,
	const ctag_mount_backend *backend, uint32_t maximum_tag_image_bytes,
	void *relocation_storage, size_t relocation_storage_bytes,
	void *stream_scratch, size_t stream_scratch_bytes)
{
	hcu_profile_mount candidate;
	hcu_asset_chunk_view ce_chunk;
	profile_chunk_reader_context ce_reader;
	ctag_stream_info ctag_info;
	ps2_ctag_stream_info ps2_info;
	uint8_t ctag_header[52];
	uint8_t digest[32];
	uint8_t zero_digest[32] = { 0 };
	size_t relocation_bytes;
	uint32_t i, j;
	uint32_t max_relocations;
	if (!mount || !profile || !catalog_entry || !backend || !backend->mount_stream ||
		!backend->register_ctag_visitor || !backend->unmount ||
		(!backend->register_bsp_visitor && catalog_entry->bsp_count) ||
		!expected_profile_id || profile->profile_id != expected_profile_id ||
		(!profile->memory_image && !profile->read_at) || !maximum_tag_image_bytes ||
		!relocation_storage || !relocation_storage_bytes || !stream_scratch ||
		stream_scratch_bytes < HCU_PROFILE_MOUNT_SCRATCH_MIN ||
		((uintptr_t)relocation_storage & 3u) || ((uintptr_t)stream_scratch & 15u) ||
		(!cbsp_bindings && cbsp_binding_count) ||
		(!resource_ranges && resource_range_count) ||
		resource_range_count > HCU_PROFILE_MOUNT_MAX_RESOURCES ||
		catalog_entry->bsp_count > HCU_PROFILE_MOUNT_MAX_BSPS ||
		cbsp_binding_count != catalog_entry->bsp_count)
		return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (mount->prepared || mount->active || mount->backend_mounted || mount->callbacks_active)
		return HCU_PROFILE_MOUNT_E_BUSY;
	if (!catalog_entry->identity.map_name[0] ||
		!memchr(catalog_entry->identity.map_name, '\0', sizeof(catalog_entry->identity.map_name)) ||
		!catalog_entry->identity.file_length ||
		catalog_entry->identity.tag_data_offset > catalog_entry->identity.file_length ||
		catalog_entry->identity.tag_data_size > catalog_entry->identity.file_length -
			catalog_entry->identity.tag_data_offset ||
		(catalog_entry->bsp_count && !catalog_entry->bsp_catalog))
		return HCU_PROFILE_MOUNT_E_IDENTITY;
	if (profile->memory_image &&
		(span_overlap(relocation_storage, relocation_storage_bytes, profile->memory_image,
			profile->total_bytes) || span_overlap(stream_scratch, stream_scratch_bytes,
			profile->memory_image, profile->total_bytes)))
		return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (span_overlap(relocation_storage, relocation_storage_bytes,
		stream_scratch, stream_scratch_bytes))
		return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (hcu_asset_profile_lookup(profile, HCU_ASSET_CHUNK_CE, 0, &ce_chunk) !=
		HCU_ASSET_PROFILE_OK || !ce_chunk.size ||
		!digest_profile_chunk(profile, &ce_chunk, stream_scratch, stream_scratch_bytes))
		return HCU_PROFILE_MOUNT_E_CHUNK;
	if (!cbsp_bindings && cbsp_binding_count) return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (cbsp_binding_count) {
		for (i = 0; i < cbsp_binding_count; ++i) {
			hcu_asset_chunk_view media_chunk;
			uint64_t end = (uint64_t)cbsp_bindings[i].source_file_offset +
				cbsp_bindings[i].source_file_size;
			if (!cbsp_bindings[i].source_file_size ||
				end > catalog_entry->identity.file_length ||
				!cbsp_binding_match_catalog(&cbsp_bindings[i], catalog_entry,
					&catalog_entry->identity) ||
				!memcmp(cbsp_bindings[i].expected_chunk_sha256, zero_digest, 32) ||
				hcu_asset_profile_lookup(profile, HCU_ASSET_CHUNK_MEDIA,
					cbsp_bindings[i].media_chunk_id, &media_chunk) != HCU_ASSET_PROFILE_OK ||
				memcmp(media_chunk.sha256, cbsp_bindings[i].expected_chunk_sha256, 32) ||
				!digest_profile_chunk(profile, &media_chunk, stream_scratch, stream_scratch_bytes))
				return HCU_PROFILE_MOUNT_E_CHUNK;
			for (j = 0; j < i; ++j)
				if (cbsp_bindings[j].source_file_offset == cbsp_bindings[i].source_file_offset ||
					cbsp_bindings[j].media_chunk_id == cbsp_bindings[i].media_chunk_id)
					return HCU_PROFILE_MOUNT_E_IDENTITY;
		}
		sha_bytes(cbsp_bindings,
			(size_t)cbsp_binding_count * sizeof(*cbsp_bindings), digest);
	} else {
		sha_bytes(NULL, 0, digest);
	}
	if (resource_range_count) {
		for (i = 0; i < resource_range_count; ++i) {
			if (!resource_range_valid(&catalog_entry->identity, catalog_entry,
				&resource_ranges[i])) return HCU_PROFILE_MOUNT_E_RESOURCE;
			for (j = 0; j < i; ++j)
				if (resource_ranges[j].output_datum == resource_ranges[i].output_datum &&
					(uint64_t)resource_ranges[i].source_offset <
						(uint64_t)resource_ranges[j].source_offset + resource_ranges[j].size &&
					(uint64_t)resource_ranges[j].source_offset <
						(uint64_t)resource_ranges[i].source_offset + resource_ranges[i].size)
					return HCU_PROFILE_MOUNT_E_RESOURCE;
		}
	}
	if (resource_range_count)
		sha_bytes(resource_ranges, (size_t)resource_range_count * sizeof(*resource_ranges),
			digest);
	else sha_bytes(NULL, 0, digest);
	if (catalog_entry->bsp_count) {
		for (i = 0; i < catalog_entry->bsp_count; ++i) {
			uint64_t end = (uint64_t)catalog_entry->bsp_catalog[i].file_offset +
				catalog_entry->bsp_catalog[i].file_size;
			if (!catalog_entry->bsp_catalog[i].file_size ||
				end > catalog_entry->identity.file_length ||
				((uint64_t)catalog_entry->bsp_catalog[i].file_offset <
					(uint64_t)catalog_entry->identity.tag_data_offset +
					catalog_entry->identity.tag_data_size &&
				(uint64_t)catalog_entry->identity.tag_data_offset < end))
				return HCU_PROFILE_MOUNT_E_IDENTITY;
		}
	}
	if (ce_chunk.size < 52u || !relocation_storage_bytes ||
		relocation_storage_bytes / 4u == 0)
		return HCU_PROFILE_MOUNT_E_CAPACITY;
	max_relocations = relocation_storage_bytes / 4u > UINT32_MAX ?
		UINT32_MAX : (uint32_t)(relocation_storage_bytes / 4u);
	memset(&ctag_info, 0, sizeof(ctag_info));
	memset(&ps2_info, 0, sizeof(ps2_info));
	memset(&ce_reader, 0, sizeof(ce_reader));
	ce_reader.profile = profile;
	ce_reader.chunk = ce_chunk;
	ce_reader.window = (uint8_t *)stream_scratch;
	ce_reader.window_cap = stream_scratch_bytes < HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES ?
		stream_scratch_bytes : HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES;
	if (ce_chunk.size < sizeof(ctag_header) ||
		chunk_reader(&ce_reader, 0, ctag_header, sizeof(ctag_header)) != 0)
		return HCU_PROFILE_MOUNT_E_CTAG;
	if (read_u32_le(ctag_header + 12) > maximum_tag_image_bytes ||
		read_u32_le(ctag_header + 16) > relocation_storage_bytes / 4u)
		return HCU_PROFILE_MOUNT_E_CAPACITY;
	if (ps2_ctag_validate_stream(chunk_reader, &ce_reader, ce_chunk.size,
		(uint8_t *)relocation_storage, relocation_storage_bytes,
		maximum_tag_image_bytes, max_relocations,
		&ps2_info) != PS2_CTAG_OK)
		return HCU_PROFILE_MOUNT_E_CTAG;
	ctag_info.image_size = ps2_info.image_size;
	ctag_info.relocation_count = ps2_info.relocation_count;
	ctag_info.scenario_tag_index = ps2_info.scenario_tag_index;
	relocation_bytes = (size_t)ctag_info.relocation_count * 4u;
	if (!ctag_info.relocation_count || relocation_bytes > relocation_storage_bytes ||
		ctag_info.image_size > catalog_entry->identity.tag_data_size ||
		ctag_info.image_size > catalog_entry->identity.file_length -
			catalog_entry->identity.tag_data_offset)
		return HCU_PROFILE_MOUNT_E_CAPACITY;
	memset(&candidate, 0, sizeof(candidate));
	candidate.profile = profile;
	candidate.profile_snapshot = *profile;
	candidate.catalog_entry = catalog_entry;
	candidate.source_identity_snapshot = catalog_entry->identity;
	candidate.catalog_bsp = catalog_entry->bsp_catalog;
	candidate.catalog_bsp_count = catalog_entry->bsp_count;
	candidate.cbsp_bindings = cbsp_bindings;
	candidate.cbsp_binding_count = cbsp_binding_count;
	memcpy(candidate.cbsp_bindings_sha256, digest, 32);
	candidate.resource_ranges = resource_ranges;
	candidate.resource_range_count = resource_range_count;
	/* Recompute the two independent table pins after their validation passes. */
	if (cbsp_binding_count)
		sha_bytes(cbsp_bindings, (size_t)cbsp_binding_count * sizeof(*cbsp_bindings),
			candidate.cbsp_bindings_sha256);
	else sha_bytes(NULL, 0, candidate.cbsp_bindings_sha256);
	if (resource_range_count)
		sha_bytes(resource_ranges, (size_t)resource_range_count * sizeof(*resource_ranges),
			candidate.resource_ranges_sha256);
	else sha_bytes(NULL, 0, candidate.resource_ranges_sha256);
	if (catalog_entry->bsp_count)
		digest_catalog_bsp(catalog_entry->bsp_catalog, catalog_entry->bsp_count,
			candidate.catalog_bsp_sha256);
	candidate.source_read = source_read;
	candidate.source_context = source_context;
	candidate.backend = *backend;
	candidate.ctag_info.image_size = ctag_info.image_size;
	candidate.ctag_info.relocation_count = ctag_info.relocation_count;
	candidate.ctag_info.scenario_tag_index = ctag_info.scenario_tag_index;
	candidate.ce_chunk = ce_chunk;
	candidate.relocation_storage = (uint8_t *)relocation_storage;
	candidate.relocation_storage_bytes = relocation_storage_bytes;
	candidate.stream_scratch = stream_scratch;
	candidate.stream_scratch_bytes = stream_scratch_bytes;
	candidate.expected_profile_id = expected_profile_id;
	candidate.maximum_tag_image_bytes = maximum_tag_image_bytes;
	candidate.prepared = 1;
	if (!prepared_inputs_match(&candidate)) return HCU_PROFILE_MOUNT_E_IDENTITY;
	if (mount->residency_bound) {
		/* The residency arena is live from load until unload, so it must not
		 * alias any span that prepare or the stream path still reads. */
		if (span_overlap(mount->residency_arena, mount->residency_arena_bytes,
			relocation_storage, relocation_storage_bytes) ||
			span_overlap(mount->residency_arena, mount->residency_arena_bytes,
			stream_scratch, stream_scratch_bytes) ||
			(profile->memory_image && span_overlap(mount->residency_arena,
			mount->residency_arena_bytes, profile->memory_image, profile->total_bytes)))
			return HCU_PROFILE_MOUNT_E_ARGUMENT;
		candidate.residency_entries = mount->residency_entries;
		candidate.residency_entry_capacity = mount->residency_entry_capacity;
		candidate.residency_arena = mount->residency_arena;
		candidate.residency_arena_bytes = mount->residency_arena_bytes;
		candidate.residency_bound = 1;
		if (hcu_asset_residency_init(&candidate.residency, candidate.residency_entries,
			candidate.residency_entry_capacity) != HCU_ASSET_PROFILE_OK)
			return HCU_PROFILE_MOUNT_E_ARGUMENT;
	}
	*mount = candidate;
	return HCU_PROFILE_MOUNT_OK;
}

static int resource_read_denied(void *context, int32_t output_datum,
	uint32_t file_offset, uint32_t size, void *buffer, int blocking)
{
	(void)context; (void)output_datum; (void)file_offset;
	(void)size; (void)buffer; (void)blocking;
	return 0;
}

static int mount_source_read(void *context, int32_t output_datum,
	uint32_t file_offset, uint32_t size, void *buffer, int blocking)
{
	hcu_profile_mount *mount = (hcu_profile_mount *)context;
	uint32_t i;
	if (!mount || !mount->active || !mount->source_read || !buffer || !size ||
		output_datum < 0 || !prepared_inputs_match(mount) ||
		file_offset > mount->source_identity_snapshot.file_length ||
		size > mount->source_identity_snapshot.file_length - file_offset)
		return 0;
	for (i = 0; i < mount->resource_range_count; ++i) {
		const hcu_profile_resource_range *range = &mount->resource_ranges[i];
		if (range->output_datum == (uint32_t)output_datum &&
			file_offset >= range->source_offset &&
			file_offset - range->source_offset <= range->size &&
			size <= range->size - (file_offset - range->source_offset)) {
			mount->callbacks_active++;
			if (prepared_inputs_match(mount) && mount->source_read(
				mount->source_context, output_datum, file_offset, size, buffer, blocking)) {
				mount->callbacks_active--;
				return 1;
			}
			mount->callbacks_active--;
			return 0;
		}
	}
	return 0;
}

static int stream_chunk_direct(hcu_profile_mount *mount,
	const hcu_asset_chunk_view *chunk, ctag_ctag_sink_fn sink,
	void *sink_context, size_t *raw_size);

static uint8_t *residency_free_slot(hcu_profile_mount *mount)
{
	size_t slots = mount->residency_arena_bytes / HCU_PROFILE_MOUNT_RESIDENCY_SEGMENT_BYTES, s;
	uint32_t i;
	for (s = 0; s < slots; ++s) {
		uint8_t *slot = mount->residency_arena + s * HCU_PROFILE_MOUNT_RESIDENCY_SEGMENT_BYTES;
		for (i = 0; i < mount->residency.count; ++i)
			if (mount->residency.entries[i].resident &&
				mount->residency.entries[i].storage == slot) break;
		if (i == mount->residency.count) return slot;
	}
	/* Every slot is resident: reuse one with no pin, lease or gameplay
	 * reference. Busy segments are never evicted. */
	for (i = 0; i < mount->residency.count; ++i) {
		hcu_asset_residency_entry *e = &mount->residency.entries[i];
		void *released = NULL;
		if (e->resident && !e->pin_count && !e->lease_count && !e->gameplay_refs &&
			hcu_asset_residency_evict(&mount->residency, e->type, e->chunk_id,
				e->segment, &released) == HCU_ASSET_PROFILE_OK)
			return (uint8_t *)released;
	}
	return NULL;
}

/* Pin one verified segment. A segment that is already resident only gains a
 * pin; a new one takes the first arena slot no resident segment uses. */
static int segment_pin(hcu_profile_mount *mount, const hcu_asset_chunk_view *chunk,
	uint32_t segment, const hcu_asset_residency_entry **entry)
{
	const hcu_asset_residency_entry *found = NULL;
	uint8_t *slot = NULL;
	int rc;
	if (hcu_asset_residency_state(&mount->residency, chunk->type, chunk->chunk_id,
		segment, &found) != HCU_ASSET_PROFILE_OK || !found->resident) {
		slot = residency_free_slot(mount);
		if (!slot) { mount->residency.refused_pins++; return HCU_ASSET_PROFILE_E_MEMORY; }
	}
	rc = hcu_asset_residency_pin(&mount->residency, mount->profile, chunk->type,
		chunk->chunk_id, segment, slot, HCU_PROFILE_MOUNT_RESIDENCY_SEGMENT_BYTES);
	if (rc != HCU_ASSET_PROFILE_OK) return rc;
	return hcu_asset_residency_state(&mount->residency, chunk->type, chunk->chunk_id,
		segment, entry);
}

/* Walk one logical chunk segment by segment. Each segment is pinned, hashed,
 * optionally sunk from its pinned bytes, and unpinned. The sink copies into
 * the CE tag/BSP cache, so gameplay pointers never refer to this staging slot
 * and the slot may be reused once unpinned. The sink never sees bytes from a
 * failed pin. */
static int pinned_walk(hcu_profile_mount *mount, const hcu_asset_chunk_view *chunk,
	int publish, ctag_ctag_sink_fn sink, void *sink_context, uint8_t digest[32])
{
	sha256_context sha;
	uint32_t segment = 0, offset = 0;
	sha256_init(&sha);
	while (offset < chunk->size) {
		uint32_t bytes, logical, at = 0;
		const hcu_asset_residency_entry *entry = NULL;
		int ok = 1;
		if (hcu_asset_profile_segment_info(mount->profile, chunk->type, chunk->chunk_id,
			segment, &bytes, &logical) != HCU_ASSET_PROFILE_OK || logical != offset ||
			!bytes || bytes > chunk->size - offset) return 0;
		if (segment_pin(mount, chunk, segment, &entry) != HCU_ASSET_PROFILE_OK ||
			entry->bytes != bytes) return 0;
		sha256_update(&sha, entry->storage, bytes);
		while (publish && ok && at < bytes) {
			uint32_t take = bytes - at;
			if (take > HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES)
				take = HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES;
			ok = sink(sink_context, offset + at, (const uint8_t *)entry->storage + at, take);
			at += take;
		}
		hcu_asset_residency_unpin(&mount->residency, chunk->type, chunk->chunk_id, segment);
		if (!ok) return 0;
		offset += bytes;
		segment++;
	}
	sha256_final(&sha, digest);
	return 1;
}

static int stream_chunk_pinned(hcu_profile_mount *mount,
	const hcu_asset_chunk_view *chunk, ctag_ctag_sink_fn sink,
	void *sink_context, size_t *raw_size)
{
	uint8_t digest[32];
	/* Pass 1 verifies every segment and the logical digest with no sink call. */
	if (!pinned_walk(mount, chunk, 0, NULL, NULL, digest) ||
		memcmp(digest, chunk->sha256, sizeof(digest)) != 0) return 0;
	if (!pinned_walk(mount, chunk, 1, sink, sink_context, digest) ||
		memcmp(digest, chunk->sha256, sizeof(digest)) != 0) return 0;
	*raw_size = chunk->size;
	return 1;
}

static int stream_chunk(hcu_profile_mount *mount,
	const hcu_asset_chunk_view *chunk, ctag_ctag_sink_fn sink,
	void *sink_context, size_t *raw_size)
{
	if (!mount || !chunk || !sink || !raw_size || !prepared_inputs_match(mount))
		return 0;
	if (mount->residency_bound)
		return stream_chunk_pinned(mount, chunk, sink, sink_context, raw_size);
	return stream_chunk_direct(mount, chunk, sink, sink_context, raw_size);
}

static int stream_chunk_direct(hcu_profile_mount *mount,
	const hcu_asset_chunk_view *chunk, ctag_ctag_sink_fn sink,
	void *sink_context, size_t *raw_size)
{
	sha256_context sha;
	uint8_t digest[32];
	uint32_t offset = 0;
	if (!mount || !chunk || !sink || !raw_size || !prepared_inputs_match(mount))
		return 0;
	/* Pass 1: verify the full chunk before any byte reaches the sink, so a
	 * post-prepare storage change never publishes unverified data to the cache. */
	if (!digest_profile_chunk(mount->profile, chunk, mount->stream_scratch,
		mount->stream_scratch_bytes)) return 0;
	/* Pass 2: stream while re-hashing; storage may change between passes. */
	sha256_init(&sha);
	while (offset < chunk->size) {
		uint32_t take = chunk->size - offset;
		if (take > mount->stream_scratch_bytes)
			take = (uint32_t)mount->stream_scratch_bytes;
		if (take > HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES)
			take = HCU_ASSET_PROFILE_MAX_MEDIA_CHUNK_BYTES;
		if (hcu_asset_profile_read_range(mount->profile, chunk->type,
			chunk->chunk_id, offset, mount->stream_scratch, take) !=
			HCU_ASSET_PROFILE_OK) return 0;
		sha256_update(&sha, mount->stream_scratch, take);
		if (!sink(sink_context, offset, (const uint8_t *)mount->stream_scratch, take))
			return 0;
		offset += take;
	}
	sha256_final(&sha, digest);
	if (memcmp(digest, chunk->sha256, sizeof(digest)) != 0) return 0;
	*raw_size = chunk->size;
	return 1;
}

static int visit_ctag(void *context, ctag_ctag_sink_fn sink,
	void *sink_context, size_t *raw_size)
{
	hcu_profile_mount *mount = (hcu_profile_mount *)context;
	int result;
	if (!mount || !mount->active || mount->callbacks_active || !sink || !raw_size ||
		!prepared_inputs_match(mount)) return 0;
	printf("HALO_PS2_LOCAL visit-ctag begin chunk=%u\n",
		(unsigned)mount->ce_chunk.size);
	mount->callbacks_active++;
	result = stream_chunk(mount, &mount->ce_chunk, sink, sink_context, raw_size);
	mount->callbacks_active--;
	printf("HALO_PS2_LOCAL visit-ctag result=%d raw=%u\n", result,
		raw_size ? (unsigned)*raw_size : 0u);
	return result;
}

static int visit_cbsp(void *context, uint32_t file_offset,
	uint32_t file_size, ctag_bsp_sink_fn sink, void *sink_context,
	size_t *raw_size)
{
	hcu_profile_mount *mount = (hcu_profile_mount *)context;
	hcu_asset_chunk_view chunk;
	const hcu_profile_cbsp_binding *binding = NULL;
	uint16_t i;
	int result;
	if (!mount || !mount->active || mount->callbacks_active || !sink || !raw_size ||
		!prepared_inputs_match(mount)) return 0;
	for (i = 0; i < mount->cbsp_binding_count; ++i)
		if (mount->cbsp_bindings[i].source_file_offset == file_offset &&
			mount->cbsp_bindings[i].source_file_size == file_size) {
			binding = &mount->cbsp_bindings[i]; break;
		}
	if (!binding || hcu_asset_profile_lookup(mount->profile,
		HCU_ASSET_CHUNK_MEDIA, binding->media_chunk_id, &chunk) !=
		HCU_ASSET_PROFILE_OK || memcmp(chunk.sha256,
		binding->expected_chunk_sha256, sizeof(chunk.sha256))) return 0;
	printf("HALO_PS2_LOCAL visit-cbsp begin offset=%u size=%u\n",
		(unsigned)file_offset, (unsigned)file_size);
	mount->callbacks_active++;
	result = stream_chunk(mount, &chunk, sink, sink_context, raw_size);
	mount->callbacks_active--;
	printf("HALO_PS2_LOCAL visit-cbsp result=%d raw=%u\n", result,
		raw_size ? (unsigned)*raw_size : 0u);
	return result;
}

/* Every failure after the backend mount call funnels through one cleanup that
 * unmounts the backend and clears the published flags. CE's CTAG and CBSP
 * visitors are registered here but run lazily from CE cache reads, so no
 * visitor can observe the mount once this function reports failure. */
static int profile_mount_abort(hcu_profile_mount *mount, int result)
{
	if (mount->backend_mounted) {
		if (mount->backend.unmount) mount->backend.unmount(mount->backend.context);
	}
	mount->backend_mounted = 0;
	mount->active = 0;
	return result;
}

int hcu_profile_mount_load(hcu_profile_mount *mount)
{
	ctag_read_at_fn source_reader;
	if (!mount || !mount->prepared || mount->active || mount->backend_mounted)
		return HCU_PROFILE_MOUNT_E_STATE;
	if (!prepared_inputs_match(mount)) return HCU_PROFILE_MOUNT_E_IDENTITY;
	source_reader = mount->source_read ? mount_source_read : resource_read_denied;
	if (!mount->backend.mount_stream(mount->backend.context,
		mount->source_identity_snapshot.map_name, &mount->ctag_info,
		mount->relocation_storage,
		(size_t)mount->ctag_info.relocation_count * 4u,
		mount->source_identity_snapshot.tag_data_offset,
		mount->source_identity_snapshot.file_length,
		source_reader, mount))
		return HCU_PROFILE_MOUNT_E_BACKEND;
	/* From here on the backend is live; any failure must unmount it. */
	mount->backend_mounted = 1;
	mount->active = 1;
	if (!mount->backend.register_ctag_visitor ||
		!mount->backend.register_ctag_visitor(mount->backend.context,
			visit_ctag, mount))
		return profile_mount_abort(mount, HCU_PROFILE_MOUNT_E_BACKEND);
	if (mount->cbsp_binding_count &&
		(!mount->backend.register_bsp_visitor ||
		 !mount->backend.register_bsp_visitor(mount->backend.context,
			visit_cbsp, mount)))
		return profile_mount_abort(mount, HCU_PROFILE_MOUNT_E_BACKEND);
	return HCU_PROFILE_MOUNT_OK;
}

int hcu_profile_mount_unload_with_residency_stats(hcu_profile_mount *mount,
	hcu_profile_residency_stats *released_stats)
{
	uint32_t i;
	hcu_profile_residency_stats stats;
	if (!mount) return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (mount->callbacks_active) return HCU_PROFILE_MOUNT_E_BUSY;
	/* A pin or lease is a live reader of resident bytes. Refuse before any
	 * teardown, so the mount and CE stay exactly as they were. */
	for (i = 0; i < mount->residency.count; ++i)
		if (mount->residency.entries[i].pin_count ||
			mount->residency.entries[i].lease_count) return HCU_PROFILE_MOUNT_E_BUSY;
	if (mount->backend_mounted) {
		if (!mount->backend.unmount) return HCU_PROFILE_MOUNT_E_BACKEND;
		mount->backend.unmount(mount->backend.context);
	}
	/* CE is unpublished, so its gameplay references end here. Each segment is
	 * then evicted and its arena slot returns to the caller. */
	for (i = 0; i < mount->residency.count; ++i) {
		hcu_asset_residency_entry *e = &mount->residency.entries[i];
		while (e->gameplay_refs &&
			hcu_asset_residency_gameplay_ref(&mount->residency, e->type,
				e->chunk_id, e->segment, -1) == HCU_ASSET_PROFILE_OK) {}
		if (e->resident)
			(void)hcu_asset_residency_evict(&mount->residency, e->type,
				e->chunk_id, e->segment, NULL);
	}
	profile_mount_residency_stats(mount, &stats);
	/* A successful release is the quiescent reset boundary for this table. */
	if (stats.bound) stats.resets = 1;
	memset(mount, 0, sizeof(*mount));
	if (released_stats) *released_stats = stats;
	return HCU_PROFILE_MOUNT_OK;
}

int hcu_profile_mount_unload(hcu_profile_mount *mount)
{
	return hcu_profile_mount_unload_with_residency_stats(mount, NULL);
}
