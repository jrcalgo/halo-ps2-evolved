#include "game/shot.h"
#include <math.h>
#include <stdio.h>
#include <string.h>

static void clear_scene(shot_scene *scene)
{
    memset(scene, 0, sizeof *scene);
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
    static const float directions[6][3] = {
        {0, 0, 1}, {0, 1, 0}, {1, 0, 0}, {0, -1, 0}, {-1, 0, 0}, {0, 0, -1}
    };
    shot_cone cone = {0.0f, 0.1745329201221466f, 0.1745329201221466f, 0};
    shot_cone ramp = {0.0f, 0.0872664600610733f, 0.1745329201221466f, 0};
    float axis[3] = {1.0f, 0.0f, 0.0f}, spread[3];
    uint32_t spread_seed = 1;
    uint32_t lower_seed = 1, upper_seed = 1;
    float lower[3], upper[3];
    shot pool[2];
    memset(pool, 0, sizeof pool);
    fly(&SHOT_PISTOL, "pistol");
    fly(&SHOT_ASSAULT_RIFLE, "rifle");
    plane_hit(&SHOT_PISTOL, 0, "pistol_stop");
    plane_hit(&SHOT_PISTOL, 9, "pistol_through");
    plane_hit(&SHOT_PISTOL, 32, "pistol_bounce");
    {
        shot_def detonating = SHOT_ASSAULT_RIFLE;
        detonating.response[11] = 1;
        plane_hit(&detonating, 11, "detonate_response");
    }
    {
        shot_def guided = SHOT_PISTOL;
        shot s;
        shot_scene scene;
        uint32_t seed = 0x12345678u;
        float origin[3] = {0, 0, 0}, forward[3] = {1, 0, 0};
        guided.velocity_bits = 0x41200000u;
        guided.guided_angular_velocity = 1.57079637f;
        clear_scene(&scene);
        scene.guidance_target = 1;
        scene.target_center[0] = 1.0f;
        scene.target_center[1] = 1.0f;
        shot_spawn(&s, origin, forward, &guided);
        shot_tick(&s, &guided, &scene, &seed);
        printf("guided_near %.6f %.6f %.6f\n", s.velocity[0], s.velocity[1], s.position[0]);
        scene.target_center[0] = 2.5f;
        scene.target_center[1] = 1.0f;
        shot_spawn(&s, origin, forward, &guided);
        shot_tick(&s, &guided, &scene, &seed);
        printf("guided_wander_open %.6f %.6f\n", s.velocity[0], s.velocity[1]);
    }
    {
        shot_def potential = SHOT_PISTOL;
        shot s;
        shot_scene scene;
        uint32_t seed = 0x31415926u;
        float origin[3] = {0, 0, 0}, forward[3] = {1, 0, 0};
        potential.response[11] = 2;
        potential.potential_response[11] = 1;
        potential.potential_flags[11] = 1;
        clear_scene(&scene);
        scene.target = 1;
        scene.target_center[0] = 5.0f;
        scene.target_radius = 0.5f;
        scene.target_material = 11;
        shot_spawn(&s, origin, forward, &potential);
        shot_tick(&s, &potential, &scene, &seed);
        printf("potential_nonunit %d %d %08x\n", s.alive, s.action, seed);
        seed = 0x31415926u;
        scene.target_is_unit = 1;
        shot_spawn(&s, origin, forward, &potential);
        shot_tick(&s, &potential, &scene, &seed);
        printf("potential_unit %d %d %08x\n", s.alive, s.action, seed);
    }
    {
        static const float noise_directions[2][3] = {{0, 1, 0}, {0, 0, 1}};
        shot_def material = SHOT_PISTOL;
        shot s;
        shot_scene scene;
        uint32_t seed = 0x12345678u;
        float origin[3] = {0, 0, 0}, forward[3] = {1, 0, 0};
        material.response[11] = 2;
        material.parallel_friction[11] = 0.2f;
        material.perpendicular_friction[11] = 0.3f;
        material.angular_noise[11] = 0.1f;
        material.velocity_noise[11] = 0.1f;
        clear_scene(&scene);
        scene.plane = 1;
        scene.plane_normal[0] = 1.0f;
        scene.plane_d = 5.0f;
        scene.plane_material = 11;
        scene.directions = noise_directions;
        scene.direction_count = 2;
        shot_spawn(&s, origin, forward, &material);
        shot_tick(&s, &material, &scene, &seed);
        printf("material_reflect %d %d %.4f %.6f %.6f %08x\n", s.alive, s.action,
            s.position[0], s.velocity[0], s.velocity[1], seed);
    }
    body_hit(&SHOT_PISTOL, "pistol");
    body_hit(&SHOT_ASSAULT_RIFLE, "rifle");
    {
        shot_def slow = SHOT_PISTOL;
        shot s;
        shot_scene scene;
        uint32_t seed = 0x12345678u;
        float origin[3] = {0, 0, 0}, forward[3] = {1, 0, 0};
        slow.velocity_bits = 0x41200000u;
        slow.final_velocity = 0.0f;
        slow.deceleration_start = 0.0f;
        slow.deceleration_end = 10.0f;
        slow.maximum_range = 100.0f;
        slow.air_gravity_scale = 0.0f;
        slow.damage_minimum = 4.0f;
        slow.damage_lower = slow.damage_upper = 10.0f;
        clear_scene(&scene);
        scene.target = 1;
        scene.target_center[0] = 4.0f;
        scene.target_radius = 0.5f;
        shot_spawn(&s, origin, forward, &slow);
        shot_tick(&s, &slow, &scene, &seed);
        printf("scaled_damage %.3f %.3f %08x\n", s.damage,
            sqrtf(s.velocity[0] * s.velocity[0] + s.velocity[1] * s.velocity[1] +
                  s.velocity[2] * s.velocity[2]), seed);
    }
    {
        shot_def crossing = SHOT_PISTOL;
        shot s;
        shot_scene scene;
        uint32_t seed = 1u;
        float origin[3] = {0, 0, 0}, forward[3] = {1, 0, 0};
        crossing.velocity_bits = 0x41200000u;
        crossing.final_velocity = 8.0f;
        crossing.deceleration_start = 0.0f;
        crossing.deceleration_end = 1.0f;
        crossing.maximum_range = 100.0f;
        crossing.air_gravity_scale = 0.0f;
        clear_scene(&scene);
        shot_spawn(&s, origin, forward, &crossing);
        shot_tick(&s, &crossing, &scene, &seed);
        printf("decel_cross %.6f %.6f\n", s.position[0], s.velocity[0]);
        shot_tick(&s, &crossing, &scene, &seed);
        printf("decel_floor %.6f %.6f\n", s.position[0], s.velocity[0]);
    }
    {
        shot_def no_lifetime = SHOT_PISTOL;
        shot s;
        shot_scene scene;
        uint32_t seed = 1u;
        float origin[3] = {0, 0, 0}, forward[3] = {1, 0, 0};
        no_lifetime.velocity_bits = 0x41200000u;
        no_lifetime.final_velocity = 8.0f;
        no_lifetime.deceleration_start = 0.0f;
        no_lifetime.deceleration_end = 1.0f;
        no_lifetime.maximum_range = 0.0f;
        no_lifetime.timer_upper_bound = 0.0f;
        no_lifetime.minimum_velocity = 0.0f;
        no_lifetime.maximum_damage_distance = 100.0f;
        no_lifetime.air_gravity_scale = 0.0f;
        clear_scene(&scene);
        shot_spawn(&s, origin, forward, &no_lifetime);
        shot_tick(&s, &no_lifetime, &scene, &seed);
        shot_tick(&s, &no_lifetime, &scene, &seed);
        printf("decel_no_lifetime %d %d %.6f\n", s.alive, s.action, s.position[0]);
    }
    {
        shot_def fuel_rod = SHOT_PISTOL;
        shot s;
        shot_scene scene;
        uint32_t seed = 1u;
        float origin[3] = {0, 0, 0}, forward[3] = {1, 0, 0};
        int ticks = 0;
        fuel_rod.velocity_bits = 0x3eeeeef0u;
        fuel_rod.final_velocity = 0.1666666716f;
        fuel_rod.deceleration_start = 0.0f;
        fuel_rod.deceleration_end = 100.0f;
        fuel_rod.maximum_range = 0.0f;
        fuel_rod.maximum_damage_distance = 10.0f;
        fuel_rod.air_gravity_scale = 1.0f;
        fuel_rod.water_gravity_scale = 0.4f;
        fuel_rod.water_damage_range_lower_bound = 0.0f;
        fuel_rod.water_damage_range_upper_bound = 10.0f;
        fuel_rod.minimum_velocity = 0.0f;
        fuel_rod.damage_minimum = fuel_rod.damage_lower = fuel_rod.damage_upper = 0.0f;

        clear_scene(&scene);
        shot_spawn(&s, origin, forward, &fuel_rod);
        shot_tick(&s, &fuel_rod, &scene, &seed);
        printf("fuel_air_first %.8f %.8f %.8f %.8f\n", s.velocity[0],
            s.position[0], s.velocity[2], s.position[2]);
        clear_scene(&scene);
        scene.underwater = 1;
        shot_spawn(&s, origin, forward, &fuel_rod);
        shot_tick(&s, &fuel_rod, &scene, &seed);
        printf("fuel_water_first %.8f %.8f %.8f %.8f\n", s.velocity[0],
            s.position[0], s.velocity[2], s.position[2]);
        ticks = 1;
        while (s.alive && ticks < 1000) {
            shot_tick(&s, &fuel_rod, &scene, &seed);
            ticks++;
        }
        printf("fuel_water_end %d %.8f %d\n", ticks, s.odometer, s.action);

        clear_scene(&scene);
        shot_spawn(&s, origin, forward, &fuel_rod);
        for (ticks = 0; ticks < 10; ++ticks) shot_tick(&s, &fuel_rod, &scene, &seed);
        scene.underwater = 1;
        shot_tick(&s, &fuel_rod, &scene, &seed);
        printf("fuel_transition %d %d %.8f %.8f %.8f\n", s.underwater, s.alive,
            s.velocity[0], s.velocity[2], s.position[2]);
    }
    {
        shot_def piercing = SHOT_ASSAULT_RIFLE;
        shot s;
        shot_scene scene;
        uint32_t seed = 0x12345678u;
        float origin[3] = {0, 0, 0}, forward[3] = {1, 0, 0};
        piercing.response[11] = 3; /* CE overpenetrate */
        piercing.initial_friction[11] = 0.7f;
        piercing.air_gravity_scale = 0.0f;
        clear_scene(&scene);
        scene.target = 1;
        scene.target_center[0] = 5.0f;
        scene.target_radius = 0.5f;
        scene.target_material = 11;
        shot_spawn(&s, origin, forward, &piercing);
        shot_tick(&s, &piercing, &scene, &seed);
        printf("pierce_friction %d %d %d %.5f %.5f %08x\n", s.alive,
            s.ignore_target, s.hit_object_this_tick, s.velocity[0], s.position[0], seed);
    }
    shot_random_cone(axis, directions, 6, &cone, 0.0f, &spread_seed, spread);
    printf("spread %.9f %.9f %.9f %08x\n", spread[0], spread[1], spread[2], spread_seed);
    shot_random_cone(axis, directions, 6, &ramp, 0.0f, &lower_seed, lower);
    shot_random_cone(axis, directions, 6, &ramp, 1.0f, &upper_seed, upper);
    printf("error_angle %.6f %.6f %08x %08x\n", acosf(lower[0]) * 57.2957795f,
        acosf(upper[0]) * 57.2957795f, lower_seed, upper_seed);
    printf("pool %d ", shot_pool_find_free(pool, 2));
    pool[0].alive = 1;
    printf("%d ", shot_pool_find_free(pool, 2));
    pool[1].alive = 1;
    printf("%d %d\n", shot_pool_find_free(pool, 2), shot_pool_find_free(0, 2));
    {
        shot saturated[2];
        const shot_def *defs[2] = {0, 0};
        shot_cone identical = {0.0f, 0.0872664600610733f, 0.1745329201221466f, 1u << 12};
        float origin[3] = {0, 0, 0}, first[3], sample[3];
        uint32_t actual_seed = 0x10203040u, expected_seed = actual_seed;
        int dropped = 0, spawned, i;
        memset(saturated, 0, sizeof saturated);
        saturated[0].alive = 1;
        for (i = 0; i < 4; ++i) {
            shot_random_cone(axis, directions, 6, &identical, 0.5f,
                             &expected_seed, sample);
            if (i == 0) memcpy(first, sample, sizeof first);
            if (i == 0)
                expected_seed = expected_seed * 1664525u + 1013904223u;
        }
        /* The one successful object_new invokes projectile_new immediately
         * after pellet zero; three failed allocations have no timer draw. */
        spawned = shot_pool_spawn_cone(saturated, defs, 2, &SHOT_PISTOL, origin, axis,
            4, directions, 6, &identical, 0.5f, 0, 0.0f, &actual_seed, &dropped);
        printf("saturated %d %d %d %08x %08x %.7f %.7f %.7f %.7f %.7f %.7f\n", spawned,
            dropped, saturated[1].alive, actual_seed, expected_seed,
            saturated[1].velocity[0], saturated[1].velocity[1], saturated[1].velocity[2],
            first[0] * 10.0f, first[1] * 10.0f, first[2] * 10.0f);
    }
    {
        shot fan[4];
        const shot_def *defs[4] = {0, 0, 0, 0};
        float origin[3] = {0, 0, 0};
        uint32_t fan_seed = 123u;
        int dropped = 0, spawned, i;
        memset(fan, 0, sizeof fan);
        spawned = shot_pool_spawn_cone(fan, defs, 4, &SHOT_PISTOL, origin, axis,
            4, 0, 0, 0, 0.0f, 1, 0.1745329201221466f, &fan_seed, &dropped);
        printf("fan %d %d %08x", spawned, dropped, fan_seed);
        for (i = 0; i < 4; ++i)
            printf(" %.7f %.7f", fan[i].velocity[0], fan[i].velocity[1]);
        putchar('\n');
    }
    {
        collide_bsp bsp;
        const int16_t types[3] = {7, 26, -1};
        memset(&bsp, 0, sizeof bsp);
        bsp.material_types = types;
        bsp.material_count = 3;
        printf("runtime_material %d %d %d %d %d\n",
            collide_material_type(&bsp, 0),
            collide_material_type(&bsp, 1),
            collide_material_type(&bsp, 2),
            collide_material_type(&bsp, -1),
            collide_material_type(&bsp, 3));
    }
    return 0;
}
