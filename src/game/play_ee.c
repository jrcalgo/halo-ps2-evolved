/* Replaces the free camera when this object is linked.
 * The pad steps the collision biped and the view is its eye. */
#include "game/collpack.h"
#include "game/move.h"
#include "game/pad.h"
#include "platform/profiler.h"
#include "render/bsp_render.h"
#include "render/camera.h"
#include "render/flycam.h"
#include <libpad.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

void __real_flycam_update(camera_t *cam, const fly_input *in, float dt);

static uint8_t *s_pack;
static collide_bsp s_bsp;
static mover s_body;
static float s_yaw, s_pitch;
static void *s_scratch;
static size_t s_scratch_bytes;
static int s_ready;
static int s_failed;
static int s_was_out;
static collide_pill_stats s_last;

static uint8_t *load_file(const char *path, size_t *size)
{
    FILE *f = fopen(path, "rb");
    long n;
    uint8_t *bytes;
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    n = ftell(f);
    if (n <= 0 || fseek(f, 0, SEEK_SET) != 0) { fclose(f); return NULL; }
    bytes = malloc((size_t)n);
    if (!bytes || fread(bytes, 1, (size_t)n, f) != (size_t)n) {
        free(bytes);
        fclose(f);
        return NULL;
    }
    fclose(f);
    *size = (size_t)n;
    return bytes;
}

static int play_init(void)
{
    size_t pack_size, coll_size, tag_size;
    const uint8_t *coll, *tag;
    float pose[4], tags[COLL_TAG_FLOATS];
    s_pack = load_file("host:/collision.hp2", &pack_size);
    if (!s_pack) {
        printf("[play] collision pack missing\n");
        return -1;
    }
    if (collpack_section(s_pack, pack_size, "COLL", &coll, &coll_size) != 0 ||
        collpack_collision(coll, coll_size, &s_bsp) != 0 ||
        collpack_spawn(coll, 0, pose) != 0 ||
        collpack_section(s_pack, pack_size, "TAGS", &tag, &tag_size) != 0 ||
        collpack_tags(tag, tag_size, tags) != 0) {
        printf("[play] collision pack rejected\n");
        return -1;
    }
    (void)tags;
    s_scratch_bytes = collide_pill_scratch_bytes();
    s_scratch = malloc(s_scratch_bytes);
    if (!s_scratch) return -1;
    player_spawn(&s_body, pose, &s_yaw, &s_pitch);
    printf("[play] ready feet %.2f %.2f %.2f yaw %.1f\n",
        pose[0], pose[1], pose[2], s_yaw * 57.2957795f);
    return 0;
}

void __wrap_flycam_update(camera_t *cam, const fly_input *in, float dt)
{
    pad_state pad;
    move_cmd cmd;
    struct padButtonStatus buttons;
    unsigned held = 0;
    collide_pill_stats stats;
    if (s_failed) {
        __real_flycam_update(cam, in, dt);
        return;
    }
    if (!s_ready) {
        if (play_init() != 0) {
            s_failed = 1;
            __real_flycam_update(cam, in, dt);
            return;
        }
        s_ready = 1;
    }
    if (padRead(0, 0, &buttons) != 0) held = (unsigned)(0xFFFF ^ buttons.btns);
    memset(&pad, 0, sizeof pad);
    pad.left_x = (int16_t)(in->move_x * 32767.0f);
    pad.left_y = (int16_t)(in->move_y * 32767.0f);
    pad.right_x = (int16_t)(in->look_x * 32767.0f);
    pad.right_y = (int16_t)(in->look_y * 32767.0f);
    pad.cross = (held & 0x4000u) != 0;
    pad.circle = (held & 0x2000u) != 0;
    pad_to_command(&pad, &cmd, &s_yaw, &s_pitch);
    mover_tick_map(&s_body, &cmd, s_yaw, &s_bsp, s_scratch, s_scratch_bytes, 0, &stats);
    s_last = stats;
    cam->pos[0] = s_body.pos[0];
    cam->pos[1] = s_body.pos[1];
    cam->pos[2] = s_body.pos[2] + s_body.eye;
    cam->yaw = s_yaw;
    cam->pitch = s_pitch;
    if (s_body.out_of_world && !s_was_out) printf("[play] out of world, restored\n");
    s_was_out = s_body.out_of_world;
}

/* Top-left budget strip. 30 Hz frame is 33.3 ms. Committed EE RAM is 26.5 MiB
 * of the 32 MiB machine. Texture upload cap is 1.5 MiB. Pill lists hold 256. */
void __wrap_profiler_overlay(const profiler_t *p, text_batch_t *b)
{
    const render_stats_t *r = &p->last;
    char line[72];
    void *brk = sbrk(0);
    unsigned mem_kb = (brk == (void *)-1) ? 0u : (unsigned)((uintptr_t)brk / 1024u);
    unsigned pages = bsp_render_cache_pages();
    float speed = s_body.vel[0] * s_body.vel[0] + s_body.vel[1] * s_body.vel[1];
    int over_frame = p->last_interval > 33.3f || p->dropped;
    int over_mem = mem_kb > (27787264u / 1024u);
    int over_gs = r->tex_failed || r->chain_overflow || (pages && r->pages_free == 0);
    text_batch_clear(b);
    snprintf(line, sizeof line, "FPS %.0f/30  MS %.1f/33.3  DROP %u",
        p->fps, p->last_interval, p->dropped);
    text_batch_print(b, 8, 8, over_frame ? 0xFF6060 : 0xFFFFFF, line);
    snprintf(line, sizeof line, "EE %.1f MS  GS %.1f  VIF %.1f  WAIT %.1f",
        p->prep_avg, p->gs_ms > 0.f ? p->gs_ms : 0.f, p->vif_ms, p->wait_avg);
    text_batch_print(b, 8, 16, p->prep_avg > 33.3f ? 0xFF6060 : 0xC0FFC0, line);
    snprintf(line, sizeof line, "RAM %u/%u KB  CAP %u KB",
        mem_kb, 27787264u / 1024u, 32768u);
    text_batch_print(b, 8, 24, over_mem ? 0xFF6060 : 0xC0FFC0, line);
    snprintf(line, sizeof line, "GS %u/%u PG  UP %u/%u KB%s",
        r->pages_free, pages, r->upload_bytes / 1024u, 1536u,
        r->tex_failed ? " FAIL" : r->tex_deferred ? " DEFER" : "");
    text_batch_print(b, 8, 32, over_gs ? 0xFF6060 : 0xFFFFC0, line);
    snprintf(line, sizeof line, "TRIS %u BAT %u CL %u/%u PRT %u/%u",
        r->triangles, r->batches, r->clusters_visible, r->clusters_total,
        r->portals_passed, r->portals_tested);
    text_batch_print(b, 8, 40, 0xFFFFC0, line);
    speed = speed > 0.f ? sqrtf(speed) * (float)MOVE_TICKS_PER_SECOND : 0.f;
    snprintf(line, sizeof line, "WALK %.1f/2.2  FEAT %d/256  NOD %d  %s%s",
        speed, s_last.features, s_last.nodes_visited,
        s_body.grounded ? "GND" : "AIR", s_body.crouching ? " CR" : "");
    text_batch_print(b, 8, 48, s_last.saturated ? 0xFF6060 : 0xC0FFFF, line);
}
