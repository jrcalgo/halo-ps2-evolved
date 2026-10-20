/* Replaces the free camera when this object is linked.
 * The pad steps the collision biped and the view is its eye. */
#include "game/collpack.h"
#include "game/combat_targets.h"
#include "game/gun.h"
#include "game/grenade.h"
#include "game/move.h"
#include "game/pad.h"
#include "game/play_fp.h"
#include "game/shot.h"
#include "game/vital.h"
#include "core/mat.h"
#include "sim/objects.h"
#include "sim/skeleton.h"
#include "world/model.h"
#include "platform/profiler.h"
#include "platform/timer.h"
#include "render/bsp_render.h"
#include "render/camera.h"
#include "render/flycam.h"
#include <libpad.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

void __real_flycam_update(camera_t *cam, const fly_input *in, float dt);
void __real_objects_tick(object_table_t *table, const object_world_t *world);

static uint8_t *s_pack;
static collide_bsp s_bsp;
static collide_location_view s_location;
static mover s_body;
static float s_yaw, s_pitch;
static void *s_scratch;
static size_t s_scratch_bytes;
static int s_ready;
static int s_failed;
static int s_was_out;
static collide_pill_stats s_last;
#define PLAY_FLY 16
#define PLAY_GRENADE_CAPACITY GRENADE_CARRY_MAX
#define PLAY_WEAPON_SLOTS 32

static gun s_gun;
static gun_trigger_pair s_trigger_pair;
static gun_trigger_profile s_trigger_profile[GUN_TRIGGER_MAX];
static int s_trigger_pair_active;
static gun s_gun_saved[PLAY_WEAPON_SLOTS];
static gun_trigger_pair s_trigger_pair_saved[PLAY_WEAPON_SLOTS];
static uint8_t s_weapon_runtime_ready[PLAY_WEAPON_SLOTS];
static uint8_t s_pair_runtime_ready[PLAY_WEAPON_SLOTS];
static int s_active_weapon_slot = -1;
static shot s_fly[PLAY_FLY];
static const shot_def *s_fly_def[PLAY_FLY];
static grenade s_grenades[PLAY_GRENADE_CAPACITY];
static int s_grenades_carried;
static uint8_t s_grenade_button;
static uint8_t s_freecam_button;
static int s_freecam_mode;
/* Fixed combat probe target: exercises the EE projectile→vitality handoff.
 * It is not an AI actor or a retail object-damage implementation. */
static vital s_probe_target;
static vital_damage_profile s_probe_damage_profile;
static collpack_actor_collision_view s_actor_collision;
static float s_probe_node_to_world[64][12];
static int16_t s_probe_body_damage_material_type = 21;
static int16_t s_probe_shield_damage_material_type = 22;
static float s_probe_target_center[3];
static uint32_t s_seed = 1;
static uint32_t s_play_sim_tick;
static int s_shotgun_state_loaded = -1;
static int s_shotgun_state_total = -1;
static int s_shotgun_state_magazine = -1;
static int s_mark; /* 0 none, 1 flying, 2 surface, 3 range */
static int s_triangle;
static float s_shot_tick_time_sum_ms;
static float s_shot_tick_time_max_ms;
static float s_shot_tick_time_max_tick_ms;
static unsigned s_shot_tick_samples;
static unsigned s_shot_tick_max_calls;
/* The engine owns these fixed-lifetime objects. Capturing them after its tick
 * lets the following play callback inspect the pose rendered on the prior
 * frame without reaching into main.c's private statics. */
static object_table_t *s_engine_objects;
static const object_world_t *s_engine_object_world;
static unsigned s_engine_object_tick;
static object_nodes_t s_live_actor_pose;
static float s_live_actor_node_to_world[64][12];
static vital s_live_actor_vital;
static int s_live_actor_vital_ready;
static int s_live_actor_index = -1;
static int s_live_actor_def = -1;
static float s_live_actor_center[3];
static unsigned s_live_actor_pose_tick;
static combat_target_registry s_combat_targets;
static float s_combat_target_matrices[COMBAT_TARGET_MAX][COMBAT_TARGET_MAX_NODES][12];
static object_nodes_t s_combat_target_workspace;
static shot_target_view s_combat_target_views[COMBAT_TARGET_MAX];
static unsigned s_combat_target_view_count;

static int play_actor_bind_pose(void)
{
    static skel_xform local[64];
    static int16_t parent[64];
    static mat4 world[64];
    mat4 root;
    unsigned node, row, column;
    float origin[3] = {0.0f, 0.0f, 0.0f}, minimum[3], maximum[3];
    float center[3], offset[3], feet[3];
    mat4_from_ypr(&root, s_yaw + 3.14159265359f, 0.0f, 0.0f, origin);
    for (node = 0; node < s_actor_collision.node_count; node++) {
        const uint8_t *record = s_actor_collision.nodes + node * s_actor_collision.node_stride;
        memcpy(&parent[node], record + 2, sizeof parent[node]);
        memcpy(local[node].trans, record + 4, sizeof local[node].trans);
        memcpy(local[node].rot, record + 16, sizeof local[node].rot);
        local[node].scale = 1.0f;
    }
    if (skel_world(world, local, parent, s_actor_collision.node_count, &root) != 0) return -1;
    for (row = 0; row < 3; row++) {
        minimum[row] = 1.0e20f;
        maximum[row] = -1.0e20f;
    }
    for (row = 0; row < s_actor_collision.triangle_count; row++) {
        const uint8_t *triangle = s_actor_collision.triangles + row * s_actor_collision.triangle_stride;
        int16_t triangle_node;
        unsigned vertex, axis;
        memcpy(&triangle_node, triangle, sizeof triangle_node);
        if (triangle_node < 0 || triangle_node >= (int16_t)s_actor_collision.node_count) return -1;
        for (vertex = 0; vertex < 3; vertex++) {
            float point[3], transformed[3];
            memcpy(point, triangle + 10 + vertex * 12, sizeof point);
            mat4_transform_point(&world[triangle_node], point, transformed);
            for (axis = 0; axis < 3; axis++) {
                if (transformed[axis] < minimum[axis]) minimum[axis] = transformed[axis];
                if (transformed[axis] > maximum[axis]) maximum[axis] = transformed[axis];
            }
        }
    }
    for (row = 0; row < 3; row++) center[row] = (minimum[row] + maximum[row]) * 0.5f;
    mat4_transform_dir(&root, center, offset);
    for (row = 0; row < 3; row++) feet[row] = s_probe_target_center[row] - offset[row];
    root.m[3][0] = feet[0]; root.m[3][1] = feet[1]; root.m[3][2] = feet[2];
    if (skel_world(world, local, parent, s_actor_collision.node_count, &root) != 0) return -1;
    for (node = 0; node < s_actor_collision.node_count; node++) {
        for (row = 0; row < 3; row++) {
            for (column = 0; column < 3; column++)
                s_probe_node_to_world[node][row * 4 + column] = world[node].m[column][row];
            s_probe_node_to_world[node][row * 4 + 3] = world[node].m[3][row];
        }
    }
    return 0;
}

