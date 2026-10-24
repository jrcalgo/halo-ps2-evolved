from pathlib import Path
import subprocess
import tempfile


def test_renderer_dma_storage_has_four_exact_fixed_chains():
	root = Path(__file__).resolve().parents[1]
	engine = root / "submodules/halo-ps2/engine/src"
	with tempfile.TemporaryDirectory(prefix="bsp-render-storage-") as temp:
		executable = Path(temp) / "storage-test"
		subprocess.run([
			"cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
			"-I" + str(engine), "tests/bsp_render_storage_main.c",
			"-o", str(executable),
		], cwd=root, check=True, capture_output=True, text=True)
		subprocess.run([str(executable)], check=True, capture_output=True,
			text=True)


def test_hcu_binds_renderer_storage_without_initializing_graphics():
	root = Path(__file__).resolve().parents[1]
	main = (root / "src/stream/hcu_main.c").read_text()
	bind = main.index("bsp_render_bind_storage(renderer_dma_storage")
	init = main.find("bsp_render_init(", bind)
	assert bind >= 0 and init == -1
	assert "BSP_RENDER_GEOMETRY_CHAIN_QW * 16u" in main
	assert "renderer_workspace = arena_alloc(frame_scratch" in main
	assert "renderer_workspace_bytes, 64)" in main
	assert "bsp_render_workspace_required()" in main
	renderer = (root / "submodules/halo-ps2/engine/src/render/bsp_render.c").read_text()
	assert "s_initialized, s_inflight" in renderer
	assert "workspace_packet" in renderer
	assert "if (!s_storage_bound) {\n\t\tfor (i = 0; i < 2; i++)" in renderer
	assert "s_env_packet.base = (qword_t *)(s_workspace + 4096u)" in renderer
