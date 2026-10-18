#include "game/pad.h"
#include <assert.h>
#include <math.h>

int main(void)
{
    move_cmd cmd;
    float yaw = 0.0f, pitch = 0.0f;
    pad_state pad = {0, 32767, 32767, 32767, 1, 1, 0};
    assert(pad_apply_dead_zone(9000) == 0);
    assert(pad_apply_dead_zone(-9000) == 0);
    assert(pad_apply_dead_zone(32767) == 32767);
    assert(pad_apply_dead_zone(-32768) == -32768);
    pad_to_command(&pad, &cmd, &yaw, &pitch);
    assert(cmd.jump == 1 && cmd.crouch == 1);
    assert(cmd.move_x > 0.99f);
    assert(fabsf(yaw - (120.0f / 30.0f) * 0.01745329252f) < 1.0e-5f);
    assert(pitch > 0.0f);
    pitch = 0.0f;
    pad.invert_look = 1;
    pad_to_command(&pad, &cmd, &yaw, &pitch);
    assert(pitch < 0.0f);
    return 0;
}
