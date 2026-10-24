from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from audit_retail_bsp_schema import (  # noqa: E402
    COMPRESSED_VERTEX_OWNER,
    CURRENT_BSP_CAPACITY,
    capacity_projection,
)


def test_capacity_projection_only_subtracts_compressed_vertex_owner():
    raw = CURRENT_BSP_CAPACITY + 4096
    projected, fits = capacity_projection(
        raw,
        {
            COMPRESSED_VERTEX_OWNER: 8192,
            "block collision_bsp.vertices": 1024,
        },
    )
    assert projected == raw - 8192
    assert fits


def test_capacity_projection_does_not_claim_capacity_without_externalization():
    raw = CURRENT_BSP_CAPACITY + 1
    projected, fits = capacity_projection(raw, {})
    assert projected == raw
    assert not fits


def test_capacity_projection_keeps_oversize_nonvertex_data_visible():
    raw = CURRENT_BSP_CAPACITY + 16384
    projected, fits = capacity_projection(
        raw, {COMPRESSED_VERTEX_OWNER: 8192}
    )
    assert projected == CURRENT_BSP_CAPACITY + 8192
    assert not fits
