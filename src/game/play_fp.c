/* Selects the held weapon's model each time the view is placed.
 * The scenario only stores one weapon. The mesh list is host:/weapons.fp. */
#include "game/play_fp.h"
#include "game/hold_pose.h"
#include "sim/fpview.h"
#include <stdio.h>
#include <string.h>

void __real_fpview_place(fpview_t *f, const object_world_t *w, const camera_t *cam);
void __real_fpview_tick(fpview_t *f, const object_world_t *w);
unsigned __real_objects_pose_model(const object_world_t *w, int model, int graph, unsigned anim,
                                   float frame, unsigned node_offset, const mat4 *root, object_nodes_t *out);

#define PLAY_FP_MAX 32
#define PLAY_FP_REC 112
#define PLAY_FP_REMAP 144
#define PLAY_FP_PROJ 68

typedef struct {
    char path[64];
    uint32_t model;
    uint32_t anim;
    uint16_t idle;
    uint16_t shared;
    char hand[32];
    uint32_t reserved;
} play_fp_weapon;

typedef struct {
    uint32_t arms_model;
    uint32_t model;
    uint32_t graph;
    uint8_t arms_n;
    uint8_t gun_n;
    uint16_t pad;
    uint8_t arms_map[64];
    uint8_t gun_map[64];
} play_fp_remap;

_Static_assert(sizeof(play_fp_weapon) == PLAY_FP_REC, "weapons.fp record");
_Static_assert(sizeof(play_fp_remap) == PLAY_FP_REMAP, "weapons.fp pose map");
_Static_assert(sizeof(play_fp_ammo) == PLAY_FP_AMMO, "weapons.fp magazine");
_Static_assert(sizeof(play_fp_proj) == PLAY_FP_PROJ, "weapons.fp projectile");

static play_fp_weapon s_weapon[PLAY_FP_MAX];
static play_fp_remap s_remap[PLAY_FP_MAX];
static gun_def s_gun[PLAY_FP_MAX];
static shot_def s_proj[PLAY_FP_MAX];
static uint8_t s_has_proj[PLAY_FP_MAX];
static int s_count;
static int s_slot;
static int s_sword_frame;
static int s_flak_frame;
static int s_carbine_frame;

static const float *sword_hold_trans(int node, int frame)
{
    (void)frame;
    return PLAY_FP_SWORD_NODE[node].t;
}

static int sword_hold_override(int node)
{
    return PLAY_FP_SWORD_NODE[node].trans_override;
}

static int flak_hold_override(int node)
{
    return PLAY_FP_FLAK_NODE[node].trans_override;
}

static int carbine_hold_override(int node)
{
    return PLAY_FP_CARBINE_NODE[node].trans_override;
}

typedef struct {
    const char *path;
    int frames;
    int *clock;
    int (*find)(const char *);
    const float *(*quat)(int, int);
    const float *(*trans)(int, int);
    int (*override)(int);
    void (*seat)(mat4 *, const mat4 *);
} play_fp_hold;

static const play_fp_hold HOLDS[] = {
    { "weapons\\energy sword\\energy sword", PLAY_FP_SWORD_FRAMES, &s_sword_frame,
      play_fp_sword_find, play_fp_sword_node_quat, sword_hold_trans, sword_hold_override,
      play_fp_sword_on_hand },
    { "weapons\\fuel rod gun\\fuel rod", PLAY_FP_FLAK_FRAMES, &s_flak_frame,
      play_fp_flak_find, play_fp_flak_node_quat, play_fp_flak_node_trans, flak_hold_override,
      play_fp_flak_on_hand },
    { "weapons\\gravity rifle\\gravity rifle", PLAY_FP_CARBINE_FRAMES, &s_carbine_frame,
      play_fp_carbine_find, play_fp_carbine_node_quat, play_fp_carbine_node_trans,
      carbine_hold_override, play_fp_carbine_on_hand },
};

static const play_fp_hold *hold_for(const char *path)
{
    int i;
    if (!path) return NULL;
    for (i = 0; i < (int)(sizeof HOLDS / sizeof HOLDS[0]); i++)
        if (strcmp(HOLDS[i].path, path) == 0) return &HOLDS[i];
    return NULL;
}
static int s_ammo;
static int s_proj_ok;
static int s_drawn = -1;

static int path_is(const char *path, const char *full)
{
    return strcmp(path, full) == 0;
}

