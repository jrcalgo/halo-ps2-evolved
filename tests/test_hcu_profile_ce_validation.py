"""Run imported C1 CTAG bytes through the PS2 C parser and CE tag validator."""
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import re
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HCU = ROOT / "submodules/halo-ce-universal"
ARTIFACTS = Path(os.environ.get("HCU_C1_CE_ARTIFACTS", ROOT / "build/m2-c1-ce-validation")).resolve()


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path):
    path = Path(path).resolve()
    try:
        display = path.relative_to(ROOT).as_posix()
    except ValueError:
        display = path.as_posix()
    return {"path": display, "sha256": _sha(path)}


def _extract_ce_chunk(package_path, manifest_path, output_path):
    from tools import hcu_profile_chunks

    package = package_path.read_bytes()
    manifest = json.loads(manifest_path.read_text())
    if _sha(package_path) != manifest["package_sha256"]:
        raise ValueError("HCP package pin mismatch")
    magic, version, hsize, _profile_id, count, directory, dsize, total = hcu_profile_chunks.HEADER.unpack_from(package)
    assert hsize == hcu_profile_chunks.HEADER.size and total == len(package)
    if (magic, version) == (hcu_profile_chunks.MAGIC_V1, 1):
        record = hcu_profile_chunks.V1_RECORD
        logical = {}
        for i in range(count):
            kind, chunk_id, offset, size, digest = record.unpack_from(package, directory + i * record.size)
            payload = package[offset:offset + size]
            assert hashlib.sha256(payload).digest() == digest
            logical[(kind, chunk_id)] = payload
    else:
        assert (magic, version) == (hcu_profile_chunks.MAGIC, 2)
        from tools.hcu_profile_validate import parse_package
        logical = parse_package(package, expected_package_sha256=_sha(package_path),
                                expected_profile_id=manifest["validation"]["profile_id"])["chunks"]
    payload = logical[(1, 0)]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(payload)
    return payload


def _inputs():
    c1_profiles = ROOT / os.environ.get("HCU_C1_PROFILES", "build/m2-c1-corpus-primary-v3")
    ui_package = Path(os.environ.get("HCU_C1_UI_PACKAGE", c1_profiles / "ui.hcp"))
    ui_manifest = Path(os.environ.get("HCU_C1_UI_MANIFEST", c1_profiles / "ui.json"))
    survival_diagnostic = Path(os.environ.get("HCU_C1_SURVIVAL_DIAGNOSTIC",
        ROOT / "build/c3/c3-fplod/audit/survival-diag-2026-10-25-r2/survival-beavercreek.failure.json"))
    survival_ctag = Path(os.environ.get("HCU_C1_SURVIVAL_CTAG",
        ROOT / "build/c3/c3-fplod/audit/survival-diag-2026-10-25-r2/survival-beavercreek.unadmitted.ctag"))
    assert ui_package.is_file() and ui_manifest.is_file()
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    ui_ctag = ARTIFACTS / "ui.ctag"
    ui_payload = _extract_ce_chunk(ui_package, ui_manifest, ui_ctag)
    survival_out = ARTIFACTS / "survival-beavercreek.ctag"
    survival_package = os.environ.get("HCU_C1_SURVIVAL_PACKAGE")
    survival_manifest = None
    if survival_package:
        survival_package = Path(survival_package)
        survival_manifest = Path(os.environ.get("HCU_C1_SURVIVAL_MANIFEST",
                                               survival_package.with_suffix('.json')))
        _extract_ce_chunk(survival_package, survival_manifest, survival_out)
        diagnostic = json.loads(survival_manifest.read_text())
    else:
        assert survival_diagnostic.is_file() and survival_ctag.is_file()
        if not survival_out.exists() or _sha(survival_out) != _sha(survival_ctag):
            survival_out.write_bytes(survival_ctag.read_bytes())
        diagnostic = json.loads(survival_diagnostic.read_text())
        assert _sha(survival_ctag) == diagnostic["unadmitted_ctag_sha256"]
    ui_manifest_data = json.loads(ui_manifest.read_text())
    ui_map = ROOT / ui_manifest_data["source_maps"]["ui"]["path"]
    assert _sha(ui_map) == ui_manifest_data["source_maps"]["ui"]["sha256"]
    for row in diagnostic["source_maps"].values():
        assert _sha(ROOT / row["path"]) == row["sha256"]
    schema_elf = Path(os.environ.get("HCU_C1_SCHEMA_ELF",
        ROOT / "build/hcu-ps2-closure/all-no-bootstrap-memory/halo-local.elf"))
    assert _sha(schema_elf) == ui_manifest_data["schema_elf_sha256"]
    assert _sha(schema_elf) == diagnostic["schema_elf_sha256"]
    survival_lengths = [
        (ROOT / row["path"]).stat().st_size
        for row in diagnostic["source_maps"].values()
    ]
    return {
        "ui_ctag": ui_ctag,
        "ui_ctag_sha256": hashlib.sha256(ui_payload).hexdigest(),
        "ui_file_length": ui_map.stat().st_size,
        "ui_source_map_sha256": _sha(ui_map),
        "ui_package_sha256": _sha(ui_package),
        "ui_schema_elf_sha256": ui_manifest_data["schema_elf_sha256"],
        "survival_ctag": survival_out,
        "survival_ctag_sha256": _sha(survival_out),
        "survival_file_length": max(survival_lengths),
        "survival_source_map_pins": diagnostic["source_maps"],
        "survival_diagnostic_sha256": _sha(survival_diagnostic) if not survival_package else None,
        "survival_package_sha256": _sha(survival_package) if survival_package else None,
        "survival_manifest_sha256": _sha(survival_manifest) if survival_manifest else None,
        "ui_manifest_sha256": _sha(ui_manifest),
        "survival_schema_elf_sha256": diagnostic["schema_elf_sha256"],
    }


