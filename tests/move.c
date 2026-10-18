#include "game/move.h"
#include <assert.h>
#include <math.h>
#include <string.h>

static int floor_at_zero(void *user, const float pos[3])
{
    (void)user;
    return pos[2] < 0.0f;
}

static int wall_at_ten(void *user, const float pos[3])
{
    (void)user;
    return pos[2] < 0.0f || pos[0] > 10.0f;
}

static int low_ceiling(void *user, const float pos[3])
{
    (void)user;
    return pos[2] < 0.0f || pos[2] > 1.2f;
}

static void settle(mover *m, move_solid_fn solid)
{
    move_cmd idle = {0};
    for (int i = 0; i < 90; i++) mover_tick(m, &idle, solid, NULL);
}

int main(void)
{
    mover a, b;
    float feet[3] = {0.0f, 0.0f, 2.0f};
    move_cmd idle = {0}, walk = {1.0f, 0.0f, 0, 0}, jump = {0}, crouch = {0};
    mover_init(&a, feet);
    settle(&a, floor_at_zero);
    assert(a.grounded && fabsf(a.pos[2]) < 0.05f && fabsf(a.vel[2]) < 0.01f);
    jump.jump = 1;
    mover_tick(&a, &jump, floor_at_zero, NULL);
    assert(!a.grounded);
    assert(fabsf(a.vel[2] - (MOVE_JUMP_VELOCITY - MOVE_GRAVITY)) < 1.0e-6f);
    {
        float peak = a.pos[2];
        for (int i = 0; i < 40; i++) {
            mover_tick(&a, &idle, floor_at_zero, NULL);
            if (a.pos[2] > peak) peak = a.pos[2];
        }
        /* v^2 / (2g) with v = jump - g, plus the displacement of the jump tick. */
        assert(peak > 0.65f && peak < 0.72f);
    }
    settle(&a, floor_at_zero);
    assert(a.grounded);
    {
        float x0 = a.pos[0];
        mover_tick(&a, &walk, floor_at_zero, NULL);
        assert(fabsf(a.vel[0] - MOVE_RUN_ACCELERATION / MOVE_TICKS_PER_SECOND) < 1.0e-6f);
        for (int i = 1; i < MOVE_TICKS_PER_SECOND; i++) mover_tick(&a, &walk, floor_at_zero, NULL);
        assert(fabsf(a.vel[0] - MOVE_RUN_FORWARD / MOVE_TICKS_PER_SECOND) < 1.0e-5f);
        assert(a.pos[0] - x0 > 2.0f && a.pos[0] - x0 < 2.25f);
    }
    crouch.crouch = 1;
    mover_tick(&a, &crouch, floor_at_zero, NULL);
    assert(a.crouching && a.eye == MOVE_CROUCH_CAMERA && a.height == MOVE_CROUCH_HEIGHT);
    feet[0] = 9.5f;
    mover_init(&b, feet);
    settle(&b, wall_at_ten);
    for (int i = 0; i < 30; i++) mover_tick(&b, &walk, wall_at_ten, NULL);
    assert(b.pos[0] <= 10.0f);
    feet[2] = 0.2f;
    mover_init(&b, feet);
    settle(&b, low_ceiling);
    jump.jump = 1;
    mover_tick(&b, &jump, low_ceiling, NULL);
    for (int i = 0; i < 30; i++) mover_tick(&b, &idle, low_ceiling, NULL);
    assert(b.pos[2] + b.height <= 1.21f);
    {
        mover c;
        move_cmd cmds[8];
        memset(cmds, 0, sizeof cmds);
        cmds[0].jump = 1;
        cmds[3].move_x = 1.0f;
        mover_init(&a, feet);
        mover_init(&c, feet);
        for (int i = 0; i < 8; i++) {
            mover_tick(&a, &cmds[i], floor_at_zero, NULL);
            mover_tick(&c, &cmds[i], floor_at_zero, NULL);
        }
        assert(a.pos[0] == c.pos[0] && a.pos[2] == c.pos[2] && a.tick == 8);
    }
    return 0;
}
