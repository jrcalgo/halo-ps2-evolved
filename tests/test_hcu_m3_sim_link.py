from tools.audit_hcu_m3_sim_link import audit


def test_hcu_link_audit_accepts_hcu_entry_and_rejects_parent_viewer_mutators():
    nm_output = """\
00100000 T main
00101000 T halo_shell_main
00102000 T render_frame
00103000 T object_get_world_matrix
"""
    assert audit(nm_output) == {
        "passed": True,
        "retained_viewer_simulation_symbols": [],
        "missing_hcu_render_path_symbols": [],
    }


def test_hcu_link_audit_fails_if_parent_sim_or_required_entry_is_retained_or_missing():
    nm_output = """\
00100000 T main
00102000 T render_frame
00103000 T objects_tick
"""
    assert audit(nm_output) == {
        "passed": False,
        "retained_viewer_simulation_symbols": ["objects_tick"],
        "missing_hcu_render_path_symbols": ["halo_shell_main"],
    }
