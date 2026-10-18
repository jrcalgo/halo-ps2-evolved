/* Halo CE biped velocity step.
 * Speeds are the Blood Gulch matg player-information floats.
 * Jump, camera, and pill sizes are characters\cyborg_mp.
 * Gravity is physics.c global_gravity. The step is bipeds.c with
 * BIPED_STEP 1: grounded acceleration, airborne acceleration, and
 * the jump impulse. collision_move_pill is not this file; the
 * solid callback is a stand-in point probe. No heap. */
#ifndef GAME_MOVE_H
#define GAME_MOVE_H
#include "game/collide.h"
#include <stddef.h>
#include <stdint.h>

#define MOVE_TICKS_PER_SECOND 30

/* matg player information, Blood Gulch, units per second. */
#define MOVE_RUN_FORWARD 2.25f
#define MOVE_RUN_BACKWARD 2.0f
#define MOVE_RUN_SIDEWAYS 2.0f
#define MOVE_RUN_ACCELERATION 0.32f
#define MOVE_SNEAK_FORWARD 0.9f
#define MOVE_SNEAK_BACKWARD 0.65f
#define MOVE_SNEAK_SIDEWAYS 0.6f
#define MOVE_SNEAK_ACCELERATION 0.16f
#define MOVE_AIRBORNE_ACCELERATION 0.035f

/* characters\cyborg_mp. Jump is world units per tick, matching
 * translational_velocity. Heights are world units. */
#define MOVE_JUMP_VELOCITY 0.07f
#define MOVE_STAND_CAMERA 0.62f
#define MOVE_CROUCH_CAMERA 0.35f
#define MOVE_CROUCH_TRANSITION 0.2f
#define MOVE_STAND_HEIGHT 0.7f
#define MOVE_CROUCH_HEIGHT 0.5f
#define MOVE_RADIUS 0.2f

/* physics.c */
#define MOVE_GRAVITY 0.0035651792f
/* bipeds.c grounded bias into the floor normal, 1/128. */
#define MOVE_GROUND_BIAS (1.0f / 128.0f)
/* cyborg_mp runtime fields. Crouch completes in six ticks (0.2 s). */
#define MOVE_MIN_NORMAL_K 0.70710677f
#define MOVE_CROUCH_STEP (1.0f / 6.0f)
#define MOVE_DOWNHILL_K0 (-0.34202012f)
#define MOVE_DOWNHILL_K1 (-0.70710677f)
#define MOVE_DOWNHILL_SCALE 1.25f
#define MOVE_UPHILL_K0 0.34202012f
#define MOVE_UPHILL_K1 0.70710677f
#define MOVE_UPHILL_SCALE 0.65f

typedef struct {
    float move_x; /* throttle.i, forward, -1..1 */
    float move_y; /* throttle.j, left, -1..1 */
    int jump;
    int crouch; /* 0 or 1. The source blends; 1 is fully crouched. */
} move_cmd;

typedef struct {
    float pos[3]; /* feet, Z up */
    float vel[3]; /* world units per tick */
    float eye;
    float height;       /* collision height, 0.70 standing to 0.50 crouched */
    float crouch;       /* 0..1, bipeds.c crouch blend */
    float ground[4];    /* last support plane */
    float last_safe[3];
    int grounded;
    int crouching;
    int stuck;
    int out_of_world;
    uint32_t tick;
} mover;

typedef int (*move_solid_fn)(void *user, const float pos[3]);

void mover_init(mover *m, const float feet[3]);
/* pose is x, y, z, yaw. One local player at a scenario start. */
void player_spawn(mover *m, const float pose[4], float *yaw, float *pitch);
void mover_tick(mover *m, const move_cmd *cmd, move_solid_fn solid, void *user);
/* Structure pill from biped_get_physics_pill and collision_move_pill.
 * render_schedule is ignored: the tick does not read it. */
void mover_tick_map(
    mover *m,
    const move_cmd *cmd,
    float yaw,
    const collide_bsp *bsp,
    void *scratch,
    size_t scratch_bytes,
    int render_schedule,
    collide_pill_stats *stats);
#endif
