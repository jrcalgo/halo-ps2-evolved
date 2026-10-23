/* Host ILP32 driver. Loads one stock-MP CBSP through ps2_cache/cache_file_read
 * (ps2_cbsp_materialize) and runs CE's extracted cluster lens-flare selector
 * on the published structure pointer. Direction normalize/compress and the
 * lens-flare definition body are stubs: this records the selector's submission,
 * not VU1 or GS output. */
#include "cseries.h"
#include "cache/cache_files.h"
#include "cache/physical_memory_map.h"
#include "halo_ps2_cache.h"
#include "lensflare_relocated.h"
#include "stream/sha256.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define LENSFLARE_TAG_CACHE_BYTES (16u * 1024u * 1024u)
#define LENSFLARE_BSP_CACHE_BYTES (8u * 1024u * 1024u)
#define LENSFLARE_MAX_RECORDS 4096
#define LENSFLARE_COLLISION_USERS 32

unsigned char lensflare_bsp_cache[LENSFLARE_BSP_CACHE_BYTES] __attribute__((aligned(16)));
unsigned long lensflare_bsp_published_bytes;
unsigned char lensflare_tag_cache[LENSFLARE_TAG_CACHE_BYTES] __attribute__((aligned(16)));
unsigned long lensflare_tag_published_bytes;
int lensflare_active_cluster;
struct lensflare_render_state render;
int lensflare_enabled = 1;
int lensflare_screenshot;
int lensflare_errors;

/* Same names as collision_usage.c. This TU does not link that file; the
 * selector must leave these published sentinels unchanged. */
short global_current_collision_user_depth;
short global_current_collision_users[LENSFLARE_COLLISION_USERS];

struct lensflare_record {
	unsigned marker;
	unsigned cluster;
	unsigned x, y, z;
	unsigned char direction[3];
	unsigned char palette;
	unsigned direction_bits[3];
	unsigned group_tag;
	long name_length;
	unsigned datum;
	char name[256];
};

static struct lensflare_record records[LENSFLARE_MAX_RECORDS];
static int record_count;
static unsigned pending_direction_bits[3];
static int pending_direction_ready;
static long pending_datum;
static int pending_datum_ready;
static struct lens_flare_definition definition_slot;

void *physical_memory_get_tag_cache_base_address(void)
{
	return lensflare_tag_cache;
}

unsigned long physical_memory_get_tag_cache_size(void)
{
	return sizeof lensflare_tag_cache;
}

void *physical_memory_get_structure_bsp_cache_base_address(void)
{
	return lensflare_bsp_cache;
}

unsigned long physical_memory_get_structure_bsp_cache_size(void)
{
	return sizeof lensflare_bsp_cache;
}

int lensflare_draw_lens_flares(void)
{
	return lensflare_enabled;
}

int screenshot_in_progress(void)
{
	return lensflare_screenshot;
}

struct structure_bsp *global_structure_bsp_get(void)
{
	uint32_t root;
	memcpy(&root, lensflare_bsp_cache, sizeof root);
	return (struct structure_bsp *)(uintptr_t)root;
}

void lens_flare_data_error(char const *message)
{
	(void)message;
	lensflare_errors++;
}

void set_real_vector3d(real_vector3d *vector, real i, real j, real k)
{
	vector->i = i;
	vector->j = j;
	vector->k = k;
	memcpy(&pending_direction_bits[0], &i, 4);
	memcpy(&pending_direction_bits[1], &j, 4);
	memcpy(&pending_direction_bits[2], &k, 4);
	pending_direction_ready = 1;
}

void perpendicular3d(real_vector3d const *direction, real_vector3d *up)
{
	(void)direction;
	up->i = 0.0f;
	up->j = 0.0f;
	up->k = 1.0f;
}

void normalize3d(real_vector3d *vector)
{
	(void)vector;
}

unsigned long compress_real_vector3d_to_int32_clamp(real_vector3d const *vector)
{
	(void)vector;
	return 0;
}

struct lens_flare_definition *lens_flare_definition_get(long index)
{
	pending_datum = index;
	pending_datum_ready = 1;
	return &definition_slot;
}

static void put_u16(unsigned char *out, unsigned value)
{
	out[0] = (unsigned char)value;
	out[1] = (unsigned char)(value >> 8);
}

