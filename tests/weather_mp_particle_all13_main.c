/* ILP32 harness for CE weather selection and weather-polyhedra lookup.

   The function bodies between the inject markers are copied from the CE
   sources. This file supplies the tag-block/math helpers those bodies call
   and records the weather index passed to the wind-vector callee. It does
   not include the weather particle sprite renderer.
*/
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

typedef unsigned char byte;
typedef byte boolean;
typedef unsigned short word;
typedef float real;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define SHORT_MAX 32767
#define FLAG(b) (1 << (b))
#define TEST_FLAG(flags, bit) (((flags) & (unsigned)FLAG(bit)) != 0)
#define VALID_INDEX(index, count) ((index) >= 0 && (index) < (count))
#define match_assert(file, line, expr) do { \
	if (!(expr)) { \
		fprintf(stderr, "match_assert %s:%d %s\n", file, line, #expr); \
		exit(5); \
	} \
} while (0)

enum {
	_scenario_current_simple_bit = 0,
	_scenario_current_damped_bit,
	_scenario_current_force_water_bit,
	_scenario_current_force_no_water_bit
};

enum {
	MAXIMUM_NUMBER_OF_VISIBLE_WEATHER_POLYHEDRA = 8,
	_error_silent = 0,
	FOG_TAG = 'fog '
};

typedef char scenario_force_water_bit_assert[
	_scenario_current_force_water_bit == 2 ? 1 : -1];
typedef char scenario_force_no_water_bit_assert[
	_scenario_current_force_no_water_bit == 3 ? 1 : -1];

union real_point3d {
	real n[3];
	struct { real x, y, z; };
};
typedef union real_point3d real_point3d;

union real_vector3d {
	real n[3];
	struct { real i, j, k; };
};
typedef union real_vector3d real_vector3d;

struct real_plane3d {
	real_vector3d n;
	real d;
};
typedef struct real_plane3d real_plane3d;

struct tag_block_definition {
	long element_size;
};

struct tag_block {
	long count;
	void *address;
	struct tag_block_definition *definition;
};

struct tag_reference {
	unsigned long group_tag;
	char *name;
	long name_length;
	long index;
};

struct location {
	short cluster_index;
	short leaf_index;
};

struct structure_cluster {
	short sky_index;
	short fog_reference;
	short background_sound_palette_index;
	short sound_environment_palette_index;
	short weather_palette_index;
	byte unusedA[0x1E];
	struct tag_block predicted_resources;
	byte unused34[0x34];
};

struct structure_fog_plane {
	short region_index;
	short runtime_material_type;
	struct real_plane3d plane;
	byte unused14[0xC];
};

struct structure_fog_region {
	byte unused[0x24];
	short fog_palette_index;
	short weather_palette_index;
};

struct structure_fog_palette_entry {
	byte unused[0x20];
	struct tag_reference fog;
	byte unused2[0x58];
};

struct structure_weather_palette_entry {
	char name[32];
	struct tag_reference particle_system;
	word pad30;
	short runtime_particle_system_global_function_index;
	char particle_system_global_function_name[32];
	long particle_system_unused[11];
	struct tag_reference wind;
	real_vector3d wind_direction;
	real wind_magnitude;
	word padA0;
	short wind_global_function_index;
	char wind_global_function_name[32];
	long wind_unused[11];
};

struct structure_weather_polyhedron {
	real_point3d bounding_sphere_center;
	real bounding_sphere_radius;
	long unused;
	struct tag_block planes;
};

struct structure_bsp {
	struct tag_block clusters;
	struct tag_block fog_planes;
	struct tag_block fog_regions;
	struct tag_block fog_palette;
	struct tag_block weather_palette;
	struct tag_block weather_polyhedra;
};

struct fog_definition {
	byte flags;
	byte unused1[0x73];
	real plane_distance;
};

struct render_camera {
	real_point3d position;
};

struct render_globals {
	short local_player_index;
	struct render_camera camera;
	long leaf_index;
	long cluster_index;
} render;

struct weather_particle_system {
	long definition_index;
	struct location location;
	short weather_palette_index;
	boolean under_water;
};

