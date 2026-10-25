"""C3.10 DMA host checks: the c3_10_dma_checks evaluator on synthetic guest lines, plus the source-level
contract of the C3:dma block and the renderer probe. The in-guest proof is the PCSX2 run (not this test)."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("c2m", ROOT / "tools/c2_profile_boot_matrix.py")
c2m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c2m)

OWNER = ("HALO_PS2_LOCAL c3-dma-owner owner-base=0x1000000 owner-cap=1179648 owner-used=1179648 "
         "storage-base=0x1000000 storage-bytes=1179648 chains=4 geom0=0x1000000/524288 geom1=0x1080000/524288 "
         "up0=0x1100000/65536 up1=0x1110000/65536 sum=1179648")


def frame_line(n, **over):
    f = dict(kick="%d" % n, fence="1", busy="0", released_before="0", refusals="0")
    f.update(over)
    rb = f["released_before"]
    return ("HALO_PS2_LOCAL c3-dma frame=%d kick-seq=%d completed=%d inflight=1 "
            "c0-kick=%s c0-fence=%s c0-kicks=1 c0-emits=%d c0-busy-emits=%s c0-used-qw=10 "
            "c1-kick=0 c1-fence=-1 c1-kicks=0 c1-emits=0 c1-busy-emits=0 c1-used-qw=0 "
            "src-gen=%d src-released=%d released-before-fence=%s "
            "src-rel-chain=%d/0 src-rel-pin=%d/%s src-rel-bitmap=0/0 "
            "overflow-refusals=%s emit-status=0 emit-codes-neg=0,0,0,0,0,0,0,0 emit-codes-pos=0,0,0,0,0,0,0,0,0"
            % (n, n, n - 1, f["kick"], f["fence"], n, f["busy"],
               n, n, rb, n, n, rb, f["refusals"]))


def frame_c3(views, frames, overflow="0", idle="0", emit="0"):
    return ("HALO_PS2_LOCAL c3-frame kind=final frame=%d views=%d chain-bytes=1 upload-bytes=1 uploads=1 "
            "overflow=%s frames=%d kick-seq=%d fence=1 prev-fence=1 idle-redirects=0 idle-violations=%s "
            "emit-failures=%s" % (frames, views + (1 if views == 3 else 0), overflow, frames, frames, idle, emit))


def good_lines(views=1, frames=3, **kw):
    lines = [OWNER] + [frame_line(n) for n in range(1, frames + 1)]
    lines.append(frame_c3(views, frames, **kw))
    return lines


def test_good_run_qualifies():
    r = c2m.c3_10_dma_checks(good_lines(views=2, frames=3), 2, 3)
    assert r["c3_10_qualified"], r["reasons"]


def test_owner_size_must_be_fixed():
    lines = good_lines()
    lines[0] = lines[0].replace("owner-cap=1179648", "owner-cap=1179647")
    assert not c2m.c3_10_dma_checks(lines, 1, 3)["checks"]["owner_cap_is_fixed"]


def test_chain_layout_must_be_contiguous():
    lines = good_lines()
    lines[0] = lines[0].replace("geom1=0x1080000", "geom1=0x1090000")
    assert not c2m.c3_10_dma_checks(lines, 1, 3)["checks"]["chains_contiguous_in_owner"]


def test_busy_emit_fails():
    lines = good_lines(frames=3)
    lines[3] = frame_line(3, busy="1")
    assert not c2m.c3_10_dma_checks(lines, 1, 3)["checks"]["no_busy_emits"]


def test_released_before_fence_fails():
    lines = good_lines(frames=3)
    lines[2] = frame_line(2, released_before="1")
    assert not c2m.c3_10_dma_checks(lines, 1, 3)["checks"]["released_before_fence_zero"]


def test_emit_failure_blocks_qualification():
    r = c2m.c3_10_dma_checks(good_lines(emit="3"), 1, 3)
    assert not r["checks"]["emit_failures_zero"] and not r["c3_10_qualified"]


def test_overflow_needs_handling():
    lines = good_lines(overflow="1")
    assert not c2m.c3_10_dma_checks(lines, 1, 3)["checks"]["overflow_zero_or_handled"]
    lines = good_lines(overflow="1")
    lines[-2] = frame_line(3, refusals="2")
    assert c2m.c3_10_dma_checks(lines, 1, 3)["checks"]["overflow_zero_or_handled"]


def test_frame_count_must_match():
    assert not c2m.c3_10_dma_checks(good_lines(frames=2), 1, 3)["checks"]["frame_lines_complete"]


def test_source_contract_in_hcu_main():
    src = (ROOT / "src/stream/hcu_main.c").read_text()
    start = src.index("/* C3:dma begin */")
    end = src.index("/* C3:dma end */", start)
    block = src[start:end]
    assert "bsp_render_chain_probe_get" in block
    assert "released-before-fence" in block
    # the block only reads the event counters; it must not derive releases after the fact
    assert "bsp_render_source_get" in block
    assert "s_c3d_pinned_gen" not in block and "unpins - s_c3d_unpins_seen" not in block


def test_release_events_read_fence_at_release_point():
    bsp = (ROOT / "submodules/halo-ps2/engine/src/render/bsp_render.c").read_text()
    body = bsp[bsp.index("int32_t bsp_render_source_release("):]
    body = body[:body.index("\n}\n") + 3]
    assert "bsp_render_fence_observed(kick_seq)" in body and "s_src_before_fence[kind]++" in body
    # chain reuse releases the chain's last kick at open_frame, after the idle choice
    open_frame = bsp[bsp.index("static void open_frame("):]
    assert open_frame.index("bsp_render_source_release(BSP_SRC_CHAIN") < open_frame.index("chain_init(&s_chain[s_build]")
    objs = (ROOT / "src/stream/hcu_render_objects.c").read_text()
    # both pin release sites (frame begin and objects release) report through the event counter
    assert objs.count("bsp_render_source_release(BSP_SRC_OBJECT_PIN") == 2
    assert "bsp_render_source_release(BSP_SRC_OBJECT_PIN, s_pending_seq);\n\t\tpin_drop();" in objs
    assert objs.count("pin_drop();") >= 2


def test_bitmap_lease_release_event_in_dispatch():
    disp = (ROOT / "src/stream/hcu_bitmap_dispatch.c").read_text()
    hdr = (ROOT / "src/stream/hcu_bitmap_dispatch.h").read_text()
    # the lease records the kick that carries its upload, and the release reads that kick's fence
    assert "uint32_t kick_seq;" in hdr
    assert "lease->kick_seq = bsp_render_kick_seq" in disp
    start = disp.index("void hcu_bitmap_dispatch_complete(")
    body = disp[start:disp.index("\n}\n", start)]
    assert "bsp_render_source_release(HCU_BITMAP_RELEASE_KIND_LEASE, ctx->leases[i].kick_seq)" in body
    assert body.index("bsp_render_source_release") < body.index("hcu_bitmap_dispatch_release(")
    # weak references keep the host builds (no bsp_render) linkable
    assert "__attribute__((weak))" in disp and "HCU_BITMAP_RELEASE_KIND_LEASE 2u" in disp


def test_owner_used_and_storage_checks_present():
    lines = good_lines()
    lines[0] = lines[0].replace("owner-used=1179648", "owner-used=1179647")
    r = c2m.c3_10_dma_checks(lines, 1, 3)
    assert not r["checks"]["owner_used_is_fixed"] and not r["c3_10_qualified"]


def test_renderer_probe_exports():
    hdr = (ROOT / "submodules/halo-ps2/engine/src/render/bsp_render.h").read_text()
    assert "bsp_render_chain_probe_get" in hdr and "bsp_render_emit_code_counts" in hdr
    assert "bsp_render_source_release" in hdr and "bsp_render_source_get" in hdr
    obj = (ROOT / "submodules/halo-ps2/engine/src/render/obj_render.h").read_text()
    assert "obj_render_space_refusals" in obj
