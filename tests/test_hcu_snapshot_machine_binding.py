from pathlib import Path


def test_machine_binds_snapshot_banks_and_keeps_decode_scratch_disjoint():
	root = Path(__file__).resolve().parents[1]
	main = (root / "src/stream/hcu_main.c").read_text()
	service = (root / "src/stream/hcu_map_service.c").read_text()

	assert '#include "stream/hcu_render_snapshot.h"' in main
	bind = main.index("hcu_render_snapshot_bind(frame_scratch->base")
	service_init = main.index("hcu_map_service_init_with_arenas(")
	shell = main.index("result = halo_shell_main();")
	assert bind < service_init < shell
	# Snapshot banks occupy the start of frame_scratch (hcu_render_snapshot_bind
	# takes the whole arena); section decode scratch is a disjoint slice of
	# streaming, so it never consumes render-time frame scratch.
	assert "snapshot_bytes > frame_scratch->cap" in main
	assert "streaming->base + 1048576u" in main
	assert "&render_section_scratch" in main
	assert "hcu_render_snapshot_unbind();" in main[shell:]

	assert "scratch_start - frame_start" in service
	assert "service->section_scratch->cap > frame_scratch->cap - scratch_offset" in service
	assert "hcu_map_service_init_with_scratch" in service