typedef char cluster_size_assert[sizeof(struct structure_cluster) == 0x68 ? 1 : -1];
typedef char cluster_fog_assert[__builtin_offsetof(struct structure_cluster, fog_reference) == 0x02 ? 1 : -1];
typedef char cluster_weather_assert[__builtin_offsetof(struct structure_cluster, weather_palette_index) == 0x08 ? 1 : -1];
typedef char fog_plane_size_assert[sizeof(struct structure_fog_plane) == 0x20 ? 1 : -1];
typedef char fog_region_size_assert[sizeof(struct structure_fog_region) == 0x28 ? 1 : -1];
typedef char fog_region_weather_assert[__builtin_offsetof(struct structure_fog_region, weather_palette_index) == 0x26 ? 1 : -1];
typedef char fog_palette_size_assert[sizeof(struct structure_fog_palette_entry) == 0x88 ? 1 : -1];
typedef char fog_datum_assert[__builtin_offsetof(struct structure_fog_palette_entry, fog) +
	__builtin_offsetof(struct tag_reference, index) == 0x2C ? 1 : -1];
typedef char weather_palette_size_assert[sizeof(struct structure_weather_palette_entry) == 0xF0 ? 1 : -1];
typedef char particle_datum_assert[__builtin_offsetof(struct structure_weather_palette_entry, particle_system) +
	__builtin_offsetof(struct tag_reference, index) == 0x2C ? 1 : -1];
typedef char polyhedron_size_assert[sizeof(struct structure_weather_polyhedron) == 0x20 ? 1 : -1];
typedef char polyhedron_planes_assert[__builtin_offsetof(struct structure_weather_polyhedron, planes) == 0x14 ? 1 : -1];
typedef char fog_plane_distance_assert[__builtin_offsetof(struct fog_definition, plane_distance) == 0x74 ? 1 : -1];
typedef char tag_block_size_assert[sizeof(struct tag_block) == 12 ? 1 : -1];

/* INJECT_MATH */

#define TAG_BLOCK_GET_ELEMENT(block_address, index, type) \
	((type *)tag_block_get_element_fast((block_address), (index), sizeof(type)))
#define fog_definition_get(index) ((struct fog_definition *)tag_get(FOG_TAG, (index)))

static struct structure_bsp active_bsp;
static struct weather_particle_system systems[1];
static struct fog_slot_tag {
	unsigned long datum;
	struct fog_definition def;
} *active_fogs;
static int active_fog_count;
static unsigned new_calls, delete_calls, update_calls, error_calls, current_calls;
static short current_palette_index;
static int mismatches;
short global_current_collision_user_depth = 1;
long global_current_collision_users[4];
boolean render_particle_systems_enabled = TRUE;
boolean weather = TRUE;

static float f32bits(unsigned bits)
{
	float value;
	memcpy(&value, &bits, sizeof value);
	return value;
}

static void *tag_block_get_element_with_size(
	struct tag_block const *block, long index, long element_size)
{
	fprintf(stderr, "tag block left the fast path count=%ld index=%ld size=%ld\n",
		block ? block->count : -1L, index, element_size);
	exit(8);
	return 0;
}

/* INJECT_FAST_BLOCK */

void *tag_get(long group, long index)
{
	int slot;
	(void)group;
	for (slot = 0; slot < active_fog_count; ++slot)
		if (active_fogs[slot].datum == (unsigned long)index)
			return &active_fogs[slot].def;
	fprintf(stderr, "fog tag_get missed datum=%ld\n", index);
	exit(7);
	return 0;
}

struct structure_bsp *global_structure_bsp_get(void)
{
	return &active_bsp;
}

static struct weather_particle_system *weather_particle_system_get(short index)
{
	if (index != 0) {
		fprintf(stderr, "weather player %d\n", index);
		exit(6);
	}
	return &systems[0];
}

void weather_particle_system_new(short index, long definition, real scale)
{
	(void)scale;
	new_calls++;
	systems[index].definition_index = definition;
}

void weather_particle_system_delete(short index)
{
	delete_calls++;
	systems[index].definition_index = NONE;
}

static void weather_particle_system_render(short index)
{
	(void)index;
	update_calls++;
}

void scenario_get_current_from_weather_palette(
	real_point3d const *position,
	real_vector3d *current,
	long flags,
	short weather_palette_index)
{
	(void)position;
	(void)flags;
	current->i = current->j = current->k = 0.f;
	current_palette_index = weather_palette_index;
	current_calls++;
}

void error(int level, char const *message)
{
	(void)level;
	error_calls++;
	fprintf(stderr, "ce-error %s\n", message);
}

