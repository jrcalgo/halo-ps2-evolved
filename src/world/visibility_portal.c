/* M11 portal path: point-location leaves can extend beyond the rendered world.
 * Preserve the M10 conservative fallback for cameras outside geometry bounds. */
#include "render/vis.h"
void halo_upstream_vis_run(vis_t *, const bsp_section *, const camera_t *,
                          const frustum_t *, const float [4][4]);
void vis_run(vis_t *v, const bsp_section *s, const camera_t *cam,
             const frustum_t *fr, const float clip[4][4])
{
    int original=v->force_all;
    for(int k=0;k<3;k++)
        if(cam->pos[k]<s->bounds[k] || cam->pos[k]>s->bounds[k+3]) v->force_all=1;
    halo_upstream_vis_run(v,s,cam,fr,clip);
    v->force_all=original;
}
