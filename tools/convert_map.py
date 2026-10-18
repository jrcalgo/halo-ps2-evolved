"""Convert one locally configured retail map twice and compare the packs."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "submodules/halo-ps2/tools"
LOCAL = ROOT / ".local/retail-source.json"
BUDGET = json.loads((ROOT / "config/memory-budget.json").read_text())
REGION = {item["name"]: item["bytes"] for item in BUDGET["regions"]}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def retail_map(name: str) -> Path:
    if not LOCAL.is_file():
        raise RuntimeError("No local retail configuration. Put the map path in .local/retail-source.json.")
    config = json.loads(LOCAL.read_text())
    configured = Path(config["extracted_map"])
    path = configured if configured.stem == name else configured.parent / f"{name}.map"
    if not path.is_file():
        raise RuntimeError(f"Configured retail map is missing: {path}")
    return path


def run(script: str, *args: str) -> None:
    env = {**os.environ, "PYTHONPATH": str(TOOLS), "PYTHONDONTWRITEBYTECODE": "1"}
    subprocess.run([sys.executable, "-I", str(TOOLS / "halo2ps2" / script), *args], check=True, env=env)


def convert_once(source: Path, output: Path) -> dict[str, str]:
    if output.exists():
        raise RuntimeError(f"Refusing to reuse an existing output directory: {output}")
    output.mkdir(parents=True)
    stem = source.stem
    packs = {
        "bsp": output / f"{stem}.hp2",
        "objects": output / f"{stem}.obj.hp2",
        "textures": output / f"{stem}.tex.hp2",
    }
    run("bspconv.py", str(source), "-o", str(packs["bsp"]))
    run("objpack.py", str(source), "-o", str(packs["objects"]))
    run("texconv.py", str(source), "-o", str(packs["textures"]), "--lm-gain", "1.5")
    return {name: sha256(path) for name, path in packs.items()}


def geometry_error(source: Path, pack: Path) -> dict:
    sys.path.insert(0, str(TOOLS))
    from halo2ps2 import bsp, bspconv, hp2, mapinfo, tagindex
    header = mapinfo.read_header(source)
    with source.open("rb") as handle:
        handle.seek(header.tag_data_offset)
        region = handle.read(header.tag_data_size)
        index = tagindex.TagIndex.read(source)
        locations = bsp.locate(index, region, header.decompressed_size)
    parsed = hp2.parse(pack.read_bytes())
    worst = 0.0
    bound = 0.0
    triangles = 0
    for bsp_index, location in enumerate(locations):
        tag = bspconv.section_tag(bsp_index)
        if not any(section.tag == tag for section in parsed.sections):
            continue
        with source.open("rb") as handle:
            handle.seek(location.file_offset)
            block = handle.read(location.size)
        materials, _bounds = bspconv.read_materials(block, location)
        structure = bsp.read_structure(location, block)
        section = bspconv.parse_section(parsed.read(tag))
        groups = {}
        for material_index, material in enumerate(materials):
            for triangle, surface in enumerate(material.surfaces):
                clusters = structure.cluster_surfaces.get(surface)
                if not clusters:
                    continue
                groups.setdefault((tuple(sorted(clusters)), material_index), []).append(triangle)
        expected = []
        ordered = sorted(groups.items(), key=lambda item: (item[0][0][0], item[0][1], item[0][0]))
        for (_clusters, material_index), group in ordered:
            material = materials[material_index]
            order = bspconv._spatial_order(material, group)
            for start in range(0, len(order), bspconv.MAX_TRIS):
                for triangle in order[start:start + bspconv.MAX_TRIS]:
                    expected.extend(material.pos[vertex] for vertex in material.tris[triangle])
        decoded = []
        for batch in section.batches:
            decoded.extend(item["pos"] for item in bspconv.decode_batch(section, batch))
            bound = max(bound, batch["radius"] / 65534.0)
        if len(decoded) != len(expected):
            raise RuntimeError(f"{tag} decoded {len(decoded)} vertices, source order has {len(expected)}")
        for source_position, decoded_position in zip(expected, decoded):
            worst = max(worst, *(abs(source_position[axis] - decoded_position[axis]) for axis in range(3)))
        triangles += section.triangles
    return {"max_axis_error": worst, "declared_bound": bound, "triangles": triangles}


def main() -> None:
    name = os.environ.get("MAP", "bloodgulch")
    compressed = retail_map(name)
    work = ROOT / "data/retail/convert" / name
    decompressed_dir = work / "decompressed"
    decompressed_dir.mkdir(parents=True, exist_ok=True)
    decompressed = decompressed_dir / compressed.name
    if not decompressed.is_file():
        run("mapinfo.py", "decompress", str(compressed), "-o", str(decompressed_dir))
    sys.path.insert(0, str(TOOLS))
    from halo2ps2 import mapinfo
    header = mapinfo.read_header(decompressed)
    if header.build != "01.10.12.2276" or header.engine_name != "xbox":
        raise RuntimeError(f"Unexpected map identity: {header.engine_name} {header.build}")
    first = convert_once(decompressed, work / "run-a")
    second = convert_once(decompressed, work / "run-b")
    if first != second:
        raise RuntimeError(f"Repeated conversions differ: {first} != {second}")
    error = geometry_error(decompressed, work / "run-a" / f"{name}.hp2")
    if error["max_axis_error"] > error["declared_bound"]:
        raise RuntimeError(f"Geometry error {error['max_axis_error']} exceeds {error['declared_bound']}")
    packs = {"bsp": ".hp2", "objects": ".obj.hp2", "textures": ".tex.hp2"}
    sizes = {key: (work / "run-a" / f"{name}{suffix}").stat().st_size for key, suffix in packs.items()}
    limits = {"bsp": "current_bsp", "objects": "resident_gameplay", "textures": "texture_cache"}
    for key, region_name in limits.items():
        if sizes[key] > REGION[region_name]:
            raise RuntimeError(f"{key} pack {sizes[key]} exceeds the {REGION[region_name]} byte {region_name} region")
    from halo2ps2 import hp2
    sections = {}
    for key, suffix in packs.items():
        parsed = hp2.parse((work / "run-a" / f"{name}{suffix}").read_bytes())
        sections[key] = {item.tag: item.raw_size for item in parsed.sections}
    pin = subprocess.run(["git", "-C", str(ROOT / "submodules/halo-ps2"), "rev-parse", "HEAD"],
                         check=True, capture_output=True, text=True).stdout.strip()
    report = {
        "map": name,
        "edition": {"engine": header.engine_name, "build": header.build, "type": header.map_type_name},
        "converter": pin,
        "compressed_sha256": sha256(compressed),
        "decompressed_sha256": sha256(decompressed),
        "pack_sha256": first,
        "sizes": sizes,
        "sections": sections,
        "geometry": error,
        "limits": "Retail bytes stayed under data/retail. This does not execute the map on PCSX2.",
    }
    destination = ROOT / "build/convert" / f"{name}.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"map": name, "pack_sha256": first, "geometry": error, "sizes": sizes}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as error:
        sys.exit(f"Conversion failed: {error}")
