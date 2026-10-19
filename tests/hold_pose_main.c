/* Gravity rifle uses the carbine idle rotation. The grip point stays put. */
#include "game/hold_pose.h"
#include <math.h>
#include <stdio.h>
#include <stdlib.h>

static int close_to(float got, float want)
{
    return fabsf(got - want) < 1.0e-5f;
}

static int dir_eq(const float got[3], float x, float y, float z)
{
    return close_to(got[0], x) && close_to(got[1], y) && close_to(got[2], z);
}

static int gap3(const float *got, const float *want, float tol)
{
    return fabsf(got[0] - want[0]) < tol
        && fabsf(got[1] - want[1]) < tol
        && fabsf(got[2] - want[2]) < tol;
}

/* The three idles share this camera-space record layout. */
typedef struct {
    float l_hand[3];
    float r_hand[3];
    float index_tip[3];
    float gun[3];
    float gun_x[3];
} hold_view;

/* Every idle frame matches its oracle. The weapon origin stays on the wrist. */
static int check_idle(int frames, int nodes, float min_travel,
                      int (*find)(const char *), int (*parent_of)(int),
                      const float *(*quat)(int, int), const float *(*trans)(int, int),
                      void (*seat)(mat4 *, const mat4 *), const float *gun_t,
                      const hold_view *oracle)
{
    int l_hand = find("frame l wriste");
    int r_hand = find("frame r wriste");
    int tip = find("frame r index tip");
    int frame;
    float travel = 0.0f;
    if (l_hand < 0 || r_hand < 0 || tip < 0 || nodes > 40) return 10;
    for (frame = 0; frame < frames; frame++) {
        mat4 world[40];
        mat4 ident, gun, inv;
        unsigned char done[40];
        int i, left = nodes;
        float ex[3] = { 1.0f, 0.0f, 0.0f };
        float axis[3], grip[3], dot;
        const hold_view *want = &oracle[frame];
        for (i = 0; i < nodes; i++) done[i] = 0;
        mat4_identity(&ident);
        while (left) {
            int moved = 0;
            for (i = 0; i < nodes; i++) {
                mat4 local;
                int parent = parent_of(i);
                const float *q, *t;
                if (done[i]) continue;
                if (parent >= 0 && !done[parent]) continue;
                q = quat(i, frame);
                t = trans(i, frame);
                mat4_from_trs(&local, q, t, 1.0f);
                mat4_mul(&world[i], &local, parent >= 0 ? &world[parent] : &ident);
                done[i] = 1;
                left--;
                moved = 1;
            }
            if (!moved) return 11;
        }
        seat(&gun, &world[r_hand]);
        if (!gap3(world[l_hand].m[3], want->l_hand, 0.001f)) return 12;
        if (!gap3(world[r_hand].m[3], want->r_hand, 0.001f)) return 13;
        if (!gap3(world[tip].m[3], want->index_tip, 0.001f)) return 14;
        if (!gap3(gun.m[3], want->gun, 0.001f)) return 15;
        mat4_transform_dir(&gun, ex, axis);
        dot = axis[0] * want->gun_x[0] + axis[1] * want->gun_x[1] + axis[2] * want->gun_x[2];
        if (dot < 0.999998f) return 16;
        mat4_rigid_inverse(&inv, &world[r_hand]);
        mat4_transform_point(&inv, gun.m[3], grip);
        if (!gap3(grip, gun_t, 0.001f)) return 17;
        {
            float dx = want->r_hand[0] - oracle[0].r_hand[0];
            float dy = want->r_hand[1] - oracle[0].r_hand[1];
            float dz = want->r_hand[2] - oracle[0].r_hand[2];
            float dist = sqrtf(dx * dx + dy * dy + dz * dz);
            if (dist > travel) travel = dist;
        }
    }
    if (travel < min_travel) return 18;
    return 0;
}

static const float *sword_trans(int node, int frame)
{
    (void)frame;
    return PLAY_FP_SWORD_NODE[node].t;
}

static int sword_parent(int node) { return PLAY_FP_SWORD_NODE[node].parent; }
static int flak_parent(int node) { return PLAY_FP_FLAK_NODE[node].parent; }
static int carbine_parent(int node) { return PLAY_FP_CARBINE_NODE[node].parent; }

