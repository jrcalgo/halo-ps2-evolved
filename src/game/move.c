#include "game/move.h"
#include <math.h>
#include <string.h>

/* bipeds.c player-physics blend, then the grounded and airborne
 * branches of the biped physics step. Facing is yaw 0 = +X. */

static float clampf(float v, float lo, float hi)
{
    if (v < lo) return lo;
    if (v > hi) return hi;
    return v;
}

static float len2(float x, float y)
{
    return sqrtf(x * x + y * y);
}

void player_spawn(mover *m, const float pose[4], float *yaw, float *pitch)
{
    float feet[3] = {pose[0], pose[1], pose[2]};
    mover_init(m, feet);
    *yaw = pose[3];
    *pitch = 0.0f;
}

void mover_init(mover *m, const float feet[3])
{
    m->pos[0] = feet[0];
    m->pos[1] = feet[1];
    m->pos[2] = feet[2];
    m->vel[0] = m->vel[1] = m->vel[2] = 0.0f;
    m->eye = MOVE_STAND_CAMERA;
    m->height = MOVE_STAND_HEIGHT;
    m->crouch = 0.0f;
    m->ground[0] = 0.0f;
    m->ground[1] = 0.0f;
    m->ground[2] = 1.0f;
    m->ground[3] = 0.0f;
    m->last_safe[0] = feet[0];
    m->last_safe[1] = feet[1];
    m->last_safe[2] = feet[2];
    m->grounded = 0;
    m->crouching = 0;
    m->stuck = 0;
    m->out_of_world = 0;
    m->tick = 0;
}

static int blocked(move_solid_fn solid, void *user, const float pos[3], float height)
{
    float head[3] = {pos[0], pos[1], pos[2] + height};
    return solid(user, pos) || solid(user, head);
}

void mover_tick(mover *m, const move_cmd *cmd, move_solid_fn solid, void *user)
{
    float throttle_i = clampf(cmd->move_x, -1.0f, 1.0f);
    float throttle_j = clampf(cmd->move_y, -1.0f, 1.0f);
    float crouch = cmd->crouch ? 1.0f : 0.0f;
    float uncrouch = 1.0f - crouch;
    float forward_speed, sideways_speed, acceleration, desired_i, desired_j;
    float speed, inv, move_i, move_j, desired_x, desired_y;
    float accel_x, accel_y, accel_len, scale;
    int was_air = !m->grounded;
    float next[3];

    m->crouching = cmd->crouch ? 1 : 0;
    m->eye = cmd->crouch ? MOVE_CROUCH_CAMERA : MOVE_STAND_CAMERA;
    m->height = cmd->crouch ? MOVE_CROUCH_HEIGHT : MOVE_STAND_HEIGHT;

    if (throttle_i <= 0.0f) {
        forward_speed = MOVE_SNEAK_BACKWARD;
        sideways_speed = MOVE_RUN_BACKWARD;
    } else {
        forward_speed = MOVE_SNEAK_FORWARD;
        sideways_speed = MOVE_RUN_FORWARD;
    }
    forward_speed = sideways_speed * uncrouch + forward_speed * crouch;
    sideways_speed = MOVE_RUN_SIDEWAYS * uncrouch + MOVE_SNEAK_SIDEWAYS * crouch;
    acceleration = (MOVE_RUN_ACCELERATION * uncrouch + MOVE_SNEAK_ACCELERATION * crouch)
        / (float)MOVE_TICKS_PER_SECOND;
    desired_i = throttle_i * forward_speed / (float)MOVE_TICKS_PER_SECOND;
    desired_j = throttle_j * sideways_speed / (float)MOVE_TICKS_PER_SECOND;

    if (cmd->jump && m->grounded && m->vel[2] < MOVE_JUMP_VELOCITY) {
        m->vel[2] = MOVE_JUMP_VELOCITY;
        m->grounded = 0;
    }

    if (!m->grounded) {
        float air = MOVE_AIRBORNE_ACCELERATION / (float)MOVE_TICKS_PER_SECOND;
        accel_x = desired_i - m->vel[0];
        accel_y = desired_j - m->vel[1];
        accel_len = len2(accel_x, accel_y);
        if (accel_len > air && accel_len > 0.0f) {
            scale = air / accel_len;
            accel_x *= scale;
            accel_y *= scale;
        }
        m->vel[0] += accel_x;
        m->vel[1] += accel_y;
        m->vel[2] -= MOVE_GRAVITY;
    } else {
        speed = len2(desired_i, desired_j);
        if (speed > 0.0f) {
            inv = 1.0f / speed;
            move_i = desired_i * inv;
            move_j = desired_j * inv;
        } else {
            move_i = move_j = 0.0f;
        }
        desired_x = move_i * speed;
        desired_y = move_j * speed;
        accel_x = desired_x - m->vel[0];
        accel_y = desired_y - m->vel[1];
        accel_len = len2(accel_x, accel_y);
        if (accel_len > acceleration && accel_len > 0.0f) {
            scale = acceleration / accel_len;
            accel_x *= scale;
            accel_y *= scale;
        }
        m->vel[0] += accel_x;
        m->vel[1] += accel_y;
        m->vel[2] -= MOVE_GROUND_BIAS;
    }

    next[0] = m->pos[0] + m->vel[0];
    next[1] = m->pos[1] + m->vel[1];
    next[2] = m->pos[2];
    if (blocked(solid, user, next, m->height)) {
        m->vel[0] = m->vel[1] = 0.0f;
    } else {
        m->pos[0] = next[0];
        m->pos[1] = next[1];
    }
    next[0] = m->pos[0];
    next[1] = m->pos[1];
    next[2] = m->pos[2] + m->vel[2];
    if (blocked(solid, user, next, m->height)) {
        if (m->vel[2] < 0.0f) m->grounded = 1;
        m->vel[2] = 0.0f;
    } else {
        m->pos[2] = next[2];
        m->grounded = 0;
    }
    m->stuck = was_air && !m->grounded && blocked(solid, user, m->pos, m->height);
    m->tick++;
}

