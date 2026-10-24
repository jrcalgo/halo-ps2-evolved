#!/usr/bin/env python3
"""Inventory included C1 2D bitmap payload roles against owners and live PS2 selectors.

The report distinguishes source-tag reachability from textures selected by the
existing BSP/TEXS and model/OTEX producers. It does not admit HCP BITM chunks to
the PS2 runtime; current profile bindings remain candidate-only.
"""
from __future__ import annotations

import argparse
import ctypes
import hashlib
import re
import json
import struct
import subprocess
from collections import Counter, defaultdict
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
import hcu_profile_consumer_exclusions as rules  # noqa: E402
PRIMARY = ROOT / "build/m2-c1-corpus-primary-v1"
REBUILD = ROOT / "build/m2-c1-corpus-rebuild-v1"
REPORT = ROOT / "docs/reports/m2-c1-bitmap-consumer-roles-2026-10-23.json"
EXCLUSION_FILE = ROOT / "docs/reports/m2-c1-consumer-exclusions-2026-10-23.json"

MODEL_SOURCES = (
    "src/stream/hcu_bitmap_quad.c",
    "submodules/halo-ps2/engine/src/world/model.c",
    "submodules/halo-ps2/engine/src/world/world.c",
    "submodules/halo-ps2/engine/src/render/obj_render.c",
    "submodules/halo-ps2/engine/src/world/tex.c",
)
BSP_SOURCES = (
    "submodules/halo-ps2/engine/src/main.c",
    "submodules/halo-ps2/engine/src/world/world.c",
    "submodules/halo-ps2/engine/src/render/bsp_render.c",
    "submodules/halo-ps2/engine/src/world/tex.c",
)
HUD_SOURCES = (
    "submodules/halo-ce-universal/source/interface/interface.c",
    "submodules/halo-ce-universal/source/interface/hud.c",
    "submodules/halo-ce-universal/source/interface/hud_draw.c",
    "submodules/halo-ce-universal/source/rasterizer/rasterizer.c",
    "submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_dynavobgeom.c",
)
EFFECT_SOURCES = (
    "submodules/halo-ce-universal/source/effects/particle_systems.c",
    "submodules/halo-ce-universal/source/effects/particles.c",
    "submodules/halo-ce-universal/source/effects/contrails.c",
    "submodules/halo-ce-universal/source/effects/decals.c",
    "submodules/halo-ce-universal/source/structures/structure_lens_flares.c",
    "submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_lights.c",
)
COMMON_SOURCES = ("submodules/halo-ps2/engine/src/render/texcache.c",)
SHADER_SOURCES = (
    "submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_models.c",
    "submodules/halo-ce-universal/source/rasterizer/xbox/rasterizer_xbox_environment.c",
    "submodules/halo-ps2/tools/halo2ps2/objtex.py",
    "submodules/halo-ps2/tools/halo2ps2/texconv.py",
)
ANTENNA_SOURCE = "submodules/halo-ce-universal/source/objects/widgets/antenna.c"

