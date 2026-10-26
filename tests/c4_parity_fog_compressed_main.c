/* C4 compressed_vertex_data consumer driver.

Compiles CE uncompress_int32_to_real_vector3d and environment_vertex_compressed_get_normal
(submodules/halo-ce-universal/source/rasterizer/rasterizer_geometry.c), extracted verbatim by
tests/test_c4_parity_fog.py. The Python test feeds the 32-bit packed normal field of every
environment_vertex_compressed record (structure_material.compressed_vertex_data, stride 0x20)
read from retail decompressed BSPs. Output: one decoded normal per line. */
#include <stdio.h>
#include <stdlib.h>

typedef float real;
typedef struct { real i, j, k; } real_vector3d;
#define match_assert(file, line, condition) ((void)0)

struct environment_vertex_compressed
{
	real normal_pad[3];
	unsigned int normal;
	unsigned int binormal;
	unsigned int tangent;
	real texcoord[2];
};

/*CE_FUNCTIONS*/

int main(void)
{
	unsigned int value;
	struct environment_vertex_compressed vertex;
	real_vector3d normal;
	while (scanf("%u", &value) == 1) {
		vertex.normal = value;
		environment_vertex_compressed_get_normal(&vertex, &normal);
		printf("%.9g %.9g %.9g\n", normal.i, normal.j, normal.k);
	}
	return 0;
}
