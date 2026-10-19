/* One pistol shot straight down from the first Blood Gulch spawn eye. */
#include "game/collpack.h"
#include "game/gun.h"
#include "game/move.h"
#include "game/shot.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static uint8_t *load_file(const char *path, size_t *size)
{
    FILE *file = fopen(path, "rb");
    long length;
    uint8_t *bytes;
    if (!file) return NULL;
    if (fseek(file, 0, SEEK_END) != 0) { fclose(file); return NULL; }
    length = ftell(file);
    if (length <= 0 || fseek(file, 0, SEEK_SET) != 0) { fclose(file); return NULL; }
    bytes = malloc((size_t)length);
    if (!bytes || fread(bytes, 1, (size_t)length, file) != (size_t)length) {
        free(bytes);
        fclose(file);
        return NULL;
    }
    fclose(file);
    *size = (size_t)length;
    return bytes;
}

int main(int argc, char **argv)
{
    size_t pack_size, coll_size, tag_size;
    const uint8_t *coll, *tag;
    uint8_t *pack;
    collide_bsp bsp;
    mover body;
    gun weapon;
    shot bullet;
    shot_scene scene;
    uint32_t seed = 1;
    float pose[4], tags[COLL_TAG_FLOATS], yaw, pitch;
    float origin[3], down[3] = {0, 0, -1};
    int ticks = 0;
    if (argc != 2) return 1;
    pack = load_file(argv[1], &pack_size);
    if (!pack) return 1;
    if (collpack_section(pack, pack_size, "COLL", &coll, &coll_size) != 0 ||
        collpack_collision(coll, coll_size, &bsp) != 0 ||
        collpack_spawn(coll, 0, pose) != 0 ||
        collpack_section(pack, pack_size, "TAGS", &tag, &tag_size) != 0 ||
        collpack_tags(tag, tag_size, tags) != 0)
        return 1;
    (void)tags;
    player_spawn(&body, pose, &yaw, &pitch);
    gun_init(&weapon, &GUN_PISTOL);
    if (!gun_tick(&weapon, &GUN_PISTOL, 1, 0)) return 1;
    origin[0] = body.pos[0];
    origin[1] = body.pos[1];
    origin[2] = body.pos[2] + body.eye;
    shot_spawn(&bullet, origin, down, &SHOT_PISTOL);
    memset(&scene, 0, sizeof scene);
    scene.bsp = &bsp;
    while (bullet.alive && ticks < 8) {
        shot_tick(&bullet, &SHOT_PISTOL, &scene, &seed);
        ticks++;
    }
    printf("pistol_world %s ticks %d loaded %d gap %.3f z %.3f eye %.3f\n",
        bullet.hit_surface ? "hit" : "miss", ticks, weapon.loaded,
        origin[2] - bullet.position[2], bullet.position[2], origin[2]);
    free(pack);
    return bullet.hit_surface ? 0 : 1;
}
