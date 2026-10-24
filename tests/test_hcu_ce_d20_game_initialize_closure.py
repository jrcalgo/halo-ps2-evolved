"""Measure whether the real CE D20 game-init call path is safely linkable.

This is intentionally a blocker/inventory test, not a gameplay pass.  It roots
the production-compiled HCU objects at real CE entry points and refuses to
replace unresolved gameplay or machine boundaries with generated success stubs.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from build_toolchain import environment  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class HcuCeD20GameInitializeClosureTests(unittest.TestCase):
    def test_real_game_initialize_load_unload_closure_has_reviewable_blockers(self):
        build, prefix, env, _jobs = environment()
        source = build / "hcu-ps2-closure/all-no-bootstrap-memory"
        result_path = source / "result.json"
        response = source / "objects.rsp"
        if not result_path.is_file() or not response.is_file():
            self.skipTest("build the pinned full HCU PS2 closure first")

        result = json.loads(result_path.read_text())
        self.assertEqual(result.get("layer"), "all")
        self.assertGreater(result.get("compiled_count", 0), 300)
        linker = prefix / "ee/bin/mips64r5900el-ps2-elf-ld"
        nm = prefix / "ee/bin/mips64r5900el-ps2-elf-nm"
        objdump = prefix / "ee/bin/mips64r5900el-ps2-elf-objdump"
        for tool in (linker, nm, objdump):
            self.assertTrue(tool.is_file(), f"missing PS2 closure tool: {tool}")

        output = build / "hcu-m2-d20-game-init-closure"
        output.mkdir(parents=True, exist_ok=True)
        rooted = output / "game-init-load-unload-rooted.o"
        link_map = output / "game-init-load-unload.map"
        roots = (
            "game_initialize", "game_load", "game_unload", "game_map_loaded",
        )
        command = [
            str(linker), "-r", "--gc-sections",
            *[arg for root in roots for arg in ("-u", root)],
            "-Map=" + str(link_map), "@" + str(response), "-o", str(rooted),
        ]
        linked = subprocess.run(command, cwd=ROOT, env=env,
                                text=True, capture_output=True)
        (output / "link.log").write_text(linked.stdout + linked.stderr)
        self.assertEqual(linked.returncode, 0, linked.stdout + linked.stderr)

        undefined = {
            line.split()[-1]
            for line in subprocess.check_output(
                [str(nm), "-u", str(rooted)], text=True).splitlines()
            if line.split()
        }
        relocations = subprocess.check_output(
            [str(objdump), "-r", str(rooted)], text=True)
        callers: dict[str, set[str]] = {}
        current = ""
        for line in relocations.splitlines():
            match = re.match(r"RELOCATION RECORDS FOR \[(.+)\]:$", line.strip())
            if match:
                current = match.group(1)
                continue
            fields = line.split()
            if len(fields) >= 3 and fields[1].startswith("R_MIPS_"):
                symbol = fields[2].split("+", 1)[0]
                if symbol in undefined:
                    callers.setdefault(symbol, set()).add(current)

        # This list is a triage vocabulary only; no category grants approval.
        def category(symbol: str) -> str:
            if symbol.startswith(("DirectSound", "IDirectSound", "dsound_", "sound_cache_")):
                return "audio boundary"
            if symbol.startswith(("rasterizer_", "render_", "draw_", "structure_render_")):
                return "render boundary/state"
            if symbol.startswith(("network_", "coop_", "distributed_")):
                return "network/co-op behavior"
            if symbol in {"CreateThread", "CreateMutexA", "WaitForSingleObject",
                          "ReleaseMutex", "ResumeThread", "CloseHandle",
                          "SwitchToThread", "GetExitCodeThread"}:
                return "thread/synchronization boundary"
            if symbol.startswith(("CreateFile", "ReadFile", "WriteFile", "FindFirst",
                                  "FindNext", "CloseHandle", "GetFile", "SetFile",
                                  "DeleteFile", "CopyFile", "XCreateSave", "XFind",
                                  "XDeleteSave")) or symbol in {"CreateDirectoryA"}:
                return "file/storage boundary"
            if symbol.startswith("__"):
                return "compiler/runtime helper"
            if symbol.startswith(("XInput", "XDEVICE_", "XGet", "XInit")):
                return "input/platform boundary"
            if symbol.startswith(("physical_memory_", "cache_file_", "cache_files_",
                                  "ps2_cache_", "Global", "Local", "Virtual")):
                return "memory/cache boundary"
            return "other unresolved CE/platform dependency"

        member_sources = []
        for rel, unit in result.get("units", {}).items():
            if unit.get("status") != "compiled":
                continue
            obj = source / (rel.replace("/", "_") + ".o")
            if obj.is_file():
                member_sources.append((rel, obj))
        owners: dict[str, set[str]] = {}
        for rel, obj in member_sources:
            listing = subprocess.check_output(
                [str(nm), "--defined-only", str(obj)], text=True)
            for row in listing.splitlines():
                fields = row.split()
                if len(fields) >= 2 and fields[-2] in {
                    "t", "T", "w", "W", "d", "D", "r", "R", "b", "B",
                    "s", "S",
                }:
                    owners.setdefault(fields[-1], set()).add(rel)

        rows = []
        for symbol in sorted(callers):
            sections = sorted(callers[symbol])
            function_names = sorted({
                section[len(".text."):]
                for section in sections if section.startswith(".text.")
            })
            source_candidates = sorted({
                rel for function in function_names
                for name, rels in owners.items()
                if name == function or name.startswith(function + ".")
                for rel in rels
            })
            rows.append({
                "symbol": symbol,
                "triage_category": category(symbol),
                "caller_sections": sections,
                "caller_functions": function_names,
                "caller_source_candidates": source_candidates,
            })

        inventory = {
            "outcome": "blocked-unsafe-closure-no-adapters-added",
            "evidence_kind": "production-flags R5900 relocatable link; not host execution",
            "roots": list(roots),
            "source_layer": "all-no-bootstrap-memory",
            "source_result_sha256": sha256(result_path),
            "source_response_sha256": sha256(response),
            "rooted_object_sha256": sha256(rooted),
            "link_map_sha256": sha256(link_map),
            "hcu_commit": result.get("hcu_commit"),
            "manifest_sha256": result.get("manifest_sha256"),
            "prefix_sha256": result.get("prefix_sha256"),
            "compiled_source_count": result.get("compiled_count"),
            "undefined_symbol_table_count": len(undefined),
            "live_unresolved_symbol_count": len(rows),
            "category_counts": {},
            "live_unresolved_symbols": rows,
            "note": "Categories are search aids, never semantic approval. No unresolved symbol is replaced in this test.",
        }
        for row in rows:
            name = row["triage_category"]
            inventory["category_counts"][name] = inventory["category_counts"].get(name, 0) + 1
        inventory_path = output / "inventory.json"
        inventory_path.write_text(json.dumps(inventory, indent=2) + "\n")

        self.assertGreaterEqual(len(rows), 100,
                                "unexpectedly small closure: re-review root and object selection")
        symbols = {row["symbol"] for row in rows}
        for required in (
            "CreateThread", "CreateMutexA", "DirectSoundCreate",
            "rasterizer_present", "XCalculateSignatureBegin", "ReadFile",
        ):
            self.assertIn(required, symbols,
                          f"closure changed; re-audit before updating blocker report ({required})")
        self.assertEqual(inventory["outcome"],
                         "blocked-unsafe-closure-no-adapters-added")
        print(json.dumps({
            "status": "blocked-as-designed",
            "reason": "real CE initializer/load/unload closure has broad unresolved dependencies; no blanket adapters were introduced",
            "inventory": str(inventory_path),
            "sha256": sha256(inventory_path),
            "live_unresolved_symbol_count": len(rows),
            "category_counts": inventory["category_counts"],
        }, indent=2))


if __name__ == "__main__":
    unittest.main()