int play_fp_open(void)
{
    FILE *file;
    char magic[4];
    unsigned short count, rec;
    int i;
    s_count = 0;
    s_slot = 0;
    s_sword_frame = 0;
    s_flak_frame = 0;
    s_carbine_frame = 0;
    s_ammo = 0;
    s_proj_ok = 0;
    s_drawn = -1;
    file = fopen("host:/weapons.fp", "rb");
    if (!file) return -1;
    if (fread(magic, 1, 4, file) != 4 || memcmp(magic, "WFP1", 4) != 0 ||
        fread(&count, 2, 1, file) != 1 || fread(&rec, 2, 1, file) != 1 ||
        rec != PLAY_FP_REC || count > PLAY_FP_MAX) {
        fclose(file);
        return -1;
    }
    for (i = 0; i < count; i++) {
        if (fread(&s_weapon[i], PLAY_FP_REC, 1, file) != 1) {
            fclose(file);
            s_count = 0;
            return -1;
        }
        s_weapon[i].path[sizeof s_weapon[i].path - 1] = 0;
        s_weapon[i].hand[sizeof s_weapon[i].hand - 1] = 0;
    }
    fclose(file);
    s_count = count;
    file = fopen("host:/weapons.fp", "rb");
    if (file) {
        char mark[4];
        unsigned short maps;
        if (fseek(file, 8 + (long)count * PLAY_FP_REC, SEEK_SET) == 0 &&
            fread(mark, 1, 4, file) == 4 && memcmp(mark, "RMP1", 4) == 0 &&
            fread(&maps, 2, 1, file) == 1 && maps == count) {
            int remap_ok = 1;
            for (i = 0; i < count; i++) {
                if (fread(&s_remap[i], PLAY_FP_REMAP, 1, file) != 1) {
                    memset(s_remap, 0, sizeof s_remap);
                    remap_ok = 0;
                    break;
                }
            }
            if (remap_ok && fread(mark, 1, 4, file) == 4 && memcmp(mark, "AMO1", 4) == 0 &&
                fread(&maps, 2, 1, file) == 1 && maps == count) {
                for (i = 0; i < count; i++) {
                    play_fp_ammo ammo;
                    if (fread(&ammo, PLAY_FP_AMMO, 1, file) != 1) {
                        s_ammo = 0;
                        break;
                    }
                    play_fp_apply_ammo(&s_gun[i], &ammo);
                    s_ammo = 1;
                }
            }
            if (s_ammo && fread(mark, 1, 4, file) == 4 && memcmp(mark, "PRJ1", 4) == 0 &&
                fread(&maps, 2, 1, file) == 1 && maps == count) {
                for (i = 0; i < count; i++) {
                    play_fp_proj proj;
                    if (fread(&proj, PLAY_FP_PROJ, 1, file) != 1) {
                        s_proj_ok = 0;
                        break;
                    }
                    play_fp_apply_proj(&s_proj[i], &proj);
                    s_has_proj[i] = proj.has_projectile;
                    s_proj_ok = 1;
                }
            }
        }
        fclose(file);
    }
    file = fopen("host:/fpstill.txt", "rb");
    if (file) {
        char line[64];
        if (fgets(line, sizeof line, file)) {
            char *end = line + strlen(line);
            while (end > line && (end[-1] == '\n' || end[-1] == '\r' || end[-1] == ' '))
                *--end = 0;
            for (i = 0; i < s_count; i++) {
                if (strcmp(s_weapon[i].path, line) == 0) {
                    s_slot = i;
                    break;
                }
            }
        }
        fclose(file);
    }
    return 0;
}

int play_fp_count(void)
{
    return s_count;
}

int play_fp_model_count(void)
{
    int i, n = 0;
    for (i = 0; i < s_count; i++) if (s_weapon[i].model) n++;
    return n;
}

const char *play_fp_path(void)
{
    return s_count ? s_weapon[s_slot].path : "weapons\\pistol\\pistol";
}

const char *play_fp_name(void)
{
    static char out[32];
    const char *path = play_fp_path();
    const char *slash = strrchr(path, '\\');
    const char *text = slash ? slash + 1 : path;
    size_t i;
    for (i = 0; i + 1 < sizeof out && text[i]; i++) {
        char c = text[i];
        out[i] = (c >= 'a' && c <= 'z') ? (char)(c - 32) : c;
    }
    out[i] = 0;
    return out;
}

void play_fp_cycle(void)
{
    if (s_count) s_slot = (s_slot + 1) % s_count;
}