void __wrap_objects_tick(object_table_t *table, const object_world_t *world)
{
    __real_objects_tick(table, world);
    s_engine_objects = table;
    s_engine_object_world = world;
    s_engine_object_tick++;
}

/* The current actor pack is deliberately cyborg-only. Bind it only to the
 * scenario's declared player biped after confirming its model tag and node
 * count; never silently collide arbitrary bipeds against this mesh. */
static int play_pose_live_player_actor(void)
{
    scen_player player;
    unsigned i, node, row, column, placed_count, skipped_count;
    if (!s_engine_objects || !s_engine_object_world || !s_engine_object_world->scen ||
        !s_engine_object_world->models || s_engine_object_tick == 0) return 0;
    if (s_live_actor_pose_tick == s_engine_object_tick) return s_live_actor_index >= 0;
    s_live_actor_pose_tick = s_engine_object_tick;
    s_live_actor_index = -1;
    player = scen_get_player(s_engine_object_world->scen);
    if (player.biped_def == 0) return 0;
    skipped_count = s_engine_objects->skipped_no_model + s_engine_objects->skipped_hidden +
        s_engine_objects->skipped_cap + s_engine_objects->skipped_other_bsp;
    if (skipped_count > s_engine_object_world->scen->placement_count) return 0;
    placed_count = s_engine_object_world->scen->placement_count - skipped_count;
    for (i = placed_count;
         i < s_engine_objects->count; i++) {
        object_t *object = &s_engine_objects->obj[i];
        scen_def definition;
        model_info model;
        unsigned count;
        if (object->type != SCEN_BIPED || object->def < 0 ||
            (uint32_t)object->def + 1u != player.biped_def || object->model < 0) continue;
        definition = scen_get_def(s_engine_object_world->scen, (uint32_t)object->def);
        model = model_get(s_engine_object_world->models, (uint32_t)object->model);
        if (model.tag_id == 0 || model.tag_id != definition.model_tag ||
            model.node_count != s_actor_collision.node_count) continue;
        /* The actor-ray diagnostic uses chiefcam's appended scenario-player
         * object. Keep it in the clear one unit in front of the collision
         * player, before the spawn-adjacent BSP lip; ordinary placed actors
         * are excluded by the counted placed-object lower bound above. */
        object->pos[0] = s_body.pos[0] + cosf(s_yaw) * 1.0f;
        object->pos[1] = s_body.pos[1] + sinf(s_yaw) * 1.0f;
        object->pos[2] = s_body.pos[2];
        object->root.m[3][0] = object->pos[0];
        object->root.m[3][1] = object->pos[1];
        object->root.m[3][2] = object->pos[2];
        count = objects_pose(object, s_engine_object_world, &s_live_actor_pose);
        if (count != s_actor_collision.node_count || count > 64) continue;
        for (node = 0; node < count; node++) {
            for (row = 0; row < 3; row++) {
                for (column = 0; column < 3; column++)
                    s_live_actor_node_to_world[node][row * 4 + column] =
                        s_live_actor_pose.world[node].m[column][row];
                s_live_actor_node_to_world[node][row * 4 + 3] =
                    s_live_actor_pose.world[node].m[3][row];
            }
        }
        s_live_actor_index = (int)i;
        s_live_actor_def = object->def;
        memcpy(s_live_actor_center, object->pos, sizeof s_live_actor_center);
        if (!s_live_actor_vital_ready) {
            vital_init(&s_live_actor_vital);
            s_live_actor_vital_ready = 1;
            printf("[play] live-actor object %d def %d model-tag %08lx nodes %u pos %.3f %.3f %.3f\n",
                s_live_actor_index, s_live_actor_def, (unsigned long)model.tag_id, count,
                object->pos[0], object->pos[1], object->pos[2]);
        }
        return 1;
    }
    return 0;
}

static combat_target *play_combat_target_find(int object_index)
{
    unsigned i;
    if (object_index < 0) return NULL;
    for (i = 0; i < s_combat_targets.count; i++)
        if (s_combat_targets.target[i].object_index == (uint16_t)object_index)
            return &s_combat_targets.target[i];
    return NULL;
}

