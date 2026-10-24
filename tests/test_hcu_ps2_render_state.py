from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
RENDER_C = ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_render.c"


def _function(source, signature):
	start = source.index(signature)
	opening = source.index("{", start)
	depth = 0
	for index in range(opening, len(source)):
		if source[index] == "{":
			depth += 1
		elif source[index] == "}":
			depth -= 1
			if depth == 0:
				return source[start:index + 1]
	raise AssertionError(f"unterminated function: {signature}")


def test_ps2_render_frame_state_with_synthetic_windows():
	source = RENDER_C.read_text()
	render_state_advance = _function(source,
		"static void ps2_render_frame_state_advance(")
	render_frame = _function(source, "void render_frame(")
	render_pregame = _function(source, "void render_frame_pregame(")
	assert "ps2_render_frame_state_advance(windoze, window_count," in render_frame
	assert render_frame.index("ps2_render_frame_state_advance(") < \
		render_frame.index("first_person_weapon_render_update();")
	fixture = r"""
#include <assert.h>
#define NONE -1
#define HALO_PS2_BITMAP_FRAME_NOT_READY -3
typedef float real;
typedef unsigned char boolean;
typedef struct { float x, y, z; } point2d;
struct bitmap_data { int unused; };
struct test_camera { float marker; };
struct render_window {
	boolean console_window;
	short local_player_index;
	struct test_camera render_camera;
};
struct render_globals {
	unsigned frame_index;
	real time_delta_since_tick_sec;
	short window_index;
	short local_player_index;
	struct test_camera camera;
} render;
int s_bitmap_frame_consumer_registered;
int s_bitmap_frame_status;
unsigned s_bitmap_frame_failures;
""";
	main = r"""
int main(void)
{
	struct render_window windows[3] = {
		{ 1, 0, { 11.0f } },
		{ 0, -1, { 22.0f } },
		{ 0, 2, { 33.0f } }
	};
	struct test_camera before;
	struct bitmap_data bitmap = { 0 };
	ps2_render_frame_state_advance(windows, 3, 1.0f / 60.0f);
	assert(render.frame_index == 1);
	assert(render.window_index == 2 && render.local_player_index == 2);
	assert(render.camera.marker == 33.0f);
	assert(render.time_delta_since_tick_sec == 1.0f / 60.0f);
	before = render.camera;
	ps2_render_frame_state_advance(windows, 2, 1.0f / 30.0f);
	assert(render.frame_index == 2);
	assert(render.camera.marker == before.marker);
	render_frame_pregame(&windows[1], &bitmap);
	assert(render.frame_index == 3);
	assert(render.camera.marker == 22.0f);
	render_frame_pregame(0, &bitmap);
	assert(render.frame_index == 4);
	assert(render.camera.marker == 22.0f);
	return 0;
}
"""
	with tempfile.TemporaryDirectory(prefix="hcu-render-state-") as temp:
		source_c = Path(temp) / "render-state.c"
		executable = Path(temp) / "render-state"
		source_c.write_text(fixture + render_state_advance + render_pregame + main)
		result = subprocess.run([
			"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
			str(source_c), "-o", str(executable),
		], check=False, capture_output=True, text=True)
		assert result.returncode == 0, result.stderr
		subprocess.run([str(executable)], check=True, capture_output=True,
			text=True)


def test_disabled_first_person_interpolation_preserves_ce_pose():
	source = RENDER_C.read_text()
	interpolate = _function(source, "void render_interpolation_first_person(")
	fixture = r"""
#include <assert.h>
#include <string.h>
typedef struct real_matrix4x3 { float values[13]; } real_matrix4x3;
struct render_camera { float unused; };
"""
	main = r"""
int main(void)
{
	real_matrix4x3 nodes[2], before[2];
	struct render_camera camera = { 0.0f };
	memset(nodes, 0x55, sizeof(nodes));
	memcpy(before, nodes, sizeof(nodes));
	render_interpolation_first_person(0, nodes, 2, &camera);
	assert(memcmp(nodes, before, sizeof(nodes)) == 0);
	return 0;
}
"""
	with tempfile.TemporaryDirectory(prefix="hcu-fp-interpolation-") as temp:
		source_c = Path(temp) / "fp-interpolation.c"
		executable = Path(temp) / "fp-interpolation"
		source_c.write_text(fixture + interpolate + main)
		result = subprocess.run([
			"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
			str(source_c), "-o", str(executable),
		], check=False, capture_output=True, text=True)
		assert result.returncode == 0, result.stderr
		subprocess.run([str(executable)], check=True, capture_output=True,
			text=True)


def test_non_pal_first_person_fraction_is_zero():
	interface = (ROOT / "submodules/halo-ce-universal/port/ps2/src/ps2_interface.c").read_text()
	function = _function(interface, "real pal_tags_first_person_fraction(")
	fixture = r"""
#include <assert.h>
typedef float real;
"""
	main = r"""
int main(void)
{
	assert(pal_tags_first_person_fraction(0, 7, 2, 10) == 0.0f);
	assert(pal_tags_first_person_fraction(-1, -1, -1, -1) == 0.0f);
	return 0;
}
"""
	with tempfile.TemporaryDirectory(prefix="hcu-pal-fraction-") as temp:
		source_c = Path(temp) / "pal-fraction.c"
		executable = Path(temp) / "pal-fraction"
		source_c.write_text(fixture + function + main)
		subprocess.run([
			"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
			str(source_c), "-o", str(executable),
		], check=True, capture_output=True, text=True)
		subprocess.run([str(executable)], check=True, capture_output=True,
			text=True)