const gun_def *play_fp_gun(void)
{
    const char *path = s_count ? s_weapon[s_slot].path : "weapons\\pistol\\pistol";
    if (s_ammo && s_count) return &s_gun[s_slot];
    if (path_is(path, "weapons\\pistol\\pistol")) return &GUN_PISTOL;
    if (path_is(path, "weapons\\assault rifle\\assault rifle")) return &GUN_ASSAULT_RIFLE;
    if (path_is(path, "weapons\\shotgun\\shotgun")) return &GUN_SHOTGUN;
    if (!s_count) return &GUN_PISTOL;
    return NULL;
}

const shot_def *play_fp_shot(void)
{
    if (s_proj_ok && s_count) {
        if (!s_has_proj[s_slot]) return NULL;
        return &s_proj[s_slot];
    }
    if (path_is(play_fp_path(), "weapons\\pistol\\pistol")) return &SHOT_PISTOL;
    if (path_is(play_fp_path(), "weapons\\assault rifle\\assault rifle")) return &SHOT_ASSAULT_RIFLE;
    return NULL;
}

/* Halo samples the first-person graph in its own node order, then copies each
 * matrix onto the model node of the same name. The graph interleaves the gun
 * among the fingers, so an index offset does not match either mesh. */
static const uint8_t *pose_map(uint32_t model, uint32_t graph, int *count)
{
    int i;
    for (i = 0; i < s_count; i++) {
        const play_fp_remap *map = &s_remap[i];
        if (!map->graph || map->graph != graph) continue;
        if (model == map->arms_model && map->arms_n) { *count = map->arms_n; return map->arms_map; }
        if (model == map->model && map->gun_n) { *count = map->gun_n; return map->gun_map; }
    }
    return NULL;
}

static int is_hold_arms(uint32_t model)
{
    int i;
    /* The fuel rod borrows the rocket launcher's first-person idle, the
     * shouldered pose. Only the sword and gravity rifle replace the arms
     * with Halo 2 tables. */
    if (!s_count || !hold_for(s_weapon[s_slot].path)) return 0;
    if (strcmp(s_weapon[s_slot].path, "weapons\\fuel rod gun\\fuel rod") == 0) return 0;
    for (i = 0; i < s_count; i++)
        if (strcmp(s_weapon[i].path, "weapons\\assault rifle\\assault rifle") == 0)
            return s_remap[i].arms_model == model;
    return 0;
}

unsigned __wrap_objects_pose_model(const object_world_t *w, int model, int graph, unsigned anim,
                                   float frame, unsigned node_offset, const mat4 *root, object_nodes_t *out)
{
    model_info info;
    anim_graph posed;
    const uint8_t *map;
    int mapped = 0;
    (void)node_offset;
    if (model < 0 || graph < 0 || !w->models || !w->anims || anim == SCEN_NO_ANIM)
        return __real_objects_pose_model(w, model, graph, anim, frame, node_offset, root, out);
    info = model_get(w->models, (uint32_t)model);
    posed = anim_get_graph(w->anims, (uint32_t)graph);
    map = pose_map(info.tag_id, posed.tag_id, &mapped);
    if (!map || mapped != (int)info.node_count)
        return __real_objects_pose_model(w, model, graph, anim, frame, node_offset, root, out);
    {
        skel_xform local[SKEL_MAX_NODES];
        skel_xform bind[SKEL_MAX_NODES];
        int16_t parent[SKEL_MAX_NODES];
        static anim_pose pose;
        static mat4 def[SKEL_MAX_NODES];
        mat4 ident, inv;
        unsigned n = info.node_count > SKEL_MAX_NODES ? SKEL_MAX_NODES : info.node_count;
        unsigned i;
        for (i = 0; i < n; i++) {
            model_node node = model_get_node(w->models, &info, i);
            memcpy(local[i].rot, node.rotation, sizeof local[i].rot);
            memcpy(local[i].trans, node.translation, sizeof local[i].trans);
            local[i].scale = node.scale;
            bind[i] = local[i];
            parent[i] = node.parent;
        }
        if (is_hold_arms(info.tag_id)) {
            /* Halo 2 idle for this weapon: both arms, translation channels
             * replace the bind, bone lengths stay. */
            const play_fp_hold *hold = hold_for(s_weapon[s_slot].path);
            int hold_frame = *hold->clock % hold->frames;
            for (i = 0; i < n; i++) {
                model_node node = model_get_node(w->models, &info, i);
                int bone = hold->find(node.name);
                const float *q, *t;
                if (bone < 0) continue;
                q = hold->quat(bone, hold_frame);
                local[i].rot[0] = q[0];
                local[i].rot[1] = q[1];
                local[i].rot[2] = q[2];
                local[i].rot[3] = q[3];
                if (hold->override(bone)) {
                    t = hold->trans(bone, hold_frame);
                    local[i].trans[0] = t[0];
                    local[i].trans[1] = t[1];
                    local[i].trans[2] = t[2];
                }
            }
        } else {
            anim_sample(w->anims, &posed, anim, frame, &pose);
            for (i = 0; i < n; i++) {
                unsigned src = map[i];
                if (src < pose.count) {
                    local[i].rot[0] = pose.node[src].rot[0];
                    local[i].rot[1] = pose.node[src].rot[1];
                    local[i].rot[2] = pose.node[src].rot[2];
                    local[i].rot[3] = pose.node[src].rot[3];
                    local[i].trans[0] = pose.node[src].trans[0];
                    local[i].trans[1] = pose.node[src].trans[1];
                    local[i].trans[2] = pose.node[src].trans[2];
                    local[i].scale = pose.node[src].scale;
                }
            }
        }
        if (!n || skel_world(out->world, local, parent, n, root) != 0) { out->count = 0; return 0; }
        mat4_identity(&ident);
        if (skel_world(def, bind, parent, n, &ident) != 0) { out->count = 0; return 0; }
        for (i = 0; i < n; i++) {
            mat4_rigid_inverse(&inv, &def[i]);
            mat4_mul(&out->skin[i], &inv, &out->world[i]);
        }
        out->count = n;
        return n;
    }
}

