"""Prove exact CE type declarations for overlap audit's family-only names.

These checks associate DWARF member names with source declarations. They do
not prove the tag bytes are semantically consumed or safe on target hardware.
"""
import json
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/reports/m2-step7-overlap-member-domain-audit-2026-10-22.json"

TYPE_SOURCES = {
    "render_lighting": ["submodules/halo-ce-universal/source/render/render.h"],
    "structure_background_sound_palette_entry": ["submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h"],
    "structure_cluster": ["submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h"],
    "structure_detail_object_data": ["submodules/halo-ce-universal/source/structures/structure_detail_objects.c"],
    "structure_fog_palette_entry": ["submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h"],
    "structure_material": ["submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h"],
    "structure_sound_environment_palette_entry": ["submodules/halo-ce-universal/source/structures/structure_bsp_definitions.h"],
    "structure_weather_palette_entry": [
        "submodules/halo-ce-universal/source/scenario/wind.c",
        "submodules/halo-ce-universal/source/effects/weather_particle_systems.c",
    ],
}


def struct_body(source: str, name: str) -> str:
    match = re.search(r"\bstruct\s+" + re.escape(name) + r"\s*\{", source)
    if not match:
        return ""
    start = match.end()
    depth = 1
    for i in range(start, len(source)):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i]
    return ""


class Step7OverlapExactMemberDeclarationsTest(unittest.TestCase):
    def test_family_only_names_have_exact_type_declarations(self):
        audit = json.loads(AUDIT.read_text())
        rows = {r["definition"]: r for r in audit["rows"]}
        family_only = [
            (r["definition"], m["member"])
            for r in audit["rows"] for m in r["members"]
            if m["source_access_classification"] == "no_exact_member_spelling_found_family_type_association_only"
        ]
        self.assertEqual(len(family_only), 18)
        unresolved = {("structure_detail_object_data", "reserved18")}
        checked = set()
        for type_name, member in family_only:
            if (type_name, member) in unresolved:
                continue
            self.assertIn(type_name, TYPE_SOURCES, type_name)
            bodies = [struct_body((ROOT / p).read_text(errors="replace"), type_name)
                      for p in TYPE_SOURCES[type_name]]
            bodies = [b for b in bodies if b]
            self.assertTrue(bodies, f"no source declaration for struct {type_name}")
            # Names must occur as declarators in the exact type body; byte-sized
            # arrays are accepted because their disposition is retention only.
            decl = re.compile(r"\b" + re.escape(member) + r"(?:\s*\[[^]]+\])?\s*;")
            self.assertTrue(any(decl.search(body) for body in bodies),
                            f"{type_name}.{member} lacks exact declaration")
            checked.add((type_name, member))
        self.assertEqual(len(checked), 17)
        self.assertEqual(unresolved, {("structure_detail_object_data", "reserved18")})

    def test_duplicate_weather_layout_is_size_pinned_and_semantics_stay_open(self):
        audit = json.loads(AUDIT.read_text())
        weather = next(r for r in audit["rows"] if r["definition"] == "structure_weather_palette_entry")
        self.assertTrue(all(m["semantic_disposition"] == "open" for m in weather["members"]))
        for path in TYPE_SOURCES["structure_weather_palette_entry"]:
            src = (ROOT / path).read_text()
            self.assertIn("sizeof(struct structure_weather_palette_entry) == 0xF0", src)
        wind = (ROOT / TYPE_SOURCES["structure_weather_palette_entry"][0]).read_text()
        self.assertIn("offsetof(struct structure_weather_palette_entry, wind) == 0x80", wind)
        self.assertIn("offsetof(struct structure_weather_palette_entry, wind_direction) == 0x90", wind)


if __name__ == "__main__":
    unittest.main()
