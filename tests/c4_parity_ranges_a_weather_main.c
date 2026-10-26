/* C4 ranges-a member-exact driver for structure_weather_polyhedron.<unclassified@0x0>.

Compiles weather_polyhedra_find, extracted verbatim from
submodules/halo-ce-universal/source/effects/weather_particle_systems.c by
tests/test_c4_parity_ranges_a.py (placeholder marker CE_FUNCTIONS). The consumer reads
bounding_sphere_center (0x0) and bounding_sphere_radius (0xc) of each polyhedron; the
trailing unused long (0x10) has no access. Stand-ins below supply the camera, the BSP
tag block and the squared distance.

stdin: camera_x camera_y camera_z maximum_distance n, then n lines: cx cy cz radius
stdout: 'w <count> <indices...>'
*/
#include <stdio.h>
#include <stdlib.h>

typedef unsigned char byte;
typedef float real;
typedef struct { real x, y, z; } real_point3d;
typedef struct { void *address; long count; } tag_block;

#define MAXIMUM_NUMBER_OF_VISIBLE_WEATHER_POLYHEDRA 8
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t*)((byte*)(b)->address+(i)*sizeof(t)))
#define error(level, ...) ((void)0)
#define _error_silent 0

struct structure_weather_polyhedron
{
	real_point3d bounding_sphere_center;
	real bounding_sphere_radius;
	int unused;
	struct { unsigned int address; int count; } planes;
};

struct structure_bsp { tag_block weather_polyhedra; };

static struct { struct { real_point3d position; } camera; } render;
static struct structure_bsp bsp_store;
static struct structure_weather_polyhedron polyhedra_store[64];

static struct structure_bsp *global_structure_bsp_get(void) { return &bsp_store; }
static real distance_squared3d(real_point3d const *a, real_point3d const *b)
{
	real dx = a->x - b->x, dy = a->y - b->y, dz = a->z - b->z;
	return dx * dx + dy * dy + dz * dz;
}

/*CE_FUNCTIONS*/

int main(void)
{
	long n, i;
	real maximum_distance;
	short indices[MAXIMUM_NUMBER_OF_VISIBLE_WEATHER_POLYHEDRA];
	short count;

	if (scanf("%f %f %f %f %ld", &render.camera.position.x, &render.camera.position.y,
		&render.camera.position.z, &maximum_distance, &n) != 5) return 3;
	bsp_store.weather_polyhedra.address = polyhedra_store;
	bsp_store.weather_polyhedra.count = n;
	for (i = 0; i < n; i++) {
		struct structure_weather_polyhedron *p = &polyhedra_store[i];
		if (scanf("%f %f %f %f", &p->bounding_sphere_center.x, &p->bounding_sphere_center.y,
			&p->bounding_sphere_center.z, &p->bounding_sphere_radius) != 4) return 3;
	}
	count = weather_polyhedra_find(indices, maximum_distance);
	printf("w %d", (int)count);
	for (i = 0; i < count; i++) printf(" %d", (int)indices[i]);
	printf("\n");
	return 0;
}