static const play_fp_weapon *weapon_named(const char *path)
{
    int i;
    for (i = 0; i < s_count; i++)
        if (strcmp(s_weapon[i].path, path) == 0) return &s_weapon[i];
    return NULL;
}

/* These three tags have no first-person model, so the play build seats their
 * third-person mesh on a borrowed first-person pose. */
static int world_hold(const char *path)
{
    return hold_for(path) != NULL;
}

void __wrap_fpview_tick(fpview_t *f, const object_world_t *w)
{
    const play_fp_hold *hold;
    __real_fpview_tick(f, w);
    hold = s_count ? hold_for(s_weapon[s_slot].path) : NULL;
    if (!hold) return;
    (*hold->clock)++;
    if (*hold->clock >= hold->frames) *hold->clock = 0;
}

static void seat_world_model(fpview_t *f, const object_world_t *w, const play_fp_weapon *weapon)
{
    const play_fp_hold *hold;
    const play_fp_weapon *donor;
    const float *quat;
    mat4 hand, gunl, held;
    float grip_point[3], anchor[3];
    int graph, k;
    static anim_pose pose;
    if (f->weapon_model < 0) return;
    hold = hold_for(weapon->path);
    if (!hold) return;
    /* Sword: handle on the right wrist. Gravity rifle: carbine arms, camera
     * rotation on the rifle grip. Fuel rod: the rocket launcher's frame gun,
     * so the barrel lies on the shoulder the way that launcher does. */
    if (hold->seat == play_fp_sword_on_hand) {
        hand = f->weapon_root;
        hold->seat(&f->weapon_root, &hand);
        return;
    }
    if (strcmp(weapon->path, "weapons\\fuel rod gun\\fuel rod") == 0) {
        /* Node 7 is frame gun on the rocket launcher first-person graph, the
         * same slot the rifle graph uses. Its local pose times the right
         * wrist is the launcher's shouldered gun. */
        mat4_identity(&gunl);
        donor = weapon_named("weapons\\rocket launcher\\rocket launcher");
        if (donor && donor->anim && w->anims) {
            graph = anim_find_graph(w->anims, donor->anim);
            if (graph >= 0) {
                anim_graph g = anim_get_graph(w->anims, (uint32_t)graph);
                anim_sample(w->anims, &g, donor->idle, f->arms_frame, &pose);
                if (pose.count > 7)
                    mat4_from_trs(&gunl, pose.node[7].rot, pose.node[7].trans, pose.node[7].scale);
            }
        }
        hand = f->weapon_root;
        /* The fuel rod's tube rises 4.5° above its model +x, so on the
         * launcher's level barrel it aims above the reticle. Pitch it down
         * onto that reticle. The stock still slides on the unpitched axis. */
        {
            mat4 nose, pitched, launcher;
            float zero[3] = { 0.0f, 0.0f, 0.0f };
            mat4_mul(&launcher, &gunl, &hand);
            mat4_from_ypr(&nose, 0.0f, -5.2f * 3.14159265f / 180.0f, 0.0f, zero);
            mat4_mul(&pitched, &nose, &gunl);
            mat4_mul(&f->weapon_root, &pitched, &hand);
            for (k = 0; k < 3; k++)
                f->weapon_root.m[3][k] = launcher.m[3][k] + launcher.m[0][k] * 0.45f;
        }
        return;
    }
    quat = play_fp_hold_quat(weapon->path);
    if (!quat) return;
    mat4_identity(&gunl);
    donor = weapon_named("weapons\\assault rifle\\assault rifle");
    if (donor && donor->anim && w->anims) {
        graph = anim_find_graph(w->anims, donor->anim);
        if (graph >= 0) {
            anim_graph g = anim_get_graph(w->anims, (uint32_t)graph);
            anim_sample(w->anims, &g, donor->idle, 0.0f, &pose);
            if (pose.count > 7)
                mat4_from_trs(&gunl, pose.node[7].rot, pose.node[7].trans, pose.node[7].scale);
        }
    }
    hand = f->weapon_root;
    mat4_mul(&held, &gunl, &hand);
    for (k = 0; k < 3; k++) anchor[k] = held.m[3][k];
    for (k = 0; k < 3; k++) grip_point[k] = 0.0f;
    play_fp_seat_hold(&f->weapon_root, &f->arms_root, grip_point, anchor, quat);
}