def _compile_fixture(host_capacity=False):
    sys.path.insert(0, str(ROOT / "tools"))
    from host_abi32 import flags as host_abi32_flags

    compiler = shutil.which("gcc-13") or shutil.which("gcc")
    if not compiler:
        pytest.skip("GCC unavailable for PS2 CE validator ILP32 fixture")
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    semantics = ARTIFACTS / "halo_ps2_msvc_semantics.h"
    generated = subprocess.run([
        sys.executable, str(HCU / "tools/linux_msvc_semantics.py"),
        "--output", str(semantics), "--all-inlines",
        "--tags", str(HCU / "source"), "--inlines", str(HCU / "source"),
        "--inlines", str(HCU / "port/include/xdk"),
    ], capture_output=True, text=True)
    assert generated.returncode == 0, generated.stdout + generated.stderr
    includes = [
        ROOT / "tests", HCU / "port/ps2/include", HCU / "port/linux/game",
        HCU / "port/include", HCU / "source", HCU / "source/cseries",
        HCU / "source/cache", HCU / "source/tag_files", HCU / "source/math",
        HCU / "source/structures", HCU / "source/render", HCU / "source/bitmaps",
        Path("/usr/include"),
    ]
    prefix = (ROOT / "tests/hcu_profile_ce_validation_host_capacity_prefix.h"
              if host_capacity else ROOT / "tests/hcu_scenario_host32_prefix.h")
    exe_name = "hcu-profile-ce-validation-host64m" if host_capacity else "hcu-profile-ce-validation"
    command = [compiler, *host_abi32_flags(), "-std=gnu99", "-fms-extensions",
               "-fshort-wchar", "-fcommon", "-fwrapv", "-ffunction-sections",
               "-fdata-sections", "-fno-strict-aliasing", "-fno-delete-null-pointer-checks",
               "-no-pie", "-include", str(prefix),
               "-include", str(semantics), "-w"]
    command.extend("-I" + str(p) for p in includes)
    schema = HCU / "port/linux/game"
    port = HCU / "port/ps2"
    validator_source = schema / "tag_validate.c"
    effects_source = schema / "tag_schema_effects.c"
    if host_capacity:
        # The checked-in validator deliberately caps per-correction logging at
        # 64. The diagnostic build raises only that test copy's print cap so
        # category counts can be recovered from named runtime normalizers.
        instrumented = ARTIFACTS / "tag_validate_host_instrumented.c"
        source_text = validator_source.read_text()
        needle = "MAXIMUM_LOGGED_CORRECTIONS = 64,"
        assert source_text.count(needle) == 1
        helper = r'''
static boolean hcu_test_run_check(struct tag_validation *validation,
	struct tag_schema_field const *field, byte *base, long size)
{
	byte *before = malloc((size_t)size);
	const char *path = getenv("HCU_VALIDATOR_CHECK_DELTA_PATH");
	static int empty_name_reported;
	boolean result;
	long i;
	if (!before) return FALSE;
	if (!empty_name_reported)
	{
		fprintf(stderr, "ceval-step=empty-name address=%p value=%s\n",
			(void *)tag_validate_empty_name, tag_validate_empty_name);
		empty_name_reported = 1;
	}
	memcpy(before, base, (size_t)size);
	result = field->check(validation, base);
	if (path && *path)
	{
		FILE *out = fopen(path, "a");
		if (out)
		{
			for (i = 0; i < size; )
			{
				long start, end, j;
				if (before[i] == base[i]) { i++; continue; }
				start = i;
				while (i < size && before[i] != base[i]) i++;
				end = i;
				fprintf(out, "%ld\t%s\t%lu\t%ld\t", validation->tag_index,
					field->name, (unsigned long)(base - validation->region), start);
				for (j = start; j < end; j++) fprintf(out, "%02x", before[j]);
				fputc('\t', out);
				for (j = start; j < end; j++) fprintf(out, "%02x", base[j]);
				fputc('\n', out);
			}
			fclose(out);
		}
	}
	free(before);
	return result;
}

static void hcu_test_log_field(struct tag_validation *validation,
	struct tag_schema_field const *field, byte *address,
	byte const *before, long size)
{
	const char *path = getenv("HCU_VALIDATOR_FIELD_DELTA_PATH");
	FILE *out;
	long i;
	if (!path || !*path) return;
	out = fopen(path, "a");
	if (!out) return;
	for (i = 0; i < size; )
	{
		long start, end, j;
		long before_index = NONE, after_index = NONE;
		if (before[i] == address[i]) { i++; continue; }
		start = i;
		while (i < size && before[i] != address[i]) i++;
		end = i;
		if (field->type == _tag_schema_reference && size >= sizeof(struct tag_reference))
		{
			memcpy(&before_index, before + offsetof(struct tag_reference, index), sizeof(before_index));
			memcpy(&after_index, address + offsetof(struct tag_reference, index), sizeof(after_index));
		}
		fprintf(out, "%ld\t%s\t%d\t%lu\t%ld\t%ld\t%ld\t", validation->tag_index,
			field->name, field->type, (unsigned long)(address - validation->region), start,
			before_index, after_index);
		for (j = start; j < end; j++) fprintf(out, "%02x", before[j]);
		fputc('\t', out);
		for (j = start; j < end; j++) fprintf(out, "%02x", address[j]);
		fputc('\n', out);
	}
	fclose(out);
}
'''
        source_text = source_text.replace(needle, "MAXIMUM_LOGGED_CORRECTIONS = 100000,")
        source_text = source_text.replace("#include <stdio.h>", "#include <stdio.h>\n#include <stdlib.h>")
        anchor = "} tag_validate_globals;"
        assert source_text.count(anchor) == 1
        source_text = source_text.replace(anchor,
            anchor + "\nstatic char const tag_validate_empty_name[];\n"
            "typedef char hcu_tag_reference_name_offset[offsetof(struct tag_reference, name) == 4 ? 1 : -1];\n"
            "typedef char hcu_tag_reference_index_offset[offsetof(struct tag_reference, index) == 12 ? 1 : -1];\n"
            "typedef char hcu_tag_reference_size[sizeof(struct tag_reference) == 16 ? 1 : -1];\n" + helper)
        call = "!field->check(validation, base)"
        assert source_text.count(call) == 1
        source_text = source_text.replace(call,
            "!hcu_test_run_check(validation, field, base, definition->size)")
        field_anchor = "\t\t\tbyte *address = base + field->offset + index * field->size;\n"
        assert source_text.count(field_anchor) == 1
        source_text = source_text.replace(field_anchor, field_anchor +
            "\t\t\tbyte hcu_field_before[1024];\n"
            "\t\t\tboolean hcu_field_track = field->type != _tag_schema_struct && "
            "field->type != _tag_schema_check && field->size > 0 && field->size <= sizeof(hcu_field_before);\n"
            "\t\t\tif (hcu_field_track) memcpy(hcu_field_before, address, field->size);\n")
        switch_end = "\t\t\t}\n\t\t}\n\t}\n\tvalidation->structure = structure;"
        assert source_text.count(switch_end) == 1
        source_text = source_text.replace(switch_end,
            "\t\t\t}\n"
            "\t\t\tif (hcu_field_track) hcu_test_log_field(validation, field, address, hcu_field_before, field->size);\n"
            "\t\t}\n\t}\n\tvalidation->structure = structure;")
        instrumented.write_text(source_text)
        validator_source = instrumented
        effects_instrumented = ARTIFACTS / "tag_schema_effects_host_instrumented.c"
        effects_text = effects_source.read_text()
        logger = r'''
static void hcu_test_log_sound_owner(void *address, unsigned long before,
	unsigned long after)
{
	const char *path = getenv("HCU_SOUND_FIXUP_PATH");
	FILE *out;
	if (!path || !*path || before == after) return;
	out = fopen(path, "a");
	if (!out) return;
	fprintf(out, "%p\t%08lx\t%08lx\n", address, before, after);
	fclose(out);
}
'''
        effects_text = effects_text.replace(
            "#include <string.h>", "#include <string.h>\n#include <stdio.h>\n#include <stdlib.h>\n" + logger)
        for member in ("unknown2", "unknown3"):
            assignment = f"permutation->{member} = (unsigned long)tag_index;"
            assert effects_text.count(assignment) == 1
            effects_text = effects_text.replace(assignment,
                f"hcu_test_log_sound_owner(&permutation->{member}, permutation->{member}, (unsigned long)tag_index);\n\t\t\t\t{assignment}")
        effects_text += r'''
typedef char hcu_sound_unknown2_offset[offsetof(struct sound_permutation, unknown2) == 52 ? 1 : -1];
typedef char hcu_sound_unknown3_offset[offsetof(struct sound_permutation, unknown3) == 60 ? 1 : -1];
'''
        effects_instrumented.write_text(effects_text)
        models_instrumented = ARTIFACTS / "tag_schema_models_host_instrumented.c"
        models_text = (schema / "tag_schema_models.c").read_text()
        models_text += r'''
typedef char hcu_model_triangle_hardware_offset[offsetof(struct model_geometry_part,
	triangle_buffer.hardware_format) == 80 ? 1 : -1];
typedef char hcu_model_vertex_hardware_offset[offsetof(struct model_geometry_part,
	vertex_buffer.hardware_format) == 100 ? 1 : -1];
typedef char hcu_model_part_size[sizeof(struct model_geometry_part) == 0x68 ? 1 : -1];
'''
        models_instrumented.write_text(models_text)
    command.extend([
        "-Wl,--gc-sections",
        str(ROOT / "tests/hcu_profile_ce_validation_main.c"),
        str(validator_source),
        str(port / "src/ps2_ctag.c"), str(port / "src/ps2_cache.c"),
        str(port / "src/ps2_cbsp.c"),
        *[str(effects_instrumented) if host_capacity and name == "effects"
          else str(models_instrumented) if host_capacity and name == "models"
          else str(schema / f"tag_schema_{name}.c") for name in (
            "groups", "collision", "models", "objects", "render", "effects", "scenario")],
        "-o", str(ARTIFACTS / exe_name),
    ])
    built = subprocess.run(command, capture_output=True, text=True)
    (ARTIFACTS / ("compile-host64m.log" if host_capacity else "compile.log")).write_text("$ " + " ".join(command) + "\n" + built.stdout + built.stderr)
    assert built.returncode == 0, built.stdout + built.stderr
    return compiler, command


