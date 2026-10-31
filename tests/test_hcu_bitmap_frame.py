"""Exercise the bounded frame hook ordering; this is not product-frame proof."""
from pathlib import Path
import re
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RENDER = ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_render.c"


def extract_function(source: str, name: str) -> str:
    match = re.search(r"^[ \t]*(?:(?:static )?int32_t|void) " + name + r"\s*\([^;{}]*\)\s*\{",
                      source, re.MULTILINE)
    assert match, f"missing implementation {name}"
    opening = source.index("{", match.start())
    depth = 0
    for index in range(opening, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[match.start():index + 1]
    raise AssertionError(f"unterminated function {name}")


def test_bounded_hook_executes_order_and_fails_closed(tmp_path):
    source = RENDER.read_text()
    hook = extract_function(source, "ps2_bitmap_frame_run")
    register = extract_function(source, "halo_ps2_bitmap_frame_consumer_register")
    pregame = extract_function(source, "render_frame_pregame")
    frame = source[source.index("void render_frame(\n"):]
    assert frame.index("ps2_bitmap_frame_run(windoze, window_count)") < frame.index(
        "halo_ps2_render_snapshot_begin()")
    assert "if (frame_status != HALO_PS2_BITMAP_FRAME_OK)" in frame
    assert hook.index("interface_draw_screen();") < hook.index("render_ui_widgets(")
    assert "s_bitmap_frame_status = HALO_PS2_BITMAP_FRAME_NOT_READY;" in pregame
    assert pregame.index("s_bitmap_frame_consumer_registered") < pregame.index("render.frame_index++")

    harness = r'''
#include "halo_ps2_bitmap_frame.h"
#include <assert.h>
#include <stdint.h>
#include <string.h>
#define NONE -1
#define TRUE 1
#define FALSE 0
#define MAXIMUM_LOCAL_PLAYERS 4
typedef float real;
typedef struct { float x0, y0, x1, y1; } rectangle2d;
struct render_camera { int token; };
struct render_window {
  int console_window;
  short local_player_index;
  struct render_camera render_camera;
  struct { rectangle2d viewport_bounds; } rasterizer_camera;
};
struct render_globals { int frame_index, window_index, local_player_index;
  struct render_camera camera; };
static struct render_globals render;
static halo_ps2_bitmap_frame_consumer s_bitmap_frame_consumer;
static int s_bitmap_frame_consumer_registered = 1;
static int s_bitmap_frame_active;
struct render_screen_flash { short type; float intensity; struct { float alpha, red, green, blue; } color; };
static short stub_flash_type;
static int flash_requests; static short flash_request_type; static float flash_request_rgba[4];
static void player_effect_get_screen_flash(short player, struct render_screen_flash *flash) {
  (void)player; flash->type = stub_flash_type; flash->intensity = 0.5f;
  flash->color.red = 1.0f; flash->color.green = 0.5f; flash->color.blue = 0.25f; flash->color.alpha = 1.0f;
}
static void halo_ps2_bitmap_request_screen_flash(short type, float r, float g, float b, float a) {
  flash_requests++; flash_request_type = type;
  flash_request_rgba[0] = r; flash_request_rgba[1] = g; flash_request_rgba[2] = b; flash_request_rgba[3] = a;
}
static real hud_split_view_begin(struct render_camera *saved) {
  if (saved) *saved = render.camera;
  return 1.0f;
}
static void hud_split_view_end(struct render_camera *saved) {
  if (saved) render.camera = *saved;
}
int events[32], event_count;
static int view_count;
static int fail_view;
static uint16_t expected_active = 2;
halo_ps2_bitmap_real_producer_descriptor const halo_ps2_real_producer_descriptor_instance =
  { HALO_PS2_BITMAP_REAL_PRODUCER_MAGIC, HALO_PS2_BITMAP_REAL_PRODUCER_VERSION,
    HALO_PS2_BITMAP_FRAME_REQUIRED_PRODUCERS };
void first_person_weapon_render_update(void) { events[event_count++] = 3; }
void interface_draw_screen(void) __attribute__((weak));
void render_ui_widgets(short player, rectangle2d const *bounds) __attribute__((weak));
void frame_log(int event) { events[event_count++] = event; }
static int32_t begin(void *ctx, uint32_t frame, uint16_t count) {
  (void)ctx; assert(frame == 12 && count == expected_active); events[event_count++] = 1; return 0;
}
static int32_t set_view(void *ctx, uint16_t view, int16_t player) {
  (void)ctx;
  if (expected_active == 2) assert((view == 0 && player == 2) || (view == 1 && player == 3));
  else assert(view == (uint16_t)player && player >= 0 && player < 4);
  view_count++; events[event_count++] = 2;
  return fail_view && view == 1 ? -1 : 0;
}
static int32_t end(void *ctx, uint32_t frame, int32_t prior) {
  (void)ctx; assert(frame == 12); events[event_count++] = 6;
  return prior;
}
'''
    harness += register + "\n" + hook + r'''
int main(void) {
  struct render_window windows[3];
  memset(windows, 0, sizeof(windows));
  windows[0].local_player_index = 2;
  windows[1].local_player_index = 3;
  windows[2].console_window = TRUE;
  render.frame_index = 12;
  s_bitmap_frame_consumer.begin = begin;
  s_bitmap_frame_consumer.set_view = set_view;
  s_bitmap_frame_consumer.end = end;
  s_bitmap_frame_consumer.producer_capabilities =
    HALO_PS2_BITMAP_FRAME_REQUIRED_PRODUCERS;
  s_bitmap_frame_consumer_registered = 0;
  assert(halo_ps2_bitmap_frame_consumer_register(&s_bitmap_frame_consumer) ==
    HALO_PS2_BITMAP_FRAME_OK);
  {
    halo_ps2_bitmap_frame_consumer replacement = s_bitmap_frame_consumer;
    replacement.context = (void *)1;
    assert(halo_ps2_bitmap_frame_consumer_register(&replacement) ==
      HALO_PS2_BITMAP_FRAME_BUSY);
    assert(s_bitmap_frame_consumer.context == 0);
  }
  assert(ps2_bitmap_frame_run(windows, 3) == HALO_PS2_BITMAP_FRAME_OK);
  assert(event_count == 10 && view_count == 2);
  assert(events[0] == 1 && events[1] == 3 && events[2] == 2 &&
    events[3] == 4 && events[4] == 5 && events[5] == 3 &&
    events[6] == 2 && events[7] == 4 && events[8] == 5 && events[9] == 6);
  assert(!s_bitmap_frame_active && render.window_index == 0 &&
    render.local_player_index == 0);
  assert(flash_requests == 0);
  stub_flash_type = 1; event_count = view_count = 0;
  assert(ps2_bitmap_frame_run(windows, 3) == HALO_PS2_BITMAP_FRAME_OK);
  assert(flash_requests == 2 && flash_request_type == 1 &&
    flash_request_rgba[0] == 0.5f && flash_request_rgba[1] == 0.25f &&
    flash_request_rgba[2] == 0.125f && flash_request_rgba[3] == 0.5f);
  stub_flash_type = 0; event_count = view_count = 0;
  {
    struct render_window four_players_and_console[5];
    int i;
    memset(four_players_and_console, 0, sizeof(four_players_and_console));
    for (i = 0; i < 4; i++) four_players_and_console[i].local_player_index = (short)i;
    four_players_and_console[4].console_window = TRUE;
    event_count = view_count = 0; expected_active = 4;
    assert(ps2_bitmap_frame_run(four_players_and_console, 5) ==
      HALO_PS2_BITMAP_FRAME_OK);
    assert(view_count == 4 && event_count == 18);
    assert(events[0] == 1 && events[17] == 6);
  }
  expected_active = 2;
  event_count = view_count = 0; fail_view = 1;
  assert(ps2_bitmap_frame_run(windows, 3) ==
    HALO_PS2_BITMAP_FRAME_CALLBACK_FAILED);
  assert(event_count == 8 && events[0] == 1 && events[1] == 3 &&
    events[2] == 2 && events[3] == 4 && events[4] == 5 &&
    events[5] == 3 && events[6] == 2 && events[7] == 6);
  assert(!s_bitmap_frame_active);
  event_count = 0;
  assert(ps2_bitmap_frame_run((struct render_window *)1, 6) ==
    HALO_PS2_BITMAP_FRAME_WINDOW_LIMIT);
  assert(event_count == 0);
  return 0;
}
'''
    source_path = tmp_path / "frame-hook.c"
    producers = tmp_path / "producer-stubs.c"
    binary = tmp_path / "frame-hook"
    source_path.write_text(harness)
    producers.write_text(r'''
typedef struct { float x0, y0, x1, y1; } rectangle2d;
void frame_log(int event);
void interface_draw_screen(void) { frame_log(4); }
void render_ui_widgets(short player, rectangle2d const *bounds) {
  (void)player; (void)bounds; frame_log(5);
}
''')
    built = subprocess.run([
        "cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
        "-I", str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
        str(source_path), str(producers), "-o", str(binary),
    ], capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    ran = subprocess.run([str(binary)], capture_output=True, text=True)
    assert ran.returncode == 0, ran.stdout + ran.stderr
