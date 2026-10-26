"""Retail Warthog bind-pose contract used by the C3 world-object skin palette."""
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import animconv, modelconv, texconv  # noqa: E402


def test_retail_warthog_default_inverse_bind_and_suspension_animation():
    map_path = ROOT / "build/retail-maps/decompressed/bloodgulch.map"
    if not map_path.is_file():
        pytest.skip("decompressed retail Blood Gulch map is not staged")

    fixture_path = ROOT / "submodules/halo-ps2/tools/tests/test_modelconv.py"
    spec = importlib.util.spec_from_file_location("retail_modelconv_fixture", fixture_path)
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)

    source = texconv.MapData.open(map_path)
    entry = next(e for e in source.index.entries
                 if e.group == "mode" and e.path == "vehicles\\warthog\\warthog")
    model = modelconv.read_model(source, entry)
    assert len(model.nodes) == 18
    # This compares each computed bind-world inverse against the retail tag's
    # stored inverse matrix, the source of CE runtime_default_inverse_matrix.
    assert fixture.real_inverse_check(source, entry, model) < 1e-6

    tags = animconv.MapTags(map_path)
    graph_entry = next(e for e in tags.idx.entries
                       if e.group == "antr" and e.path == "vehicles\\warthog\\warthog")
    graph = animconv.read_graph(tags, graph_entry)
    suspension = next(a for a in graph.anims if a.name == "suspension left back")
    decoded = animconv.decode(suspension)
    assert suspension.node_count == len(model.nodes)
    assert suspension.frame_count == 2
    assert len(decoded.rot[2]) == 2
    assert max(abs(a - b) for a, b in zip(decoded.rot[2][0], decoded.rot[2][1])) > 0.1