HUD_GROUPS = {"hud#", "hudg", "wphi", "grhi", "unhi", "nhdt"}
EFFECT_GROUPS = {"part", "pctl", "cont", "deca", "lens", "ligh", "glw!", "mgs2"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


EE_WORLD_MK = ROOT / "tools/ee-world.mk"
UI_PACKAGE_SHA256 = "7a7c03b8f77bab655d0902a3cc391a008cdf46a8f64d25fe862d83ca2fc9b0e7"
UI_PACKAGE_REBUILD = ROOT / "build/m2-c1-corpus-rebuild-v1/ui.hcp"
PROFILE_KIND_ORDER = ("ui", "bots", "survival")
# live-consumer: a real, non-stub PS2 reader for the class is linked in the parent renderer or the HCU closure.
# excluded-by-proven-profile-policy: no real reader, and the exclusion is proven by policy and a token scan.
# drop-no-ps2-reader: no real PS2 reader anywhere; the profile builder drops the MEDIA payload.
# undecided: the evidence cannot decide the occurrence; it is reported and never guessed.
DISPOSITIONS = ("live-consumer", "excluded-by-proven-profile-policy", "drop-no-ps2-reader", "undecided")
GUARD_REASON = "selected_or_model_covered_parent_material"
DROP_DISPOSITIONS = frozenset({"excluded-by-proven-profile-policy", "drop-no-ps2-reader"})
SELECTED_ROLES = frozenset({"ps2_model_otex_base_selected", "ps2_bsp_material_base_selected",
                            "ps2_bsp_lightmap_page_selected"})
RULE_DATE = "2026-10-23"
USER_DECISION = (
    "CONSUMER RULE = \"a data class is live if a real (non-stub) PS2 reader for it is linked in the CURRENT "
    "parent renderer build or the CURRENT HCU closure. Its hookup into the HCU frame is a C3 carry-over (like "
    "the running-frame binding). Classes with no PS2 reader anywhere are dropped from the profiles.\" "
    "Runtime admission is NOT an input (it is a later gate); it is reported only as a separate field."
)
DEFERRED_TO = [{"gate": "C3", "item": "C3.6", "reason": "reader hookup into HCU frame"}]

# Pinned ELF inputs. Each SHA-256 is verified before the audit runs.
PARENT_ELF = ROOT / "build/hcu-c1-final-default/world.elf"
PARENT_ELF_SHA256 = "1387249199643f3670ce18971af3ec277fc2b13f18a4570b42cc591550329cb8"
CE_CLOSURE_ELF = ROOT / "build/hcu-ps2-closure/all/halo-local.elf"
CE_CLOSURE_ELF_SHA256 = "55bfec22e8bf5b4c60635feb7a163165baf541ee7aa0806c17ad4cd50f61968b"
CE_STUB_SOURCE = ROOT / "build/hcu-ps2-closure/all/ps2_platform.c"
CE_STUB_SHA256 = "31dd7cbaadaa6074e7d2ff2e79fdb05413074b3a6e907e5ee88f8f190fe55a51"
# Typed tag walks use the same pinned schema ELF as the profile builder and qualifier; the relinked
# closure above is used only for reader linkage.
SCHEMA_ELF = ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"
EE_NM = ROOT / "build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-nm"
CE_PORT_JSON = ROOT / "submodules/halo-ce-universal/port/ps2/port.json"
DEFINED_TYPES = set("TtWwDdBbRr")

CE = "submodules/halo-ce-universal/source/"
PARENT = "submodules/halo-ps2/engine/src/"
PS2_PORT_RASTERIZER = "submodules/halo-ce-universal/port/ps2/src/ps2_rasterizer.c"
PS2_PORT_GEOMETRY = "submodules/halo-ce-universal/port/ps2/src/ps2_geometry.c"
PS2_PORT_BITMAP_REQUESTS = "submodules/halo-ce-universal/port/ps2/src/ps2_bitmap_requests.c"
PS2_PORT_SOUND_CACHE = "submodules/halo-ce-universal/port/ps2/src/ps2_sound_cache.c"
# Port functions that are real code but never submit pixels to GS. A reader whose pixel path forwards into one
# of these is metadata-only. Each entry is proven by reading its body (see reason).
NON_GS_SINKS = {
    (PS2_PORT_GEOMETRY, "build_sprite"):
        "port sprite accumulator: build_sprite only discards its arguments and increments sprite_count "
        "(ps2_geometry.c:65-86); it never builds or submits geometry, so nothing reaches GS",
}

# Reported only (not an input to disposition): the HCP BITM feed chain is a C3.6 carry-over.
HCP_FEED_EE = (
    ("src/stream/hcu_bitmap_dispatch.c", "hcu_bitmap_dispatch_request"),
    ("src/stream/hcu_bitmap_frame.c", "hcu_bitmap_frame_owner_bind"),
)
HCP_FEED_CE = (
    ("submodules/halo-ce-universal/port/ps2/src/ps2_render.c", "halo_ps2_bitmap_frame_consumer_register"),
    ("submodules/halo-ce-universal/port/ps2/src/ps2_bitmap_requests.c", "halo_ps2_bitmap_requests_begin"),
)


def _r(side, file, symbol, forward=None):
    """A reader: side is 'parent' (world.elf) or 'closure' (halo-local.elf). forward names a callee that must be real too."""
    return {"side": side, "file": file, "symbol": symbol, "forward": forward}


# Each class: kind is consumer | policy | no_owner. Consumer classes with "groups" decide per owner group.
CONSUMER_CLASSES = {
    "ps2_model_otex_base_selected": {
        "kind": "consumer",
        "reason": ("selected MODL/OTEX base maps: the parent binds them through tex_find_binding (world.c src_binding) "
                   "and draws them in obj_render_pass"),
        "readers": [_r("parent", PARENT + "world/tex.c", "tex_find_binding"),
                    _r("parent", PARENT + "world/world.c", "world_load_objects"),
                    _r("parent", PARENT + "render/obj_render.c", "obj_render_pass")],
    },
    "ps2_bsp_material_base_selected": {
        "kind": "consumer",
        "reason": ("selected BSP/TEXS base maps: bsp_render_build binds materials through the BSP texture callback "
                   "(world.c src_binding_bsp -> tex_find_binding)"),
        "readers": [_r("parent", PARENT + "render/bsp_render.c", "bsp_render_build"),
                    _r("parent", PARENT + "world/tex.c", "tex_find_binding")],
    },
    "ps2_bsp_lightmap_page_selected": {
        "kind": "consumer",
        "reason": "selected BSP lightmap pages: bsp_render_build's lightmap pass reads pages through s_src.lightmap (world.c src_lightmap)",
        "readers": [_r("parent", PARENT + "render/bsp_render.c", "bsp_render_build")],
    },
    "ce_ui_hud_screenquad_source_only": {
        "kind": "consumer",
        "reason": ("HUD and interface bitmaps, pixel path: hud_draw_bitmap_direct (hud_draw.c:1804) -> "
                   "hud_draw_bitmap_internal (hud_draw.c:1548-1657) -> rasterizer_psuedo_dynamic_screen_quad_draw, "
                   "the PS2 port that calls halo_ps2_bitmap_request_rasterizer_capture (ps2_bitmap_requests.c:12-16, "
                   "271). The request queue consumer is the C3.6 carry-over. interface_draw_bitmap "
                   "(interface.c:417) reaches the same quad call"),
        "readers": [_r("closure", CE + "interface/hud_draw.c", "hud_draw_bitmap_direct",
                       forward={"file": PS2_PORT_BITMAP_REQUESTS,
                                "symbol": "rasterizer_psuedo_dynamic_screen_quad_draw"})],
    },
    "ce_world_widget_antenna_source_only": {
        "kind": "consumer",
        "reason": ("ant! texture, pixel path: antenna_render (antenna.c:265) -> antenna_render_proper "
                   "(antenna.c:418) -> build_sprites_begin/build_sprite (antenna.c:490, 516) -> build_sprite is a "
                   "count-only port accumulator (ps2_geometry.c:65-86), so the path is metadata-only"),
        "readers": [_r("closure", CE + "objects/widgets/antenna.c", "antenna_render",
                       forward={"file": PS2_PORT_GEOMETRY, "symbol": "build_sprite"})],
    },
    "ce_typed_index_resource_reference_source_only": {
        "kind": "consumer",
        "reason": ("scenario predicted-resource bitmap references, pixel path: predicted_resources_precache "
                   "(predicted_resources.c:38) -> _texture_cache_bitmap_get_hardware_format (predicted_resources.c:61) "
                   "which is an identity passthrough (ps2_sound_cache.c:51-57); metadata-only"),
        "readers": [_r("closure", CE + "cache/predicted_resources.c", "predicted_resources_precache",
                       forward={"file": PS2_PORT_SOUND_CACHE,
                                "symbol": "_texture_cache_bitmap_get_hardware_format"})],
    },
    "ce_world_particle_sprite_decal_lens_effect_source_only": {
        "kind": "consumer",
        "reason": "effect bitmaps decided per owner group: a group is live only when its pixel path reaches GS through real code",
        "groups": {
            "part": {
                "reason": ("no PS2 pixel path: particle_new (particles.c:810) only reads sequence metadata; its draw "
                           "function render_particles (render_particles.c:131) is absent from the closure"),
                "readers": [_r("closure", CE + "effects/particles.c", "particle_new",
                               forward={"file": CE + "render/render_particles.c", "symbol": "render_particles"})],
            },
            "cont": {
                "reason": ("no PS2 pixel path: contrail_next_frame (contrails.c:733) updates points; its draw "
                           "function render_contrails_normal (render_contrails.c:16) is absent from the closure"),
                "readers": [_r("closure", CE + "effects/contrails.c", "contrail_next_frame",
                               forward={"file": CE + "render/render_contrails.c",
                                        "symbol": "render_contrails_normal"})],
            },
            "deca": {
                "reason": ("no PS2 pixel path: decal_new_from_collision (decals.c:1559) sizes decals from metadata; "
                           "its draw function rasterizer_decals_draw (render.c:354) is absent from the closure"),
                "readers": [_r("closure", CE + "effects/decals.c", "decal_new_from_collision",
                               forward={"file": CE + "rasterizer/rasterizer.c",
                                        "symbol": "rasterizer_decals_draw"})],
            },
            "glw!": {
                "reason": ("no PS2 pixel path: glow_render (glow.c:541) submits every sprite through build_sprite "
                           "(glow.c:561), a count-only port accumulator (ps2_geometry.c:65-86)"),
                "readers": [_r("closure", CE + "objects/widgets/glow.c", "glow_render",
                               forward={"file": PS2_PORT_GEOMETRY, "symbol": "build_sprite"})],
            },
            "pctl": {
                "reason": ("no PS2 reader: particle_systems_render is absent from the closure and its only bitmap "
                           "dereferences (particle_system_render, particle_systems.c:1542/1599/1659) are unlinked"),
                "readers": [_r("closure", CE + "effects/particle_systems.c", "particle_systems_render"),
                            _r("closure", CE + "effects/particle_systems.c", "particle_system_render")],
            },
            "lens": {
                "reason": ("no PS2 reader: rasterizer_lens_flares_draw (primary_map) is absent; rasterizer_lens_flare_submit "
                           "is a generated stub; build_structure_lens_flares reads no bitmap"),
                "readers": [_r("closure", CE + "rasterizer/rasterizer_lights.c", "rasterizer_lens_flares_draw")],
            },
            "mgs2": {
                "reason": ("no PS2 pixel path: light_volume_render forwards definition->map.index only into "
                           "rasterizer_widget_set_texture, a port stub that returns FALSE"),
                "readers": [_r("closure", CE + "objects/widgets/light_volumes.c", "light_volume_render",
                               forward={"file": PS2_PORT_RASTERIZER, "symbol": "rasterizer_widget_set_texture"})],
            },
        },
    },
    "ce_shader_detail_or_helper_no_enabled_ps2_consumer": {
        "kind": "policy",
        "reason": ("excluded by proven profile policy: detail_map is read only by Xbox rasterizer draw paths that the "
                   "PS2 closure does not link as real code, and no linked PS2 engine source references detail_map"),
        "readers": [_r("closure", CE + "rasterizer/xbox/rasterizer_xbox_models.c", "_rasterizer_model_draw"),
                    _r("closure", CE + "rasterizer/xbox/rasterizer_xbox_models.c", "rasterizer_model_draw_environment_shader"),
                    _r("closure", CE + "rasterizer/xbox/rasterizer_xbox_transparent_geometry.c", "rasterizer_transparent_geometry_group_draw"),
                    _r("closure", CE + "rasterizer/xbox/rasterizer_xbox_environment.c", "_rasterizer_environment_diffuse_texture_draw")],
        "tokens": ("detail_map",),
    },
    "shader_base_reference_not_selected_by_current_material_set": {
        "kind": "policy",
        "reason": ("excluded by proven profile policy: unselected base maps are never bound; the parent readers iterate "
                   "only the MODL/OTEX and BSP/TEXS material sets selected for the profile"),
        "readers": [],
        "tokens": (),
    },
    "missing_owner_fail_closed": {
        "kind": "no_owner",
        "reason": "no schema owner and no selected material: undecided (fail closed), never dropped",
        "readers": [],
    },
}


def _linked_objects(make_text: str) -> tuple[set[str], set[str]]:
    """Return (base EE viewer objects, gameplay-only objects) parsed from tools/ee-world.mk."""
    marker = "ifeq ($(WORLD_HCU_GAMEPLAY),1)"
    head, _, tail = make_text.partition(marker)
    gameplay_block = tail.partition("\nelse")[0]
    pattern = re.compile(r"\$\(WORLD_OUTPUT\)/([A-Za-z0-9_./-]+\.o)")

    def objects(text: str) -> set[str]:
        found: set[str] = set()
        for line in text.splitlines():
            if line.startswith("$(WORLD_OUTPUT)/") and ":" in line:
                continue  # build rules, not EE_OBJS entries
            found.update(pattern.findall(line))
        return found

    return objects(head), objects(gameplay_block)


def _token_hits(tokens: tuple[str, ...], sources: list[Path]) -> int:
    hits = 0
    for path in sources:
        text = path.read_text(errors="replace")
        hits += sum(text.count(token) for token in tokens)
    return hits


def symbol_table(elf: Path) -> dict[str, str]:
    """Defined symbols of an ELF, name -> nm type letter. Undefined symbols are absent."""
    out = subprocess.run([str(EE_NM), str(elf)], capture_output=True, text=True, check=True).stdout
    table: dict[str, str] = {}
    for line in out.splitlines():
        parts = line.split()
        if len(parts) == 3 and parts[1] in DEFINED_TYPES:
            table[parts[2]] = parts[1]
    return dict(sorted(table.items()))


STUB_DEFINITION = re.compile(r"^(?:__attribute__\(\(weak\)\) )?[A-Za-z_][^;=]*?\b([A-Za-z_]\w*)\([^;]*\)\s*\{.*\}\s*$")


def generated_stub_names(path: Path) -> set[str]:
    """Functions defined by hcu_ps2_link.py's generated ps2_platform.c. Each one is a stub."""
    names: set[str] = set()
    for line in path.read_text().splitlines():
        match = STUB_DEFINITION.match(line)
        if match:
            names.add(match.group(1))
    return names


def _callers(symbol: str, defining: str) -> list[str]:
    """Source files under src/ and the CE PS2 port that mention the symbol outside its definition."""
    found = []
    for root in (ROOT / "src", ROOT / "submodules/halo-ce-universal/port/ps2"):
        for path in sorted(root.rglob("*.[ch]")):
            rel = path.relative_to(ROOT).as_posix()
            if rel == defining or path.suffix != ".c":
                continue
            if re.search(r"\b" + re.escape(symbol) + r"\s*\(", path.read_text(errors="replace")):
                found.append(rel)
    return found


def _source_defines(rel: str, symbol: str) -> bool:
    path = ROOT / rel
    return path.is_file() and re.search(r"\b" + re.escape(symbol) + r"\s*\(", path.read_text(errors="replace")) is not None


def feed_status(ee_table: dict[str, str], ce_table: dict[str, str], ce_stubs: set[str]) -> dict:
    """Reported only: the HCP BITM feed into the frame is a C3.6 carry-over and is not a disposition input."""
    rows = {"ee": [], "ce": []}
    for side, links, table in (("ee", HCP_FEED_EE, ee_table), ("ce", HCP_FEED_CE, ce_table)):
        for rel, symbol in links:
            state = "absent" if symbol not in table else ("stub" if symbol in ce_stubs and side == "ce" else "real")
            rows[side].append({"file": rel, "symbol": symbol, "state": state,
                               "callers_outside_definition": _callers(symbol, rel)
                               if symbol == "hcu_bitmap_frame_owner_bind" else None})
    ok = all(r["state"] == "real" for side in rows for r in rows[side])
    ok = ok and bool(rows["ee"][1]["callers_outside_definition"])
    return {"linked": ok, "links": rows}


def verify_elf_pins() -> dict:
    """Refuse to run against any ELF that is not the pinned build."""
    pins = {}
    for label, path, expected in (("parent_renderer", PARENT_ELF, PARENT_ELF_SHA256),
                                  ("hcu_closure", CE_CLOSURE_ELF, CE_CLOSURE_ELF_SHA256),
                                  ("closure_stub_source", CE_STUB_SOURCE, CE_STUB_SHA256)):
        digest = file_sha(path)
        if digest != expected:
            raise ValueError(f"{label} does not match its pinned SHA-256: {path.relative_to(ROOT).as_posix()}")
        pins[label] = {"path": path.relative_to(ROOT).as_posix(), "sha256": digest}
    pins["nm"] = {"path": EE_NM.relative_to(ROOT).as_posix(), "sha256": file_sha(EE_NM)}
    pins["schema_elf"] = {"path": SCHEMA_ELF.relative_to(ROOT).as_posix(), "sha256": file_sha(SCHEMA_ELF)}
    return pins


def _definition_line(path: Path, symbol: str) -> int | None:
    pattern = re.compile(r"^[A-Za-z_].*\b" + re.escape(symbol) + r"\s*\(")
    for number, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if pattern.match(line) and not line.rstrip().endswith(";"):
            return number
    return None


def _parameter_names(parameters: str) -> set[str]:
    """Names of a C parameter list: the last identifier of each comma-separated parameter."""
    names = set()
    for chunk in parameters.split(","):
        identifiers = re.findall(r"[A-Za-z_]\w*", chunk)
        if identifiers and identifiers[-1] != "void":
            names.add(identifiers[-1])
    return names


def _port_stub_body(path: Path, symbol: str) -> bool:
    """True when the definition of symbol only discards its arguments or returns FALSE/0/NULL or an argument unchanged.

    An identity passthrough (`return <parameter>;`) forwards the caller's pointer without reading its pixels, so
    it is a stub for the purpose of pixel reachability.
    """
    text = path.read_text(errors="replace")
    match = re.search(r"\b" + re.escape(symbol) + r"\s*\(([^{;]*)\)\s*\{", text)
    if not match:
        return False
    depth, index = 1, match.end()
    start = index
    while index < len(text) and depth:
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
        index += 1
    body = re.sub(r"//[^\n]*", "", re.sub(r"/\*.*?\*/", "", text[start:index - 1], flags=re.S))
    statements = [s.strip() for s in body.split(";") if s.strip()]
    passthrough = {f"return {name}" for name in _parameter_names(match.group(1))}
    return all(s.startswith("(void)") or s in ("return FALSE", "return 0", "return NULL") or s in passthrough
               for s in statements)


def _reader_state(side: str, rel: str, symbol: str, tables: dict, stubs: set[str]) -> str:
    if symbol not in tables[side]:
        return "absent"
    if side == "closure" and symbol in stubs:
        return "stub"
    if side == "closure" and (rel, symbol) in NON_GS_SINKS:
        return "stub"
    path = ROOT / rel
    if path.is_file() and _port_stub_body(path, symbol):
        return "stub"
    return "real"


def _evaluate_reader(spec: dict, tables: dict, stubs: set[str]) -> dict:
    state = _reader_state(spec["side"], spec["file"], spec["symbol"], tables, stubs)
    path = ROOT / spec["file"]
    row = {"side": spec["side"], "file": spec["file"], "symbol": spec["symbol"],
           "nm_type": tables[spec["side"]].get(spec["symbol"]),
           "definition_line": _definition_line(path, spec["symbol"]) if path.is_file() else None,
           "forward": None}
    if spec.get("forward"):
        forward = spec["forward"]
        fstate = _reader_state("closure", forward["file"], forward["symbol"], tables, stubs)
        row["forward"] = {"file": forward["file"], "symbol": forward["symbol"], "state": fstate,
                          "nm_type": tables["closure"].get(forward["symbol"]),
                          "definition_line": _definition_line(ROOT / forward["file"], forward["symbol"])}
        if state == "real" and fstate != "real":
            state = "forward_" + fstate
    row["state"] = state
    return row


def qualify_consumer_classes() -> dict:
    """Evaluate every class from the pinned parent and closure ELFs. A reader counts only when real and not a stub."""
    tables = {"parent": symbol_table(PARENT_ELF), "closure": symbol_table(CE_CLOSURE_ELF)}
    stubs = generated_stub_names(CE_STUB_SOURCE)
    base, _gameplay = _linked_objects(EE_WORLD_MK.read_text())
    engine_src = ROOT / "submodules/halo-ps2/engine/src"
    linked_engine = sorted(p for p in engine_src.rglob("*.c")
                           if p.relative_to(engine_src).with_suffix(".o").as_posix() in base)
    result: dict = {}
    for name, spec in sorted(CONSUMER_CLASSES.items()):
        entry: dict = {"kind": spec["kind"], "reason": spec["reason"], "readers": [], "groups": None}
        if spec.get("groups"):
            entry["groups"] = {}
            for group, gspec in sorted(spec["groups"].items()):
                rows = [_evaluate_reader(r, tables, stubs) for r in gspec["readers"]]
                entry["groups"][group] = {"reason": gspec["reason"], "readers": rows,
                                          "live": any(r["state"] == "real" for r in rows)}
            real = any(g["live"] for g in entry["groups"].values())
        else:
            entry["readers"] = [_evaluate_reader(r, tables, stubs) for r in spec["readers"]]
            real = any(r["state"] == "real" for r in entry["readers"])
        tokens = tuple(spec.get("tokens", ()))
        hits = _token_hits(tokens, linked_engine) if tokens else None
        entry["live"] = real
        entry["real_reader"] = real
        entry["token_scan"] = {"tokens": list(tokens), "hits": hits}
        entry["policy_proven"] = spec["kind"] == "policy" and not real and (not tokens or hits == 0)
        result[name] = entry
    result["_linked_engine_sources"] = [p.relative_to(ROOT).as_posix() for p in linked_engine]
    result["_hcp_bitm_feed"] = feed_status(symbol_table(PARENT_ELF), tables["closure"], stubs)
    return result


def occurrence_disposition(role: str, consumers: list[dict], qualification: dict) -> str:
    """Decide one BITM occurrence from evidence. Unknown or inconsistent roles are undecided, never blocking."""
    spec = qualification.get(role)
    if spec is None:
        return "undecided"
    kind = spec["kind"]
    if kind == "consumer":
        if spec["groups"] is not None:
            groups = {str(c.get("owner_group")) for c in consumers}
            if not groups:
                return "undecided"
            lives = []
            for group in groups:
                gspec = spec["groups"].get(group)
                if gspec is None:
                    return "undecided"
                lives.append(gspec["live"])
            return "live-consumer" if any(lives) else "drop-no-ps2-reader"
        return "live-consumer" if spec["live"] else "drop-no-ps2-reader"
    if kind == "policy":
        return "excluded-by-proven-profile-policy" if spec["policy_proven"] else "undecided"
    return "undecided"  # no_owner and unknown kinds fail closed


def _exclusion_entry(cls: str, owner_group: str | None, reason: str) -> dict:
    return {"class": cls, "reason": reason, "profile_kinds": list(PROFILE_KIND_ORDER),
            "match": {"definition": None, "field": None, "owner_group": owner_group, "role": cls},
            "counts": {}}


def consumer_exclusion_rows(qualification: dict) -> list[dict]:
    """Exclusion rows for every consumer reference class that has no live pixel path (counts left empty)."""
    entries = []
    for cls, spec in sorted(qualification.items()):
        if cls.startswith("_"):
            continue
        if spec["kind"] == "consumer" and spec["groups"] is not None:
            for group, gspec in sorted(spec["groups"].items()):
                if not gspec["live"]:
                    entries.append(_exclusion_entry(cls, group, gspec["reason"]))
        elif spec["kind"] == "consumer" and not spec["live"]:
            entries.append(_exclusion_entry(cls, None, spec["reason"]))
        elif spec["kind"] == "policy" and spec["policy_proven"]:
            entries.append(_exclusion_entry(cls, None, spec["reason"]))
    entries.sort(key=lambda e: (e["class"], e["match"]["owner_group"] or ""))
    return entries


def image_disposition(role: str, refs: list[tuple[dict, str]], qualification: dict,
                      rows: list[dict], profile_kind: str) -> tuple[str, list[dict]]:
    """Label one bitmap image in one profile from its consumer references.

    refs: (consumer reference, per-reference role). The keep/drop decision itself is
    hcu_profile_consumer_exclusions.decide_references (shared with the builder); this only names it.
    Returns (label, covering exclusion rows). Selected parent material is always live.
    """
    if role in SELECTED_ROLES:
        return "live-consumer", []
    if not refs:
        return "undecided", []
    per_reference = [occurrence_disposition(ref_role, [ref], qualification) for ref, ref_role in refs]
    if "undecided" in per_reference:
        return "undecided", []
    if "live-consumer" in per_reference:
        return "live-consumer", []
    decision = rules.decide_references([ref for ref, _ in refs], profile_kind, rows)
    if decision["keep"]:
        raise ValueError(f"exclusion rows do not cover a drop-classified {role} reference")
    if "drop-no-ps2-reader" in per_reference:
        return "drop-no-ps2-reader", decision["rows"]
    return "excluded-by-proven-profile-policy", decision["rows"]


def exclusion_document(rows: list[dict]) -> bytes:
    """The pinned exclusion file: {"required_profile_exclusions": [...]} with sorted keys."""
    return (json.dumps({"required_profile_exclusions": rows}, indent=2, sort_keys=True) + "\n").encode()


def classify_role(owners: list[dict], *, selected_model=False, selected_bsp=False) -> str:
    """Classify schema owner evidence separately from actual material selection.

    Selected material takes precedence even without a schema owner: the parent renderer's own readers bind it.
    """
    if not owners and not (selected_model or selected_bsp):
        return "missing_owner_fail_closed"
    if any(owner.get("owner_group") == "ant!" for owner in owners):
        return "ce_world_widget_antenna_source_only"
    if selected_bsp:
        return "ps2_bsp_material_base_selected"
    if selected_model:
        return "ps2_model_otex_base_selected"
    groups = {str(owner.get("owner_group", "")) for owner in owners}
    if groups & HUD_GROUPS or any(
            owner.get("owner_group") == "matg" and "interface_tag_references" in str(owner.get("field", ""))
            for owner in owners):
        return "ce_ui_hud_screenquad_source_only"
    if any(owner.get("schema_kind") == "tag_index" and
           (owner.get("definition") == "predicted_resource" or "predicted" in str(owner.get("field", "")))
           for owner in owners):
        return "ce_typed_index_resource_reference_source_only"
    if groups & EFFECT_GROUPS:
        return "ce_world_particle_sprite_decal_lens_effect_source_only"
    shader_base = any(
        owner.get("owner_group") in {"soso", "sotr", "schi", "senv", "sgla", "swat"}
        and str(owner.get("field", "")).split(".")[-1] in {"base_map", "map", "diffuse_map"}
        for owner in owners)
    if shader_base:
        return "shader_base_reference_not_selected_by_current_material_set"
    if groups & {"soso", "sotr", "schi", "senv", "sgla", "swat", "spla", "smet", "matg"}:
        return "ce_shader_detail_or_helper_no_enabled_ps2_consumer"
    return "unknown_owner_group_fail_closed"


_typed_index_owners = rules.typed_index_owners  # shared implementation (hcu_profile_consumer_exclusions)


def _load_model_reader() -> ctypes.CDLL:
    engine = ROOT / "submodules/halo-ps2/engine"
    source = engine / "src/world/model.c"
    wrapper_text = r'''#include <stddef.h>
#include <stdint.h>
#include "world/model.h"
int hcu_model_pairs(const uint8_t *bytes,size_t size,uint32_t *out,size_t cap) {
 model_section s; uint32_t mi,perm,lod; size_t n=0;
 if(model_open(&s,bytes,size)!=MODEL_OK) return -1;
 for(mi=0;mi<s.model_count;mi++) {
  model_info m=model_get(&s,mi);
  for(perm=0;perm<m.permutation_count;perm++) for(lod=0;lod<MODEL_LODS;lod++) {
   model_part_range r=model_parts(&s,&m,perm,lod); uint32_t i;
   for(i=0;i<r.part_count;i++) {
    model_part p=model_get_part(&s,(uint32_t)r.first_part+i);
    size_t j; int found=0;
    for(j=0;j<n;j++) if(out[2*j]==m.tag_id && out[2*j+1]==p.shader_id) {found=1;break;}
    if(!found) { if(n>=cap) return -2; out[2*n]=m.tag_id; out[2*n+1]=p.shader_id; n++; }
   }
  }
 }
 return (int)n;
}
'''
    key = sha(wrapper_text.encode() + source.read_bytes())
    cache = ROOT / "build/hcu-c1-bitmap-role-audit"
    cache.mkdir(exist_ok=True)
    wrapper = cache / f"model-{key}.c"
    library = cache / f"model-{key}.so"
    if not library.exists():
        wrapper.write_text(wrapper_text)
        subprocess.run(["cc", "-shared", "-fPIC", "-std=c11", "-I", str(engine / "src"),
                        str(wrapper), str(source), "-o", str(library)], check=True,
                       capture_output=True, text=True)
    lib = ctypes.CDLL(str(library))
    lib.hcu_model_pairs.argtypes = (ctypes.c_void_p, ctypes.c_size_t,
                                    ctypes.POINTER(ctypes.c_uint32), ctypes.c_size_t)
    lib.hcu_model_pairs.restype = ctypes.c_int
    return lib


def _package_chunks(package_path: Path, manifest: dict) -> dict[tuple[int, int], bytes]:
    data = package_path.read_bytes()
    if sha(data) != manifest.get("package_sha256"):
        raise ValueError(f"package hash mismatch: {package_path}")
    if len(data) < 32:
        raise ValueError(f"short HCP: {package_path}")
    magic, version, hsize, profile_id, count, directory, dsize, total = struct.unpack_from("<4s7I", data)
    if magic != b"HCP1" or version != 1 or hsize != 32 or total != len(data) or dsize != count * 48:
        raise ValueError(f"invalid HCP header: {package_path}")
    chunks = {}
    last_end = directory + dsize
    for i in range(count):
        kind, cid, offset, size, digest = struct.unpack_from("<4I32s", data, directory + i * 48)
        if offset < last_end or size == 0 or offset + size > len(data):
            raise ValueError(f"invalid HCP chunk extent: {package_path}:{i}")
        blob = data[offset:offset + size]
        if hashlib.sha256(blob).digest() != digest:
            raise ValueError(f"HCP chunk digest mismatch: {package_path}:{i}")
        chunks[(kind, cid)] = blob
        last_end = offset + size
    media = manifest.get("media", {}).get("chunks", [])
    media_rows = sorted(((cid, blob) for (kind, cid), blob in chunks.items() if kind == 2))
    if len(media_rows) != len(media):
        raise ValueError(f"media chunk inventory mismatch: {package_path}")
    for expected_id, ((chunk_id, blob), row) in enumerate(zip(media_rows, media), 1):
        if chunk_id != expected_id or len(blob) != row.get("bytes") or sha(blob) != row.get("sha256"):
            raise ValueError(f"media row does not match package: {package_path}:{expected_id}")
    return chunks


def _map_for(source_key: str, manifest: dict, maps: dict):
    if source_key not in maps:
        from halo2ps2 import texconv
        row = manifest.get("source_maps", {}).get(source_key)
        if not row:
            raise ValueError(f"missing source map identity {source_key}")
        path = ROOT / row["path"]
        if not path.is_file() or file_sha(path) != row.get("sha256"):
            raise ValueError(f"source map pin mismatch: {path}")
        maps[source_key] = texconv.MapData.open(path)
    return maps[source_key]


def _selected_object_bitmaps(manifest: dict, chunks: dict, maps: dict, reader) -> set[tuple[str, int, int]]:
    """Audit view of the shared MODL selection (hcu_profile_consumer_exclusions.selected_model_bitmaps)."""
    modl = [(row.get("key"), chunks[(2, index)]) for index, row in enumerate(manifest["media"]["chunks"], 1)
            if row.get("kind") == "MODL"]
    pairs = rules.selected_model_bitmaps(modl, manifest["media"].get("bindings", []),
                                         lambda key: _map_for(key, manifest, maps))
    return {(sk, datum, 0) for sk, datum in pairs}


def _selected_bsp_bitmaps(manifest: dict, maps: dict) -> tuple[set[tuple[str, int, int]], set[tuple[str, int, int]], list[dict]]:
    """Audit view of the shared BSP selection scan (hcu_profile_consumer_exclusions.selected_bsp_bitmaps)."""
    descriptors = [(d.get("owner", {}).get("source_key"), int(d["source_file_offset"]))
                   for d in manifest.get("media", {}).get("bsp_catalog", [])]
    selected_tags, lightmap_tags, evidence = rules.selected_bsp_bitmaps(
        descriptors, lambda key: _map_for(key, manifest, maps))
    selected = {(sk, datum, 0) for sk, datum in selected_tags}
    lightmaps = set(lightmap_tags)
    cbsp = {int(d["source_file_offset"]): d for d in manifest.get("media", {}).get("bsp_catalog", [])}
    for row in evidence:
        descriptor = cbsp.get(int(row["source_file_offset"]), {})
        remaps = [r for r in descriptor.get("tag_remaps", []) if r.get("group") == "bitm"]
        row["cbsp_bitmap_tag_remap_count"] = len(remaps)
        row["cbsp_bitmap_tag_remap_source_datums"] = sorted({r.get("source_datum") for r in remaps})
        row["bsp_path"] = descriptor.get("owner", {}).get("path")
    return selected, lightmaps, evidence


def _classify_consumers(consumers, selected_model, selected_bsp,
                        selected_bsp_lightmap=False, cbsp_reference=False):
    if selected_bsp_lightmap:
        return "ps2_bsp_lightmap_page_selected"
    if not consumers and not (selected_model or selected_bsp):
        if cbsp_reference:
            return "cbsp_bitmap_reference_not_selected_by_rendered_materials"
        return "missing_owner_fail_closed"
    return classify_role(consumers, selected_model=selected_model, selected_bsp=selected_bsp)


def audit(primary: Path = PRIMARY, rebuild: Path = REBUILD) -> dict:
    import sys
    sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
    sys.path.insert(0, str(ROOT / "tools"))
    from hcu_schema_manifest import Elf32, SchemaManifest
    from ctag import decode as decode_ctag

    pins = verify_elf_pins()
    reader = _load_model_reader()
    profile_paths = sorted(p for p in primary.glob("*.json")
                           if (primary / p.name.replace(".json", ".hcp")).is_file())
    if len(profile_paths) != 27:
        raise ValueError(f"expected 27 primary profile manifests, found {len(profile_paths)}")
    if file_sha(primary / "ui.hcp") != UI_PACKAGE_SHA256 or file_sha(UI_PACKAGE_REBUILD) != UI_PACKAGE_SHA256:
        raise ValueError("ui.hcp does not match the pinned SHA-256 in primary or rebuild corpus")
    reb_manifests = {p.name: json.loads(p.read_text()) for p in rebuild.glob("*.json")
                     if (rebuild / p.name.replace(".json", ".hcp")).is_file()}
    if len(reb_manifests) != 27:
        raise ValueError(f"expected 27 rebuild manifests, found {len(reb_manifests)}")
    qualification = qualify_consumer_classes()
    template_rows = [rules._check_row(row, i) for i, row in enumerate(consumer_exclusion_rows(qualification))]
    if EXCLUSION_FILE.is_file():
        pinned_rows = rules.load_exclusions(EXCLUSION_FILE)["rows"]
        if [_without_counts(r) for r in pinned_rows] != [_without_counts(r) for r in template_rows]:
            raise ValueError("pinned consumer exclusion file differs from the qualification-derived rows")
    dropped_images: dict[str, set] = defaultdict(set)
    row_images: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    schema = SchemaManifest(Elf32(SCHEMA_ELF)).build()
    profile_names = [p.stem for p in profile_paths]

    maps: dict = {}
    global_rows: dict[tuple, dict] = {}
    occurrences: list[tuple] = []
    profile_inventory = []
    bsp_evidence: dict = {}
    kinds_by_profile: dict[str, str] = {}
    occurrence_roles: dict[str, Counter] = {}
    role_counts: Counter = Counter()
    runtime_admitted_count = 0
    typed_joins: dict[str, int] = {}
    for path in profile_paths:
        profile = path.stem
        manifest = json.loads(path.read_text())
        package_path = primary / f"{profile}.hcp"
        rebuild_package_path = rebuild / f"{profile}.hcp"
        if path.name not in reb_manifests or file_sha(package_path) != manifest.get("package_sha256"):
            raise ValueError(f"primary package/manifest identity mismatch: {profile}")
        if manifest.get("package_sha256") != reb_manifests[path.name].get("package_sha256"):
            raise ValueError(f"primary/rebuild package mismatch: {profile}")
        if (not rebuild_package_path.is_file() or
                file_sha(rebuild_package_path) != manifest.get("package_sha256") or
                rebuild_package_path.read_bytes() != package_path.read_bytes()):
            raise ValueError(f"primary/rebuild package bytes differ: {profile}")
        chunks = _package_chunks(package_path, manifest)
        kinds_by_profile[profile] = str(manifest.get("profile", {}).get("kind"))

        consumers_by_datum: dict[int, list] = defaultdict(list)
        for consumer in manifest.get("bitmap_consumers", []):
            consumers_by_datum[int(consumer["bitmap_output_datum"])].append(consumer)
        # Schema-walked tag_index owners of this profile's CTAG, joined by exact field offset and width.
        ctag = decode_ctag(chunks[(1, 0)], max_image_size=64 * 1024 * 1024)
        typed = rules.typed_references(ctag.image, schema, manifest.get("tag_index_remaps", []))
        joined = 0
        for output, rows_typed in sorted(typed.items()):
            consumers_by_datum[output].extend(rows_typed)
            joined += len(rows_typed)
        typed_joins[profile] = joined
        deps = {int(d["output_datum"]): d for d in manifest.get("dependencies", [])}

        selected_model = _selected_object_bitmaps(manifest, chunks, maps, reader)
        selected_bsp, selected_bsp_lightmaps, bsp_rows = _selected_bsp_bitmaps(manifest, maps)
        bsp_evidence[profile] = bsp_rows
        binding_rows = [b for b in manifest["media"].get("bindings", []) if b.get("kind") == "BITM"]
        chunk_rows = {row.get("key"): row for row in manifest["media"].get("chunks", [])}
        if len(binding_rows) != manifest.get("validation", {}).get("bitmap_coverage", {}).get("serialized_images"):
            raise ValueError(f"BITM binding count differs from strict validator coverage: {profile}")
        cbsp_remap_map: dict[int, list] = defaultdict(list)
        for descriptor in manifest["media"].get("bsp_catalog", []):
            for remap in descriptor.get("tag_remaps", []):
                if remap.get("group") == "bitm":
                    dep = deps.get(int(remap.get("output_datum", -1)))
                    if not dep or dep.get("group") != "bitm" or dep.get("source_datum") != remap.get("source_datum"):
                        raise ValueError(f"CBSP bitmap tag remap does not join dependency: {profile}:{remap}")
                    cbsp_remap_map[int(remap["output_datum"])].append(remap)

        # One shared drop decision per bitmap (builder and audit call the same function).
        guard_tags = {(k[0], k[1]) for k in (selected_model | selected_bsp | selected_bsp_lightmaps)}
        guard_tags |= {(d["source_key"], int(d["source_datum"])) for d in manifest.get("dependencies", [])
                       if d.get("group") == "bitm" and int(d["output_datum"]) in cbsp_remap_map}
        decisions = rules.decide_profile(manifest, {"kind": kinds_by_profile[profile], "rows": template_rows},
                                         ctag_image=ctag.image, schema=schema, guard_tags=guard_tags)
        occurrence_roles[profile] = Counter()
        category_counts: Counter = Counter()
        selected_model_hits = selected_bsp_hits = selected_bsp_lightmap_hits = 0
        for binding in binding_rows:
            runtime_admitted_count += int(bool(binding.get("runtime_admitted", False)))
            owner = binding.get("owner", {})
            source_key, source_datum = owner.get("source_key"), int(owner.get("source_datum", -1))
            image_index = int(owner.get("source_image_index", -1))
            dep = next((d for d in manifest["dependencies"] if d.get("group") == "bitm" and
                        d.get("source_key") == source_key and d.get("source_datum") == source_datum and
                        d.get("path") == owner.get("path")), None)
            if dep is None or image_index < 0:
                raise ValueError(f"BITM binding owner missing source dependency: {profile}:{owner}")
            consumers = consumers_by_datum[int(dep["output_datum"])]
            identity = (source_key, source_datum, image_index)
            is_model = identity in selected_model
            is_bsp = identity in selected_bsp
            is_bsp_lightmap = identity in selected_bsp_lightmaps
            has_cbsp_reference = bool(cbsp_remap_map.get(int(dep["output_datum"])))
            role = _classify_consumers(consumers, is_model, is_bsp, is_bsp_lightmap, has_cbsp_reference)
            groups = tuple(sorted({str(c.get("owner_group")) for c in consumers}))
            refs = [(c, classify_role([c])) for c in consumers]
            decision = decisions[(source_key, source_datum)]
            if decision["reason"] == GUARD_REASON:
                disposition = "live-consumer"  # selected or model/CBSP-covered parent material is always live
            else:
                disposition, _covering = image_disposition(role, refs, qualification, template_rows,
                                                           kinds_by_profile[profile])
                if decision["keep"] == (disposition in DROP_DISPOSITIONS):
                    raise ValueError(f"audit label and shared decision disagree: {profile}:{owner}")
            occurrences.append((profile, role, groups, disposition))
            image_key = (source_key, source_datum, image_index)
            if not decision["keep"]:
                dropped_images[profile].add(image_key)
                for row in decision["rows"]:
                    row_images[json.dumps(row, sort_keys=True)][profile].add(image_key)
            occurrence_roles[profile][role] += 1

            m = _map_for(source_key, manifest, maps)
            entry = m.by_id.get(source_datum)
            if entry is None or entry.path != owner.get("path"):
                raise ValueError(f"BITM source owner tag is missing: {profile}:{owner}")
            images = m.images(source_datum)
            if image_index >= len(images) or not images[image_index].is_2d:
                raise ValueError(f"BITM profile binding is not a 2D source image: {profile}:{owner}")
            image = images[image_index]
            pixel_bytes = bytes(m.pixels(image))
            key = (source_key, source_datum, image_index, sha(pixel_bytes))
            media_chunk = chunk_rows.get(binding.get("chunk_key"))
            if not media_chunk:
                raise ValueError(f"BITM binding has no package media chunk: {profile}:{binding}")
            item = global_rows.setdefault(key, {
                "source_key": source_key, "source_datum": source_datum,
                "source_map_sha256": manifest["source_maps"][source_key]["sha256"],
                "path": entry.path, "image_index": image_index,
                "width": int(image.width), "height": int(image.height),
                "source_pixel_sha256": key[3], "package_chunk_sha256": media_chunk["sha256"],
                "classification": role, "profiles": [], "schema_owners": {},
                "runtime_admitted": bool(binding.get("runtime_admitted", False)),
                "cbsp_bitmap_reference": bool(cbsp_remap_map.get(int(dep["output_datum"]))),
                "_dispositions": set(),
            })
            item["_dispositions"].add(disposition)
            if role != item["classification"]:
                if role == "ps2_bsp_material_base_selected":
                    item["classification"] = role
                elif role == "ps2_model_otex_base_selected" and item["classification"] != "ps2_bsp_material_base_selected":
                    item["classification"] = role
                else:
                    item["classification"] = "multiple_owner_role_families"
            if profile not in item["profiles"]:
                item["profiles"].append(profile)
            for consumer in consumers:
                owner_key = (str(consumer.get("owner_group")), str(consumer.get("definition")),
                             str(consumer.get("field")), str(consumer.get("schema_kind") or ""))
                item["schema_owners"][owner_key] = item["schema_owners"].get(owner_key, 0) + 1
            if is_model:
                selected_model_hits += 1
            if is_bsp:
                selected_bsp_hits += 1
            if is_bsp_lightmap:
                selected_bsp_lightmap_hits += 1
            category_counts[item["classification"]] += 1
            role_counts[item["classification"]] += 1
        occurrence_counts = Counter(o[3] for o in occurrences if o[0] == profile)
        coverage = manifest.get("validation", {}).get("bitmap_coverage", {})
        profile_inventory.append({
            "profile": profile, "kind": manifest.get("profile", {}).get("kind"),
            "map": manifest.get("profile", {}).get("map"),
            "package_sha256": manifest["package_sha256"],
            "manifest_sha256": file_sha(path), "package_bytes": package_path.stat().st_size,
            "bitmap_2d_occurrences": len(binding_rows),
            "bitmap_2d_unique_source_images": len({(b["owner"]["source_key"], b["owner"]["source_datum"],
                                                    b["owner"]["source_image_index"]) for b in binding_rows}),
            "bitmap_coverage": coverage,
            "typed_tag_index_consumers_joined": typed_joins[profile],
            "selected_model_otex_bitmap_binding_hits": selected_model_hits,
            "selected_bsp_texs_bitmap_binding_hits": selected_bsp_hits,
            "selected_bsp_lightmap_page_binding_hits": selected_bsp_lightmap_hits,
            "cbsp_bitmap_tag_remap_count": sum(len(v) for v in cbsp_remap_map.values()),
            "role_counts": dict(sorted(category_counts.items())),
            "disposition_counts": {k: occurrence_counts.get(k, 0) for k in DISPOSITIONS},
            "occurrence_role_counts": dict(sorted(occurrence_roles[profile].items())),
        })

    source_files = set(MODEL_SOURCES) | set(BSP_SOURCES) | set(HUD_SOURCES) | set(EFFECT_SOURCES) | \
        set(COMMON_SOURCES) | set(SHADER_SOURCES)
    for spec in CONSUMER_CLASSES.values():
        for reader in list(spec.get("readers", [])) + [r for g in (spec.get("groups") or {}).values()
                                                       for r in g["readers"]]:
            source_files.add(reader["file"])
            if reader.get("forward"):
                source_files.add(reader["forward"]["file"])
    report_pins = {}
    for rel in sorted(source_files):
        if not (ROOT / rel).is_file():
            raise ValueError(f"consumer evidence source missing: {rel}")
        report_pins[rel] = file_sha(ROOT / rel)
    for row in global_rows.values():
        dispositions = row.pop("_dispositions")
        row["dispositions"] = sorted(dispositions)
        if "undecided" in dispositions:
            row["disposition"] = "undecided"
        elif "live-consumer" in dispositions:
            row["disposition"] = "live-consumer"
        elif len(dispositions) == 1:
            row["disposition"] = next(iter(dispositions))
        else:
            row["disposition"] = "undecided"
        row["profiles"].sort()
        row["schema_owners"] = [
            {"owner_group": key[0], "definition": key[1], "field": key[2], "schema_kind": key[3] or None,
             "occurrence_count": count}
            for key, count in sorted(row["schema_owners"].items())]

    disposition_totals = Counter(o[3] for o in occurrences)
    by_kind: dict[str, Counter] = defaultdict(Counter)
    for profile, _role, _groups, disposition in occurrences:
        by_kind[kinds_by_profile[profile]][disposition] += 1
    kinds = [k for k in PROFILE_KIND_ORDER if k in by_kind] + sorted(k for k in by_kind if k not in PROFILE_KIND_ORDER)
    exclusions = []
    for index, row in enumerate(template_rows):
        counts = {name: len(row_images[json.dumps(row, sort_keys=True)][name]) for name in profile_names}
        exclusions.append(dict(row, counts=counts))
    exclusion_bytes = exclusion_document(exclusions)
    dropped_by_profile = {name: len(dropped_images[name]) for name in profile_names}
    dropped_by_kind: dict[str, int] = defaultdict(int)
    for name in profile_names:
        dropped_by_kind[kinds_by_profile[name]] += dropped_by_profile[name]
    undecided = disposition_totals.get("undecided", 0)

    class_table = []
    for name, spec in sorted(CONSUMER_CLASSES.items()):
        seen = Counter(o[3] for o in occurrences if o[1] == name)
        row = {"class": name, "kind": spec["kind"], "reason": spec["reason"],
               "occurrence_dispositions": {k: seen.get(k, 0) for k in DISPOSITIONS if seen.get(k, 0)},
               "qualification": qualification[name]}
        class_table.append(row)

    inputs = {rel: report_pins[rel] for rel in report_pins}
    for path in (EE_WORLD_MK, PARENT_ELF, CE_CLOSURE_ELF, CE_STUB_SOURCE, EE_NM, UI_PACKAGE_REBUILD):
        inputs[path.relative_to(ROOT).as_posix()] = file_sha(path)
    return {
        "schema": "hcu-c1-bitmap-consumer-roles-v4",
        "result": "all_occurrences_decided" if undecided == 0 else "undecided_occurrences_present",
        "rule": {
            "user_decision": USER_DECISION,
            "date": RULE_DATE,
            "reader": ("a real PS2 reader consumes the MEDIA pixels: a reader's pixel path must reach GS upload "
                       "through non-stub code. Dereferencing tag fields (bounds, counts, sequence metadata), a "
                       "passthrough that returns its argument, a port function that only discards its arguments or "
                       "returns FALSE/0/NULL, or a count-only sprite accumulator (NON_GS_SINKS) keeps metadata alive "
                       "but does NOT keep media alive. Absent functions are not readers."),
            "runtime_admission": "not an input; reported only as totals.runtime_admitted_bitm_bindings",
            "exclusion_semantics": ("a bitmap MEDIA payload is dropped in a profile only when every consumer reference of "
                                    "that bitmap (bitmap_consumers plus typed tag_index references joined through the "
                                    "CTAG) is covered by a pinned exclusion row for its own role (per-reference match, "
                                    "per-profile kind), via hcu_profile_consumer_exclusions.decide_profile. Any pixel-path "
                                    "reference, selected or model/CBSP-covered material, undecided role or zero references keep it. "
                                    "Each row's counts are the distinct dropped 2D images in that profile that one of its rows covers; "
                                    "dropped_images holds the distinct dropped total per profile."),
            "ce_metadata": "CE tag metadata is never dropped by these entries; only the MEDIA payload is affected.",
        },
        "elf_inputs": pins,
        "deferred_to": DEFERRED_TO,
        "live_consumer_summary": {
            "dispositions": list(DISPOSITIONS),
            "occurrence_counts": {k: disposition_totals.get(k, 0) for k in DISPOSITIONS},
            "occurrence_counts_by_profile_kind": {
                kind: {k: by_kind[kind].get(k, 0) for k in DISPOSITIONS} for kind in kinds},
            "undecided_occurrences": undecided,
        },
        "class_table": class_table,
        "required_profile_exclusions": exclusions,
        "consumer_exclusions": {"path": EXCLUSION_FILE.relative_to(ROOT).as_posix(),
                                "sha256": sha(exclusion_bytes), "row_count": len(exclusions),
                                "loader": "tools/hcu_profile_consumer_exclusions.py"},
        "dropped_images": {"unit": "distinct 2D source images",
                           "decision_function": "tools/hcu_profile_consumer_exclusions.py decide_profile",
                           "non_2d_policy": "non-2D images are reported separately under the non-2D policy and are not counted here",
                           "per_profile": dict(sorted(dropped_by_profile.items())),
                           "per_kind": dict(sorted(dropped_by_kind.items())),
                           "total": sum(dropped_by_profile.values())},
        "linkage": qualification,
        "hcp_bitm_feed": qualification["_hcp_bitm_feed"],
        "inputs_sha256": dict(sorted(inputs.items())),
        "corpus": {"primary_directory": str(PRIMARY.relative_to(ROOT)),
                   "independent_rebuild_directory": str(REBUILD.relative_to(ROOT)),
                   "profile_count": len(profile_inventory),
                   "profiles": profile_inventory},
        "totals": {"included_2d_profile_occurrences": len(occurrences),
                   "unique_source_images": len(global_rows),
                   "role_occurrence_counts": dict(sorted(role_counts.items())),
                   "runtime_admitted_bitm_bindings": runtime_admitted_count,
                   "disposition_occurrence_counts": {k: disposition_totals.get(k, 0) for k in DISPOSITIONS}},
        "bsp_selections": bsp_evidence,
        "payloads": sorted(global_rows.values(), key=lambda x: (x["source_key"], x["path"], x["source_datum"], x["image_index"])),
        "source_pins": dict(sorted(report_pins.items())),
    }


def _without_counts(row: dict) -> dict:
    return {k: v for k, v in row.items() if k != "counts"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, default=PRIMARY)
    parser.add_argument("--rebuild", type=Path, default=REBUILD)
    parser.add_argument("--output", type=Path, default=REPORT)
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    report = audit(args.primary, args.rebuild)
    exclusion_bytes = exclusion_document(report["required_profile_exclusions"])
    if sha(exclusion_bytes) != report["consumer_exclusions"]["sha256"]:
        raise ValueError("exclusion document hash does not match the report")
    EXCLUSION_FILE.parent.mkdir(parents=True, exist_ok=True)
    EXCLUSION_FILE.write_bytes(exclusion_bytes)
    loaded = rules.load_exclusions(EXCLUSION_FILE)
    if loaded["sha256"] != report["consumer_exclusions"]["sha256"]:
        raise ValueError("written exclusion file does not load with the pinned hash")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"result": report["result"], "profiles": report["corpus"]["profile_count"],
                      "included_2d_profile_occurrences": report["totals"]["included_2d_profile_occurrences"],
                      "dispositions": report["totals"]["disposition_occurrence_counts"],
                      "exclusions": len(report["required_profile_exclusions"]),
                      "output": str(output)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