def _audit_host_validation(host_process, callback_delta_path, field_delta_path,
                           sound_fixup_path, delta_path, audit_path):
    """Attribute every mutated byte to the compiled validator mutation sites."""
    callback_counts = Counter(re.findall(
        r"([A-Za-z0-9_]+_check)\b", host_process.stderr))
    deltas = json.loads(delta_path.read_text())
    callback_delta_rows = []
    for line in callback_delta_path.read_text().splitlines():
        tag_index, callback, base_offset, structure_offset, before_hex, after_hex = line.split("\t")
        callback_delta_rows.append({
            "tag_index": int(tag_index), "callback": callback,
            "offset": int(base_offset) + int(structure_offset),
            "structure_offset": int(structure_offset),
            "before_hex": before_hex, "after_hex": after_hex,
        })
    callback_delta_categories = Counter(row["callback"] for row in callback_delta_rows)
    # Every byte touched by tag_validate_tags must have been changed inside a
    # named schema callback. Verify its original and normalized values too.
    callback_bytes = {}
    check_bytes = {}
    field_bytes = {}
    for row in callback_delta_rows:
        before_bytes = bytes.fromhex(row["before_hex"])
        after_bytes = bytes.fromhex(row["after_hex"])
        for offset, before_byte, after_byte in zip(
                range(row["offset"], row["offset"] + len(before_bytes)),
                before_bytes, after_bytes):
            callback_bytes.setdefault(offset, set()).add((before_byte, after_byte))
            check_bytes.setdefault(offset, set()).add((before_byte, after_byte))
    field_delta_rows = []
    for line in field_delta_path.read_text().splitlines():
        tag_index, field_name, field_type, base_offset, structure_offset, before_index, after_index, before_hex, after_hex = line.split("\t")
        field_delta_rows.append({
            "tag_index": int(tag_index), "field": field_name,
            "field_type": int(field_type),
            "offset": int(base_offset) + int(structure_offset),
            "structure_offset": int(structure_offset),
            "before_index": int(before_index), "after_index": int(after_index),
            "before_hex": before_hex, "after_hex": after_hex,
        })
    field_delta_categories = Counter(row["field"] for row in field_delta_rows)
    for row in field_delta_rows:
        before_bytes = bytes.fromhex(row["before_hex"])
        after_bytes = bytes.fromhex(row["after_hex"])
        for offset, before_byte, after_byte in zip(
                range(row["offset"], row["offset"] + len(before_bytes)),
                before_bytes, after_bytes):
            callback_bytes.setdefault(offset, set()).add((before_byte, after_byte))
            field_bytes.setdefault(offset, set()).add((before_byte, after_byte))
    sound_fixup_rows = []
    sound_byte_pairs = {}
    host_base_match = re.search(r"host-materialize base=0x([0-9a-fA-F]+)", host_process.stderr)
    assert host_base_match
    host_base = int(host_base_match.group(1), 16)
    empty_name_match = re.search(r"empty-name address=0x([0-9a-fA-F]+) value=", host_process.stderr)
    assert empty_name_match
    empty_name_address = int(empty_name_match.group(1), 16)
    empty_name_bytes = empty_name_address.to_bytes(4, "little")
    for line in sound_fixup_path.read_text().splitlines():
        address, before_hex, after_hex = line.split("\t")
        offset = int(address, 16) - host_base
        before_bytes = int(before_hex, 16).to_bytes(4, "little")
        after_bytes = int(after_hex, 16).to_bytes(4, "little")
        sound_fixup_rows.append((offset, before_bytes, after_bytes))
        for i, (before_byte, after_byte) in enumerate(zip(before_bytes, after_bytes)):
            callback_bytes.setdefault(offset + i, set()).add((before_byte, after_byte))
            sound_byte_pairs.setdefault(offset + i, set()).add((before_byte, after_byte))
    changed_bytes_verified = 0
    attribution = Counter()
    for row in deltas["spans"]:
        before_bytes = bytes.fromhex(row["before_hex"])
        after_bytes = bytes.fromhex(row["after_hex"])
        for i, pair in enumerate(zip(before_bytes, after_bytes)):
            assert pair in callback_bytes.get(row["offset"] + i, set())
            offset = row["offset"] + i
            if pair in sound_byte_pairs.get(offset, set()):
                attribution["sound_owner_index_fixups"] += 1
            elif pair in check_bytes.get(offset, set()):
                attribution["schema_check_callbacks"] += 1
            elif pair in field_bytes.get(offset, set()):
                attribution["typed_schema_field_validation"] += 1
            else:
                raise AssertionError(f"unattributed validator mutation at image byte {offset}")
            changed_bytes_verified += 1
    callback_audit = {
        "callback_delta_span_counts": dict(sorted(callback_delta_categories.items())),
        "field_delta_span_counts": dict(sorted(field_delta_categories.items())),
        "callback_delta_bytes": sum(len(bytes.fromhex(row["before_hex"])) for row in callback_delta_rows),
        "whole_image_delta_bytes_verified": changed_bytes_verified,
        "whole_image_delta_bytes": deltas["changed_bytes"],
        "all_byte_deltas_attributed_to_validator_mutation_sites": changed_bytes_verified == deltas["changed_bytes"],
        "sound_owner_index_field_writes": len(sound_fixup_rows),
        "byte_attribution": dict(sorted(attribution.items())),
        "null_reference_name_pointer_repairs": sum(
            row["field_type"] == 3 and row["structure_offset"] == 4 and
            row["before_index"] == -1 and row["after_index"] == -1 and
            row["before_hex"] == "00000000" and row["after_hex"] == empty_name_bytes.hex()
            for row in field_delta_rows),
        "null_reference_name_repairs_match_compiled_empty_name_pointer": all(
            row["field_type"] == 3 and row["structure_offset"] == 4 and
            row["before_index"] == -1 and row["after_index"] == -1
            for row in field_delta_rows
            if row["before_hex"] == "00000000" and row["after_hex"] == empty_name_bytes.hex()),
        "compiled_empty_name_pointer": hex(empty_name_address),
        "model_geometry_changed_bytes_within_compiled_hardware_format_fields": all(
            row["callback"] != "model_geometry_part_check" or
            any(start <= row["structure_offset"] and
                row["structure_offset"] + len(bytes.fromhex(row['before_hex'])) <= end
                for start, end in ((80, 84), (100, 104)))
            for row in callback_delta_rows),
        "model_geometry_correction_messages": sum(
            value for key, value in callback_counts.items() if key == "model_geometry_part_check"),
        "model_geometry_hardware_format_changed_bytes": sum(
            len(bytes.fromhex(row["before_hex"])) for row in callback_delta_rows
            if row["callback"] == "model_geometry_part_check"),
    }
    audit_path.write_text(
        json.dumps(callback_audit, indent=2) + "\n")
    return callback_counts, deltas, callback_audit