/* INJECT_CE */

struct weather_query {
	int map_index;
	int cluster;
	int flags;
	int null_fog;
	int do_under;
	int do_particles;
	int do_current;
	unsigned xbits, ybits, zbits;
	int exp_fog;
	int exp_under_weather;
	int exp_underwater;
	int exp_current_weather;
	int exp_in_water;
	long exp_datum;
	unsigned exp_new, exp_del, exp_upd;
};

struct map_view {
	const char *name;
	const char *bsp_sha;
	int palette_count, cluster_count, plane_count, region_count;
	int fog_palette_count, poly_count, fog_count, expect_poly_found;
	struct structure_cluster *clusters;
	const unsigned char *cluster_bytes;
	unsigned cluster_bytes_n;
	struct structure_fog_plane *planes;
	const unsigned char *plane_bytes;
	unsigned plane_bytes_n;
	struct structure_fog_region *regions;
	const unsigned char *region_bytes;
	unsigned region_bytes_n;
	struct structure_fog_palette_entry *fog_palette;
	const unsigned char *fog_palette_bytes;
	unsigned fog_palette_bytes_n;
	struct structure_weather_palette_entry *weather;
	const unsigned char *weather_bytes;
	unsigned weather_bytes_n;
	struct structure_weather_polyhedron *poly;
	const unsigned char *poly_bytes;
	unsigned poly_bytes_n;
	const long *plane_counts;
	struct fog_slot_tag *fogs;
	const unsigned char *fog_bytes;
	const unsigned long *fog_datums;
	const unsigned long *expect_group;
	const long *expect_datum;
	unsigned char *cluster_snap;
	unsigned char *plane_snap;
	unsigned char *region_snap;
	unsigned char *fog_palette_snap;
	unsigned char *weather_snap;
	unsigned char *poly_snap;
	unsigned char *fog_snap;
};

/* INJECT_DATA */

static void expect_int(const char *what, const char *map, int cluster,
	long actual, long expected)
{
	if (actual != expected) {
		fprintf(stderr, "mismatch %s map=%s cluster=%d actual=%ld expected=%ld\n",
			what, map, cluster, actual, expected);
		mismatches++;
	}
}

static void load_copy(const char *map, const char *label, void *dest,
	const unsigned char *src, unsigned bytes, unsigned expect,
	unsigned char **snap)
{
	if (bytes != expect) {
		fprintf(stderr, "block size map=%s block=%s bytes=%u expect=%u\n",
			map, label, bytes, expect);
		exit(11);
	}
	if (!bytes)
		return;
	memcpy(dest, src, bytes);
	*snap = malloc(bytes);
	if (!*snap)
		exit(10);
	memcpy(*snap, dest, bytes);
}

static void check_copy(const char *map, const char *label, void *dest,
	unsigned char *snap, unsigned bytes)
{
	if (bytes && memcmp(dest, snap, bytes) != 0) {
		fprintf(stderr, "bsp bytes changed map=%s block=%s\n", map, label);
		mismatches++;
	}
}

static void bind_map(struct map_view *map)
{
	memset(&active_bsp, 0, sizeof active_bsp);
	active_bsp.clusters.count = map->cluster_count;
	active_bsp.clusters.address = map->cluster_count ? map->clusters : 0;
	active_bsp.fog_planes.count = map->plane_count;
	active_bsp.fog_planes.address = map->plane_count ? map->planes : 0;
	active_bsp.fog_regions.count = map->region_count;
	active_bsp.fog_regions.address = map->region_count ? map->regions : 0;
	active_bsp.fog_palette.count = map->fog_palette_count;
	active_bsp.fog_palette.address = map->fog_palette_count ? map->fog_palette : 0;
	active_bsp.weather_palette.count = map->palette_count;
	active_bsp.weather_palette.address = map->weather;
	active_bsp.weather_polyhedra.count = map->poly_count;
	active_bsp.weather_polyhedra.address = map->poly_count ? map->poly : 0;
	active_fogs = map->fogs;
	active_fog_count = map->fog_count;
}

