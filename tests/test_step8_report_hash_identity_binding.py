"""Regression checks that report-only runner pins bind to exact local files."""
from pathlib import Path
import importlib.util
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "hcu_step7_step8_generator", ROOT / "tools/generate_hcu_step7_step8_closure.py")
GENERATOR = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(GENERATOR)


def test_step8_texture_report_binds_fixture_and_runner_by_exact_digest():
    report = ROOT / "docs/reports/mp-step8-texture-runtime-host-2026-10-22.md"
    fixture_digest = "e97cbf1746436b6363359f6b533ff35044406d63ac8fd995377a64390bef1861"
    runner_digest = "039e31d0e705fe89112a83e68c096d1075f67204838b2695898227d3a720ebb6"

    fixture, _measurements = GENERATOR._normalized_report_data([report], ())
    bindings = {entry["sha256"]: entry for entry in fixture["reported_hash_pins"]}

    assert bindings[fixture_digest]["local_path"] == "tests/mp_texture_runtime_main.c"
    assert bindings[runner_digest]["local_path"] == "tools/test_halo_ps2_mp_texture_runtime.py"
    assert bindings[fixture_digest]["matches_current_file"]
    assert bindings[runner_digest]["matches_current_file"]


def test_markdown_hash_pins_use_row_cells_and_ignore_separator_rows():
    digest_a = "a" * 64
    digest_b = "b" * 64
    with tempfile.TemporaryDirectory(dir=ROOT / "docs/reports") as tmp:
        report = Path(tmp) / "table.md"
        report.write_text(
            "| Artifact | SHA-256 |\n"
            "| --- | --- |\n"
            f"| `first.bin` | `{digest_a}` |\n"
            f"| second output | `{digest_b}` |\n"
        )
        fixture, _measurements = GENERATOR._normalized_report_data([report], ())

    pins = fixture["reported_hash_pins"]
    assert [entry["sha256"] for entry in pins] == [digest_a, digest_b]
    assert [entry["reported_label"] for entry in pins] == ["first.bin", "second output"]
    assert all(entry["reported_label"] not in ("SHA-256", "`", "SHA-256 `") for entry in pins)


def test_report_hash_pins_keep_following_artifact_roles_per_digest():
    first = "1" * 64
    second = "2" * 64
    with tempfile.TemporaryDirectory(dir=ROOT / "docs/reports") as tmp:
        report = Path(tmp) / "prose.md"
        report.write_text(
            f"Recompiler result/guest-log SHA-256 `{first}`; Interpreter result/guest-log SHA-256 `{second}`.\n"
        )
        fixture, _measurements = GENERATOR._normalized_report_data([report], ())
    pins = {entry["sha256"]: entry for entry in fixture["reported_hash_pins"]}
    assert "Recompiler result/guest-log" in pins[first]["reported_label"]
    assert "Interpreter result/guest-log" in pins[second]["reported_label"]
