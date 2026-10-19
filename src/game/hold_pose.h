/* Camera-relative first-person orientations from Halo 2 Vista shared.map
 * (build 11081.07.04.30.0934.main, SHA-256
 * 6c0afbcf46ecd3a70ef5106e4f51d68414d5a389c1e0b1d14c47a2766abddfe0).
 * Master Chief first_person:idle, frame 0. Each quaternion is the weapon
 * node's world rotation after the camera_control node, which decodes to the
 * identity at the origin, so the rotation is already camera-relative:
 * model +x forward, +y left, +z up. Hamilton x,y,z,w.
 *
 * Carbine: jmad 0xEC973232, animation 3, node gun. Gravity rifle uses this.
 * Flak cannon (the fuel rod): jmad 0xEDCC3367, animation 3 (73 frames), node gun.
 * Energy sword: jmad 0xEE9B3436, animation 0, all 89 idle frames, in
 * sword_idle.h. The blade mesh extends along the handle node's +x. */
#ifndef GAME_HOLD_POSE_H
#define GAME_HOLD_POSE_H
#include "core/mat.h"
#include "game/sword_idle.h"
#include "game/carbine_idle.h"
#include "game/flak_idle.h"
#include <string.h>

static const float PLAY_FP_Q_CARBINE[4] = {
    0.0260977951f, 0.0046413656f, -0.0262397111f, -0.999304175f
};
static const float PLAY_FP_Q_FLAK[4] = {
    0.0236243617f, -0.0448583996f, -0.0235100094f, -0.998437226f
};
static const float PLAY_FP_Q_SWORD[4] = {
    0.0726722216f, 0.0857866107f, -0.0980628055f, -0.988808930f
};

static inline const float *play_fp_hold_quat(const char *path)
{
    if (path && strcmp(path, "weapons\\fuel rod gun\\fuel rod") == 0)
        return PLAY_FP_Q_FLAK;
    if (path && strcmp(path, "weapons\\energy sword\\energy sword") == 0)
        return PLAY_FP_Q_SWORD;
    if (path && strcmp(path, "weapons\\gravity rifle\\gravity rifle") == 0)
        return PLAY_FP_Q_CARBINE;
    return NULL;
}

/* Halo 2 camera and this port's player eye use one basis: +x forward along
 * the look, +y left, +z up. Screen-right is -y. Halo CE tags store the
 * conjugate of the Hamilton quaternion mat4_from_trs applies; these Halo 2
 * animation samples are already that Hamilton form. The carbine gun's +x is
 * (0.999, 0.053, 0.008), the player's look axis. Conjugating it aims the
 * barrel backward. A Halo 2 camera vector (x, y, z) is therefore
 * x*forward + y*left + z*up of the eye. */
static inline void play_fp_player_from_h2(mat4 *out, const mat4 *eye,
                                         const float q[4], const float t[3])
{
    mat4 local;
    mat4_from_trs(&local, q, t, 1.0f);
    mat4_mul(out, &local, eye);
}

/* The handle is a child of the right wrist. sword_idle.h holds its local
 * transform and both arms for every idle frame. */
static inline void play_fp_sword_on_hand(mat4 *out, const mat4 *hand)
{
    play_fp_player_from_h2(out, hand, PLAY_FP_SWORD_HANDLE_Q, PLAY_FP_SWORD_HANDLE_T);
}

/* Fuel rod uses the flak idle; gravity rifle uses the carbine idle. The CE
 * mesh origin sits on that gun node. */
static inline void play_fp_flak_on_hand(mat4 *out, const mat4 *hand)
{
    play_fp_player_from_h2(out, hand, PLAY_FP_FLAK_GUN_Q, PLAY_FP_FLAK_GUN_T);
}

static inline void play_fp_carbine_on_hand(mat4 *out, const mat4 *hand)
{
    play_fp_player_from_h2(out, hand, PLAY_FP_CARBINE_GUN_Q, PLAY_FP_CARBINE_GUN_T);
}

/* Orient the mesh in the player's view, then shift it so grip lands on anchor. */
static inline void play_fp_seat_hold(mat4 *out, const mat4 *camera,
                                    const float grip[3], const float anchor[3],
                                    const float q[4])
{
    float zero[3] = { 0.0f, 0.0f, 0.0f };
    float at[3];
    int k;
    play_fp_player_from_h2(out, camera, q, zero);
    mat4_transform_point(out, grip, at);
    for (k = 0; k < 3; k++) out->m[3][k] += anchor[k] - at[k];
}
#endif