static void prepare_map(struct map_view *map)
{
	int index;
	load_copy(map->name, "clusters", map->clusters, map->cluster_bytes,
		map->cluster_bytes_n, (unsigned)map->cluster_count * sizeof(struct structure_cluster),
		&map->cluster_snap);
	load_copy(map->name, "fog_planes", map->planes, map->plane_bytes,
		map->plane_bytes_n, (unsigned)map->plane_count * sizeof(struct structure_fog_plane),
		&map->plane_snap);
	load_copy(map->name, "fog_regions", map->regions, map->region_bytes,
		map->region_bytes_n, (unsigned)map->region_count * sizeof(struct structure_fog_region),
		&map->region_snap);
	load_copy(map->name, "fog_palette", map->fog_palette, map->fog_palette_bytes,
		map->fog_palette_bytes_n,
		(unsigned)map->fog_palette_count * sizeof(struct structure_fog_palette_entry),
		&map->fog_palette_snap);
	load_copy(map->name, "weather_palette", map->weather, map->weather_bytes,
		map->weather_bytes_n,
		(unsigned)map->palette_count * sizeof(struct structure_weather_palette_entry),
		&map->weather_snap);
	load_copy(map->name, "weather_polyhedra", map->poly, map->poly_bytes,
		map->poly_bytes_n,
		(unsigned)map->poly_count * sizeof(struct structure_weather_polyhedron),
		&map->poly_snap);
	if (map->fog_count) {
		map->fog_snap = malloc((unsigned)map->fog_count * sizeof map->fogs[0].def);
		if (!map->fog_snap)
			exit(10);
		for (index = 0; index < map->fog_count; ++index) {
			map->fogs[index].datum = map->fog_datums[index];
			memcpy(&map->fogs[index].def, map->fog_bytes + index * 0x78, 0x78);
			memcpy(map->fog_snap + index * 0x78, &map->fogs[index].def, 0x78);
		}
	}
	for (index = 0; index < map->poly_count; ++index) {
		if (map->poly[index].planes.count != map->plane_counts[index]) {
			fprintf(stderr, "poly plane count map=%s index=%d ce=%ld raw=%ld\n",
				map->name, index, map->poly[index].planes.count,
				map->plane_counts[index]);
			mismatches++;
		}
		map->poly[index].planes.definition = 0;
		if (map->poly[index].planes.count == 0)
			map->poly[index].planes.address = 0;
	}
	if (map->poly_bytes_n)
		memcpy(map->poly_snap, map->poly, map->poly_bytes_n);
}

static void check_stable(struct map_view *map)
{
	int index;
	int before = mismatches;
	check_copy(map->name, "clusters", map->clusters, map->cluster_snap, map->cluster_bytes_n);
	check_copy(map->name, "fog_planes", map->planes, map->plane_snap, map->plane_bytes_n);
	check_copy(map->name, "fog_regions", map->regions, map->region_snap, map->region_bytes_n);
	check_copy(map->name, "fog_palette", map->fog_palette, map->fog_palette_snap,
		map->fog_palette_bytes_n);
	check_copy(map->name, "weather_palette", map->weather, map->weather_snap,
		map->weather_bytes_n);
	check_copy(map->name, "weather_polyhedra", map->poly, map->poly_snap, map->poly_bytes_n);
	for (index = 0; index < map->fog_count; ++index) {
		if (memcmp(&map->fogs[index].def, map->fog_snap + index * 0x78, 0x78) != 0) {
			fprintf(stderr, "fog definition bytes changed map=%s\n", map->name);
			mismatches++;
		}
	}
	expect_int("collision_depth", map->name, -1,
		global_current_collision_user_depth, 1);
	expect_int("collision_user", map->name, -1,
		global_current_collision_users[0], 0x11L);
	printf("ce map=%s op=stable bsp=%d depth=%d user=%ld\n",
		map->name, mismatches == before, global_current_collision_user_depth,
		global_current_collision_users[0]);
}