static void put_u32(unsigned char *out, unsigned value)
{
	out[0] = (unsigned char)value;
	out[1] = (unsigned char)(value >> 8);
	out[2] = (unsigned char)(value >> 16);
	out[3] = (unsigned char)(value >> 24);
}

static size_t pack_record(unsigned char *out, struct lensflare_record const *record)
{
	size_t name_len = strlen(record->name);
	unsigned char *cursor = out;
	put_u16(cursor, record->marker);
	cursor += 2;
	put_u32(cursor, record->x);
	cursor += 4;
	put_u32(cursor, record->y);
	cursor += 4;
	put_u32(cursor, record->z);
	cursor += 4;
	*cursor++ = record->direction[0];
	*cursor++ = record->direction[1];
	*cursor++ = record->direction[2];
	*cursor++ = record->palette;
	put_u32(cursor, record->direction_bits[0]);
	cursor += 4;
	put_u32(cursor, record->direction_bits[1]);
	cursor += 4;
	put_u32(cursor, record->direction_bits[2]);
	cursor += 4;
	put_u32(cursor, record->group_tag);
	cursor += 4;
	put_u32(cursor, (unsigned)record->name_length);
	cursor += 4;
	put_u32(cursor, record->datum);
	cursor += 4;
	if ((size_t)(cursor - out) != 42) {
		fprintf(stderr, "lensflare record prefix size %u\n",
			(unsigned)(cursor - out));
		exit(41);
	}
	put_u16(cursor, (unsigned)name_len);
	cursor += 2;
	memcpy(cursor, record->name, name_len);
	cursor += name_len;
	return (size_t)(cursor - out);
}

void rasterizer_lens_flare_submit(struct rasterizer_lens_flare_submit_parameters *parameters)
{
	unsigned marker;
	struct structure_bsp *structure;
	struct structure_lens_flare_marker *marker_record;
	struct structure_lens_flare *flare;
	struct lensflare_record *record;
	const char *name;
	uintptr_t name_address, tag_base, tag_end;
	size_t index, room;
	if (!parameters || !pending_direction_ready || !pending_datum_ready)
		exit(22);
	marker = ((unsigned)(unsigned short)parameters->light_index << 16) |
		(unsigned)(unsigned short)parameters->lens_flare_index;
	structure = global_structure_bsp_get();
	marker_record = TAG_BLOCK_GET_ELEMENT(&structure->lens_flare_markers,
		(long)marker, struct structure_lens_flare_marker);
	flare = TAG_BLOCK_GET_ELEMENT(&structure->lens_flares,
		marker_record->lens_flare_index, struct structure_lens_flare);
	if ((unsigned)pending_datum != (unsigned)flare->lens_flare.index)
		exit(23);
	name = flare->lens_flare.name;
	name_address = (uintptr_t)name;
	tag_base = (uintptr_t)lensflare_tag_cache;
	tag_end = tag_base + lensflare_tag_published_bytes;
	if (!name || name_address < tag_base || name_address >= tag_end)
		exit(24);
	room = (size_t)(tag_end - name_address);
	for (index = 0; index < room && name[index] && index < 255; ++index)
		;
	if (index == room || name[index] != 0)
		exit(25);
	if (record_count >= LENSFLARE_MAX_RECORDS ||
		record_count >= LENSFLARE_SPRITE_REQUEST_BOUND)
		exit(26);
	record = &records[record_count++];
	memset(record, 0, sizeof *record);
	record->marker = marker;
	record->cluster = (unsigned)lensflare_active_cluster;
	memcpy(&record->x, &parameters->position.x, 4);
	memcpy(&record->y, &parameters->position.y, 4);
	memcpy(&record->z, &parameters->position.z, 4);
	record->direction[0] = (unsigned char)marker_record->i_direction;
	record->direction[1] = (unsigned char)marker_record->j_direction;
	record->direction[2] = (unsigned char)marker_record->k_direction;
	record->palette = marker_record->lens_flare_index;
	memcpy(record->direction_bits, pending_direction_bits, sizeof record->direction_bits);
	record->group_tag = flare->lens_flare.group_tag;
	record->name_length = flare->lens_flare.name_length;
	record->datum = (unsigned)flare->lens_flare.index;
	memcpy(record->name, name, index);
	pending_direction_ready = 0;
	pending_datum_ready = 0;
}

