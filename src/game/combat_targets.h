/* Bounded, host-testable bridge from the pinned PS2 object table to combat
 * collision. This owns no heap memory: matrices are supplied by the caller. */
#ifndef GAME_COMBAT_TARGETS_H
#define GAME_COMBAT_TARGETS_H

#include "game/collpack.h"
#include "game/shot.h"
#include "sim/objects.h"

#define COMBAT_TARGET_MAX 64
#define COMBAT_TARGET_MAX_NODES SKEL_MAX_NODES

typedef struct {
    const collpack_actor_collision_view *mesh;
    const vital_damage_profile *vitality;
    int16_t body_damage_material_type;
    int16_t shield_damage_material_type;
} combat_target_definition;

/* Resolve the source biped object tag and its render-model tag to a matching
 * exported collision mesh and damage-resistance profile. Return 0 on success.
 * Unsupported/missing species are rejected, never silently treated as cyborgs. */
typedef int (*combat_target_resolver)(void *user, uint32_t object_tag_id,
    uint32_t model_tag_id, combat_target_definition *out);

typedef enum {
    COMBAT_TARGET_ACCEPTED = 0,
    COMBAT_TARGET_REJECT_UNSUPPORTED_TYPE,
    COMBAT_TARGET_REJECT_DEFINITION,
    COMBAT_TARGET_REJECT_MODEL,
    COMBAT_TARGET_REJECT_MESH,
    COMBAT_TARGET_REJECT_PROFILE,
    COMBAT_TARGET_REJECT_POSE,
    COMBAT_TARGET_REJECT_DUPLICATE,
    COMBAT_TARGET_REJECT_CAPACITY
} combat_target_reject;

typedef struct {
    uint16_t object_index;       /* stable slot in this object_table_t lifetime */
    int16_t definition_index;
    int16_t model_index;
    uint32_t object_tag_id;
    uint32_t model_tag_id;
    const object_t *object;
    const collpack_actor_collision_view *mesh;
    const vital_damage_profile *profile;
    int16_t body_damage_material_type;
    int16_t shield_damage_material_type;
    vital health;
    float bounds_min[3], bounds_max[3]; /* world AABB of the posed collision mesh */
    float (*node_to_world)[12];
} combat_target;

typedef struct {
    combat_target target[COMBAT_TARGET_MAX];
    unsigned count;
    unsigned rejected[COMBAT_TARGET_REJECT_CAPACITY + 1];
} combat_target_registry;

typedef struct {
    uint16_t object_index;
    collpack_actor_hit collision;
} combat_target_hit;

/* Caller supplies COMBAT_TARGET_MAX x COMBAT_TARGET_MAX_NODES x 12 floats.
 * Reset at map/object-table replacement, not on every simulation tick. */
void combat_targets_reset(combat_target_registry *registry);

/* Register one already-resolved and posed object. This is also the focused
 * host-test seam for object_table_t/objects_pose integration. `nodes->world`
 * must contain world-space posed node matrices; `mesh` vertices are node-local. */
combat_target_reject combat_targets_add_pose(combat_target_registry *registry,
    float (*matrix_pool)[COMBAT_TARGET_MAX_NODES][12], uint16_t object_index,
    const object_t *object, const scen_def *definition, const model_info *model,
    const object_nodes_t *nodes, const combat_target_definition *resolved);

/* Rebuild the per-tick pose/bounds cache from the pinned engine's object table.
 * Existing vitality is retained for a matching object-table slot/definition/model.
 * The engine table is dense and has no deletion/generation API today. */
void combat_targets_update(combat_target_registry *registry,
    float (*matrix_pool)[COMBAT_TARGET_MAX_NODES][12],
    const object_table_t *table, const object_world_t *world,
    object_nodes_t *workspace, combat_target_resolver resolver, void *user);

/* Closest collision before `maximum_t` (normally the BSP hit parameter).
 * Equal-distance ties retain the earliest object-table slot for determinism. */
int combat_targets_ray(const combat_target_registry *registry,
    const float origin[3], const float direction[3], float maximum_t,
    combat_target_hit *hit);

/* Apply one already-attributed projectile event to one target. The caller maps
 * CE collision damage-part/headshot rules before passing `vital_part`, and
 * supplies damage-effect modifiers resolved for this target's body/shield
 * material types. If the projectile carries valid resolved modifiers whose
 * stored material types match this target, those projectile values take
 * precedence; stale/single-target modifiers are never applied to another type. */
int combat_targets_apply_projectile(combat_target_registry *registry,
    uint16_t object_index, shot *projectile, int vital_part, int headshot,
    float body_material_modifier, float shield_material_modifier);
/* Apply one immutable per-impact event; caller owns event ordering. */
int combat_targets_apply_impact(combat_target_registry *registry,
    const shot_impact_event *impact, int vital_part, int headshot);

void combat_targets_tick(combat_target_registry *registry);

#endif