static int play_resolve_combat_target(void *user, uint32_t object_tag_id,
    uint32_t model_tag_id, combat_target_definition *out)
{
    const scen_section *scen = (const scen_section *)user;
    scen_player player;
    scen_def player_definition;
    if (!scen || !out) return -1;
    player = scen_get_player(scen);
    if (player.biped_def == 0 || player.biped_def > scen->def_count) return -1;
    player_definition = scen_get_def(scen, player.biped_def - 1u);
    /* The currently exported ACOL/VITA pair is cyborg-only. Match both object
     * and model tag identities; node-count coincidence alone is insufficient. */
    if (player_definition.type != SCEN_BIPED ||
        object_tag_id != player_definition.tag_id ||
        model_tag_id != player_definition.model_tag ||
        !s_actor_collision.node_count || !s_probe_damage_profile.maximum_body)
        return -1;
    out->mesh = &s_actor_collision;
    out->vitality = &s_probe_damage_profile;
    out->body_damage_material_type = s_probe_body_damage_material_type;
    out->shield_damage_material_type = s_probe_shield_damage_material_type;
    return 0;
}

static void play_update_combat_targets(void)
{
    unsigned i;
    if (!s_engine_objects || !s_engine_object_world || !s_engine_object_world->scen) {
        s_combat_target_view_count = 0;
        return;
    }
    combat_targets_update(&s_combat_targets, s_combat_target_matrices,
        s_engine_objects, s_engine_object_world, &s_combat_target_workspace,
        play_resolve_combat_target, (void *)s_engine_object_world->scen);
    s_combat_target_view_count = s_combat_targets.count;
    for (i = 0; i < s_combat_target_view_count; i++) {
        const combat_target *target = &s_combat_targets.target[i];
        shot_target_view *view = &s_combat_target_views[i];
        view->object_index = (int16_t)target->object_index;
        view->body_damage_material_type = target->body_damage_material_type;
        view->shield_damage_material_type = target->shield_damage_material_type;
        view->mesh = target->mesh;
        view->vitality_profile = target->profile;
        view->node_to_world = (const float (*)[12])target->node_to_world;
        memcpy(view->center, target->object->pos, sizeof view->center);
        memcpy(view->bounds_min, target->bounds_min, sizeof view->bounds_min);
        memcpy(view->bounds_max, target->bounds_max, sizeof view->bounds_max);
    }
    if (s_live_actor_vital_ready && s_live_actor_index >= 0) {
        combat_target *target = play_combat_target_find(s_live_actor_index);
        if (target) s_live_actor_vital = target->health;
    }
}

static void play_store_live_target_health(void)
{
    combat_target *target = play_combat_target_find(s_live_actor_index);
    if (target && s_live_actor_vital_ready) target->health = s_live_actor_vital;
}

static void play_select_weapon(void)
{
    const gun_def *def = play_fp_gun();
    const play_fp_weapon_trigger_policy *policy = play_fp_weapon_trigger_policy_get();
    int16_t loaded[GUN_TRIGGER_MAGAZINES] = {0, 0};
    int trigger_count, i, slot;
    if (s_active_weapon_slot >= 0 && s_active_weapon_slot < PLAY_WEAPON_SLOTS) {
        s_gun_saved[s_active_weapon_slot] = s_gun;
        s_trigger_pair_saved[s_active_weapon_slot] = s_trigger_pair;
    }
    slot = play_fp_slot();
    if (slot < 0 || slot >= PLAY_WEAPON_SLOTS) return;
    s_active_weapon_slot = slot;
    if (s_weapon_runtime_ready[slot]) {
        s_gun = s_gun_saved[slot];
        s_trigger_pair = s_trigger_pair_saved[slot];
    } else {
        gun_init(&s_gun, def ? def : &GUN_PISTOL);
        memset(&s_trigger_pair, 0, sizeof s_trigger_pair);
        s_weapon_runtime_ready[slot] = 1;
    }
    memset(s_trigger_profile, 0, sizeof s_trigger_profile);
    s_trigger_pair_active = 0;
    trigger_count = play_fp_trigger_profiles(s_trigger_profile);
    if (!policy || trigger_count <= 1 ||
        policy->secondary_trigger_mode == GUN_SECONDARY_TRIGGER_LOADS_ALTERNATE_AMMO ||
        policy->secondary_trigger_mode == GUN_SECONDARY_TRIGGER_LOADS_MULTIPLE_PRIMARY_AMMO)
        return;
    for (i = 0; i < trigger_count; i++)
        if (play_fp_trigger_uses_weapon_origin(i)) return;
    if (!play_fp_trigger_loaded(loaded)) return;
    if (!s_pair_runtime_ready[slot]) {
        gun_trigger_pair_init(&s_trigger_pair, loaded);
        s_trigger_pair.player_owned = 1;
        s_trigger_pair.weapon_flags = policy->flags;
        s_trigger_pair.age_rate_of_fire_penalty = policy->age_rate_of_fire_penalty;
        s_trigger_pair.age_heat_recovery_penalty = policy->age_heat_recovery_penalty;
        if (def) {
            s_trigger_pair.heat_overheated_threshold = def->heat_overheat;
            s_trigger_pair.heat_recovery_threshold = def->heat_recovery;
            s_trigger_pair.heat_loss_per_second = def->heat_loss;
        }
        s_pair_runtime_ready[slot] = 1;
    }
    s_trigger_pair_active = 1;
}

static int play_spawn_projectiles(const shot_def *bullet, int pellets,
    const shot_cone *cone, float error_fraction,
    int distribution_function, float distribution_angle)
{
    float origin[3], forward[3];
    const float (*directions)[3] = play_fp_directions();
    unsigned direction_count = play_fp_direction_count();
    float cy = cosf(s_yaw), sy = sinf(s_yaw), cp = cosf(s_pitch), sp = sinf(s_pitch);
    int dropped = 0;
    if (!bullet || pellets <= 0) return 0;
    origin[0] = s_body.pos[0];
    origin[1] = s_body.pos[1];
    origin[2] = s_body.pos[2] + s_body.eye;
    forward[0] = cp * cy;
    forward[1] = cp * sy;
    forward[2] = sp;
    return shot_pool_spawn_cone(s_fly, s_fly_def, PLAY_FLY, bullet, origin, forward,
        pellets, directions, direction_count, cone, error_fraction,
        distribution_function, distribution_angle, &s_seed, &dropped);
}

