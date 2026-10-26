/* C4 probe of the frustum->world_bounds consumer (render_cameras.c:521-546).
 *
 * NOT evidence for the ledger member structure_bsp.world_bounds: the frustum
 * field is written by render_cameras.c:1344-1358 from the frustum's own world
 * vertices, not from structure_bsp.world_bounds. The structure member's real
 * reader is structure_visibility.c:1588/1640 (see the JSON row, blocked). visible is the
 * return value: 0 means culled by the world-bounds early-out, nonzero means
 * the cube reached the frustum test. The frustum is
 * built in-host with only world_bounds set; the test varies only that
 * rectangle. Host ILP32 only. */
#include "cseries/cseries.h"
#include "math/real_math.h"
#include "render/render_cameras.h"
#include "render/render_cameras_internal.h"
#include <stdio.h>
#include <string.h>

void error(long type, const char *format, ...) { (void)type; (void)format; }
void display_assert(char *information, char *file, long line, boolean fatal)
{ (void)information; (void)file; (void)line; (void)fatal; }
void system_exit(long code) { (void)code; }
void *csmemset(void *buffer, long value, unsigned long size)
{ return __builtin_memset(buffer, (int)value, size); }
char *csprintf(char *buffer, char *format, ...) { (void)format; return buffer; }
void render_debug_line(boolean immediate, real_point3d const *point0,
    real_point3d const *point1, real_argb_color const *color)
{ (void)immediate; (void)point0; (void)point1; (void)color; }
const union real_argb_color *global_real_argb_red = NULL;
const union real_argb_color *global_real_argb_green = NULL;
/* render_frustum_cube_visible() reads only world_bounds; these matrix and
 * vector helpers are referenced by other render_cameras.c functions only.
 * They trap if reached so a misrouted call cannot pass silently. */
const real_point3d *global_origin3d = NULL;
char temporary[256];
#define C4_UNREACHABLE() (__builtin_trap(), 0)
real_vector3d *reflect_vector3d(real_vector3d const *i, real_vector3d const *n, real_vector3d *r)
{ (void)i; (void)n; (void)r; return C4_UNREACHABLE(); }
void matrix4x3_inverse(real_matrix4x3 const *m, real_matrix4x3 *r)
{ (void)m; (void)r; C4_UNREACHABLE(); }
real_vector3d *matrix4x3_transform_vector(real_matrix4x3 const *m, real_vector3d const *v, real_vector3d *r)
{ (void)m; (void)v; (void)r; return C4_UNREACHABLE(); }
real_point3d *matrix4x3_transform_point(real_matrix4x3 const *m, real_point3d const *p, real_point3d *r)
{ (void)m; (void)p; (void)r; return C4_UNREACHABLE(); }
real_plane3d *matrix4x3_transform_plane(real_matrix4x3 const *m, real_plane3d const *p, real_plane3d *r)
{ (void)m; (void)p; (void)r; return C4_UNREACHABLE(); }

static struct render_frustum frustum;

static int visible(real_rectangle3d const *world, real_rectangle3d const *cube)
{
    memset(&frustum, 0, sizeof frustum);
    frustum.world_bounds = *world;
    return render_frustum_cube_visible(&frustum, cube, FALSE);
}

int main(void)
{
    /* Cube fully inside the baseline world bounds [-10,10]^3. */
    real_rectangle3d cube = { .x0 = -1.f, .x1 = 1.f, .y0 = -1.f, .y1 = 1.f, .z0 = -1.f, .z1 = 1.f };
    real_rectangle3d baseline = { .x0 = -10.f, .x1 = 10.f, .y0 = -10.f, .y1 = 10.f, .z0 = -10.f, .z1 = 10.f };
    /* Alternative member value: bounds moved to [20,30] on x only. */
    real_rectangle3d moved = baseline;
    moved.x0 = 20.f; moved.x1 = 30.f;
    int base_v, moved_v, zrange_v;
    int failures = 0;

    base_v = visible(&baseline, &cube);
    moved_v = visible(&moved, &cube);
    /* Alternative: z range [5,6] excludes the cube's z [-1,1]. */
    zrange_v = visible(&(real_rectangle3d){ .x0 = -10.f, .x1 = 10.f, .y0 = -10.f, .y1 = 10.f,
        .z0 = 5.f, .z1 = 6.f }, &cube);

    printf("member=structure_bsp.world_bounds variant=baseline visible=%d status=%s\n",
        base_v, base_v != 0 ? "passed" : "failed");
    printf("member=structure_bsp.world_bounds variant=x_shifted visible=%d status=%s\n",
        moved_v, moved_v == 0 ? "passed" : "failed");
    printf("member=structure_bsp.world_bounds variant=z_excluded visible=%d status=%s\n",
        zrange_v, zrange_v == 0 ? "passed" : "failed");
    failures += (base_v == 0) + (moved_v != 0) + (zrange_v != 0);
    printf("c4_render_bounds failures=%d\n", failures);
    return failures ? 1 : 0;
}