static int no_read(void *context, int32_t tag_index, uint32_t offset,
	uint32_t size, void *buffer, int blocking)
{
	(void)context;
	(void)tag_index;
	(void)offset;
	(void)size;
	(void)buffer;
	(void)blocking;
	return 0;
}

static unsigned char *read_file(char const *path, size_t *size)
{
	FILE *file = fopen(path, "rb");
	long length;
	unsigned char *data;
	if (!file || fseek(file, 0, SEEK_END) != 0) {
		if (file)
			fclose(file);
		return NULL;
	}
	length = ftell(file);
	if (length < 0 || fseek(file, 0, SEEK_SET) != 0) {
		fclose(file);
		return NULL;
	}
	data = (unsigned char *)malloc(length ? (size_t)length : 1);
	if (!data) {
		fclose(file);
		return NULL;
	}
	if (fread(data, 1, (size_t)length, file) != (size_t)length) {
		free(data);
		fclose(file);
		return NULL;
	}
	fclose(file);
	*size = (size_t)length;
	return data;
}

static void digest_hex(unsigned char const digest[32], char out[65])
{
	static char const hex[] = "0123456789abcdef";
	int index;
	for (index = 0; index < 32; ++index) {
		out[index * 2] = hex[digest[index] >> 4];
		out[index * 2 + 1] = hex[digest[index] & 15];
	}
	out[64] = 0;
}

static void sha256_bytes(void const *data, size_t size, char out[65])
{
	sha256_context context;
	unsigned char digest[32];
	sha256_init(&context);
	sha256_update(&context, data, size);
	sha256_final(&context, digest);
	digest_hex(digest, out);
}

static void sprite_digest(char out[65])
{
	sha256_context context;
	unsigned char digest[32];
	unsigned char packed[44 + 256];
	int index;
	sha256_init(&context);
	for (index = 0; index < record_count; ++index) {
		size_t packed_size = pack_record(packed, &records[index]);
		sha256_update(&context, packed, packed_size);
	}
	sha256_final(&context, digest);
	digest_hex(digest, out);
}

static int publish_map(char const *name, unsigned char *ctag, size_t ctag_size,
	unsigned char *cbsp, size_t cbsp_size, unsigned bsp_offset, unsigned bsp_size,
	unsigned tag_offset, unsigned tag_image_size, unsigned file_length)
{
	unsigned char header[2048];
	boolean complete = FALSE;
	short read_result;
	struct {
		uint32_t base_address;
		int32_t vertex_buffer_count;
		uint32_t vertex_buffers;
		int32_t index_buffer_count;
		uint32_t index_buffers;
		uint32_t signature;
	} bsp_header;
	if (bsp_size > sizeof lensflare_bsp_cache ||
		tag_image_size > sizeof lensflare_tag_cache)
		return 4;
	ps2_cache_unmount_ctag();
	memset(lensflare_tag_cache, 0xCD, sizeof lensflare_tag_cache);
	memset(lensflare_bsp_cache, 0xCD, sizeof lensflare_bsp_cache);
	lensflare_tag_published_bytes = 0;
	lensflare_bsp_published_bytes = 0;
	if (!ps2_cache_mount_ctag_with_file_source(name, ctag, ctag_size,
			tag_offset, file_length, no_read, NULL)) {
		fprintf(stderr, "lensflare ctag mount failed map=%s\n", name);
		return 5;
	}
	if (!ps2_cache_mount_cbsp_for_extent(cbsp, cbsp_size, bsp_offset, bsp_size)) {
		fprintf(stderr, "lensflare cbsp mount failed map=%s\n", name);
		return 6;
	}
	if (!cache_file_open(name, (struct cache_file_header *)header)) {
		fprintf(stderr, "lensflare cache open failed map=%s\n", name);
		return 7;
	}
	complete = FALSE;
	read_result = cache_file_read(NONE, (long)tag_offset, (long)tag_image_size,
		lensflare_tag_cache, &complete, TRUE);
	if (read_result != NONE || complete != TRUE) {
		fprintf(stderr, "lensflare ctag read failed map=%s\n", name);
		return 8;
	}
	lensflare_tag_published_bytes = tag_image_size;
	complete = FALSE;
	read_result = cache_file_read(NONE, (long)bsp_offset, (long)bsp_size,
		lensflare_bsp_cache, &complete, TRUE);
	if (read_result != NONE || complete != TRUE) {
		fprintf(stderr, "lensflare cbsp read failed map=%s\n", name);
		return 9;
	}
	memcpy(&bsp_header, lensflare_bsp_cache, sizeof bsp_header);
	if (bsp_header.signature != 0x73627370u ||
		bsp_header.vertex_buffer_count != 0 || bsp_header.vertex_buffers != 0 ||
		bsp_header.index_buffer_count != 0 || bsp_header.index_buffers != 0) {
		fprintf(stderr, "lensflare production header normalization missing map=%s\n", name);
		return 10;
	}
	if (bsp_header.base_address < (uint32_t)(uintptr_t)lensflare_bsp_cache ||
		bsp_header.base_address > (uint32_t)(uintptr_t)lensflare_bsp_cache + bsp_size - 0x140) {
		fprintf(stderr, "lensflare structure root leaves BSP cache map=%s\n", name);
		return 11;
	}
	lensflare_bsp_published_bytes = bsp_size;
	if (bsp_size + 16 <= sizeof lensflare_bsp_cache) {
		unsigned index;
		for (index = 0; index < 16; ++index) {
			if (lensflare_bsp_cache[bsp_size + index] != 0xCD) {
				fprintf(stderr, "lensflare materialize wrote past BSP image map=%s\n", name);
				return 12;
			}
		}
	}
	return 0;
}