static void play_tick_trigger_pair(unsigned held)
{
    const play_fp_weapon_trigger_policy *policy = play_fp_weapon_trigger_policy_get();
    unsigned fired;
    int trigger;
    if (!policy) return;
    /* CE checks scenario_location_underwater at the weapon position when
     * beginning a trigger. The player weapon origin follows the view origin. */
    {
        float weapon_position[3] = {s_body.pos[0], s_body.pos[1], s_body.pos[2] + s_body.eye};
        s_trigger_pair.can_begin_firing =
            !collide_location_underwater(&s_bsp, &s_location, weapon_position);
    }
    fired = gun_trigger_pair_tick_controls_seeded(&s_trigger_pair, s_trigger_profile,
        GUN_TRIGGER_MAX, policy->secondary_trigger_mode, policy->flags,
        policy->age_rate_of_fire_penalty, (held & PAD_R1) != 0,
        (held & PAD_L1) != 0, 1, 0, 0, &s_seed);
    for (trigger = 0; trigger < GUN_TRIGGER_MAX; trigger++) {
        const play_fp_trigger *source;
        const shot_def *bullet;
        shot_cone cone;
        int pellets, spawned;
        if (!(fired & (1u << trigger))) continue;
        if (s_trigger_pair.trigger[trigger].misfired) {
            printf("[play] misfire %s trigger %d\n", play_fp_name(), trigger);
            continue;
        }
        source = play_fp_trigger_at(trigger);
        bullet = play_fp_trigger_shot(trigger);
        if (!source || !bullet) continue;
        cone.inner_cone_angle = source->values[PLAY_FP_TRIGGER_ERROR_CONE_INNER];
        cone.error_lower_bound = source->values[PLAY_FP_TRIGGER_ERROR_CONE_LOWER];
        cone.error_upper_bound = source->values[PLAY_FP_TRIGGER_ERROR_CONE_UPPER];
        cone.trigger_flags = source->flags;
        pellets = s_trigger_profile[trigger].projectiles_per_shot > 0 ?
            s_trigger_profile[trigger].projectiles_per_shot : 1;
        spawned = play_spawn_projectiles(bullet, pellets, &cone,
            s_trigger_pair.trigger[trigger].error_fraction, source->halves[9],
            source->values[PLAY_FP_TRIGGER_DISTRIBUTION_ANGLE]);
        if (spawned) {
            s_mark = 1;
            printf("[play] fire %s trigger %d pellets %d tick %u magazine %d loaded %d\n",
                play_fp_name(), trigger, spawned, (unsigned)s_play_sim_tick,
                s_trigger_profile[trigger].magazine_index,
                s_trigger_profile[trigger].magazine_index >= 0 &&
                    s_trigger_profile[trigger].magazine_index < GUN_TRIGGER_MAGAZINES ?
                    s_trigger_pair.magazine_loaded[s_trigger_profile[trigger].magazine_index] : -1);
        }
        if (spawned < pellets)
            printf("[play] projectile pool full capacity %d dropped %d\n",
                PLAY_FLY, pellets - spawned);
    }
}

static uint8_t *load_file(const char *path, size_t *size)
{
    FILE *f = fopen(path, "rb");
    long n;
    uint8_t *bytes;
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    n = ftell(f);
    if (n <= 0 || fseek(f, 0, SEEK_SET) != 0) { fclose(f); return NULL; }
    bytes = malloc((size_t)n);
    if (!bytes || fread(bytes, 1, (size_t)n, f) != (size_t)n) {
        free(bytes);
        fclose(f);
        return NULL;
    }
    fclose(f);
    *size = (size_t)n;
    return bytes;
}

static int play_init(void)
{
    size_t pack_size, coll_size, tag_size, vita_size, acol_size;
    size_t location_size;
    const uint8_t *coll, *tag, *vita, *acol, *location;
    float pose[4], tags[COLL_TAG_FLOATS];
    s_pack = load_file("host:/collision.hp2", &pack_size);
    if (!s_pack) {
        printf("[play] collision pack missing\n");
        return -1;
    }
    if (collpack_section(s_pack, pack_size, "COLL", &coll, &coll_size) != 0 ||
        collpack_collision(coll, coll_size, &s_bsp) != 0 ||
        collpack_spawn(coll, 0, pose) != 0 ||
        collpack_section(s_pack, pack_size, "TAGS", &tag, &tag_size) != 0 ||
        collpack_tags(tag, tag_size, tags) != 0 ||
        collpack_section(s_pack, pack_size, "VITA", &vita, &vita_size) != 0 ||
        collpack_vital_profile(vita, vita_size, &s_probe_damage_profile,
            &s_probe_body_damage_material_type, &s_probe_shield_damage_material_type) != 0 ||
        collpack_section(s_pack, pack_size, "LOC1", &location, &location_size) != 0 ||
        collpack_location(location, location_size, &s_location) != 0) {
        printf("[play] collision pack rejected\n");
        return -1;
    }
    (void)tags;
    s_scratch_bytes = collide_pill_scratch_bytes();
    s_scratch = malloc(s_scratch_bytes);
    if (!s_scratch) return -1;
    player_spawn(&s_body, pose, &s_yaw, &s_pitch);
    vital_init(&s_probe_target);
    memset(s_grenades, 0, sizeof s_grenades);
    s_grenades_carried = GRENADE_CARRY_MAX;
    s_grenade_button = 0;
    s_freecam_button = 0;
    s_freecam_mode = 0;
    /* Keep the diagnostic target before the nearby spawn-side BSP occluder;
     * the previous six-unit placement was behind geometry and could never
     * receive a real projectile hit in the normal play camera. */
    s_probe_target_center[0] = s_body.pos[0] + cosf(s_yaw) * 1.0f;
    s_probe_target_center[1] = s_body.pos[1] + sinf(s_yaw) * 1.0f;
    s_probe_target_center[2] = s_body.pos[2] + s_body.eye;
    if (collpack_section(s_pack, pack_size, "ACOL", &acol, &acol_size) != 0 ||
        collpack_actor_collision(acol, acol_size, &s_actor_collision) != 0 ||
        play_actor_bind_pose() != 0) {
        printf("[play] cyborg actor collision rejected\n");
        return -1;
    }
    if (play_fp_open() != 0) printf("[play] weapon models missing\n");
    play_select_weapon();
    memset(s_fly, 0, sizeof s_fly);
    s_mark = 0;
    printf("[play] ready feet %.2f %.2f %.2f yaw %.1f %s %d models %d actor-mesh %u bind-pose tris\n",
        pose[0], pose[1], pose[2], s_yaw * 57.2957795f, play_fp_name(), s_gun.loaded,
        play_fp_model_count(), (unsigned)s_actor_collision.triangle_count);
    return 0;
}

