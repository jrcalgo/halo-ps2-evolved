from pathlib import Path


def test_machine_allocates_exact_snapshot_renderer_spans_and_keeps_decode_scratch_disjoint():
	root = Path(__file__).resolve().parents[1]
	main = (root / "src/stream/hcu_main.c").read_text()
	service = (root / "src/stream/hcu_map_service.c").read_text()

	assert '#include "stream/hcu_render_snapshot.h"' in main
	bind = main.index("hcu_render_snapshot_bind(snapshot_storage, snapshot_bytes)")
	service_init = main.index("hcu_map_service_init_with_arenas(")
	shell = main.index("result = halo_shell_main();")
	assert bind < service_init < shell
	assert "snapshot_storage = arena_alloc(frame_scratch, snapshot_bytes, 16)" in main
	assert "renderer_workspace = arena_alloc(frame_scratch" in main
	assert "renderer_workspace_bytes = bsp_render_workspace_required()" in main
	assert "bsp_render_bind_storage(renderer_dma_storage" in main
	assert "renderer_workspace_bytes)" in main
	assert "snapshot_guard = arena_alloc(frame_scratch" in main
	assert "renderer_workspace_guard = arena_alloc(frame_scratch" in main
	assert "hcu_guard_intact(renderer_workspace_guard, 0xC7u)" in main[shell:]
	assert "frame_scratch->used, (unsigned)frame_scratch->high" in main
	assert "renderer_dma_storage = arena_alloc(dma_commands" in main
	assert "streaming->base + 1048576u" in main
	assert "&render_section_scratch" in main
	assert "hcu_render_snapshot_unbind();" in main[shell:]
	assert "frame_scratch->cap - renderer_workspace_offset" not in main

	assert "scratch_start - frame_start" in service
	assert "service->section_scratch->cap > frame_scratch->cap - scratch_offset" in service
	assert "hcu_map_service_init_with_scratch" in service