static void run_control(void)
{
	struct structure_weather_palette_entry palette;
	struct structure_cluster cluster;
	struct structure_weather_polyhedron poly;
	struct real_plane3d planes[2];
	struct location location;
	real_point3d position;
	real_vector3d current;
	short weather_index = 999;
	short indices[8];
	short found;
	boolean under;
	memset(&palette, 0, sizeof palette);
	memset(&cluster, 0, sizeof cluster);
	memset(&poly, 0, sizeof poly);
	memset(planes, 0, sizeof planes);
	memset(&active_bsp, 0, sizeof active_bsp);
	palette.particle_system.group_tag = 0x7261696Eu;
	palette.particle_system.index = 4;
	cluster.weather_palette_index = 0;
	cluster.fog_reference = NONE;
	poly.bounding_sphere_center.x = 0.f;
	poly.bounding_sphere_center.y = 0.f;
	poly.bounding_sphere_center.z = 0.f;
	poly.bounding_sphere_radius = 10.f;
	poly.planes.count = 2;
	poly.planes.address = planes;
	poly.planes.definition = 0;
	active_bsp.weather_palette.count = 1;
	active_bsp.weather_palette.address = &palette;
	active_bsp.clusters.count = 1;
	active_bsp.clusters.address = &cluster;
	active_bsp.weather_polyhedra.count = 1;
	active_bsp.weather_polyhedra.address = &poly;
	active_fogs = 0;
	active_fog_count = 0;
	location.cluster_index = 0;
	location.leaf_index = NONE;
	position.x = position.y = position.z = 0.f;
	render.local_player_index = 0;
	render.cluster_index = 0;
	render.leaf_index = NONE;
	render.camera.position = position;
	systems[0].definition_index = NONE;
	new_calls = delete_calls = update_calls = 0;
	weather_particle_systems_render();
	under = scenario_location_underwater(&location, &position, &weather_index);
	found = weather_polyhedra_find(indices, 0.f);
	if (new_calls != 1 || update_calls != 1 || delete_calls != 0 ||
		systems[0].definition_index != 4 || systems[0].weather_palette_index != 0 ||
		weather_index != 0 || under != FALSE || found != 1 || indices[0] != 0 ||
		poly.planes.count != 2) {
		fprintf(stderr, "synthetic control failed new=%u upd=%u del=%u datum=%ld "
			"weather=%d under=%d found=%d plane_count=%ld\n",
			new_calls, update_calls, delete_calls, systems[0].definition_index,
			systems[0].weather_palette_index, under, found, poly.planes.count);
		mismatches++;
	}
	render.camera.position.x = 100.f;
	found = weather_polyhedra_find(indices, 0.f);
	if (found != 0) {
		fprintf(stderr, "synthetic far polyhedron visible found=%d\n", found);
		mismatches++;
	}
	current_calls = 0;
	scenario_get_current(&location, &position, &current, 0);
	if (current_calls != 1 || current_palette_index != 0) {
		fprintf(stderr, "synthetic current failed index=%d calls=%u\n",
			current_palette_index, current_calls);
		mismatches++;
	}
	printf("ce-control particles_datum=4 new=1 upd=1 poly_near=1 poly_far=0 "
		"plane_count=2 current_weather=0\n");
}