void __wrap_flycam_update(camera_t *cam, const fly_input *in, float dt)
{
    pad_state pad;
    move_cmd cmd;
    struct padButtonStatus buttons;
    unsigned held = 0;
    int actor_live;
    collide_pill_stats stats;
    if (s_failed) {
        __real_flycam_update(cam, in, dt);
        return;
    }
    if (!s_ready) {
        if (play_init() != 0) {
            s_failed = 1;
            __real_flycam_update(cam, in, dt);
            return;
        }
        s_ready = 1;
    }
    if (padRead(0, 0, &buttons) != 0) held = (unsigned)(0xFFFF ^ buttons.btns);
    if ((held & PAD_R3) && !s_freecam_button) {
        s_freecam_mode = !s_freecam_mode;
        printf("[play] freecam %s (R3/4 toggles)\n", s_freecam_mode ? "on" : "off");
    }
    s_freecam_button = (uint8_t)((held & PAD_R3) != 0);
    if (s_freecam_mode) {
        /* Diagnostic free flight is opt-in; ordinary play (including grenade
         * smoke) always advances the collision-resolved player body. */
        s_grenade_button = (uint8_t)((held & PAD_L2) != 0);
        s_triangle = (held & PAD_TRIANGLE) != 0;
        __real_flycam_update(cam, in, dt);
        return;
    }
    s_play_sim_tick++;
    memset(&pad, 0, sizeof pad);
    pad.left_x = (int16_t)(in->move_x * 32767.0f);
    pad.left_y = (int16_t)(in->move_y * 32767.0f);
    pad.right_x = (int16_t)(in->look_x * 32767.0f);
    pad.right_y = (int16_t)(in->look_y * 32767.0f);
    pad.cross = (held & PAD_CROSS) != 0;
    pad.circle = (held & PAD_CIRCLE) != 0;
    pad_to_command(&pad, &cmd, &s_yaw, &s_pitch);
    /* The combat probe follows the same fixed 30 Hz simulation tick as
     * projectiles. Advance stun/recharge before this tick's damage events. */
    actor_live = play_pose_live_player_actor();
    play_update_combat_targets();
    vital_tick_profile(&s_probe_target, &s_probe_damage_profile);
    combat_targets_tick(&s_combat_targets);
    if (actor_live) {
        combat_target *target = play_combat_target_find(s_live_actor_index);
        if (target) s_live_actor_vital = target->health;
        else vital_tick_profile(&s_live_actor_vital, &s_probe_damage_profile);
    }
    mover_tick_map(&s_body, &cmd, s_yaw, &s_bsp, s_scratch, s_scratch_bytes, 0, &stats);
    s_last = stats;
    if ((held & PAD_L2) && !s_grenade_button) {
        int slot;
        float origin[3] = {s_body.pos[0], s_body.pos[1], s_body.pos[2] + s_body.eye};
        float aim[3] = {cosf(s_pitch) * cosf(s_yaw),
            cosf(s_pitch) * sinf(s_yaw), sinf(s_pitch)};
        for (slot = 0; slot < PLAY_GRENADE_CAPACITY && s_grenades[slot].alive; ++slot) {}
        if (slot < PLAY_GRENADE_CAPACITY && grenade_throw(&s_grenades[slot],
                &GRENADE_FRAG, origin, aim,
                &s_grenades_carried, &s_seed)) {
            printf("[play] grenade throw frag carried %d slot %d mode player eye %.3f %.3f %.3f aim %.3f %.3f %.3f\n",
                s_grenades_carried, slot, origin[0], origin[1], origin[2],
                aim[0], aim[1], aim[2]);
        } else {
            printf("[play] grenade unavailable carried %d\n", s_grenades_carried);
        }
    }
    s_grenade_button = (uint8_t)((held & PAD_L2) != 0);
    {
        const gun_def *def = play_fp_gun();
        const shot_def *bullet = NULL;
        if ((held & PAD_TRIANGLE) && !s_triangle) {
            play_fp_cycle();
            def = play_fp_gun();
            play_select_weapon();
            printf("[play] weapon %s %d %d\n", play_fp_name(), s_gun.loaded, s_gun.total);
        }
        s_triangle = (held & PAD_TRIANGLE) != 0;
        bullet = play_fp_shot();
        if (s_trigger_pair_active) {
            play_tick_trigger_pair(held);
        } else {
            float weapon_position[3] = {s_body.pos[0], s_body.pos[1], s_body.pos[2] + s_body.eye};
            int can_begin_firing = !collide_location_underwater(&s_bsp, &s_location, weapon_position);
            int requires_weapon_origin = play_fp_trigger_uses_weapon_origin(0);
            if (def && def->has_trigger && !requires_weapon_origin &&
                gun_tick_seeded(&s_gun, def, (held & PAD_R1) != 0 && can_begin_firing,
                         (held & PAD_SQUARE) != 0, &s_seed) && bullet && !s_gun.misfired) {
                const play_fp_cone *cone = play_fp_spread();
                int pellets = def->projectiles_per_shot > 0 ? def->projectiles_per_shot : 1;
                const play_fp_trigger *source = play_fp_trigger_at(0);
                int spawned = play_spawn_projectiles(bullet, pellets,
                    (const shot_cone *)cone, s_gun.shot_error_fraction,
                    source ? source->halves[9] : 0,
                    source ? source->values[PLAY_FP_TRIGGER_DISTRIBUTION_ANGLE] : 0.0f);
                if (spawned) {
                    s_mark = 1;
                    printf("[play] fire %s %d pellets %d tick %u loaded %d\n",
                        play_fp_name(), s_gun.loaded, spawned,
                        (unsigned)s_play_sim_tick, s_gun.loaded);
                }
                if (spawned < pellets)
                    printf("[play] projectile pool full capacity %d dropped %d\n",
                        PLAY_FLY, pellets - spawned);
            }
        }
    }
    if (strcmp(play_fp_path(), "weapons\\shotgun\\shotgun") == 0 &&
        (s_shotgun_state_loaded != s_gun.loaded || s_shotgun_state_total != s_gun.total ||
         s_shotgun_state_magazine != s_gun.magazine)) {
        printf("[play] shotgun-state tick %u loaded %d total %d magazine %d timer %d\n",
            (unsigned)s_play_sim_tick, s_gun.loaded, s_gun.total,
            s_gun.magazine, s_gun.magazine_timer);
        s_shotgun_state_loaded = s_gun.loaded;
        s_shotgun_state_total = s_gun.total;
        s_shotgun_state_magazine = s_gun.magazine;
    }
    {
        shot_scene scene;
        actor_live = play_pose_live_player_actor();
        int slot, flying = 0, hits = 0, ended = 0, shot_calls = 0;
        int shot_actor_hits = 0, shot_surface_hits = 0, shot_resolved = 0;
        float hit_at[3], shot_tick_ms = 0.0f;
        memset(&scene, 0, sizeof scene);
        scene.bsp = &s_bsp;
        scene.directions = play_fp_directions();
        scene.direction_count = play_fp_direction_count();
        if (s_combat_target_view_count > 0) {
            const combat_target *first = &s_combat_targets.target[0];
            scene.target = 1;
            scene.target_is_unit = 1;
            memcpy(scene.target_center, first->object->pos, sizeof scene.target_center);
            scene.target_radius = 0.0f;
            scene.targets = s_combat_target_views;
            scene.target_count = s_combat_target_view_count;
            scene.actor_mesh = NULL;
            scene.actor_node_to_world = NULL;
            scene.target_material = 0;
            scene.target_body_damage_material_type = first->body_damage_material_type;
            scene.target_shield_damage_material_type = first->shield_damage_material_type;
            scene.target_damage_material_types_valid = 1;
            scene.target_damage_resistance_index = first->profile->indirect_material_index;
            scene.target_damage_resistance_index_valid = 1;
            scene.target_vitality_profile = first->profile;
        } else if ((actor_live && !s_live_actor_vital.dead) ||
                   (!actor_live && !s_probe_target.dead)) {
            scene.target = 1;
            scene.target_is_unit = 1;
            memcpy(scene.target_center, actor_live ? s_live_actor_center : s_probe_target_center,
                sizeof scene.target_center);
            scene.target_radius = 0.0f;
            scene.actor_mesh = &s_actor_collision;
            scene.actor_node_to_world = (const float (*)[12])(actor_live ?
                s_live_actor_node_to_world : s_probe_node_to_world);
            scene.target_vitality_profile = &s_probe_damage_profile;
            scene.target_material = 0;
            scene.target_body_damage_material_type = s_probe_body_damage_material_type;
            scene.target_shield_damage_material_type = s_probe_shield_damage_material_type;
            scene.target_damage_material_types_valid = 1;
            scene.target_damage_resistance_index = s_probe_damage_profile.indirect_material_index;
            scene.target_damage_resistance_index_valid = 1;
        }
        hit_at[0] = hit_at[1] = hit_at[2] = 0.0f;
        for (slot = 0; slot < PLAY_FLY; slot++) {
            int was, object_hit;
            u32 shot_start;
            float shot_ms;
            if (!s_fly[slot].alive || !s_fly_def[slot]) continue;
            was = 1;
            scene.underwater = (uint8_t)collide_location_underwater(
                &s_bsp, &s_location, s_fly[slot].position);
            shot_start = timer_cycles();
            shot_tick(&s_fly[slot], s_fly_def[slot], &scene, &s_seed);
            shot_ms = timer_ms(shot_start, timer_cycles());
            shot_tick_ms += shot_ms;
            s_shot_tick_time_sum_ms += shot_ms;
            if (shot_ms > s_shot_tick_time_max_ms) s_shot_tick_time_max_ms = shot_ms;
            shot_calls++;
            s_shot_tick_samples++;
            if (s_fly[slot].impact_count > 0) {
                unsigned impact_index;
                for (impact_index = 0; impact_index < s_fly[slot].impact_count; impact_index++) {
                    const shot_impact_event *impact = &s_fly[slot].impacts[impact_index];
                    shot attributed = s_fly[slot];
                    int object_index = impact->object_index;
                    combat_target *target = play_combat_target_find(object_index);
                    int applied;
                    attributed.hit_object_this_tick = 1;
                    attributed.hit_object_index = impact->object_index;
                    attributed.hit_node_index = impact->node_index;
                    attributed.hit_damage_part = impact->damage_part;
                    attributed.hit_region_index = impact->region_index;
                    attributed.damage_resistance_index = impact->resistance_index;
                    attributed.damage_body_material_type = impact->body_material_type;
                    attributed.damage_shield_material_type = impact->shield_material_type;
                    attributed.damage_material_types_valid = impact->material_types_valid;
                    attributed.damage = impact->damage;
                    attributed.damage_body_modifier = impact->body_modifier;
                    attributed.damage_shield_modifier = impact->shield_modifier;
                    applied = combat_targets_apply_projectile(&s_combat_targets,
                        (uint16_t)object_index, &attributed, VITAL_BODY, 0, 1.0f, 1.0f);
                    if (applied) object_hit = 1;
                    if (target && applied && object_index == s_live_actor_index)
                        s_live_actor_vital = target->health;
                    if (target && applied && impact->damage > 0.0f)
                        printf("[play] actor damage object %d def %d amount %.2f node %d region %d part %d resistance %d shield %.3f body %.3f dead %d\n",
                            object_index, target->definition_index, impact->damage,
                            impact->node_index, impact->region_index, impact->damage_part,
                            impact->resistance_index, target->health.shield,
                            target->health.body, target->health.dead);
                }
            } else if (s_fly[slot].hit_object_index >= 0) {
                int object_index = s_fly[slot].hit_object_index;
                combat_target *target = play_combat_target_find(object_index);
                object_hit = combat_targets_apply_projectile(&s_combat_targets,
                    (uint16_t)object_index, &s_fly[slot], VITAL_BODY, 0, 1.0f, 1.0f);
                if (target && object_hit && object_index == s_live_actor_index)
                    s_live_actor_vital = target->health;
                if (target && object_hit && s_fly[slot].damage > 0.0f)
                    printf("[play] actor damage object %d def %d amount %.2f node %d region %d part %d resistance %d shield %.3f body %.3f dead %d\n",
                        object_index, target->definition_index, s_fly[slot].damage,
                        s_fly[slot].hit_node_index, s_fly[slot].hit_region_index,
                        s_fly[slot].hit_damage_part, s_fly[slot].damage_resistance_index,
                        target->health.shield, target->health.body, target->health.dead);
            } else if (actor_live) {
                object_hit = vital_apply_projectile_hit_profile(&s_live_actor_vital, &s_fly[slot],
                    VITAL_BODY, &s_probe_damage_profile,
                    s_fly_def[slot]->damage_material_modifier_21,
                    s_fly_def[slot]->damage_material_modifier_22, 0);
                if (object_hit && s_fly[slot].damage > 0.0f) {
                    printf("[play] actor damage object %d def %d amount %.2f node %d region %d part %d resistance %d shield %.3f body %.3f dead %d\n",
                        s_live_actor_index, s_live_actor_def, s_fly[slot].damage,
                        s_fly[slot].hit_node_index, s_fly[slot].hit_region_index,
                        s_fly[slot].hit_damage_part,
                        s_fly[slot].damage_resistance_index, s_live_actor_vital.shield,
                        s_live_actor_vital.body, s_live_actor_vital.dead);
                }
            } else {
                object_hit = vital_apply_projectile_hit_profile(&s_probe_target, &s_fly[slot],
                    VITAL_BODY, &s_probe_damage_profile,
                    s_fly_def[slot]->damage_material_modifier_21,
                    s_fly_def[slot]->damage_material_modifier_22, 0);
                if (object_hit && s_fly[slot].damage > 0.0f) {
                    printf("[play] probe damage %.2f node %d part %d resistance %d shield %.3f body %.3f dead %d\n",
                        s_fly[slot].damage, s_fly[slot].hit_node_index,
                        s_fly[slot].hit_damage_part, s_fly[slot].damage_resistance_index,
                        s_probe_target.shield, s_probe_target.body, s_probe_target.dead);
                }
            }
            if (object_hit) shot_actor_hits++;
            if (s_fly[slot].alive) flying = 1;
            else if (was && (object_hit || s_fly[slot].hit_surface)) {
                hits++;
                shot_resolved++;
                if (!object_hit && s_fly[slot].hit_surface) shot_surface_hits++;
                hit_at[0] = s_fly[slot].position[0];
                hit_at[1] = s_fly[slot].position[1];
                hit_at[2] = s_fly[slot].position[2];
            } else if (was) {
                ended++;
            }
        }
        if (hits) {
            s_mark = 2;
            printf("[play] hit %d %.2f %.2f %.2f\n", hits,
                hit_at[0], hit_at[1], hit_at[2]);
        } else if (ended) {
            s_mark = 3;
            printf("[play] range %d\n", ended);
        } else if (flying) {
            s_mark = 1;
        }
        if (shot_calls >= 15) {
            printf("[play] pellet-result tick %u calls %d actor-hits %d bsp-hits %d resolved %d flying %d\n",
                (unsigned)s_play_sim_tick, shot_calls, shot_actor_hits,
                shot_surface_hits, shot_resolved, flying);
        }
        if ((unsigned)shot_calls > s_shot_tick_max_calls)
            s_shot_tick_max_calls = (unsigned)shot_calls;
        if (shot_tick_ms > s_shot_tick_time_max_tick_ms)
            s_shot_tick_time_max_tick_ms = shot_tick_ms;
        if (s_body.tick != 0 && s_body.tick % 60 == 0) {
            printf("[play] shot-cost samples %u avg-ms %.4f max-shot-ms %.4f max-tick-ms %.4f max-calls-per-tick %u\n",
                s_shot_tick_samples,
                s_shot_tick_samples ? s_shot_tick_time_sum_ms / s_shot_tick_samples : 0.0f,
                s_shot_tick_time_max_ms, s_shot_tick_time_max_tick_ms, s_shot_tick_max_calls);
            s_shot_tick_time_sum_ms = 0.0f;
            s_shot_tick_time_max_ms = 0.0f;
            s_shot_tick_time_max_tick_ms = 0.0f;
            s_shot_tick_samples = 0;
            s_shot_tick_max_calls = 0;
        }
    }
    {
        int slot;
        for (slot = 0; slot < PLAY_GRENADE_CAPACITY; ++slot) {
            grenade *item = &s_grenades[slot];
            if (item->alive && grenade_tick_bsp(item, &GRENADE_FRAG, &s_bsp, &s_seed)) {
                vital *target = actor_live ? &s_live_actor_vital : &s_probe_target;
                const float *target_center = actor_live ? s_live_actor_center : s_probe_target_center;
                const char *target_name = actor_live ? "actor" : "probe";
                float dx = item->position[0] - target_center[0];
                float dy = item->position[1] - target_center[1];
                float dz = item->position[2] - target_center[2];
                float distance = sqrtf(dx * dx + dy * dy + dz * dz);
                if (distance < GRENADE_FRAG.cutoff) {
                    float damage = grenade_damage(&GRENADE_FRAG, distance, &s_seed);
                    vital_hurt_profile(target, damage, VITAL_BODY,
                        &s_probe_damage_profile,
                        GRENADE_FRAG.damage_material_modifier_21,
                        GRENADE_FRAG.damage_material_modifier_22, 0);
                    printf("[play] grenade explosion frag slot %d target %s damage %.2f distance %.2f shield %.3f body %.3f dead %d\n",
                        slot, target_name, damage, distance, target->shield,
                        target->body, target->dead);
                } else {
                    printf("[play] grenade explosion frag slot %d target %s outside %.2f\n",
                        slot, target_name, distance);
                }
            }
        }
    }
    play_store_live_target_health();
    cam->pos[0] = s_body.pos[0];
    cam->pos[1] = s_body.pos[1];
    cam->pos[2] = s_body.pos[2] + s_body.eye;
    cam->yaw = s_yaw;
    cam->pitch = s_pitch;
    if (s_body.out_of_world && !s_was_out) printf("[play] out of world, restored\n");
    s_was_out = s_body.out_of_world;
}