def test_actual_ui_and_survival_ctags_use_ps2_c_validator_and_owner_lifetime():
    pins = _inputs()
    compiler, command = _compile_fixture()
    exe = ARTIFACTS / "hcu-profile-ce-validation"
    results = {}
    runs = {}
    for profile in ("ui", "survival-beavercreek"):
        ctag_path = pins["ui_ctag"] if profile == "ui" else pins["survival_ctag"]
        file_length = pins["ui_file_length"] if profile == "ui" else pins["survival_file_length"]
        run_command = [str(exe), str(ctag_path), profile, str(file_length)]
        process = subprocess.run(run_command,
                                 capture_output=True, text=True)
        if process.returncode in (-31, 159):
            pytest.skip("sandbox blocks native ILP32 C validator execution with SIGSYS")
        stdout, stderr = process.stdout, process.stderr
        log = ARTIFACTS / f"{profile}.log"
        log.write_text(stdout + stderr)
        assert process.returncode == 0, stdout + stderr
        key = "ui" if profile == "ui" else "survival"
        results[key] = stdout.strip()
        runs[key] = {"command": run_command, "returncode": process.returncode,
                     "package_sha256": pins[key + '_package_sha256'],
                     "ctag_sha256": pins[key + '_ctag_sha256'], "log": _artifact(log)}
    _, host_command = _compile_fixture(host_capacity=True)
    host_exe = ARTIFACTS / "hcu-profile-ce-validation-host64m"
    callback_delta_path = ARTIFACTS / "survival-beavercreek-callback-deltas.tsv"
    callback_delta_path.unlink(missing_ok=True)
    field_delta_path = ARTIFACTS / "survival-beavercreek-field-deltas.tsv"
    field_delta_path.unlink(missing_ok=True)
    sound_fixup_path = ARTIFACTS / "survival-beavercreek-sound-owner-fixups.tsv"
    sound_fixup_path.unlink(missing_ok=True)
    for path in (callback_delta_path, field_delta_path, sound_fixup_path):
        path.touch()
    host_env = os.environ.copy()
    host_env["HCU_VALIDATOR_CHECK_DELTA_PATH"] = str(callback_delta_path)
    host_env["HCU_VALIDATOR_FIELD_DELTA_PATH"] = str(field_delta_path)
    host_env["HCU_SOUND_FIXUP_PATH"] = str(sound_fixup_path)
    host_run_command = [str(host_exe), str(pins["survival_ctag"]), "survival-beavercreek",
         str(pins["survival_file_length"]), str(64 * 1024 * 1024),
         str(ARTIFACTS / "survival-beavercreek-validation-deltas.json")]
    host_process = subprocess.run(host_run_command,
        capture_output=True, text=True, timeout=300, env=host_env)
    if host_process.returncode in (-31, 159):
        pytest.skip("sandbox blocks host-capacity native ILP32 C validator execution with SIGSYS")
    (ARTIFACTS / "survival-beavercreek-host64m.log").write_text(
        host_process.stdout + host_process.stderr)
    assert host_process.returncode == 0, host_process.stdout + host_process.stderr
    runs['survival_host_oversized_diagnostic'] = {
        'command': host_run_command, 'returncode': host_process.returncode,
        'package_sha256': pins['survival_package_sha256'],
        'ctag_sha256': pins['survival_ctag_sha256'],
        'log': _artifact(ARTIFACTS / 'survival-beavercreek-host64m.log')}
    results["survival_host_oversized_diagnostic"] = host_process.stdout.strip()
    delta_path = ARTIFACTS / "survival-beavercreek-validation-deltas.json"
    callback_counts, deltas, callback_audit = _audit_host_validation(
        host_process, callback_delta_path, field_delta_path, sound_fixup_path,
        delta_path, ARTIFACTS / "survival-beavercreek-callback-delta-audit.json")
    results["survival_host_oversized_correction_callbacks"] = dict(sorted(callback_counts.items()))
    results["survival_host_oversized_changed_bytes"] = {
        "changed_bytes": deltas["changed_bytes"],
        "span_count": deltas["span_count"],
        "record": _artifact(delta_path)['path'],
    }
    results["survival_host_oversized_callback_delta_audit"] = callback_audit
    metadata = {
        "format": "hcu-c1-ce-native-validation-v1",
        "runtime_admitted": False,
        "validator": "submodules/halo-ce-universal/port/linux/game/tag_validate.c:tag_validate_tags",
        "ctag_parser": "submodules/halo-ce-universal/port/ps2/src/ps2_ctag.c:ps2_ctag_open/ps2_ctag_rebase_in_place (target), ps2_ctag_materialize (host oversized diagnostic)",
        "target_tag_cache_capacity_bytes": 2 * 1024 * 1024,
        "artifact_directory": str(ARTIFACTS),
        "survival_host_image_bytes": deltas['image_size'],
        "host_62mb_storage_is_ee_capacity_evidence": False,
        "host_oversized_capacity_bytes": 64 * 1024 * 1024,
        "host_oversized_execution": "test-only ILP32 provider override and claims buffer; no production arena change",
        "host_correction_logging": "test-only copy of validator with 100000 report cap; repository source unchanged",
        "pins": {
            "ui_package_sha256": pins["ui_package_sha256"],
            "ui_manifest_sha256": pins["ui_manifest_sha256"],
            "ui_ctag_sha256": pins["ui_ctag_sha256"],
            "ui_source_map_sha256": pins["ui_source_map_sha256"],
            "ui_schema_elf_sha256": pins["ui_schema_elf_sha256"],
            "survival_ctag_sha256": pins["survival_ctag_sha256"],
            "survival_diagnostic_sha256": pins["survival_diagnostic_sha256"],
            "survival_package_sha256": pins["survival_package_sha256"],
            "survival_manifest_sha256": pins["survival_manifest_sha256"],
            "survival_schema_elf_sha256": pins["survival_schema_elf_sha256"],
            "survival_source_maps": pins["survival_source_map_pins"],
        },
        "implementation_source_pins": {
            str(path.relative_to(ROOT)): _sha(path)
            for path in [
                HCU / "port/ps2/src/ps2_ctag.c",
                HCU / "port/ps2/src/ps2_cache.c",
                HCU / "port/linux/game/tag_validate.c",
                *[HCU / "port/linux/game" / f"tag_schema_{name}.c" for name in (
                    "groups", "collision", "models", "objects", "render", "effects", "scenario")],
                ROOT / "tests/hcu_profile_ce_validation_main.c",
                ROOT / "tests/hcu_profile_ce_validation_host_capacity_prefix.h",
                ROOT / "tests/test_hcu_profile_ce_validation.py",
            ]
        },
        "host_instrumented_validator_copy_sha256": _sha(ARTIFACTS / "tag_validate_host_instrumented.c"),
        "host_instrumented_effects_copy_sha256": _sha(ARTIFACTS / "tag_schema_effects_host_instrumented.c"),
        "host_instrumented_models_copy_sha256": _sha(ARTIFACTS / "tag_schema_models_host_instrumented.c"),
        "executables": {"target": _artifact(exe), "host": _artifact(host_exe)},
        "generated_sources": {name: _artifact(ARTIFACTS / name) for name in (
            'halo_ps2_msvc_semantics.h', 'tag_validate_host_instrumented.c',
            'tag_schema_effects_host_instrumented.c', 'tag_schema_models_host_instrumented.c')},
        "mutation_artifacts": {path.name: _artifact(path) for path in (
            callback_delta_path, field_delta_path, sound_fixup_path, delta_path,
            ARTIFACTS / 'survival-beavercreek-callback-delta-audit.json')},
        "runs": runs,
        "compile_command": command,
        "host_compile_command": host_command,
        "results": results,
        "logs": {key: row['log']['path'] for key, row in runs.items()},
    }
    (ARTIFACTS / "result.json").write_text(json.dumps(metadata, indent=2) + "\n")
    assert "ctag=ok" in results["ui"]
    assert "validator=accepted" in results["ui"]
    assert "corrupt_schema_rejected=1" in results["ui"]
    assert "pointers_stable=1 owner_unpublished=1 released_after_unmount=1" in results["ui"]
    assert re.search(r'corrections=\d+', results['ui'])
    assert "ctag=ok" in results["survival"]
    assert "validator=rejected" in results["survival"]
    assert "mount=0" in results["survival"]
    assert "capacity=2097152" in results["survival"]
    assert "capacity=2097152" in results["survival"]
    assert "capacity=67108864" in results["survival_host_oversized_diagnostic"]
    assert "validator=" in results["survival_host_oversized_diagnostic"]
    assert callback_audit["all_byte_deltas_attributed_to_validator_mutation_sites"]
    assert callback_audit["null_reference_name_repairs_match_compiled_empty_name_pointer"]
    assert callback_audit["model_geometry_changed_bytes_within_compiled_hardware_format_fields"]
    assert callback_audit["sound_owner_index_field_writes"] == 2 * callback_counts["sound_check"]
    host_correction_match = re.search(r"corrections=(\d+)", results["survival_host_oversized_diagnostic"])
    assert host_correction_match and sum(callback_counts.values()) == int(host_correction_match.group(1))
    assert deltas["span_count"] > 0 and deltas["changed_bytes"] > 0

