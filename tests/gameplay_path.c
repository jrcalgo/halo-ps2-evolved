/* Record the player eye along a short Blood Gulch bout.
 * Lines are pathkey fields: seconds x y z yaw_deg pitch_deg. */
#include "game/collpack.h"
#include "game/move.h"
#include "game/pad.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t *slurp(const char *path, size_t *size)
{
    FILE *f = fopen(path, "rb");
    long n;
    uint8_t *bytes;
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) return NULL;
    n = ftell(f);
    if (n < 0 || fseek(f, 0, SEEK_SET) != 0) return NULL;
    bytes = malloc((size_t)n);
    if (!bytes || fread(bytes, 1, (size_t)n, f) != (size_t)n) return NULL;
    fclose(f);
    *size = (size_t)n;
    return bytes;
}

static void eye_line(const mover *body, float yaw, float pitch, uint32_t tick)
{
    printf("%.3f %.4f %.4f %.4f %.4f %.4f\n",
        (float)tick / (float)MOVE_TICKS_PER_SECOND,
        body->pos[0], body->pos[1], body->pos[2] + body->eye,
        yaw * 57.2957795f, pitch * 57.2957795f);
}

int main(int argc, char **argv)
{
    size_t pack_size, coll_size, tag_size, scratch_bytes;
    const uint8_t *coll, *tag;
    uint8_t *pack, *scratch;
    collide_bsp bsp;
    float pose[4], tags[COLL_TAG_FLOATS], yaw, pitch;
    mover body;
    collide_pill_stats stats;
    pad_state pad;
    move_cmd cmd;
    uint32_t tick;
    if (argc != 3) return 2;
    pack = slurp(argv[1], &pack_size);
    if (!pack) return 1;
    if (collpack_section(pack, pack_size, "COLL", &coll, &coll_size) != 0) return 1;
    if (collpack_section(pack, pack_size, "TAGS", &tag, &tag_size) != 0) return 1;
    if (collpack_collision(coll, coll_size, &bsp) != 0) return 1;
    if (collpack_spawn(coll, 0, pose) != 0) return 1;
    if (collpack_tags(tag, tag_size, tags) != 0) return 1;
    (void)tags;
    scratch_bytes = collide_pill_scratch_bytes();
    scratch = malloc(scratch_bytes);
    if (!scratch) return 1;
    player_spawn(&body, pose, &yaw, &pitch);
    eye_line(&body, yaw, pitch, 0);
    for (tick = 1; tick <= 90; tick++) {
        memset(&pad, 0, sizeof pad);
        if (strcmp(argv[2], "walk") == 0 && tick >= 20)
            pad.left_y = 32767;
        else if (strcmp(argv[2], "jump") == 0 && tick == 50)
            pad.cross = 1;
        else if (strcmp(argv[2], "crouch") == 0 && tick >= 70)
            pad.circle = 1;
        else if (strcmp(argv[2], "turn") == 0 && tick >= 20)
            pad.right_x = 32767;
        else if (strcmp(argv[2], "walk") != 0 && strcmp(argv[2], "jump") != 0 &&
                 strcmp(argv[2], "crouch") != 0 && strcmp(argv[2], "turn") != 0)
            return 2;
        pad_to_command(&pad, &cmd, &yaw, &pitch);
        mover_tick_map(&body, &cmd, yaw, &bsp, scratch, scratch_bytes, 0, &stats);
        if (tick % 5 == 0) eye_line(&body, yaw, pitch, tick);
    }
    return 0;
}