/* Top-left budget strip. 30 Hz frame is 33.3 ms. Committed EE RAM is 26.5 MiB
 * of the 32 MiB machine. Texture upload cap is 1.5 MiB. Pill lists hold 256. */
void __wrap_profiler_overlay(const profiler_t *p, text_batch_t *b)
{
    const render_stats_t *r = &p->last;
    char line[72];
    void *brk = sbrk(0);
    unsigned mem_kb = (brk == (void *)-1) ? 0u : (unsigned)((uintptr_t)brk / 1024u);
    unsigned pages = bsp_render_cache_pages();
    float speed = s_body.vel[0] * s_body.vel[0] + s_body.vel[1] * s_body.vel[1];
    int over_frame = p->last_interval > 33.3f || p->dropped;
    int over_mem = mem_kb > (27787264u / 1024u);
    int over_gs = r->tex_failed || r->chain_overflow || (pages && r->pages_free == 0);
    text_batch_clear(b);
    snprintf(line, sizeof line, "FPS %.0f/30  MS %.1f/33.3  DROP %u",
        p->fps, p->last_interval, p->dropped);
    text_batch_print(b, 8, 8, over_frame ? 0xFF6060 : 0xFFFFFF, line);
    snprintf(line, sizeof line, "EE %.1f MS  GS %.1f  VIF %.1f  WAIT %.1f",
        p->prep_avg, p->gs_ms > 0.f ? p->gs_ms : 0.f, p->vif_ms, p->wait_avg);
    text_batch_print(b, 8, 16, p->prep_avg > 33.3f ? 0xFF6060 : 0xC0FFC0, line);
    snprintf(line, sizeof line, "RAM %u/%u KB  CAP %u KB",
        mem_kb, 27787264u / 1024u, 32768u);
    text_batch_print(b, 8, 24, over_mem ? 0xFF6060 : 0xC0FFC0, line);
    snprintf(line, sizeof line, "GS %u/%u PG  UP %u/%u KB%s",
        r->pages_free, pages, r->upload_bytes / 1024u, 1536u,
        r->tex_failed ? " FAIL" : r->tex_deferred ? " DEFER" : "");
    text_batch_print(b, 8, 32, over_gs ? 0xFF6060 : 0xFFFFC0, line);
    snprintf(line, sizeof line, "TRIS %u BAT %u CL %u/%u PRT %u/%u",
        r->triangles, r->batches, r->clusters_visible, r->clusters_total,
        r->portals_passed, r->portals_tested);
    text_batch_print(b, 8, 40, 0xFFFFC0, line);
    speed = speed > 0.f ? sqrtf(speed) * (float)MOVE_TICKS_PER_SECOND : 0.f;
    snprintf(line, sizeof line, "WALK %.1f/2.2  FEAT %d/256  NOD %d  %s%s",
        speed, s_last.features, s_last.nodes_visited,
        s_body.grounded ? "GND" : "AIR", s_body.crouching ? " CR" : "");
    text_batch_print(b, 8, 48, s_last.saturated ? 0xFF6060 : 0xC0FFFF, line);
    {
        const gun_def *def = play_fp_gun();
        const char *mark = s_mark == 1 ? "FLY" : s_mark == 2 ? "HIT" : s_mark == 3 ? "END" : "----";
        if (def && def->rounds_loaded_maximum > 0)
            snprintf(line, sizeof line, "%s %d|%d  %s  Q",
                play_fp_name(), s_gun.loaded, s_gun.total, mark);
        else
            snprintf(line, sizeof line, "%s  %s  Q", play_fp_name(), mark);
    }
    text_batch_print(b, 8, 56, s_mark == 2 ? 0xFFC080 : 0xFFFFFF, line);
    snprintf(line, sizeof line, "PROBE SH %.2f BODY %.2f %s",
        s_probe_target.shield, s_probe_target.body,
        s_probe_target.dead ? "DEAD" : "ALIVE");
    text_batch_print(b, 8, 64, s_probe_target.dead ? 0xFF6060 : 0xC0FFC0, line);
}