static int run_selector(struct structure_bsp *structure)
{
	int cluster;
	int calls = 0;
	if (structure->clusters.definition || structure->lens_flares.definition ||
		structure->lens_flare_markers.definition) {
		fprintf(stderr, "lensflare definition pointer is not null\n");
		return -13;
	}
	if (structure->clusters.count <= 0 || structure->clusters.count > 1024)
		return -14;
	for (cluster = 0; cluster < structure->clusters.count; ++cluster) {
		lensflare_active_cluster = cluster;
		calls++;
		rasterizer_lens_flare_submit_for_cluster((short)cluster);
	}
	return calls;
}

static int run_map(char const *name, char const *ctag_path, char const *cbsp_path,
	unsigned bsp_offset, unsigned bsp_size, unsigned tag_offset,
	unsigned tag_image_size, unsigned file_length)
{
	size_t ctag_size = 0, cbsp_size = 0;
	unsigned char *ctag;
	unsigned char *cbsp;
	unsigned char *snapshot;
	struct structure_bsp *structure;
	short depth_before;
	short users_before[LENSFLARE_COLLISION_USERS];
	char bsp_before[65], bsp_after[65], tag_before[65], tag_after[65], sprite[65];
	int calls, status, index, submits_before;
	ctag = read_file(ctag_path, &ctag_size);
	cbsp = read_file(cbsp_path, &cbsp_size);
	if (!ctag || !cbsp) {
		free(ctag);
		free(cbsp);
		return 3;
	}
	status = publish_map(name, ctag, ctag_size, cbsp, cbsp_size, bsp_offset,
		bsp_size, tag_offset, tag_image_size, file_length);
	if (status) {
		free(ctag);
		free(cbsp);
		return status;
	}
	snapshot = (unsigned char *)malloc(bsp_size);
	if (!snapshot)
		return 15;
	memcpy(snapshot, lensflare_bsp_cache, bsp_size);
	sha256_bytes(snapshot, bsp_size, bsp_before);
	sha256_bytes(lensflare_tag_cache, tag_image_size, tag_before);
	global_current_collision_user_depth = 1;
	for (index = 0; index < LENSFLARE_COLLISION_USERS; ++index)
		global_current_collision_users[index] = (short)(index == 0 ? 19 : 0);
	depth_before = global_current_collision_user_depth;
	memcpy(users_before, global_current_collision_users, sizeof users_before);
	record_count = 0;
	lensflare_errors = 0;
	pending_direction_ready = 0;
	pending_datum_ready = 0;
	lensflare_enabled = 1;
	lensflare_screenshot = 0;
	render.window_index = 0;
	structure = global_structure_bsp_get();
	calls = run_selector(structure);
	if (calls < 0) {
		free(snapshot);
		free(ctag);
		free(cbsp);
		return -calls;
	}
	if (record_count > LENSFLARE_SPRITE_REQUEST_BOUND) {
		free(snapshot);
		free(ctag);
		free(cbsp);
		return 16;
	}
	sprite_digest(sprite);
	sha256_bytes(lensflare_bsp_cache, bsp_size, bsp_after);
	sha256_bytes(lensflare_tag_cache, tag_image_size, tag_after);
	if (memcmp(snapshot, lensflare_bsp_cache, bsp_size) != 0 ||
		strcmp(bsp_before, bsp_after) != 0 ||
		strcmp(tag_before, tag_after) != 0 ||
		global_current_collision_user_depth != depth_before ||
		memcmp(users_before, global_current_collision_users, sizeof users_before) != 0) {
		fprintf(stderr, "lensflare published bytes or collision depth changed map=%s\n", name);
		free(snapshot);
		free(ctag);
		free(cbsp);
		return 17;
	}
	submits_before = record_count;
	lensflare_enabled = 0;
	lensflare_screenshot = 0;
	if (run_selector(structure) != structure->clusters.count)
		return 18;
	lensflare_enabled = 1;
	lensflare_screenshot = 1;
	if (run_selector(structure) != structure->clusters.count)
		return 19;
	lensflare_screenshot = 0;
	if (record_count != submits_before || lensflare_errors != 0 ||
		memcmp(snapshot, lensflare_bsp_cache, bsp_size) != 0 ||
		global_current_collision_user_depth != depth_before) {
		fprintf(stderr, "lensflare guard mutated submissions or BSP map=%s\n", name);
		free(snapshot);
		free(ctag);
		free(cbsp);
		return 27;
	}
	printf("MAP name=%s clusters=%ld markers=%ld flares=%ld calls=%d submissions=%d errors=%d "
		"bsp_bytes=%u bsp_sha256=%s bsp_sha256_after=%s tag_sha256=%s collision_depth=%d "
		"collision_user=%d sprite_count=%d sprite_sha256=%s sprite_bound=%d guards=1 "
		"vertex_cleared=1 empty=%d status=passed\n",
		name, structure->clusters.count, structure->lens_flare_markers.count,
		structure->lens_flares.count, calls, record_count, lensflare_errors,
		bsp_size, bsp_before, bsp_after, tag_before, (int)depth_before,
		(int)global_current_collision_users[0], record_count, sprite,
		LENSFLARE_SPRITE_REQUEST_BOUND, record_count == 0);
	for (index = 0; index < record_count; ++index) {
		struct lensflare_record const *record = &records[index];
		printf("REC c=%x m=%x x=%x y=%x z=%x di=%x dj=%x dk=%x dfi=%x dfj=%x dfk=%x "
			"pal=%x group=%x nlen=%x datum=%x name=",
			record->cluster, record->marker, record->x, record->y, record->z,
			record->direction[0], record->direction[1], record->direction[2],
			record->direction_bits[0], record->direction_bits[1], record->direction_bits[2],
			record->palette, record->group_tag, (unsigned)record->name_length,
			record->datum);
		{
			unsigned char const *text = (unsigned char const *)record->name;
			while (*text)
				printf("%02x", *text++);
		}
		printf("\n");
	}
	printf("ENDMAP %s\n", name);
	free(snapshot);
	free(ctag);
	free(cbsp);
	ps2_cache_unmount_ctag();
	return 0;
}

int main(int argc, char **argv)
{
	FILE *manifest;
	char line[1280];
	int maps = 0;
	if (argc != 2)
		return 2;
	cache_files_initialize();
	manifest = fopen(argv[1], "r");
	if (!manifest)
		return 3;
	while (fgets(line, sizeof line, manifest)) {
		char name[64], ctag_path[768], cbsp_path[768];
		unsigned bsp_offset, bsp_size, tag_offset, tag_image_size, file_length;
		int status;
		if (line[0] == '#' || line[0] == '\n')
			continue;
		if (sscanf(line, "%63s %767s %767s %u %u %u %u %u", name, ctag_path,
				cbsp_path, &bsp_offset, &bsp_size, &tag_offset, &tag_image_size,
				&file_length) != 8)
			return 28;
		status = run_map(name, ctag_path, cbsp_path, bsp_offset, bsp_size,
			tag_offset, tag_image_size, file_length);
		if (status)
			return status;
		maps++;
	}
	fclose(manifest);
	printf("RESULT maps=%d status=passed\n", maps);
	return maps == 13 ? 0 : 29;
}