int main(void)
{
	unsigned query_index;
	unsigned retail_new = 0;
	unsigned retail_poly_found = 0;
	int map_index;
	global_current_collision_users[0] = 0x11L;
	for (map_index = 0; map_index < map_count; ++map_index)
		prepare_map(&maps[map_index]);
	for (query_index = 0; query_index < query_count; ++query_index) {
		const struct weather_query *query = &queries[query_index];
		struct map_view *map = &maps[query->map_index];
		struct location location;
		real_point3d position;
		short fog;
		bind_map(map);
		location.cluster_index = (short)query->cluster;
		location.leaf_index = NONE;
		position.x = f32bits(query->xbits);
		position.y = f32bits(query->ybits);
		position.z = f32bits(query->zbits);
		render.local_player_index = 0;
		render.cluster_index = query->cluster;
		render.leaf_index = NONE;
		render.camera.position = position;
		if (query->null_fog) {
			fog = scenario_get_fog_region_index(&location, 0);
			expect_int("fog", map->name, query->cluster, fog, query->exp_fog);
			printf("ce map=%s op=fog cluster=%d null=1 fog=%d\n",
				map->name, query->cluster, fog);
		} else {
			fog = scenario_get_fog_region_index(&location, &position);
			expect_int("fog", map->name, query->cluster, fog, query->exp_fog);
			printf("ce map=%s op=fog cluster=%d null=0 fog=%d\n",
				map->name, query->cluster, fog);
		}
		if (query->do_under) {
			short weather_index = 999;
			boolean under = scenario_location_underwater(&location, &position, &weather_index);
			expect_int("under_weather", map->name, query->cluster,
				weather_index, query->exp_under_weather);
			expect_int("underwater", map->name, query->cluster, under, query->exp_underwater);
			printf("ce map=%s op=underwater cluster=%d weather=%d underwater=%d\n",
				map->name, query->cluster, weather_index, under ? 1 : 0);
		}
		if (query->do_particles) {
			systems[0].definition_index = NONE;
			new_calls = delete_calls = update_calls = 0;
			weather_particle_systems_render();
			expect_int("particle_weather", map->name, query->cluster,
				systems[0].weather_palette_index, query->exp_under_weather);
			expect_int("particle_underwater", map->name, query->cluster,
				systems[0].under_water, query->exp_underwater);
			expect_int("particle_datum", map->name, query->cluster,
				systems[0].definition_index, query->exp_datum);
			expect_int("particle_new", map->name, query->cluster, new_calls, query->exp_new);
			expect_int("particle_del", map->name, query->cluster, delete_calls, query->exp_del);
			expect_int("particle_upd", map->name, query->cluster, update_calls, query->exp_upd);
			retail_new += new_calls;
			printf("ce map=%s op=particles cluster=%d weather=%d underwater=%d "
				"datum=%ld new=%u del=%u upd=%u\n",
				map->name, query->cluster, systems[0].weather_palette_index,
				systems[0].under_water ? 1 : 0, systems[0].definition_index,
				new_calls, delete_calls, update_calls);
		}
		if (query->do_current) {
			real_vector3d current;
			boolean in_water;
			current_calls = 0;
			current_palette_index = 999;
			in_water = scenario_get_current(&location, &position, &current, query->flags);
			expect_int("current_calls", map->name, query->cluster, current_calls, 1);
			expect_int("current_weather", map->name, query->cluster,
				current_palette_index, query->exp_current_weather);
			expect_int("in_water", map->name, query->cluster, in_water, query->exp_in_water);
			printf("ce map=%s op=current cluster=%d flags=%d weather=%d in_water=%d\n",
				map->name, query->cluster, query->flags, current_palette_index,
				in_water ? 1 : 0);
		}
	}
	for (map_index = 0; map_index < map_count; ++map_index) {
		struct map_view *map = &maps[map_index];
		short indices[MAXIMUM_NUMBER_OF_VISIBLE_WEATHER_POLYHEDRA];
		short found;
		int palette_index;
		bind_map(map);
		render.camera.position.x = 0.f;
		render.camera.position.y = 0.f;
		render.camera.position.z = 0.f;
		found = weather_polyhedra_find(indices, f32bits(0x49742400u));
		expect_int("poly_found", map->name, -1, found, map->expect_poly_found);
		retail_poly_found += (unsigned)found;
		printf("ce map=%s op=polyhedra count=%d found=%d empty=%d\n",
			map->name, map->poly_count, found, map->poly_count == 0);
		for (palette_index = 0; palette_index < map->palette_count; ++palette_index) {
			struct structure_weather_palette_entry *entry = &map->weather[palette_index];
			expect_int("palette_group", map->name, palette_index,
				(long)entry->particle_system.group_tag,
				(long)map->expect_group[palette_index]);
			expect_int("palette_datum", map->name, palette_index,
				entry->particle_system.index, map->expect_datum[palette_index]);
			printf("ce map=%s op=palette index=%d group=%08lx datum=%ld\n",
				map->name, palette_index, entry->particle_system.group_tag,
				entry->particle_system.index);
		}
		printf("ce map=%s op=identity bsp_sha=%s palettes=%d clusters=%d poly=%d\n",
			map->name, map->bsp_sha, map->palette_count, map->cluster_count,
			map->poly_count);
		check_stable(map);
	}
	expect_int("error_calls", "retail", -1, error_calls, 0);
	printf("ce-summary maps=%d queries=%u retail_new=%u retail_poly_found=%u "
		"mismatches=%d result=%s\n",
		map_count, query_count, retail_new, retail_poly_found, mismatches,
		mismatches ? "failed" : "passed");
	run_control();
	expect_int("collision_depth_final", "control", -1,
		global_current_collision_user_depth, 1);
	expect_int("collision_user_final", "control", -1,
		global_current_collision_users[0], 0x11L);
	if (mismatches)
		printf("ce-final mismatches=%d result=failed\n", mismatches);
	else
		printf("ce-final mismatches=0 result=passed\n");
	return mismatches ? 1 : 0;
}
