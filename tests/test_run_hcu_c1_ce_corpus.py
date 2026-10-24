import hashlib
import json
from pathlib import Path

import pytest

from tools.run_hcu_c1_ce_corpus import (expected_identity, expected_profile_names,
                                        file_pin, _assert_markers, _profile_input)


def test_profile_roster_is_exact_ui_plus_13_bots_plus_13_survival():
    names = expected_profile_names()
    assert len(names) == 27
    assert names[0] == "ui"
    assert sum(name.startswith("bots-") for name in names) == 13
    assert sum(name.startswith("survival-") for name in names) == 13
    assert expected_identity("ui") == (1, "ui", "ui")
    assert expected_identity("bots-beavercreek") == (2, "bots", "beavercreek")
    assert expected_identity("survival-wizard") == (27, "survival", "wizard")
    with pytest.raises(ValueError):
        expected_identity("survival-campaign")


def test_target_acceptance_policy_only_accepts_ui():
    _assert_markers("ui", "ctag=ok validator=accepted mount=1 corrupt_schema_rejected=1 "
                    "pointers_stable=1 owner_unpublished=1", target=True)
    _assert_markers("survival-beavercreek", "ctag=ok validator=rejected mount=0 "
                    "capacity=2097152 pointers_stable=1 owner_unpublished=1", target=True)
    with pytest.raises(RuntimeError, match="required markers"):
        _assert_markers("bots-beavercreek", "ctag=ok validator=accepted mount=1 "
                        "pointers_stable=1 owner_unpublished=1", target=True)


def test_host_semantic_run_requires_acceptance_and_capacity_label():
    _assert_markers("survival-beavercreek", "ctag=ok validator=accepted capacity=67108864 "
                    "corrupt_schema_rejected=1 pointers_stable=1 owner_unpublished=1", target=False)
    with pytest.raises(RuntimeError, match="required markers"):
        _assert_markers("survival-beavercreek", "ctag=ok validator=rejected capacity=67108864 "
                        "pointers_stable=1 owner_unpublished=1", target=False)


def test_profile_input_rejects_stale_package_manifest_hash(tmp_path):
    package = tmp_path / "ui.hcp"
    manifest = tmp_path / "ui.json"
    package.write_bytes(b"tampered HCP")
    manifest.write_text(json.dumps({"package_sha256": "0" * 64}))
    with pytest.raises(ValueError, match="package hash differs"):
        _profile_input(tmp_path, "ui", {}, root=tmp_path)


def test_file_pin_detects_changed_native_log(tmp_path):
    path = tmp_path / "run.log"
    path.write_bytes(b"accepted")
    pin = file_pin(path, root=tmp_path)
    assert pin["sha256"] == hashlib.sha256(b"accepted").hexdigest()
    path.write_bytes(b"rejected")
    assert file_pin(path, root=tmp_path)["sha256"] != pin["sha256"]
