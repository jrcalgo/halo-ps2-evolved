from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_menu_render_profile_is_forwarded_to_gameplay_before_renderer_init():
    main = (ROOT / "src/stream/hcu_main.c").read_text()
    menu = (ROOT / "src/stream/hcu_main_menu.c").read_text()
    assert "argv[7] = render_profile" in main
    assert "argv[8] = fov_text" in main
    assert "LoadExecPS2(chosen->elf, 9, argv)" in main
    assert "j == i + 6" in main
    assert "s_hcu_render_profile = (unsigned)render_profile" in main
    ensure = main[main.index("static void hcu_video_ensure(void)"):]
    ensure = ensure[:ensure.index("\n}")]
    assert ensure.index("video_init(&s_hcu_video)") < ensure.index(
        "video_set_render_profile(&s_hcu_video, s_hcu_render_profile)")
    assert "s_selected_render_profile = state.resolution" in menu


def test_renderer_profile_controls_resolution_and_fog_path():
    video = (ROOT / "submodules/halo-ps2/engine/src/platform/video.c").read_text()
    bsp = (ROOT / "submodules/halo-ps2/engine/src/render/bsp_render.c").read_text()
    assert "{750u, 625u, 500u, 1000u}" in video
    assert "video_render_profile(v) != VIDEO_PROFILE_HIGH_DETAIL" in bsp
    assert "s_opt.fog = 1" in bsp
    assert "s_opt.fog_near = vc.far_z * 0.8f" in bsp
    assert "s_opt.fog_far = vc.far_z" in bsp


def test_iso_builder_refreshes_authored_sky_fog_headers():
    builder = (ROOT / "tools/build_halo_ps2_iso.py").read_text()
    generator = (ROOT / "tools/hcu_c3_objects_table.py").read_text()
    assert "refresh_object_tables(table)" in builder
    assert '"--sky-from-scenario"' in builder
    assert "OBJECTS_SKY_FOG_RGB" in generator
    main = (ROOT / "src/stream/hcu_main.c").read_text()
    assert "options.profile_fog_rgb_valid = 1" in main


def test_chained_gameplay_releases_loading_screen_after_map_setup():
    main = (ROOT / "src/stream/hcu_main.c").read_text()
    start = main.index("void hcu_c3_render_map_loaded(")
    end = main.index("\nstatic void hcu_c3_print_frame", start)
    map_loaded = main[start:end]
    assert "hcu_loading_screen_release();" in map_loaded
    assert map_loaded.index("c3-render-ready") < map_loaded.index("hcu_loading_screen_release();")
    assert "return;" not in map_loaded
