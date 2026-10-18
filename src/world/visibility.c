/* M10 conservative baseline: frustum tests remain, portal reachability is bypassed.
 * The upstream algorithm is compiled unchanged under an explicit alternate name.
 * M11 must compare portal-culling output against this baseline before enabling it.
 */
#include "render/vis.h"
void halo_upstream_vis_run(vis_t *, const bsp_section *, const camera_t *, const frustum_t *, const float [4][4]);
void vis_run(vis_t *visibility, const bsp_section *bsp, const camera_t *camera,
             const frustum_t *frustum, const float clip[4][4])
{
    visibility->force_all = 1;
    halo_upstream_vis_run(visibility, bsp, camera, frustum, clip);
}
