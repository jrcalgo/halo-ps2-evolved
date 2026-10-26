/* C4 distant-lighting member-exact consumer driver.

Compiles CE lights_distant_lighting_at_point and build_distant_lights, extracted
verbatim from submodules/halo-ce-universal/source/objects/object_lights.c by
tests/test_c4_parity_fog.py (placeholder marker CE_FUNCTIONS). The collision,
texture-sampling, vertex-decode and shading helpers it calls are replaced by
deterministic stubs whose behaviour the Python oracle mirrors; the members under
test (structure_bsp.default_lighting, structure_bsp.lightmap_group, and the
render_lighting counts) are read from stdin and are NOT stubbed.
Cases are read from stdin; one output block per case. */
#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef unsigned char byte;
typedef unsigned short word;
typedef int boolean;
typedef float real;
#define TRUE 1
#define FALSE 0
#define NONE (-1)
#define TEST_FLAG(flags, bit) (((flags)&(unsigned)(1u << (bit)))!=0)
#define PIN(n,floor,ceiling) ((n)<(floor) ? (floor) : CEILING((n),(ceiling)))
#define CEILING(n,ceiling) ((n)>(ceiling)?(ceiling):(n))
#define MAX(a,b) ((a)>(b)?(a):(b))
#define TAG_BLOCK_GET_ELEMENT(b,i,t) ((t*)((byte*)(b)->address+(i)*sizeof(t)))
#define MAXIMUM_RENDERED_DISTANT_LIGHTS 2
#define MAXIMUM_RENDERED_POINT_LIGHTS 2
#define NUMBER_OF_LIGHTMAP_SAMPLE_SIDEWAYS_RAYCASTS 4
enum { _distant_lighting_raycast_sideways_bit = 0, _distant_lighting_block_on_textures_bit, _distant_lighting_brighten_bit };

typedef struct { real red, green, blue; } real_rgb_color;
typedef struct { real i, j, k; } real_vector3d;
typedef struct { real i, j; } real_vector2d;
typedef struct { real x, y, z; } real_point3d;
typedef union {
	struct { real alpha, red, green, blue; };
	struct { real alpha2; real_rgb_color rgb; };
} real_argb_color;
typedef struct { void *address; int count; } tag_block;
typedef struct { unsigned int group_tag; unsigned int name; int name_length; int index; } tag_reference;

struct render_distant_light { real_rgb_color color; real_vector3d direction; };
struct render_lighting
{
	real_rgb_color ambient_color;
	short distant_light_count;
	word pad;
	struct render_distant_light distant_lights[MAXIMUM_RENDERED_DISTANT_LIGHTS];
	short point_light_count;
	word pad1;
	int point_light_indices[MAXIMUM_RENDERED_POINT_LIGHTS]; /* CE long is 32-bit (ILP32) */
	real_argb_color reflection_tint_color;
	real_vector3d shadow_vector;
	real_rgb_color shadow_color;
};
typedef char render_lighting_size_assert[sizeof(struct render_lighting) == 116 ? 1 : -1];

/* ---- synthetic vertex/material/lightmap/surface data (member values come from stdin) ---- */
struct vertex_data { real n[3]; real r[3]; };
struct structure_material
{
	tag_reference shader;
	short permutation_index;
	real_rgb_color diffuse;
	real_rgb_color lightmap_color;
	struct vertex_data vertices[3];
};
struct structure_lightmap { tag_block materials; short bitmap_index; };
struct structure_surface { short vertex_indices[3]; };
struct structure_bsp
{
	tag_block lightmaps;
	tag_block surfaces;
	tag_reference lightmap_group;
	struct render_lighting default_lighting;
};
struct shader { struct { short type; } base; };
struct shader_environment_definition { tag_reference base_map; };
struct bitmap_group { tag_block bitmaps; };
struct bitmap_data { int unused; };

enum { _shader_type_environment = 1, _shader_type_other = 0 };

static struct structure_bsp bsp;
static struct structure_lightmap lightmap_store[1];
static struct structure_material material_store[1];
static struct structure_surface surface_store[1];
static struct structure_bsp *global_structure_bsp_get(void) { return &bsp; }
static struct shader shader_store[2];
static struct shader_environment_definition env_store[2];
static struct bitmap_group group_store;
static struct bitmap_data bitmap_store;
static int debug_object_lights = 0;

/* hit configuration for structure_test_vector */
static int hit_flag;
static short hit_lightmap_index, hit_material_index;
static long hit_surface_index;
static real hit_s, hit_t;

