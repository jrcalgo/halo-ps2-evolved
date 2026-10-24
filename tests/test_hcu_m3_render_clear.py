from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_render_clear_is_opt_in_and_uses_bounded_dma_arena():
	main = (ROOT / "src/stream/hcu_main.c").read_text()
	makefile = (ROOT / "tools/ee-world.mk").read_text()
	probe = (ROOT / "tools/hcu_parent_link_probe.py").read_text()

	assert "#ifdef HALO_PS2_M3_RENDER_CLEAR_TEST" in main
	assert "dma_channel_initialize(DMA_CHANNEL_GIF, NULL, 0);" in main
	assert "video_add_setup_env(&video, &packet);" in main
	assert "video_add_clear(&video, &packet, 24, 72, 120);" in main
	assert "video_present(&video);" in main
	assert "HALO_PS2_FAIL m3 GS eDRAM ranges invalid or overlapping" in main
	assert "fb_words > VIDEO_VRAM_WORDS - fb0" in main
	assert "HALO_PS2_FAIL m3 GIF clear packet exceeded its arena slice" in main
	assert "packet.max_qwords_count" in main
	assert "packet2_create(" not in main
	assert "packet2_create_from(" in main  # Documented explicitly as intentionally avoided.
	assert "WORLD_HCU_RENDER_CLEAR_TEST ?= 0" in makefile
	assert 'f"WORLD_HCU_RENDER_CLEAR_TEST={1 if args.m3_render_clear_test else 0}"' in probe
	assert '"-m3-render-clear"' in probe


def test_boot_probe_has_diagnostic_marker_not_a_scene_acceptance_marker():
	boot = (ROOT / "tools/test_hcu_boot.py").read_text()
	assert '"m3-render-clear": "HALO_PS2_LOCAL m3-render-clear-presented"' in boot
	assert "m3-render-clear-presented" in (ROOT / "src/stream/hcu_main.c").read_text()
