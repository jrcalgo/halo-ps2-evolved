"""Compose source-extracted CE tick/scheduler/input and PS2 render adapters.

The simulation phase callbacks below are deterministic test doubles. This is a
host integration slice for cadence invariance, not a full gameplay simulation
or EE render qualification.
"""
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"


def extract_function(source: str, name: str) -> str:
    import re
    matches = list(re.finditer(
        r"^[ \t]*(?:static\s+)?[\w\s*]+\b" + name +
        r"\s*\([^;{}]*\)\s*\{", source, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError(f"expected one definition of {name}, found {len(matches)}")
    opening = source.index("{", matches[0].start())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[matches[0].start():index + 1]
    raise AssertionError(f"unterminated function {name}")


def test_ce_tick_input_and_ps2_render_cadence_do_not_change_tick_state():
    game = (HCU / "source/game/game.c").read_text()
    scheduler = (HCU / "source/game/game_time.c").read_text()
    input_source = (HCU / "source/input/input_xbox.c").read_text()
    render_source = (HCU / "port/ps2/src/ps2_render.c").read_text()
    tick = extract_function(game, "game_tick")
    update = extract_function(scheduler, "game_time_update")
    input_begin = extract_function(input_source, "input_frame_begin")
    input_end = extract_function(input_source, "input_frame_end")
    render = extract_function(render_source, "render_frame")
    bitmap_frame_run = extract_function(render_source, "ps2_bitmap_frame_run")
    advance = extract_function(render_source, "ps2_render_frame_state_advance")

    prefix = r'''
#include "stream/hcu_render_snapshot.h"
#include "halo_ps2_bitmap_frame.h"
#include <assert.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef float real;
typedef unsigned char byte;
typedef byte boolean;
typedef unsigned short word;
#define TRUE 1
#define FALSE 0
#define NONE -1
#define TICKS_PER_SECOND 30
#define MAXIMUM_LOCAL_PLAYERS 4
#define SOME_LARGE_NUMBER_OF_TICKS 1000
#define MIN(a,b) ((a)<(b)?(a):(b))
#define match_assert(file,line,condition) ((void)0)
#define profile_scope(section, ...) { (void)(section); __VA_ARGS__ }
#define profile_enter(section) ((void)(section))
#define profile_exit(section) ((void)(section))
enum {
 game_update_section=1, game_tick_cheats_enforce_section,
 game_tick_remove_quitting_players_section, game_tick_allegiance_section,
 game_tick_units_section, game_tick_ai_section, game_tick_actors_drive_section,
 game_tick_players_before_section, game_tick_effects_section,
 game_tick_antennas_section, game_tick_first_person_section,
 game_tick_game_engine_section, game_tick_editor_section, game_tick_hs_section,
 game_tick_recorded_animations_section, game_tick_objects_section,
 game_tick_players_after_section, game_tick_hud_section,
 game_tick_player_effect_section, game_time_render_interpolation_tick_section,
 game_time_network_distributed_tick_section, game_time_game_frame_section,
 _game_connection_local, _game_connection_network_client,
 _game_connection_network_server, _game_connection_film_playback,
 _object_mask_all=-1
};
struct game_globals_definition { boolean active, players_are_double_speed; };
static struct game_globals_definition globals = { TRUE, FALSE };
static struct game_globals_definition *game_globals = &globals;
struct game_time_globals_struct {
 boolean initialized, active, paused;
 short monitor_state, monitor_counter, monitor_latency;
 long local_time; short last_local_time_elapsed; long server_time;
 real speed, leftover_dt;
};
static struct game_time_globals_struct game_time_storage = {0,TRUE,FALSE,0,0,0,0,0,0,1.0f,0.0f};
static struct game_time_globals_struct *game_time_globals = &game_time_storage;
struct render_camera {
 struct { float x,y,z; } position, forward, up;
 float vertical_field_of_view, z_near, z_far;
 union { float v[4]; } viewport_bounds, window_bounds;
};
struct render_globals {
 int frame_index, window_index, local_player_index;
 float time_delta_since_tick_sec; struct render_camera camera;
};
    struct render_window { boolean console_window; short local_player_index; struct render_camera render_camera; struct { struct { float x0,y0,x1,y1; } viewport_bounds; } rasterizer_camera; };
struct real_matrix4x3 {
 float scale; struct {float i,j,k;} forward,left,up;
 struct {float x,y,z;} position;
};
struct object_datum { int definition_index; struct { byte type,render_flags; } object; };
struct object_iterator { long index; int cursor; };
struct object_header { int valid; };
struct bitmap_data { int unused; };
typedef struct { float x,y; } point2d;
struct input_globals_fixture { boolean frame_active; };
static struct input_globals_fixture input_globals;
static struct render_globals render;
static struct object_header object_header_storage={1};
static struct object_header *object_header_data=&object_header_storage;
static boolean render_contrails_enabled=TRUE, render_particles_enabled=TRUE;
static boolean render_particle_systems_enabled=TRUE, render_weather_particle_systems_enabled=TRUE;
static boolean render_shadows=TRUE;
    static halo_ps2_bitmap_frame_consumer s_bitmap_frame_consumer;
    static uint8_t s_bitmap_frame_consumer_registered, s_bitmap_frame_active;
    static int32_t s_bitmap_frame_status;
    static uint32_t s_bitmap_frame_failures;
static struct object_datum objects[1];
static struct real_matrix4x3 matrices[1];
static uint32_t rng_state=0x13579BDFu;
static uint32_t consumed_sample, frame_sample, next_sample=1, poll_count, read_count;
static uint32_t ticks, object_updates, first_person_renders;
static unsigned char snapshot_storage[
 ((sizeof(halo_ps2_render_snapshot)+15u)&~(size_t)15u)*2u]
 __attribute__((aligned(16)));
long game_connection(void);
void update_client_local_ticks(long);
void network_game_server_update_ticks(void *, short);
void *global_network_game_server_get(void);
long update_client_get_maximum_possible_server_time(void);
boolean game_time_held(void);
real game_time_get_speed(void);
void game_tick(void);
void render_interpolation_tick(void);
void network_distributed_tick(void);
void render_interpolation_frame_begin(void);
void game_frame(real);
void render_interpolation_frame_end(void);
void ps2_input_poll_devices(void);
void input_get_device_states(void);
void acquire_input_mutex(void);
void release_input_mutex(void);
    void interface_draw_screen(void);
    void render_ui_widgets(short, void const *);
void profile_tick_start(void);
void collision_log_begin_period(int);
void collision_log_end_period(void);
void profile_tick_end(void);
void real_math_reset_precision(void);
void game_state_check_data_arrays(void);
void lights_port_recover(void);
void cheats_network_client_enforce(void);
void remove_quitting_players_from_game(void);
void game_allegiance_update(void);
boolean network_game_distributed_client(void);
void units_update(void);
void ai_update(void);
void network_actors_drive(void);
void players_update_before_game(void);
void effects_update(real);
void antennas_update(real);
void lock_global_random_seed(void);
void rumble_update(void);
void first_person_weapons_update(void);
void unlock_global_random_seed(void);
void game_engine_update(void);
void editor_update(void);
boolean network_coop_active(void);
void hs_update(void);
void recorded_animations_update(void);
void objects_update(void);
void players_update_after_game(void);
void hud_update(void);
void player_effect_update(void);
void first_person_weapon_render_update(void);
unsigned first_person_weapon_copy_node_matrices(short, void *, unsigned);
void object_iterator_new(struct object_iterator *, int, int);
struct object_datum *object_iterator_next(struct object_iterator *);
void object_get_world_matrix(long, struct real_matrix4x3 *);
'''

    suffix = bitmap_frame_run + "\n" + advance + "\n" + render + "\n" + input_begin + "\n" + input_end + "\n" + update + "\n" + tick + r'''
long game_connection(void) { return _game_connection_local; }
void update_client_local_ticks(long n) { (void)n; }
void network_game_server_update_ticks(void *p, short n) { (void)p;(void)n; }
void *global_network_game_server_get(void) { return 0; }
long update_client_get_maximum_possible_server_time(void) { return 10000; }
boolean game_time_held(void) { return FALSE; }
real game_time_get_speed(void) { return game_time_globals->speed; }
void render_interpolation_tick(void) {}
void network_distributed_tick(void) {}
void render_interpolation_frame_begin(void) {}
void game_frame(real delta) { (void)delta; }
void render_interpolation_frame_end(void) {}
void ps2_input_poll_devices(void) { poll_count++; consumed_sample=next_sample; }
void input_get_device_states(void) { read_count++; frame_sample=consumed_sample; }
void acquire_input_mutex(void) {}
void release_input_mutex(void) {}
void profile_tick_start(void) {}
void collision_log_begin_period(int n) { (void)n; }
void collision_log_end_period(void) {}
void profile_tick_end(void) {}
void real_math_reset_precision(void) {}
void game_state_check_data_arrays(void) {}
void lights_port_recover(void) {}
void cheats_network_client_enforce(void) {}
void remove_quitting_players_from_game(void) {}
void game_allegiance_update(void) {}
boolean network_game_distributed_client(void) { return FALSE; }
void units_update(void) {}
void ai_update(void) {}
void network_actors_drive(void) {}
void players_update_before_game(void) {}
void effects_update(real d) { (void)d; }
void antennas_update(real d) { (void)d; }
void lock_global_random_seed(void) {}
void rumble_update(void) {}
void first_person_weapons_update(void) { rng_state=rng_state*1664525u+1013904223u; }
void unlock_global_random_seed(void) {}
void game_engine_update(void) {}
void editor_update(void) {}
boolean network_coop_active(void) { return FALSE; }
void hs_update(void) {}
void recorded_animations_update(void) {}
void objects_update(void) {
  object_updates++; matrices[0].position.x += (float)(consumed_sample & 3u)+1.0f;
  rng_state = rng_state*1664525u+1013904223u;
}
void players_update_after_game(void) {}
void hud_update(void) {}
void player_effect_update(void) {}
void first_person_weapon_render_update(void) { first_person_renders++; }
void interface_draw_screen(void) {}
void render_ui_widgets(short player, void const *bounds) { (void)player; (void)bounds; }
unsigned first_person_weapon_copy_node_matrices(short p, void *o, unsigned c)
{ (void)p;(void)o;(void)c; return 0; }
void object_iterator_new(struct object_iterator *i,int m,int f)
{ (void)m;(void)f;i->index=-1;i->cursor=0; }
struct object_datum *object_iterator_next(struct object_iterator *i)
{ if(i->cursor) return 0; i->index=0; i->cursor++; return &objects[0]; }
void object_get_world_matrix(long i,struct real_matrix4x3 *out)
{ assert(i==0); memcpy(out,&matrices[0],sizeof(*out)); }
static uint32_t authoritative_state_hash(void) {
 uint32_t h=2166136261u; const unsigned char *p;
 const void *parts[]={&game_time_storage.local_time,&rng_state,objects,matrices,&frame_sample};
 const size_t sizes[]={sizeof(game_time_storage.local_time),sizeof(rng_state),sizeof(objects),sizeof(matrices),sizeof(frame_sample)};
 for(int k=0;k<5;k++){ p=(const unsigned char*)parts[k]; for(size_t q=0;q<sizes[k];q++) h=(h^p[q])*16777619u; }
 return h;
}
int main(void) {
 point2d page={0,0}, shot={0,0}; struct bitmap_data bitmap={0};
 struct render_window window; unsigned char store_before[sizeof(matrices)];
     int schedule,step,r; static uint32_t trace[4];
 assert(hcu_render_snapshot_bind(snapshot_storage,sizeof(snapshot_storage))==0);
 objects[0].definition_index=17; objects[0].object.type=2; objects[0].object.render_flags=1;
 matrices[0].scale=1.0f; matrices[0].forward.i=1.0f; matrices[0].left.j=1.0f;
 matrices[0].up.k=1.0f; matrices[0].position.z=4.0f;
 window.console_window=FALSE; window.local_player_index=0;
 window.render_camera.forward.x=1.0f; window.render_camera.up.z=1.0f;
 window.render_camera.vertical_field_of_view=1.0f;
 window.render_camera.z_near=0.1f; window.render_camera.z_far=100.0f;
 for(schedule=0;schedule<3;schedule++) {
   /* Start each render schedule with a fresh publisher and no retained reader. */
   hcu_render_snapshot_unbind();
   assert(hcu_render_snapshot_bind(snapshot_storage,sizeof(snapshot_storage))==0);
   memset(&game_time_storage,0,sizeof(game_time_storage));
   game_time_storage.active=TRUE; game_time_storage.speed=1.0f;
   input_globals.frame_active=FALSE; next_sample=1; poll_count=read_count=0;
       consumed_sample=frame_sample=0; ticks=object_updates=first_person_renders=0;
   rng_state=0x13579BDFu; memset(&matrices[0].position.x,0,sizeof(float));
   matrices[0].position.z=4.0f; render.frame_index=0;
   for(step=0;step<4;step++) {
     next_sample=(uint32_t)(step+1);
     input_frame_begin();
     if(!(input_globals.frame_active && poll_count==read_count && poll_count==(uint32_t)(step+1)))
       fprintf(stderr,"input state active=%u poll=%u read=%u step=%d\\n",input_globals.frame_active,poll_count,read_count,step);
     assert(input_globals.frame_active && poll_count==read_count && poll_count==(uint32_t)(step+1));
     /* Verify the port poll occurs before CE's state snapshot. */
     assert(consumed_sample==next_sample && frame_sample==next_sample);
     ticks++;
     game_time_update(0.034f);
     assert(game_time_storage.local_time==ticks);
     assert(object_updates==ticks);
     memcpy(store_before,matrices,sizeof(matrices));
     /* A sub-tick frame must not mutate authoritative simulation state. */
     { uint32_t hash_before=authoritative_state_hash();
       game_time_update(0.001f);
       assert(game_time_storage.local_time==ticks);
       assert(authoritative_state_hash()==hash_before); }
     if(schedule==0) r=0; else if(schedule==1) r=1; else r=3;
     for(int j=0;j<r;j++) {
       window.render_camera.position.x=(float)(100+step*3+j);
       render_frame(&window,1,&page,&shot,&bitmap,1.0f/60.0f);
       assert(memcmp(store_before,matrices,sizeof(matrices))==0);
     }
     /* FNV over tick-owned time, RNG, CE object identity and transform. */
     { uint32_t h=authoritative_state_hash();
       if(schedule==0) trace[step]=h;
       else assert(trace[step]==h);
     }
   }
   assert(first_person_renders==(uint32_t)(4*(schedule==0?0:(schedule==1?1:3))));
       assert(render.frame_index==4*(schedule==0?0:(schedule==1?1:3)));
       if(schedule==0) assert(hcu_render_snapshot_latest()==NULL);
       else {
         halo_ps2_render_snapshot const *published=hcu_render_snapshot_latest();
         assert(published && published->object_count==1);
         assert(published->frame_index==(uint32_t)render.frame_index);
         assert(published->objects[0].world.position[0]==matrices[0].position.x);
       }
   assert(ticks==4 && object_updates==4);
   input_frame_end();
 }
 hcu_render_snapshot_unbind();
 puts("integrated-source-slice ticks=4 render-schedules=0,1,3 input-before-snapshot=true no-tick-stable=true status=passed");
 return 0;
}
'''

    # Audit that the extraction points stay the expected pinned source functions.
    assert "ps2_input_poll_devices();" in input_begin
    assert input_begin.index("ps2_input_poll_devices();") < input_begin.index("input_get_device_states();")
    assert "game_tick();" in update and "render_interpolation_frame_begin();" in update
    assert "object_iterator_new(&iterator" in render and "halo_ps2_render_snapshot_commit(snapshot)" in render

    engine = ROOT / "submodules/halo-ps2/engine/src"
    with tempfile.TemporaryDirectory(prefix="hcu-m3-tick-render-") as temp:
        temp = Path(temp)
        cfile, exe = temp / "fixture.c", temp / "fixture"
        cfile.write_text(prefix + suffix)
        built = subprocess.run([
            "cc", "-std=c11", "-DHALO_PS2=1", "-Wall", "-Wextra", "-Werror",
            "-Wno-unused-function", "-Wno-address",
            "-Isrc", "-I" + str(engine), "-I" + str(HCU / "source"),
            "-I" + str(HCU / "port/ps2/include"), str(cfile),
            str(HCU / "port/ps2/src/ps2_animation_trace.c"),
            "src/stream/hcu_render_snapshot.c", str(engine / "core/mat.c"),
                str(engine / "render/chain.c"),
            "-lm", "-o", str(exe)], cwd=ROOT, capture_output=True, text=True)
        assert built.returncode == 0, built.stdout + built.stderr
        run = subprocess.run([str(exe)], capture_output=True, text=True)
        assert run.returncode == 0, run.stdout + run.stderr
        assert "status=passed" in run.stdout
