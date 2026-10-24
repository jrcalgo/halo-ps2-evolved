"""Execute the actual CE PS2 render_frame body against immutable object stubs."""
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RENDER_C = ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_render.c"


def extract_function(source: str, name: str) -> str:
    import re

    matches = list(re.finditer(
        r"^[ \t]*(?:static\s+)?void\s+" + re.escape(name) +
        r"\s*\([^;{}]*\)\s*\{", source, re.MULTILINE))
    if len(matches) != 1:
        raise AssertionError(f"expected one definition of {name}, found {len(matches)}")
    start = matches[0].start()
    opening = source.index("{", matches[0].start())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"unterminated function {name}")


def extract_bitmap_hook(source: str) -> str:
    import re
    match = re.search(r"^[ \t]*static int32_t ps2_bitmap_frame_run\s*\([^;{}]*\)\s*\{",
                      source, re.MULTILINE)
    assert match, "missing bounded bitmap frame hook"
    opening = source.index("{", match.start())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{": depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0: return source[match.start():index + 1]
    raise AssertionError("unterminated bitmap frame hook")


def test_production_render_frame_is_read_only_over_ce_object_state():
    render_source = RENDER_C.read_text()
    render_frame = extract_function(render_source, "render_frame")
    advance_frame = extract_function(render_source, "ps2_render_frame_state_advance")
    bitmap_hook = extract_bitmap_hook(render_source)
    prefix = r'''
#include "stream/hcu_render_snapshot.h"
#include "ps2_animation_trace.h"
#include "halo_ps2_bitmap_frame.h"
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>
typedef float real;
typedef unsigned char byte;
typedef unsigned char boolean;
typedef unsigned short word;
typedef unsigned long dword;
#define TRUE 1
#define FALSE 0
#define NONE -1
#define MAXIMUM_LOCAL_PLAYERS 4
enum { _object_mask_all = -1 };
typedef struct { float x, y; } point2d;
typedef struct { float x0, y0, x1, y1; } rectangle2d;
struct bitmap_data { int unused; };
struct real_matrix4x3 {
  float scale;
  struct { float i, j, k; } forward, left, up;
  struct { float x, y, z; } position;
};
struct render_camera {
  struct { float x, y, z; } position, forward, up;
  float vertical_field_of_view, z_near, z_far;
  union { float v[4]; } viewport_bounds, window_bounds;
};
struct render_globals {
  int frame_index, window_index, local_player_index;
  float time_delta_since_tick_sec;
  struct render_camera camera;
};
struct render_window {
  boolean console_window;
  short local_player_index;
  struct render_camera render_camera;
  struct { rectangle2d viewport_bounds; } rasterizer_camera;
};
struct object_datum {
  int definition_index;
  struct { byte type, render_flags; } object;
};
struct object_iterator { long index; int cursor; };
struct object_header { int valid; };
static struct render_globals render;
static struct object_header object_header_storage = { 1 };
static struct object_header *object_header_data = &object_header_storage;
static int render_contrails_enabled = 1, render_particles_enabled = 1;
static int render_particle_systems_enabled = 1;
static int render_weather_particle_systems_enabled = 1, render_shadows = 1;
static int s_bitmap_frame_consumer_registered;
static int s_bitmap_frame_active;
static int32_t s_bitmap_frame_status;
static uint32_t s_bitmap_frame_failures;
static halo_ps2_bitmap_frame_consumer s_bitmap_frame_consumer;
static int frame_events[16], frame_event_count;
halo_ps2_bitmap_real_producer_descriptor const
  halo_ps2_real_producer_descriptor_instance = {
    HALO_PS2_BITMAP_REAL_PRODUCER_MAGIC,
    HALO_PS2_BITMAP_REAL_PRODUCER_VERSION,
    HALO_PS2_BITMAP_FRAME_REQUIRED_PRODUCERS
  };
static struct object_datum objects[2];
static struct real_matrix4x3 matrices[2];
static unsigned first_person_updates, matrix_reads;
static struct object_datum objects_before[2];
static struct real_matrix4x3 matrices_before[2];
static unsigned char state_sentinel[64], sentinel_before[sizeof(state_sentinel)];
static struct ps2_animation_trace_event trace_events[8];
static struct ps2_animation_trace_context trace_contexts[8];
extern halo_ps2_render_snapshot *halo_ps2_render_snapshot_begin(void)
  __attribute__((weak));
extern int halo_ps2_render_snapshot_commit(halo_ps2_render_snapshot *)
  __attribute__((weak));
static void ps2_render_frame_state_advance(struct render_window *, short, real);
void interface_draw_screen(void) __attribute__((weak));
void render_ui_widgets(short, void const *) __attribute__((weak));
static int32_t frame_begin(void *, uint32_t, uint16_t);
static int32_t frame_set_view(void *, uint16_t, int16_t);
static int32_t frame_end(void *, uint32_t, int32_t);
void first_person_weapon_render_update(void);
unsigned first_person_weapon_copy_node_matrices(short, void *, unsigned);
void object_iterator_new(struct object_iterator *, int, int);
struct object_datum *object_iterator_next(struct object_iterator *);
void object_get_world_matrix(long, struct real_matrix4x3 *);
'''
    suffix = r'''
static int32_t frame_begin(void *ctx, uint32_t frame, uint16_t count) {
  (void)ctx; assert(frame > 0 && count == 1); frame_events[frame_event_count++] = 1; return 0;
}
static int32_t frame_set_view(void *ctx, uint16_t view, int16_t player) {
  (void)ctx; assert(view == 0 && player == 0); frame_events[frame_event_count++] = 2; return 0;
}
static int32_t frame_end(void *ctx, uint32_t frame, int32_t prior) {
  (void)ctx; assert(frame > 0 && prior == 0); frame_events[frame_event_count++] = 5; return 0;
}
void frame_producer_event(int event) { frame_events[frame_event_count++] = event; }
'''+bitmap_hook+"\n"+render_frame+r'''
void interface_draw_screen(void) { frame_producer_event(3); }
void render_ui_widgets(short player, void const *bounds) {
  assert(player == 0 && bounds); frame_producer_event(4);
}
void first_person_weapon_render_update(void) { first_person_updates++; }
unsigned first_person_weapon_copy_node_matrices(short player, void *out,
  unsigned capacity) { (void)player; (void)out; (void)capacity; return 0; }
void object_iterator_new(struct object_iterator *it, int mask, int flags) {
  (void)mask; (void)flags; it->index = -1; it->cursor = 0;
}
struct object_datum *object_iterator_next(struct object_iterator *it) {
  if (it->cursor >= 2) return 0;
  it->index = it->cursor;
  return &objects[it->cursor++];
}
void object_get_world_matrix(long index, struct real_matrix4x3 *out) {
  assert(index >= 0 && index < 2);
  matrix_reads++;
  memcpy(out, &matrices[index], sizeof(*out));
}
int main(void) {
  struct render_window windows[1];
  point2d page = { 0, 0 }, shot = { 0, 0 };
  struct bitmap_data bitmap = { 0 };
  halo_ps2_render_snapshot const *published;
  unsigned count, i;
  static unsigned char storage[
    ((sizeof(halo_ps2_render_snapshot) + 15u) & ~(size_t)15u) * 2u]
    __attribute__((aligned(16)));
  assert(ps2_animation_trace_bind(trace_events, 8));
  assert(ps2_animation_trace_bind_contexts(trace_contexts, 8));
  ps2_animation_trace_reset();
  assert(hcu_render_snapshot_bind(storage, sizeof(storage)) == 0);
  objects[0].definition_index = 7; objects[0].object.type = 2;
  objects[0].object.render_flags = 3;
  objects[1].definition_index = 11; objects[1].object.type = 4;
  objects[1].object.render_flags = 5;
  for (i = 0; i < 2; ++i) {
    matrices[i].scale = 1.0f;
    matrices[i].forward.i = 1.0f;
    matrices[i].left.j = 1.0f;
    matrices[i].up.k = 1.0f;
    matrices[i].position.x = (float)(10 + i);
    matrices[i].position.y = (float)(20 + i);
    matrices[i].position.z = (float)(30 + i);
  }
  memcpy(objects_before, objects, sizeof(objects));
  memcpy(matrices_before, matrices, sizeof(matrices));
  windows[0].console_window = FALSE;
  windows[0].local_player_index = 0;
  windows[0].render_camera.position.x = 1.0f;
  windows[0].render_camera.position.y = 2.0f;
  windows[0].render_camera.position.z = 3.0f;
  windows[0].render_camera.forward.x = 1.0f;
  windows[0].render_camera.up.z = 1.0f;
  windows[0].render_camera.vertical_field_of_view = 1.0f;
  windows[0].render_camera.z_near = 0.1f;
  windows[0].render_camera.z_far = 100.0f;
  memset(state_sentinel, 0x6D, sizeof(state_sentinel));
  memcpy(sentinel_before, state_sentinel, sizeof(state_sentinel));

  for (count = 0; count <= 2; ++count) {
    for (i = 0; i < count; ++i)
      render_frame(windows, 1, &page, &shot, &bitmap, 1.0f / 60.0f);
    if (count) {
      long row = ps2_animation_trace_count();
      ps2_animation_trace_record(_ps2_animation_trace_frame_info, NULL, NULL,
        0, 0, 0, 1);
      assert(ps2_animation_trace_events()[row].context_token == row + 1);
      assert(ps2_animation_trace_contexts()[row].render_frame ==
        (unsigned)(count * (count + 1) / 2));
      assert(ps2_animation_trace_contexts()[row].valid_mask &
        _ps2_animation_trace_context_render_frame);
      assert(!(ps2_animation_trace_contexts()[row].valid_mask &
        _ps2_animation_trace_context_tick));
    }
    assert(memcmp(objects, objects_before, sizeof(objects)) == 0);
    assert(memcmp(matrices, matrices_before, sizeof(matrices)) == 0);
    assert(memcmp(state_sentinel, sentinel_before, sizeof(state_sentinel)) == 0);
    if (count) {
      published = hcu_render_snapshot_latest();
      assert(published && published->object_count == 2);
      assert(published->objects[0].datum_index == 0);
      assert(published->objects[1].datum_index == 1);
      assert(published->objects[0].definition_index == 7);
      assert(published->objects[1].definition_index == 11);
      assert(published->objects[0].world.position[0] == 10.0f);
      assert(published->objects[1].world.position[0] == 11.0f);
      assert(published->sequence > 0);
      assert(memcmp(objects, objects_before, sizeof(objects)) == 0);
      assert(memcmp(matrices, matrices_before, sizeof(matrices)) == 0);
      assert(memcmp(state_sentinel, sentinel_before,
        sizeof(state_sentinel)) == 0);
    }
  }
  assert(first_person_updates == 3);
  assert(matrix_reads == 6);
  s_bitmap_frame_consumer.begin = frame_begin;
  s_bitmap_frame_consumer.set_view = frame_set_view;
  s_bitmap_frame_consumer.end = frame_end;
  s_bitmap_frame_consumer.context = 0;
  s_bitmap_frame_consumer.producer_capabilities =
    HALO_PS2_BITMAP_FRAME_REQUIRED_PRODUCERS;
  s_bitmap_frame_consumer_registered = 1;
  render_frame(windows, 1, &page, &shot, &bitmap, 1.0f / 60.0f);
  assert(frame_event_count == 5 && frame_events[0] == 1 &&
    frame_events[1] == 2 && frame_events[2] == 3 &&
    frame_events[3] == 4 && frame_events[4] == 5);
  assert(s_bitmap_frame_status == HALO_PS2_BITMAP_FRAME_OK);
  assert(first_person_updates == 4 && matrix_reads == 8);
  {
    unsigned before_frame = (unsigned)render.frame_index;
    render_frame((struct render_window *)1, 6, &page, &shot, &bitmap,
      1.0f / 60.0f);
    assert((unsigned)render.frame_index == before_frame);
    assert(s_bitmap_frame_status == HALO_PS2_BITMAP_FRAME_WINDOW_LIMIT);
    assert(s_bitmap_frame_failures == 1 && first_person_updates == 4 &&
      matrix_reads == 8);
  }
  hcu_render_snapshot_unbind();
  return 0;
}
'''
    engine = ROOT / "submodules/halo-ps2/engine/src"
    with tempfile.TemporaryDirectory(prefix="hcu-render-frame-") as temp:
        temp_path = Path(temp)
        harness = temp_path / "render-frame.c"
        executable = temp_path / "render-frame"
        harness.write_text(prefix + advance_frame + suffix)
        built = subprocess.run([
            "cc", "-std=c11", "-Wall", "-Wextra", "-Werror", "-Wno-address",
            "-DHALO_PS2=1", "-DHALO_PS2_M2_ANIMATION_TRACE=1",
            "-Isrc", "-I" + str(engine),
            "-I" + str(ROOT / "submodules/halo-ce-universal/source"),
            "-I" + str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
            str(harness),
            str(ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_animation_trace.c"),
            "src/stream/hcu_render_snapshot.c",
            str(engine / "render/chain.c"),
            str(engine / "core/mat.c"), "-lm", "-o", str(executable),
        ], cwd=ROOT, capture_output=True, text=True)
        assert built.returncode == 0, built.stdout + built.stderr
        result = subprocess.run([str(executable)], capture_output=True, text=True)
        assert result.returncode == 0, result.stdout + result.stderr
