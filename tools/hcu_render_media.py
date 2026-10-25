"""Opt-in C3 render chunks for HCU profile packages.

For one structure BSP index of a scenario map this emits three typed HCP2
chunks, all keyed by the BSP index:

  kind 4 BSPS  raw BSPS v2 section (halo2ps2 bspconv, BSP<i>)
  kind 5 TEXS  shader texture pack (halo2ps2 texconv, restricted to that BSP)
  kind 6 LMn   lightmap pages (halo2ps2 texconv, LM<i>; absent when the BSP has none)

Each chunk records its source map SHA-256 and the converter versions in the
returned manifest rows. Bytes are the raw section payloads extracted from the
converter HP2 envelopes, so the C loader reads them with hcu_asset_profile_read_range.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HALO_PS2_TOOLS = ROOT / "submodules/halo-ps2/tools"
sys.path.insert(0, str(HALO_PS2_TOOLS))
from halo2ps2 import bspconv, hp2, texconv  # noqa: E402
import hcu_profile_chunks as chunks  # noqa: E402

FORMAT = "hcu-render-media-v1"


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def converter_identity() -> dict:
    try:
        head = subprocess.run(["git", "-C", str(ROOT / "submodules/halo-ps2"), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        head = "unknown"
    return {"bspconv_version": bspconv.VERSION, "texconv_version": texconv.VERSION,
            "hp2_version": hp2.VERSION, "halo_ps2_commit": head,
            "tools": "halo2ps2 bspconv+texconv (BSPS v2, TEXS, LMn)"}


def build(map_path: Path, bsp_index: int = 0) -> dict:
    """Return {'chunks': {(kind, id): bytes}, 'manifest': {...}} for one BSP index."""
    map_path = Path(map_path)
    source_sha = _file_sha(map_path)
    bsp_tag = f"BSP{bsp_index}"
    lm_tag = f"LM{bsp_index}"
    converter = converter_identity()
    bsps_pack = bspconv.convert_map(map_path, [bsp_index], chroma=True)
    bsps_sections = {s.tag: s for s in hp2.parse(bsps_pack).sections}
    if bsp_tag not in bsps_sections:
        raise ValueError(f"{map_path.name}: BSP index {bsp_index} produced no {bsp_tag} section")
    bsps = hp2.parse(bsps_pack).read(bsp_tag)
    result = texconv.convert_map(map_path, lightmaps=True, bsp_filter=[bsp_index])
    pack = hp2.parse(result.pack)
    texs = pack.read("TEXS")
    payloads = {(chunks.CHUNK_BSPS, bsp_index): bsps,
                (chunks.CHUNK_TEXS, bsp_index): texs}
    if lm_tag in {s.tag for s in pack.sections}:
        payloads[(chunks.CHUNK_LIGHTMAP, bsp_index)] = pack.read(lm_tag)
    names = {chunks.CHUNK_BSPS: "BSPS", chunks.CHUNK_TEXS: "TEXS", chunks.CHUNK_LIGHTMAP: "LMn"}
    rows = []
    for (kind, cid) in sorted(payloads):
        blob = payloads[(kind, cid)]
        if not blob:
            raise ValueError(f"empty render chunk {names[kind]}{bsp_index}")
        rows.append({"kind": kind, "chunk_id": cid, "name": f"{names[kind]}{bsp_index}",
                     "bytes": len(blob), "sha256": _sha(blob),
                     "source_map": map_path.stem, "source_map_sha256": source_sha,
                     "converter": converter})
    return {"chunks": payloads,
            "manifest": {"format": FORMAT, "bsp_index": bsp_index, "source_map": map_path.stem,
                         "source_map_sha256": source_sha, "converter": converter,
                         "chunks": rows,
                         "total_bytes": sum(r["bytes"] for r in rows)}}


MAGICS = {chunks.CHUNK_BSPS: (b"BSPS", 2), chunks.CHUNK_TEXS: (b"TEXS", 1),
          chunks.CHUNK_LIGHTMAP: (b"LMAP", 1)}


class RenderMediaError(ValueError):
    pass


def check_render_chunks(package_chunks: dict, manifest: dict, *, maps_dir: Path | None = None):
    """Validator hook. Returns None when the package carries no render chunks and the
    manifest declares none; otherwise checks the chunks against manifest['render_media']
    and returns a summary. Raises RenderMediaError on any mismatch."""
    present = {k: v for k, v in package_chunks.items() if k[0] in MAGICS}
    declared = manifest.get("render_media")
    if not present and declared is None:
        return None
    if not present or declared is None:
        raise RenderMediaError("render chunks and manifest render_media must appear together")
    if declared.get("format") != FORMAT:
        raise RenderMediaError("unsupported render_media format")
    index = declared.get("bsp_index")
    if not isinstance(index, int) or index < 0:
        raise RenderMediaError("render_media bsp_index invalid")
    if (chunks.CHUNK_BSPS, index) not in present or (chunks.CHUNK_TEXS, index) not in present:
        raise RenderMediaError("render chunks lack the BSPS or TEXS chunk for the declared BSP")
    if any(cid != index for (_k, cid) in present):
        raise RenderMediaError("render chunk ids must all equal the declared BSP index")
    rows = {(r.get("kind"), r.get("chunk_id")): r for r in declared.get("chunks", [])}
    if set(rows) != set(present) or len(rows) != len(declared.get("chunks", [])):
        raise RenderMediaError("render_media rows do not match the packaged render chunks")
    source_sha = declared.get("source_map_sha256")
    converter = declared.get("converter") or {}
    if not isinstance(source_sha, str) or len(source_sha) != 64:
        raise RenderMediaError("render_media lacks a source map SHA-256")
    if (converter.get("bspconv_version"), converter.get("texconv_version"), converter.get("hp2_version")) != \
            (bspconv.VERSION, texconv.VERSION, hp2.VERSION):
        raise RenderMediaError("render_media converter version differs from the installed converters")
    for key, blob in present.items():
        row = rows[key]
        magic, version = MAGICS[key[0]]
        if (row.get("bytes"), row.get("sha256")) != (len(blob), _sha(blob)):
            raise RenderMediaError(f"render chunk {key} size or SHA-256 differs from its manifest row")
        if row.get("source_map_sha256") != source_sha or row.get("converter") != converter:
            raise RenderMediaError(f"render chunk {key} source or converter record differs")
        if blob[:4] != magic or int.from_bytes(blob[4:6], "little") != version:
            raise RenderMediaError(f"render chunk {key} has the wrong section magic or version")
    if declared.get("total_bytes") != sum(len(b) for b in present.values()):
        raise RenderMediaError("render_media total_bytes mismatch")
    if maps_dir is not None:
        path = Path(maps_dir) / f"{declared.get('source_map')}.map"
        if not path.is_file() or _file_sha(path) != source_sha:
            raise RenderMediaError("source map SHA-256 differs from the map on disk")
    return {"bsp_index": index, "chunks": len(present),
            "bytes": sum(len(b) for b in present.values()), "source_map_sha256": source_sha}


def append_to_package(package: bytes, manifest: dict, map_path: Path, bsp_index: int, *,
                      expected_package_sha256: str):
    """Append render chunks to an already-qualified HCP2 package without rebuilding its CE
    closure. The input must match `expected_package_sha256` and re-encode to itself; the output
    keeps the profile id and every existing chunk byte-for-byte."""
    import hcu_profile_validate as validate
    parsed = validate.parse_package(package, expected_package_sha256=expected_package_sha256,
                                    expected_profile_id=chunks.HEADER.unpack_from(package)[3])
    if parsed["version"] != 2 or any(k[0] in MAGICS for k in parsed["chunks"]):
        raise RenderMediaError("input must be a render-free HCP2 package")
    pid = parsed["profile_id"]
    if chunks.encode(pid, parsed["chunks"]) != package:
        raise RenderMediaError("input package does not re-encode to itself")
    render = build(map_path, bsp_index)
    typed = dict(parsed["chunks"])
    typed.update(render["chunks"])
    out = chunks.encode(pid, typed)
    new_manifest = dict(manifest)
    new_manifest["render_media"] = render["manifest"]
    new_manifest["base_package_sha256"] = expected_package_sha256
    new_manifest["package_sha256"] = _sha(out)
    # Appending sections changes the envelope size; consumers validate this
    # field before selecting any memory partition. Preserve the input manifest.
    new_manifest["memory"] = {**manifest.get("memory", {}), "package_file_bytes": len(out)}
    return out, new_manifest


def main(argv=None) -> int:
    import argparse
    import json
    ap = argparse.ArgumentParser(description="Append C3 render chunks to a qualified C2 HCP2 package.")
    ap.add_argument("--package", type=Path, required=True)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--expected-sha256", required=True, help="pinned SHA-256 of the input package")
    ap.add_argument("--map", type=Path, required=True)
    ap.add_argument("--bsp", type=int, default=0)
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args(argv)
    for src in (args.package, args.manifest):
        if args.output_dir.resolve() in src.resolve().parents:
            raise SystemExit("output dir must not contain the input")
    out, manifest = append_to_package(args.package.read_bytes(), json.loads(args.manifest.read_text()),
                                      args.map, args.bsp, expected_package_sha256=args.expected_sha256)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / args.package.name).write_bytes(out)
    (args.output_dir / args.manifest.name).write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"{args.package.name} {len(out)} {_sha(out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
