/* DualShock binding for one local player.
 * Dead zone is input_xbox.c GAMEPAD_STICK_DEAD_RANGE (9000).
 * Look rates are player_ui.c sensitivity 3, the profile default:
 * yaw 120 degrees/second, pitch 60. Invert look defaults off.
 * Cross is jump. Circle is crouch. */
#ifndef GAME_PAD_H
#define GAME_PAD_H
#include "game/move.h"
#include <stdint.h>

#define PAD_DEAD_ZONE 9000
#define PAD_STICK_MAX 32767
#define PAD_STICK_MIN (-32768)
#define PAD_LOOK_SENSITIVITY 3
#define PAD_YAW_DEGREES_PER_SECOND 120.0f
#define PAD_PITCH_DEGREES_PER_SECOND 60.0f

typedef struct {
    int16_t left_x, left_y, right_x, right_y;
    int cross;
    int circle;
    int invert_look;
} pad_state;

int pad_apply_dead_zone(int value);

/* Fills cmd. Adds look radians to *yaw and *pitch. Pitch is clamped. */
void pad_to_command(const pad_state *pad, move_cmd *cmd, float *yaw, float *pitch);
#endif