static boolean structure_test_vector(real_point3d const *point, real_vector3d const *vector,
	real_point3d *collision_point, short *lightmap_index, short *material_index,
	long *surface_index, real *s, real *t)
{
	(void)vector;
	if (!hit_flag) return FALSE;
	*collision_point = *point;
	*lightmap_index = hit_lightmap_index;
	*material_index = hit_material_index;
	*surface_index = hit_surface_index;
	*s = hit_s; *t = hit_t;
	return TRUE;
}
static struct shader *shader_definition_get(long index) { return &shader_store[index]; }
static struct shader_environment_definition *shader_environment_definition_get(struct shader *s)
{
	return &env_store[s == &shader_store[0] ? 0 : 1];
}
static struct bitmap_data *bitmap_group_try_and_get_bitmap(long group_index, short bitmap_index)
{
	if (group_index < 0 || bitmap_index < 0) return NULL;
	return &bitmap_store;
}
static struct bitmap_group *bitmap_group_get(long group_index) { (void)group_index; return &group_store; }
static struct bitmap_data *texture_cache_bitmap_load(struct bitmap_data *b) { return b; }
static void sample_diffuse_texture(struct structure_material *m, struct bitmap_data *b, struct structure_surface const *s,
	real u, real v, real_rgb_color *color)
{ (void)b; (void)s; (void)u; (void)v; *color = m->diffuse; }
static void sample_lightmap(struct structure_material *m, struct bitmap_data *b, struct structure_surface const *s,
	real u, real v, real_rgb_color *color)
{ (void)b; (void)s; (void)u; (void)v; *color = m->lightmap_color; }
static struct vertex_data *structure_material_get_vertex(struct structure_material *m, short i) { return &m->vertices[i]; }
static struct vertex_data *structure_material_get_lightmap_vertex(struct structure_material *m, short i) { return &m->vertices[i]; }
static void environment_vertex_compressed_get_normal(struct vertex_data *v, real_vector3d *n)
{ n->i = v->n[0]; n->j = v->n[1]; n->k = v->n[2]; }
static void environment_lightmap_vertex_compressed_get_incident_radiosity(struct vertex_data *v, real_vector3d *n)
{ n->i = v->r[0]; n->j = v->r[1]; n->k = v->r[2]; }
static void shade_vector3d(real_vector3d const *a, real_vector3d const *b, real_vector3d const *c, real s, real t, real_vector3d *out)
{
	real w = 1.0f - s - t;
	out->i = w * a->i + s * b->i + t * c->i;
	out->j = w * a->j + s * b->j + t * c->j;
	out->k = w * a->k + s * b->k + t * c->k;
}
static real shade_scalar(real l0, real l1, real l2, real s, real t) { real w = 1.0f - s - t; return w * l0 + s * l1 + t * l2; }
static real normalize3d(real_vector3d *v)
{
	real len = sqrtf(v->i * v->i + v->j * v->j + v->k * v->k);
	if (len > 0.0f) { v->i /= len; v->j /= len; v->k /= len; }
	return len;
}
static real square_root(real x) { return sqrtf(x); }
static real power(real x, real y) { return powf(x, y); }
static real real_rgb_color_brightness(real_rgb_color const *c) { return c->red * 0.299f + c->green * 0.587f + c->blue * 0.114f; }
static real magnitude2d(real_vector2d const *v) { return sqrtf(v->i * v->i + v->j * v->j); }
static void render_debug_point(boolean a, real_point3d const *p, real r, void const *c) { (void)a; (void)p; (void)r; (void)c; }
static void render_debug_vector(boolean a, real_point3d const *p, real_vector3d const *v, real r, void const *c) { (void)a; (void)p; (void)v; (void)r; (void)c; }

real object_light_ambient_base = 0.03f;
real object_light_ambient_scale = 0.4f;
real object_light_secondary_scale = 1.0f;
static real_vector3d const lightmap_sample_raycast_down = { 0.0f, 0.0f, -10.0f };
static real_vector3d const lightmap_sample_raycast_sideways[NUMBER_OF_LIGHTMAP_SAMPLE_SIDEWAYS_RAYCASTS] =
{
	{ -10.0f, 0.0f, 0.0f }, { 10.0f, 0.0f, 0.0f }, { 0.0f, -10.0f, 0.0f }, { 0.0f, 10.0f, 0.0f },
};
static struct render_lighting const default_object_lighting =
{
	{ 0.2f, 0.2f, 0.2f },
	2,
	0,
	{
		{ { 1.0f, 1.0f, 1.0f }, { -0.577f, -0.577f, -0.577f } },
		{ { 0.4f, 0.4f, 0.5f }, { 0.0f, 0.0f, 1.0f } },
	},
	0,
	0,
	{ 0, 0 },
	{ 0.5f, 1.0f, 1.0f, 1.0f },
	{ 0.0f, 0.0f, -1.0f },
	{ 0.0f, 0.0f, 0.0f },
};

/*CE_FUNCTIONS*/

static real rd(void) { float v; if (scanf("%f", &v) != 1) exit(3); return v; }
static int ri(void) { int v; if (scanf("%d", &v) != 1) exit(3); return v; }