static void attach_hand(fpview_t *f, const object_world_t *w, const char *hand)
{
    model_info arms;
    unsigned k;
    f->hand_marker = -1;
    f->hand_node = -1;
    f->weapon_node_offset = 0;
    if (!hand[0] || f->arms_model < 0) return;
    arms = model_get(w->models, (uint32_t)f->arms_model);
    f->hand_marker = model_find_marker(w->models, &arms, hand);
    if (f->hand_marker >= 0) return;
    for (k = 0; k < arms.node_count; k++) {
        model_node node = model_get_node(w->models, &arms, k);
        if (strcmp(node.name, hand) == 0) {
            f->hand_node = (int)k;
            return;
        }
    }
}

void __wrap_fpview_place(fpview_t *f, const object_world_t *w, const camera_t *cam)
{
    const play_fp_weapon *weapon = NULL;
    if (f->active && s_count && w->models) {
        weapon = &s_weapon[s_slot];
        if (s_slot != s_drawn) {
            f->arms_frame = 0.0f;
            f->weapon_frame = 0.0f;
            s_sword_frame = 0;
            s_flak_frame = 0;
            s_carbine_frame = 0;
            s_drawn = s_slot;
        }
        if (!weapon->model) {
            f->weapon_model = -1;
            f->weapon_graph = -1;
            f->weapon_node_offset = 0;
            f->hand_marker = -1;
            f->hand_node = -1;
            f->arms_graph = -1;
            f->arms_anim = SCEN_NO_ANIM;
        } else {
            int model = model_find(w->models, weapon->model);
            int graph = -1;
            if (model >= 0) {
                if (weapon->anim && weapon->idle != SCEN_NO_ANIM && w->anims)
                    graph = anim_find_graph(w->anims, weapon->anim);
                f->weapon_model = model;
                f->weapon_node_offset = 0;
                if (graph >= 0 && s_remap[s_slot].arms_n && s_remap[s_slot].graph == weapon->anim) {
                    /* The CE first-person idle already places these guns: the assault
                     * rifle node is 6.7 cm forward and the shotgun 17.9 cm, with the
                     * stock crossing the 5 cm near plane. No extra offset. */
                    f->arms_graph = graph;
                    f->weapon_graph = graph;
                    f->arms_anim = weapon->idle;
                    f->weapon_anim = weapon->idle;
                } else if (world_hold(weapon->path)) {
                    const char *donor_path = strcmp(weapon->path, "weapons\\fuel rod gun\\fuel rod") == 0
                        ? "weapons\\rocket launcher\\rocket launcher"
                        : "weapons\\assault rifle\\assault rifle";
                    const play_fp_weapon *donor = weapon_named(donor_path);
                    int donor_graph = donor && donor->anim && w->anims
                        ? anim_find_graph(w->anims, donor->anim) : -1;
                    f->weapon_graph = -1;
                    f->weapon_anim = SCEN_NO_ANIM;
                    if (donor_graph >= 0) {
                        f->arms_graph = donor_graph;
                        f->arms_anim = donor->idle;
                    } else {
                        f->arms_graph = -1;
                        f->arms_anim = SCEN_NO_ANIM;
                    }
                } else {
                    f->arms_graph = f->weapon_graph = -1;
                    f->arms_anim = f->weapon_anim = SCEN_NO_ANIM;
                }
                attach_hand(f, w, weapon->hand[0] ? weapon->hand : "frame r wriste");
            }
        }
    }
    __real_fpview_place(f, w, cam);
    if (weapon && world_hold(weapon->path)) seat_world_model(f, w, weapon);
}
