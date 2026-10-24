#include "stream/hcu_profile_mount.h"

#include <limits.h>
#include <string.h>
#include "ps2_ctag.h"
#include "stream/sha256.h"

#define HCU_PROFILE_MOUNT_SCRATCH_MIN 512u
#define HCU_PROFILE_MOUNT_MAX_BSPS 64u
#define HCU_PROFILE_MOUNT_MAX_RESOURCES 65536u

typedef struct {
	const hcu_asset_profile_view *profile;
	hcu_asset_chunk_view chunk;
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

static int profile_read(const hcu_asset_profile_view *profile,
	uint32_t offset, void *destination, uint32_t size)
{
	if (!profile || (!destination && size) || offset > profile->total_bytes ||
		size > profile->total_bytes - offset)
		return 0;
	if (profile->memory_image) {
		memcpy(destination, profile->memory_image + offset, size);
		return 1;
	}
	return profile->read_at &&
		profile->read_at(profile->reader_context, offset, destination, size) == 0;
}

static int chunk_reader(void *context, size_t offset,
	uint8_t *destination, size_t size)
{
	profile_chunk_reader_context *reader =	(profile_chunk_reader_context *)context;
	size_t end;
	uint32_t absolute;
	if (!reader || !reader->profile || !add_size_ok(offset, size, &end) ||
		end > reader->chunk.size || offset > UINT32_MAX - reader->chunk.offset ||
		size > UINT32_MAX)
		return -1;
	absolute = reader->chunk.offset + (uint32_t)offset;
	return profile_read(reader->profile, absolute, destination, (uint32_t)size) ? 0 : -1;
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
		if (!profile_read(profile, chunk->offset + offset, scratch, take)) return 0;
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
	uint16_t i, j;
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
	ce_reader.profile = profile;
	ce_reader.chunk = ce_chunk;
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

static int stream_chunk(hcu_profile_mount *mount,
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
		if (!profile_read(mount->profile, chunk->offset + offset,
			mount->stream_scratch, take)) return 0;
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
	mount->callbacks_active++;
	result = stream_chunk(mount, &mount->ce_chunk, sink, sink_context, raw_size);
	mount->callbacks_active--;
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
	mount->callbacks_active++;
	result = stream_chunk(mount, &chunk, sink, sink_context, raw_size);
	mount->callbacks_active--;
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

int hcu_profile_mount_unload(hcu_profile_mount *mount)
{
	if (!mount) return HCU_PROFILE_MOUNT_E_ARGUMENT;
	if (mount->callbacks_active) return HCU_PROFILE_MOUNT_E_BUSY;
	if (mount->backend_mounted) {
		if (!mount->backend.unmount) return HCU_PROFILE_MOUNT_E_BACKEND;
		mount->backend.unmount(mount->backend.context);
	}
	memset(mount, 0, sizeof(*mount));
	return HCU_PROFILE_MOUNT_OK;
}