static void print_lighting(struct render_lighting const *l, boolean result)
{
	int i;
	printf("result=%d ambient=%.7g,%.7g,%.7g distant=%d", result, l->ambient_color.red, l->ambient_color.green,
		l->ambient_color.blue, (int)l->distant_light_count);
	for (i = 0; i < MAXIMUM_RENDERED_DISTANT_LIGHTS; i++)
		printf(" dl%d=%.7g,%.7g,%.7g|%.7g,%.7g,%.7g", i, l->distant_lights[i].color.red, l->distant_lights[i].color.green,
			l->distant_lights[i].color.blue, l->distant_lights[i].direction.i, l->distant_lights[i].direction.j,
			l->distant_lights[i].direction.k);
	printf(" point=%d", (int)l->point_light_count);
	for (i = 0; i < MAXIMUM_RENDERED_POINT_LIGHTS; i++) printf(" pli%d=%d", i, l->point_light_indices[i]);
	printf(" tint=%.7g,%.7g,%.7g,%.7g shadow_vec=%.7g,%.7g,%.7g shadow_col=%.7g,%.7g,%.7g\n",
		l->reflection_tint_color.alpha, l->reflection_tint_color.red, l->reflection_tint_color.green,
		l->reflection_tint_color.blue, l->shadow_vector.i, l->shadow_vector.j, l->shadow_vector.k,
		l->shadow_color.red, l->shadow_color.green, l->shadow_color.blue);
}

int main(void)
{
	int cases, c;
	group_store.bitmaps.count = 1;
	if (sizeof(struct render_lighting) != 116) return 2;
	cases = ri();
	for (c = 0; c < cases; c++) {
		struct render_lighting out;
		real_point3d position = { 0.0f, 0.0f, 0.0f };
		long flags = ri();
		boolean result;
		int i;
		/* default_lighting: ambient, distant count, pad, 2 distant lights, point count, pad, indices, tint, shadow vec, shadow color */
		struct render_lighting *d = &bsp.default_lighting;
		d->ambient_color.red = rd(); d->ambient_color.green = rd(); d->ambient_color.blue = rd();
		d->distant_light_count = (short)ri(); d->pad = 0;
		for (i = 0; i < 2; i++) {
			d->distant_lights[i].color.red = rd(); d->distant_lights[i].color.green = rd(); d->distant_lights[i].color.blue = rd();
			d->distant_lights[i].direction.i = rd(); d->distant_lights[i].direction.j = rd(); d->distant_lights[i].direction.k = rd();
		}
		d->point_light_count = (short)ri(); d->pad1 = 0;
		d->point_light_indices[0] = ri(); d->point_light_indices[1] = ri();
		d->reflection_tint_color.alpha = rd(); d->reflection_tint_color.red = rd(); d->reflection_tint_color.green = rd(); d->reflection_tint_color.blue = rd();
		d->shadow_vector.i = rd(); d->shadow_vector.j = rd(); d->shadow_vector.k = rd();
		d->shadow_color.red = rd(); d->shadow_color.green = rd(); d->shadow_color.blue = rd();
		/* lightmap_group index */
		bsp.lightmap_group.index = ri();
		/* hit configuration */
		hit_flag = ri();
		hit_lightmap_index = 0; hit_material_index = 0; hit_surface_index = 0; hit_s = 0.25f; hit_t = 0.25f;
		/* shader / lightmap / material */
		shader_store[0].base.type = (short)ri() ? _shader_type_environment : _shader_type_other;
		env_store[0].base_map.index = ri();
		lightmap_store[0].bitmap_index = (short)ri();
		material_store[0].permutation_index = (short)ri();
		material_store[0].diffuse.red = rd(); material_store[0].diffuse.green = rd(); material_store[0].diffuse.blue = rd();
		material_store[0].lightmap_color.red = rd(); material_store[0].lightmap_color.green = rd(); material_store[0].lightmap_color.blue = rd();
		for (i = 0; i < 3; i++) {
			int k;
			for (k = 0; k < 3; k++) material_store[0].vertices[i].n[k] = rd();
		}
		for (i = 0; i < 3; i++) {
			int k;
			for (k = 0; k < 3; k++) material_store[0].vertices[i].r[k] = rd();
		}
		surface_store[0].vertex_indices[0] = 0; surface_store[0].vertex_indices[1] = 1; surface_store[0].vertex_indices[2] = 2;
		lightmap_store[0].materials.address = material_store; lightmap_store[0].materials.count = 1;
		bsp.lightmaps.address = lightmap_store; bsp.lightmaps.count = 1;
		bsp.surfaces.address = surface_store; bsp.surfaces.count = 1;
		shader_store[1].base.type = _shader_type_other;
		group_store.bitmaps.count = 1;

		result = lights_distant_lighting_at_point(flags, &position, &out);
		print_lighting(&out, result);
	}
	return 0;
}
