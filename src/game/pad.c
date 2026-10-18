#include "game/pad.h"

int pad_apply_dead_zone(int value)
{
    if (value > PAD_DEAD_ZONE)
        return (value - PAD_DEAD_ZONE) * PAD_STICK_MAX / (PAD_STICK_MAX - PAD_DEAD_ZONE);
    if (value < -PAD_DEAD_ZONE)
        return (value + PAD_DEAD_ZONE) * PAD_STICK_MIN / (PAD_STICK_MIN + PAD_DEAD_ZONE);
    return 0;
}

static float stick(int value)
{
    return (float)pad_apply_dead_zone(value) / (float)PAD_STICK_MAX;
}

void pad_to_command(const pad_state *pad, move_cmd *cmd, float *yaw, float *pitch)
{
    float look = stick(pad->right_y);
    cmd->move_x = stick(pad->left_y);
    cmd->move_y = stick(-pad->left_x);
    cmd->jump = pad->cross;
    cmd->crouch = pad->circle;
    *yaw += stick(pad->right_x) * (PAD_YAW_DEGREES_PER_SECOND / MOVE_TICKS_PER_SECOND) * 0.01745329252f;
    if (pad->invert_look) look = -look;
    *pitch += look * (PAD_PITCH_DEGREES_PER_SECOND / MOVE_TICKS_PER_SECOND) * 0.01745329252f;
    if (*pitch > 1.5533f) *pitch = 1.5533f;
    if (*pitch < -1.5533f) *pitch = -1.5533f;
}
