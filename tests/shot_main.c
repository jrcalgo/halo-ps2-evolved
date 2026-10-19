#include "game/shot.h"
#include <stdio.h>

static void clear_scene(shot_scene *scene)
{
    int i;
    scene->bsp = 0;
    scene->plane = 0;
    scene->target = 0;
    scene->plane_d = 0;
    scene->plane_material = 0;
    scene->target_radius = 0;
    scene->target_material = 0;
    for (i = 0; i < 3; i++) {
        scene->plane_normal[i] = 0;
        scene->target_center[i] = 0;
    }
}

static void fly(const shot_def *def, const char *name)
{
    shot s;
    shot_scene scene;
    uint32_t seed = 0x12345678u;
    float origin[3] = {0, 0, 0};
    float forward[3] = {1, 0, 0};
    int tick = 0;
    clear_scene(&scene);
    shot_spawn(&s, origin, forward, def);
    shot_tick(&s, def, &scene, &seed);
    printf("%s first %.9f %.9f %.9f %.9f\n", name, s.position[0], s.position[2], s.velocity[0], s.velocity[2]);
    while (s.alive && tick < 8) {
        shot_tick(&s, def, &scene, &seed);
        tick++;
    }
    printf("%s range %d %.6f %d\n", name, tick, s.odometer, s.action);
}

static void plane_hit(const shot_def *def, int material, const char *name)
{
    shot s;
    shot_scene scene;
    uint32_t seed = 0x12345678u;
    float origin[3] = {0, 0, 0};
    float forward[3] = {1, 0, 0};
    clear_scene(&scene);
    scene.plane = 1;
    scene.plane_normal[0] = 1;
    scene.plane_d = 5;
    scene.plane_material = (int16_t)material;
    shot_spawn(&s, origin, forward, def);
    shot_tick(&s, def, &scene, &seed);
    printf("%s plane %d %d %.4f %.4f %.4f %08x\n",
        name, s.alive, s.action, s.position[0], s.velocity[0], s.velocity[2], seed);
}

static void body_hit(const shot_def *def, const char *name)
{
    shot s;
    shot_scene scene;
    uint32_t seed = 0x12345678u;
    float origin[3] = {0, 0, 0};
    float forward[3] = {1, 0, 0};
    clear_scene(&scene);
    scene.target = 1;
    scene.target_center[0] = 5;
    scene.target_radius = 0.5f;
    shot_spawn(&s, origin, forward, def);
    shot_tick(&s, def, &scene, &seed);
    printf("%s body %d %.1f %.3f %08x\n", name, s.alive, s.damage, s.position[0], seed);
}

int main(void)
{
    fly(&SHOT_PISTOL, "pistol");
    fly(&SHOT_ASSAULT_RIFLE, "rifle");
    plane_hit(&SHOT_PISTOL, 0, "pistol_stop");
    plane_hit(&SHOT_PISTOL, 9, "pistol_through");
    plane_hit(&SHOT_PISTOL, 32, "pistol_bounce");
    body_hit(&SHOT_PISTOL, "pistol");
    body_hit(&SHOT_ASSAULT_RIFLE, "rifle");
    return 0;
}