static float pill_height(float crouch)
{
    float collision = MOVE_STAND_HEIGHT + (MOVE_CROUCH_HEIGHT - MOVE_STAND_HEIGHT) * crouch;
    float height = collision - 2.0f * MOVE_RADIUS;
    return height > 0.0f ? height : 0.0f;
}

static void blend_crouch(mover *m, int want)
{
    if (want) {
        if (1.0f - m->crouch <= MOVE_CROUCH_STEP) m->crouch = 1.0f;
        else m->crouch += MOVE_CROUCH_STEP;
    } else if (m->crouch <= MOVE_CROUCH_STEP) {
        m->crouch = 0.0f;
    } else {
        m->crouch -= MOVE_CROUCH_STEP;
    }
    m->crouching = m->crouch > 0.0f;
    m->eye = MOVE_STAND_CAMERA + (MOVE_CROUCH_CAMERA - MOVE_STAND_CAMERA) * m->crouch;
    m->height = MOVE_STAND_HEIGHT + (MOVE_CROUCH_HEIGHT - MOVE_STAND_HEIGHT) * m->crouch;
}

void mover_tick_map(
    mover *m,
    const move_cmd *cmd,
    float yaw,
    const collide_bsp *bsp,
    void *scratch,
    size_t scratch_bytes,
    int render_schedule,
    collide_pill_stats *stats)
{
    float throttle_i = clampf(cmd->move_x, -1.0f, 1.0f);
    float throttle_j = clampf(cmd->move_y, -1.0f, 1.0f);
    float forward_speed, sideways_speed, acceleration;
    float desired_i, desired_j, speed, facing_i, facing_j;
    float move_i, move_j, move_k;
    float fx = cosf(yaw), fy = sinf(yaw);
    float base[3], velocity[3];
    float center[3];
    collide_pill_out hit;
    (void)render_schedule;
    blend_crouch(m, cmd->crouch);
    if (throttle_i <= 0.0f) {
        forward_speed = MOVE_SNEAK_BACKWARD;
        sideways_speed = MOVE_RUN_BACKWARD;
    } else {
        forward_speed = MOVE_SNEAK_FORWARD;
        sideways_speed = MOVE_RUN_FORWARD;
    }
    forward_speed = sideways_speed * (1.0f - m->crouch) + forward_speed * m->crouch;
    sideways_speed = MOVE_RUN_SIDEWAYS * (1.0f - m->crouch) + MOVE_SNEAK_SIDEWAYS * m->crouch;
    acceleration = (MOVE_RUN_ACCELERATION * (1.0f - m->crouch) + MOVE_SNEAK_ACCELERATION * m->crouch)
        / (float)MOVE_TICKS_PER_SECOND;
    desired_i = throttle_i * forward_speed / (float)MOVE_TICKS_PER_SECOND;
    desired_j = throttle_j * sideways_speed / (float)MOVE_TICKS_PER_SECOND;
    if (cmd->jump && m->grounded && m->vel[2] < MOVE_JUMP_VELOCITY) {
        m->vel[2] = MOVE_JUMP_VELOCITY;
        m->grounded = 0;
    }
    facing_i = desired_i * fx - fy * desired_j;
    facing_j = desired_j * fx + desired_i * fy;
    if (!m->grounded) {
        float air = MOVE_AIRBORNE_ACCELERATION / (float)MOVE_TICKS_PER_SECOND;
        float ax = facing_i - m->vel[0];
        float ay = facing_j - m->vel[1];
        float al = len2(ax, ay);
        if (al > air && al > 0.0f) { ax *= air / al; ay *= air / al; }
        m->vel[0] += ax;
        m->vel[1] += ay;
        m->vel[2] -= MOVE_GRAVITY;
    } else {
        speed = len2(desired_i, desired_j);
        move_i = facing_i;
        move_j = facing_j;
        move_k = -(move_i * m->ground[0] + move_j * m->ground[1]) /
            (m->ground[2] > 0.0001f ? m->ground[2] : 1.0f);
        {
            float l = sqrtf(move_i * move_i + move_j * move_j + move_k * move_k);
            if (l > 0.0f) { move_i /= l; move_j /= l; move_k /= l; }
        }
        if (move_k <= MOVE_DOWNHILL_K1) speed *= MOVE_DOWNHILL_SCALE;
        else if (move_k < MOVE_DOWNHILL_K0)
            speed *= (move_k - MOVE_DOWNHILL_K0) * (MOVE_DOWNHILL_SCALE - 1.0f) /
                (MOVE_DOWNHILL_K1 - MOVE_DOWNHILL_K0) + 1.0f;
        else if (move_k >= MOVE_UPHILL_K1) speed *= MOVE_UPHILL_SCALE;
        else if (move_k > MOVE_UPHILL_K0)
            speed *= (move_k - MOVE_UPHILL_K0) * (MOVE_UPHILL_SCALE - 1.0f) /
                (MOVE_UPHILL_K1 - MOVE_UPHILL_K0) + 1.0f;
        {
            float dx = move_i * speed - m->vel[0];
            float dy = move_j * speed - m->vel[1];
            float dz = move_k * speed - m->vel[2];
            float al = sqrtf(dx * dx + dy * dy + dz * dz);
            if (al > acceleration && al > 0.0f) {
                float s = acceleration / al;
                dx *= s; dy *= s; dz *= s;
            }
            m->vel[0] += dx - m->ground[0] * MOVE_GROUND_BIAS;
            m->vel[1] += dy - m->ground[1] * MOVE_GROUND_BIAS;
            m->vel[2] += dz - m->ground[2] * MOVE_GROUND_BIAS;
        }
    }
    base[0] = m->pos[0];
    base[1] = m->pos[1];
    base[2] = m->pos[2] + MOVE_RADIUS;
    memcpy(velocity, m->vel, sizeof velocity);
    if (collide_move_pill(bsp, base, velocity, pill_height(m->crouch), MOVE_RADIUS,
            MOVE_MIN_NORMAL_K, scratch, scratch_bytes, &hit, stats) != 0) {
        m->stuck = 1;
        m->tick++;
        return;
    }
    m->pos[0] = hit.pos[0];
    m->pos[1] = hit.pos[1];
    m->pos[2] = hit.pos[2] - MOVE_RADIUS;
    m->vel[0] = hit.vel[0];
    m->vel[1] = hit.vel[1];
    m->vel[2] = hit.vel[2];
    m->grounded = hit.grounded;
    if (hit.grounded) memcpy(m->ground, hit.normal, sizeof m->ground);
    center[0] = hit.pos[0];
    center[1] = hit.pos[1];
    center[2] = hit.pos[2] + pill_height(m->crouch) * 0.5f;
    if (!hit.grounded && !collide_point_empty(bsp, center)) {
        m->pos[0] = m->last_safe[0];
        m->pos[1] = m->last_safe[1];
        m->pos[2] = m->last_safe[2];
        m->vel[0] = m->vel[1] = m->vel[2] = 0.0f;
        m->out_of_world = 1;
        m->stuck = 1;
    } else {
        m->last_safe[0] = m->pos[0];
        m->last_safe[1] = m->pos[1];
        m->last_safe[2] = m->pos[2];
        m->out_of_world = 0;
        m->stuck = 0;
    }
    m->tick++;
}
