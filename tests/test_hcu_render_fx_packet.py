"""Offline fixture drives the production `fx_pass` C emitter and decodes its DMA/VIF bytes."""
import re
import struct
import shutil
import subprocess

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = Path(__file__).resolve().parent
def decode_chain(path):
    """Decode the fixture's emitted CNT/END tags and supported VIF command stream."""
    raw = path.read_bytes()
    pos = 0
    directs = []
    ended = False
    while pos + 16 <= len(raw):
        lo, hi = struct.unpack_from("<QQ", raw, pos)
        qwc, ident = lo & 0xffff, (lo >> 28) & 7
        pos += 16
        if ident == 7:
            assert qwc == 0, f"END has payload QWC={qwc}"
            ended = True
            break
        assert ident == 1, f"unsupported DMA tag ID {ident}"
        payload_bytes = qwc * 16
        assert payload_bytes <= len(raw) - pos, "CNT payload truncated"
        end = pos + payload_bytes
        cursor = pos
        while cursor < end:
            assert cursor + 4 <= end, "trailing partial VIF word"
            word = struct.unpack_from("<I", raw, cursor)[0]
            cmd = (word >> 24) & 0xff
            imm = word & 0xffff
            cursor += 4
            if cmd == 0x00:  # NOP
                continue
            if cmd == 0x13:  # FLUSHA
                continue
            if cmd == 0x50:  # DIRECT: immediate is the following GIF QWC
                size = (imm or 65536) * 16
                assert size <= end - cursor, "DIRECT payload exceeds CNT QWC"
                directs.append({"payload_bytes": size})
                cursor += size
                continue
            raise AssertionError(f"unknown VIF command 0x{cmd:02x} at byte {cursor - 4}")
        assert cursor == end, "VIF parser did not consume the CNT payload"
        pos = end
    assert ended, "missing END DMA tag"
    assert pos == len(raw), "bytes follow END DMA tag"
    return directs


def compile_fixture(tmp):
    compiler = shutil.which("cc") or shutil.which("gcc")
    sdk = ROOT / "build/toolchain/install/ps2sdk"
    if not compiler or not (sdk / "common/include/tamtypes.h").exists():
        pytest.skip("host compiler or installed PS2SDK headers unavailable")
    exe = tmp / "fx_fixture"
    cmd = [compiler, "-std=c11", "-D_EE", "-include", "tamtypes.h", "-ffunction-sections", "-fdata-sections",
           "-Wno-unused-parameter", "-Wno-int-to-pointer-cast", "-Wno-pointer-to-int-cast",
           "-I" + str(ROOT / "src"), "-I" + str(ROOT / "submodules/halo-ps2/engine/src"),
           "-I" + str(ROOT / "submodules/halo-ce-universal/port/ps2/include"),
           "-I" + str(ROOT / "submodules/halo-ce-universal/source"),
           "-I" + str(ROOT / "submodules/halo-ce-universal/port/include"),
           "-I" + str(ROOT / "submodules/halo-ce-universal/source/cseries"),
           "-I" + str(sdk / "ee/include"), "-I" + str(sdk / "common/include"),
           str(HERE / "hcu_render_fx_packet_ee_fixture.c"), str(ROOT / "src/stream/hcu_fx_bitmap.c"),
           str(ROOT / "submodules/halo-ps2/engine/src/render/chain.c"),
           str(ROOT / "submodules/halo-ps2/engine/src/render/camera.c"),
           str(ROOT / "submodules/halo-ps2/engine/src/render/clip.c"),
           "-Wl,--gc-sections", "-lm", "-o", str(exe)]
    subprocess.run(cmd, cwd=ROOT, check=True, capture_output=True, text=True)
    return exe


def run_case(exe, tmp, limit, count, buckets=1, scope=0):
    chain = tmp / f"chain-{limit}-{count}-{buckets}-{scope}.bin"
    p = subprocess.run([str(exe), str(limit), str(count), str(buckets), str(scope), str(chain)], check=True,
                       capture_output=True, text=True)
    m = re.search(r"used-before-END=(\d+).*drawn=(\d+)", p.stderr)
    assert m, p.stderr
    used, drawn = map(int, m.groups())
    directs = decode_chain(chain)
    return used, drawn, directs


def test_production_fx_counts_and_chain_boundary(tmp_path):
    exe = compile_fixture(tmp_path)
    for bucket_count in (1, 2):
        for count in range(65):
            used, drawn, directs = run_case(exe, tmp_path, 2000, count, bucket_count)
            assert drawn == count
            groups = [sum(1 for i in range(count) if (bucket_count == 1 or i % 2 == group))
                      for group in range(bucket_count)]
            expected_buckets = sum(n > 0 for n in groups)
            assert len(directs) == (2 + 2 * expected_buckets if count else 0)
            if count:
                # Common state (4 QW), one blend state per bucket and final restore (2 QW each),
                # plus one geometry DIRECT per bucket (tag QW + 3 QW per six clipped verts).
                sizes = sorted(event["payload_bytes"] // 16 for event in directs)
                expected = [4] + [2] * (expected_buckets + 1) + [1 + 18 * n for n in groups if n]
                assert sizes == sorted(expected)
                assert directs[-1]["payload_bytes"] == 2 * 16  # final blend-state restore

    # Check exact fit and one-QW-short limits for a one-bucket packet and two
    # distinct blend buckets. Every emitted state must still end with restore.
    for count, bucket_count in ((1, 1), (2, 2)):
        baseline, _, _ = run_case(exe, tmp_path, 2000, count, bucket_count)
        for limit in (baseline, baseline - 1):
            used, drawn, directs = run_case(exe, tmp_path, limit, count, bucket_count)
            assert used <= limit
            assert 0 <= drawn <= count
            if directs:
                assert directs[-1]["payload_bytes"] == 2 * 16
            if drawn:
                assert directs[-1]["payload_bytes"] == 2 * 16

    # HUD uses its own bound; CLOSE is refused without changing scope or emitting FX.
    _, drawn, directs = run_case(exe, tmp_path, 2000, 4, 2, scope=1)
    assert drawn == 4 and directs[-1]["payload_bytes"] == 2 * 16
    _, drawn, directs = run_case(exe, tmp_path, 2000, 4, 2, scope=2)
    assert drawn == 0 and not directs
    _, drawn, directs = run_case(exe, tmp_path, 3, 1, 1)
    assert drawn == 0 and not directs