static void basis(const float q[4], float fwd[3], float left[3], float up[3])
{
    mat4 m;
    float zero[3] = { 0.0f, 0.0f, 0.0f };
    float ex[3] = { 1.0f, 0.0f, 0.0f };
    float ey[3] = { 0.0f, 1.0f, 0.0f };
    float ez[3] = { 0.0f, 0.0f, 1.0f };
    mat4_from_trs(&m, q, zero, 1.0f);
    mat4_transform_dir(&m, ex, fwd);
    mat4_transform_dir(&m, ey, left);
    mat4_transform_dir(&m, ez, up);
}

int main(void)
{
    const float *gravity = play_fp_hold_quat("weapons\\gravity rifle\\gravity rifle");
    const float *flak = play_fp_hold_quat("weapons\\fuel rod gun\\fuel rod");
    const float *sword = play_fp_hold_quat("weapons\\energy sword\\energy sword");
    float fwd[3], left[3], up[3];
    float grip[3] = { 0.30f, 0.01f, -0.02f };
    float anchor[3] = { 1.5f, -2.0f, 0.25f };
    float cam_t[3] = { 10.0f, -4.0f, 2.0f };
    float at[3], world_fwd[3], got_fwd[3], ex[3] = { 1.0f, 0.0f, 0.0f };
    mat4 camera, seated;
    if (gravity != PLAY_FP_Q_CARBINE) return 1;
    if (flak == gravity || sword == gravity || flak == sword) return 2;
    basis(gravity, fwd, left, up);
    if (!dir_eq(fwd, 0.99857987f, 0.05268516f, 0.00790667f)) return 3;
    if (!dir_eq(left, -0.05220065f, 0.99726077f, -0.05240285f)) return 4;
    if (!dir_eq(up, -0.01064587f, 0.05191570f, 0.99859473f)) return 5;
    basis(flak, fwd, left, up);
    if (!dir_eq(fwd, 0.99487001f, 0.04482703f, -0.09068741f)) return 6;
    basis(sword, fwd, left, up);
    if (!dir_eq(fwd, 0.96604869f, 0.20639936f, 0.15540025f)) return 7;
    {
        int sword_err = check_idle(PLAY_FP_SWORD_FRAMES, PLAY_FP_SWORD_NODES, 0.005f,
                                   play_fp_sword_find, sword_parent, play_fp_sword_node_quat,
                                   sword_trans, play_fp_sword_on_hand, PLAY_FP_SWORD_HANDLE_T,
                                   (const hold_view *)PLAY_FP_SWORD_ORACLE);
        int flak_err = check_idle(PLAY_FP_FLAK_FRAMES, PLAY_FP_FLAK_NODES, 0.0003f,
                                  play_fp_flak_find, flak_parent, play_fp_flak_node_quat,
                                  play_fp_flak_node_trans, play_fp_flak_on_hand, PLAY_FP_FLAK_GUN_T,
                                  (const hold_view *)PLAY_FP_FLAK_ORACLE);
        int carbine_err = check_idle(PLAY_FP_CARBINE_FRAMES, PLAY_FP_CARBINE_NODES, 0.0003f,
                                     play_fp_carbine_find, carbine_parent, play_fp_carbine_node_quat,
                                     play_fp_carbine_node_trans, play_fp_carbine_on_hand,
                                     PLAY_FP_CARBINE_GUN_T, (const hold_view *)PLAY_FP_CARBINE_ORACLE);
        if (sword_err) return sword_err;
        if (flak_err) return 20 + flak_err;
        if (carbine_err) return 40 + carbine_err;
    }
    mat4_from_ypr(&camera, 0.4f, -0.2f, 0.1f, cam_t);
    play_fp_seat_hold(&seated, &camera, grip, anchor, gravity);
    mat4_transform_point(&seated, grip, at);
    if (!dir_eq(at, anchor[0], anchor[1], anchor[2])) return 8;
    basis(gravity, fwd, left, up);
    mat4_transform_dir(&camera, fwd, world_fwd);
    mat4_transform_dir(&seated, ex, got_fwd);
    if (!dir_eq(got_fwd, world_fwd[0], world_fwd[1], world_fwd[2])) return 9;
    printf("hold carbine %g %g %g flak %g sword %g\n",
           fwd[0], fwd[1], fwd[2], flak[1], sword[0]);
    return 0;
}
