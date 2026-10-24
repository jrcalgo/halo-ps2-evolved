#!/usr/bin/env python3
"""Build a provenance-bound table of guarded C2 owner measurements by profile.

This tool deliberately separates actual guest counters from package/fixture
floors. Missing or incomplete guest evidence is represented as unmeasured.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OWNER = re.compile(r"HALO_PS2_LOCAL owner-telemetry phase=(\S+) name=(\S+) kind=(\S+) parent=(\S+) bound=(\d+) cap=(\d+) used=(\d+) high=(\d+) failures=(\d+) resets=(\d+)")
CACHE = re.compile(r"HALO_PS2_LOCAL cache-owner phase=(\S+) name=(\S+) current=(\d+) peak=(\d+).*?failures=(\d+).*?resets=(\d+)")
ARENA = re.compile(r"HALO_PS2_LOCAL arena name=(\S+).*?cap=(\d+) used=(\d+) high=(\d+).*?alloc_failures=(\d+) resets=(\d+)")
REQUIRED = ("partition-selected", "profile-runtime", "owner-telemetry", "cache-owner", "arena",
            "render-storage-bound", "map-lifecycle")
OWNER_NAMES = ("game_state", "object_pool", "actor_pool", "widget_pool", "dynamic_simulation", "tags", "bsp",
               "render_chunks", "render_texture", "streaming", "scratch", "dma", "audio_requests")


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_run(path, run_name=None):
    if not path or not path.exists():
        return None
    data = json.loads(path.read_text())
    runs = data.get("runs", []) if isinstance(data, dict) else []
    if run_name:
        selected = next((r for r in runs if r.get("run") == run_name), None)
    else:
        selected = runs[0] if runs else data
    if selected is None:
        return None
    inherited = {k:v for k,v in data.items() if k != "runs"}
    return {**inherited, **selected}


def extract(run, run_path):
    result = {"provenance": None, "complete": False, "blocker": "run result missing",
              "identity": None}
    if run is None:
        return result
    logp = Path(run.get("log", ""))
    if not logp.is_absolute():
        logp = ROOT / logp
    lines = []
    if logp.is_file():
        lines = logp.read_text(errors="replace").splitlines()
    elif run.get("halo_lines_saved"):
        lp = Path(run["halo_lines_saved"])
        if not lp.is_absolute(): lp = ROOT / lp
        if lp.is_file(): lines = lp.read_text(errors="replace").splitlines()
    owners, caches, arenas, markers, identities = {}, {}, {}, set(), set()
    map_diagnostics=[]
    workload_diagnostics=[]
    runtime_profile = {"row":None,"map":None,"profile_id":None}
    pending_loaded_owners=[]
    pending_loaded_caches=[]
    active_map=None
    errors = []
    boot_diagnostics = []
    machine_entered = False
    for line in lines:
        if "HALO_PS2_LOCAL machine entry" in line:
            machine_entered = True
        if "HALO_PS2_LOCAL partition-selected " in line:
            markers.add("partition-selected")
            if "qualified=1" in line: markers.add("partition-selected-qualified")
        if "HALO_PS2_LOCAL owner-telemetry " in line: markers.add("owner-telemetry")
        if "HALO_PS2_LOCAL cache-owner " in line: markers.add("cache-owner")
        if "HALO_PS2_LOCAL arena " in line: markers.add("arena")
        if "HALO_PS2_LOCAL render-storage-bound " in line: markers.add("render-storage-bound")
        if "HALO_PS2_LOCAL map-mount result=" in line or "HALO_PS2_LOCAL m2-ui-lifecycle-complete " in line: markers.add("map-lifecycle")
        if "HALO_PS2_LOCAL partition-selected " in line:
            mm = re.search(r"\bname=(\S+)", line)
            if mm: identities.add(mm.group(1))
        if "HALO_PS2_LOCAL profile-runtime " in line:
            markers.add("profile-runtime")
            # This marker is emitted only after runtime registration succeeds.
            markers.add("profile-runtime-qualified")
            rm=re.search(r"\brow=(\S+)",line)
            mp=re.search(r"\bmap=(\S+)",line)
            pi=re.search(r"\bprofile=(\d+)",line)
            if rm: runtime_profile["row"]=rm.group(1); identities.add(rm.group(1))
            if mp: runtime_profile["map"]=mp.group(1)
            if pi: runtime_profile["profile_id"]=int(pi.group(1))
        mounted = re.search(r"HALO_PS2_LOCAL map-mount result=1 active=1 map=(\S+)", line)
        if mounted: identities.add("mounted-map:" + mounted.group(1))
        if "HALO_PS2_LOCAL step8-mp-workload " in line:
            fields={k:v for k,v in re.findall(r"([A-Za-z_]+)=(\S+)",line)}
            for k,v in list(fields.items()):
                if re.fullmatch(r"-?\d+",v): fields[k]=int(v)
            fields["line"]=line.strip()
            workload_diagnostics.append(fields)
        if "[err]" in line or "HALO_PS2_FAIL" in line:
            errors.append(line.strip())
        elif "Address Error" in line:
            (errors if machine_entered else boot_diagnostics).append(line.strip())
        query=re.search(r"HALO_PS2_LOCAL step8-mp-capacity-query map=(\S+)",line)
        if query:
            active_map={"map":query.group(1),"query_line":line.strip(),
                        "loaded_owner_snapshots":pending_loaded_owners,
                        "loaded_cache_snapshots":pending_loaded_caches,
                        "released_owner_snapshots":[],"released_cache_snapshots":[]}
            map_diagnostics.append(active_map)
            pending_loaded_owners=[]; pending_loaded_caches=[]
        m = OWNER.search(line)
        if m:
            phase, name, kind, parent, bound, cap, used, high, failures, resets = m.groups()
            sample=dict(phase=phase, kind=kind, parent=parent,
                bound=int(bound), capacity=int(cap), current=int(used), peak=int(high),
                failures=int(failures), resets=int(resets))
            owners.setdefault(name, []).append(sample)
            if phase == "map-loaded": pending_loaded_owners.append({"owner":name,**sample})
            elif phase == "map-released" and active_map is not None:
                active_map["released_owner_snapshots"].append({"owner":name,**sample})
        m = CACHE.search(line)
        if m:
            phase, name, current, peak, failures, resets = m.groups()
            sample=dict(phase=phase, current=int(current), peak=int(peak), failures=int(failures), resets=int(resets))
            caches.setdefault(name, []).append(sample)
            if phase == "map-loaded": pending_loaded_caches.append({"owner":name,**sample})
            elif phase == "map-released" and active_map is not None:
                active_map["released_cache_snapshots"].append({"owner":name,**sample})
        m = ARENA.search(line)
        if m:
            name, cap, used, high, failures, resets = m.groups()
            arenas.setdefault(name, []).append(dict(capacity=int(cap), current=int(used), peak=int(high), failures=int(failures), resets=int(resets)))
    elf = Path(run.get("elf", ""))
    if not elf.is_absolute(): elf = ROOT / elf
    staged_sha = sha(elf) if elf.is_file() else None
    elf_sha = run.get("elf_sha256")
    hash_valid = bool(elf_sha and staged_sha and elf_sha == staged_sha)
    maps_dir = Path(run.get("maps_dir", ""))
    if not run.get("maps_dir") and logp.parent.joinpath("maps").exists():
        maps_dir = logp.parent / "maps"
    if not maps_dir.is_absolute(): maps_dir = ROOT / maps_dir
    if maps_dir.exists(): maps_dir=maps_dir.resolve()
    map_hashes = {p.name:sha(p) for p in sorted(maps_dir.iterdir()) if p.is_file()} if maps_dir.is_dir() else {}
    build_path=Path(run.get("build_result", ""))
    if not build_path.is_absolute(): build_path=ROOT/build_path
    build_data=json.loads(build_path.read_text()) if build_path.is_file() else {}
    gameplay=build_data.get("hcu_gameplay_machine", {})
    built_elf_sha=gameplay.get("elf",{}).get("sha256")
    hcu_main_hash=next((v for k,v in gameplay.get("parent_object_sha256",{}).items()
                        if k.endswith("/stream/hcu_main.o")),None)
    build_identity_valid=bool(built_elf_sha and elf_sha and built_elf_sha==elf_sha)
    missing = sorted(set(REQUIRED) - markers)
    blockers = []
    if missing: blockers.append("missing guest behavior: " + ", ".join(missing))
    terminal_ok = run.get("guest_completed") is True and run.get("guest_terminal") in ("completion-marker", "release-marker")
    if not terminal_ok: blockers.append("guest terminal sequence was not completed")
    if not hash_valid: blockers.append("ELF source hash absent or does not match staged ELF")
    if build_path.is_file() and not build_identity_valid: blockers.append("ELF hash does not match linked build result")
    if errors: blockers.append("guest log contains errors")
    if "profile-runtime-qualified" not in markers: blockers.append("profile registration was not qualified")
    mode=run.get("scenario_mode") or run.get("run")
    diagnostic_terminal={"mode":mode,"completed":False,"reason":"no matching clean completion sequence"}
    if mode in ("workload2p","workload4p"):
        players=2 if mode=="workload2p" else 4
        observed=any(d.get("local_players")==players and d.get("bots")=="not-exercised" for d in workload_diagnostics)
        complete=any("HALO_PS2_LOCAL step8-mp-workload-complete " in x and
            re.search(rf"\blocal_players={players}\b",x) and "teardown=clean" in x for x in lines)
        clean=any("HALO_PS2_LOCAL step8-mp-workload-teardown-state " in x and
            "map_loaded=0" in x and "scenario_unpublished=1" in x for x in lines)
        diagnostic_terminal={"mode":mode,"completed":bool(observed and complete and clean and not errors),
            "local_players":players,"bots":"not-exercised","completion_marker":complete,"clean_teardown":clean,
            "reason":None if observed and complete and clean and not errors else "workload/teardown completion evidence incomplete"}
    elif mode in ("capacity","step8-mp-capacity-13-map"):
        queries={m["map"] for m in map_diagnostics}
        complete=any("HALO_PS2_LOCAL step8-mp-capacity-complete maps=13 query_only=1" in x for x in lines)
        diagnostic_terminal={"mode":mode,"completed":bool(complete and len(queries)==13 and not errors),
            "query_map_count":len(queries),"completion_marker":complete,
            "reason":None if complete and len(queries)==13 and not errors else "13-map completion or query coverage incomplete"}
    elif mode=="lifecycle":
        released=any("HALO_PS2_LOCAL m2-ui-lifecycle-owner-released " in x for x in lines)
        complete=any("HALO_PS2_LOCAL m2-ui-lifecycle-complete " in x for x in lines)
        diagnostic_terminal={"mode":mode,"completed":bool(released and complete and not errors),
            "owner_released":released,"completion_marker":complete,
            "reason":None if released and complete and not errors else "UI lifecycle release/completion missing"}
    result.update({"provenance": {"run_manifest": str(run_path), "elf": run.get("elf"), "elf_sha256": elf_sha,
        "staged_elf_sha256": staged_sha, "elf_hash_valid": hash_valid,
        "profile_package_sha256": run.get("profile_package_sha256"),
        "profile_name":run.get("profile_name"),"partition_profile":run.get("partition_profile"),
        "scenario_mode":run.get("scenario_mode"),"scenario":run.get("run"),
        "build_result":str(build_path) if build_path.is_file() else run.get("build_result"),
        "build_result_sha256":sha(build_path) if build_path.is_file() else None,
        "linked_hcu_elf_sha256":built_elf_sha,"build_identity_valid":build_identity_valid,
        "compiled_hcu_main_object_sha256":hcu_main_hash,
        "runtime_profile":runtime_profile,"diagnostic_terminal":diagnostic_terminal,
        "maps_dir":str(maps_dir) if maps_dir.is_dir() else run.get("maps_dir"),"map_file_sha256":map_hashes,
        "log": str(logp) if logp.is_file() else run.get("halo_lines_saved"), "exit": run.get("exit"),
        "elapsed_seconds": run.get("elapsed_seconds"), "observed_markers": sorted(markers), "errors": errors,
        "boot_diagnostics":boot_diagnostics},
        "identity": sorted(identities),
        "owners": owners, "cache_owners": caches, "arenas": arenas,"map_diagnostics":map_diagnostics,
        "workload_diagnostics":workload_diagnostics,
        "complete": not blockers, "blocker": "; ".join(blockers) if blockers else None})
    return result


def matched_owner(profile, evidence, owner, scenario):
    if not profile.get("hcp_package_sha256") or not evidence.get("complete"):
        return None
    if not profile.get("hcp_package_sha256_matches_manifest"):
        return None
    if profile.get("name") not in (evidence.get("identity") or []):
        return None
    if "mounted-map:" + str(profile.get("map")) not in (evidence.get("identity") or []):
        return None
    provenance = evidence.get("provenance") or {}
    if provenance.get("profile_package_sha256") != profile["hcp_package_sha256"]:
        return None
    if provenance.get("profile_name") != profile.get("name") or provenance.get("partition_profile") != profile.get("name"):
        return None
    runtime = provenance.get("runtime_profile") or {}
    if runtime.get("row") != profile.get("name") or runtime.get("map") != profile.get("map"):
        return None
    if profile.get("profile_id") is not None and runtime.get("profile_id") != profile.get("profile_id"):
        return None
    if scenario == "partition-selected":
        expected_mode = "production-ce-map-load-headless"
    elif profile.get("name") == "ui":
        expected_mode = "lifecycle"
    else:
        expected_mode = scenario
    scenario_matches = (scenario == "partition-selected" and expected_mode == "production-ce-map-load-headless") or scenario == expected_mode
    if not scenario_matches or provenance.get("scenario_mode") != expected_mode:
        return None
    if expected_mode in ("workload2p", "workload4p") and owner not in ("game_state", "object_pool", "actor_pool", "dynamic_simulation"):
        return None
    if expected_mode == "lifecycle" and profile.get("name") != "ui":
        return None
    rows = evidence.get("owners", {}).get(owner, [])
    if not rows or rows[-1].get("bound") != 1 or not rows[-1].get("capacity"):
        return None
    return (rows[-1], provenance)


def owner_qualifies_fit(sample, expected_capacity=None):
    current=sample.get("current",-1); peak=sample.get("peak",-1); capacity=sample.get("capacity",0)
    return (sample.get("bound") == 1 and capacity > 0 and 0 <= current <= peak <= capacity and
            sample.get("failures", 0) == 0 and
            (expected_capacity is None or capacity == expected_capacity))


def build(matrix_path, manifest_path, workload2_path, workload4_path, lifecycle_path):
    matrix = json.loads(matrix_path.read_text())
    partition_path = ROOT / "build/m2-c2-r2-budget/partition-table-profile-v2.json"
    partition_data = json.loads(partition_path.read_text()) if partition_path.is_file() else {"profiles": []}
    partition_rows = {r["name"]: r for r in partition_data.get("profiles", [])}
    sources = {"capacity": (read_run(manifest_path, "capacity"), manifest_path),
        "workload2p": (read_run(workload2_path, "workload2p"), workload2_path),
        "workload4p": (read_run(workload4_path, "workload4p"), workload4_path),
        "lifecycle": (read_run(lifecycle_path, "lifecycle"), lifecycle_path)}
    build_results={
        "capacity":ROOT/"build/m2-c2-resume-fit/capacity/result-step8-mp-capacity-tagcache-4477120.json",
        "workload2p":ROOT/"build/m2-c2-resume-fit/workload2p/result-step8-mp-workload-2p-tagcache-4477120.json",
        "workload4p":ROOT/"build/m2-c2-resume-fit/workload4p/result-step8-mp-workload-4p-tagcache-4477120.json",
        "lifecycle":ROOT/"build/m2-c2-resume-fit/lifecycle/result-m2-ui-lifecycle.json"}
    for scenario,(run,path) in list(sources.items()):
        if run is not None and build_results[scenario].is_file():
            run["build_result"]=str(build_results[scenario])
    parsed = {k: extract(v[0], v[1]) for k, v in sources.items()}
    rows=[]
    profile_inputs = list(matrix["profiles"])
    package_root = ROOT / "build/m2-c2-r3-selected-packages"
    for p in profile_inputs:
        package_manifest = package_root / "pkg" / p["name"] / f"{p['name']}.json"
        package = package_root / "pkg" / p["name"] / f"{p['name']}.hcp"
        p["hcp_package_path"] = str(package.relative_to(ROOT))
        p["hcp_package_sha256"] = sha(package) if package.is_file() else None
        if package_manifest.is_file():
            manifest = json.loads(package_manifest.read_text())
            p["hcp_manifest_sha256"] = sha(package_manifest)
            p["hcp_package_sha256_matches_manifest"] = p["hcp_package_sha256"] == manifest.get("package_sha256")
            p["profile_id"] = manifest.get("profile", {}).get("id")
        else:
            p["hcp_package_sha256_matches_manifest"] = False
    # UI is the separate 27th package and has a lifecycle scenario, not a
    # session-map capacity row.
    ui_package = ROOT / "build/m2-c2-r3-selected-packages/pm/ui-under-test.hcp"
    ui = {}
    profile_inputs.append({"name":"ui", "map":"ui", "local_players":0, "spartan_bots":0,
        "hcp_package_path":str(ui_package.relative_to(ROOT)), "hcp_package_sha256":sha(ui_package) if ui_package.is_file() else None,
        "hcp_package_sha256_matches_manifest":False,
        "resident_ce_bytes":None,"bsp_payload_bytes":None,
        "claims_bitmap_payload_capacity_floor_bytes":None,"ctag_relocation_staging_bytes":None})
    # Only this explicitly asserted identity can populate a selected-profile
    # row. A generic 13-map diagnostic or local-player fixture does not name
    # the package/partition instance and stays supporting evidence.
    for p in profile_inputs:
        name=p["name"]
        measurements={}
        pr = partition_rows.get(name, {})
        known_caps={"tags":pr.get("tag_cache_bytes"),"bsp":pr.get("structure_bsp_bytes")}
        for owner in OWNER_NAMES:
            sample = None
            provenance = None
            for evidence in parsed.values():
                found = matched_owner(p, evidence, owner, (evidence.get("provenance") or {}).get("scenario"))
                if found:
                    sample, provenance = found
                    break
            measurements[owner] = ({"status":"measured", **sample,
                                    "expected_static_capacity":known_caps.get(owner),
                                    "qualifies_fit":owner_qualifies_fit(sample,known_caps.get(owner)), "provenance":provenance}
                if sample else {"status":"unmeasured", "capacity":None,"current":None,"peak":None,"failures":None,"resets":None,
                    "expected_static_capacity":known_caps.get(owner),
                    "reason":"no complete guest run bound to this exact partition and HCP package hash", "evidence":None})
        rows.append({"profile":name,"map":p["map"],"players":p.get("local_players"),"bots":p.get("spartan_bots"),
            "package":p.get("hcp_package_path"),"package_sha256":p.get("hcp_package_sha256"),
            "hcp_manifest_sha256":p.get("hcp_manifest_sha256"),"hcp_package_sha256_matches_manifest":p.get("hcp_package_sha256_matches_manifest"),
            "ce_ctag_sha256":p.get("ctag_sha256"),
            "static_capacity_floor_bytes":{"ce_resident":p.get("resident_ce_bytes"),"bsp_payload":p.get("bsp_payload_bytes"),"claims_bitmap":p.get("claims_bitmap_payload_capacity_floor_bytes"),"relocation":p.get("ctag_relocation_staging_bytes")},
            "static_partition_terms_bytes":{"tag_cache":pr.get("tag_cache_bytes"),"structure_bsp":pr.get("structure_bsp_bytes"),"map_parent":pr.get("map_parent_bytes"),"render_texture":pr.get("render_texture_bytes"),"claims_scratch":pr.get("claims_scratch_bytes"),"resident_gameplay_cap":pr.get("resident_gameplay_cap_bytes"),"renderer_packet_workspace":pr.get("renderer_packet_workspace_bytes"),"renderer_reserved_texture":pr.get("renderer_reserved_texture_bytes"),"staging_slot":pr.get("staging_slot_bytes"),"simultaneous_staging":pr.get("simultaneous_staging_bytes")},
            "partition_terms_source":str(partition_path.relative_to(ROOT)) if partition_path.is_file() else None,
            "owner_measurements":measurements,"profile_specific_guest_fit":"not_measured",
            "missing_behavior":["profile-specific map registration and mount", "live 2-player and 4-player gameplay peaks", "owner reset/failure behavior", "renderer drain/UI lifecycle"]})
    diagnostics={}
    for scenario,evidence in parsed.items():
        prov=evidence.get("provenance") or {}
        diagnostics[scenario]={"scenario_mode":prov.get("scenario_mode") or scenario,
            "scenario_terminal":prov.get("diagnostic_terminal"),"run_complete_for_profile_fit":evidence.get("complete",False),
            "profile_fit_blocker":evidence.get("blocker"),"elf_sha256":prov.get("elf_sha256"),
            "elf_hash_valid":prov.get("elf_hash_valid"),"build_result":prov.get("build_result"),
            "build_result_sha256":prov.get("build_result_sha256"),"build_identity_valid":prov.get("build_identity_valid"),
            "compiled_hcu_main_object_sha256":prov.get("compiled_hcu_main_object_sha256"),"maps_dir":prov.get("maps_dir"),
            "map_file_sha256":prov.get("map_file_sha256",{}),"map_diagnostics":evidence.get("map_diagnostics",[]),
            "workload_diagnostics":evidence.get("workload_diagnostics",[]),
            "owner_snapshots":evidence.get("owners",{}),"cache_owner_snapshots":evidence.get("cache_owners",{}),
            "arena_snapshots":evidence.get("arenas",{}),"errors":(prov.get("errors") or []),
            "boot_diagnostics":(prov.get("boot_diagnostics") or [])}
    validation_path=ROOT/"build/m2-c2-resume-root-tests/workload-validation.json"
    if validation_path.is_file():
        validation=json.loads(validation_path.read_text())
        for item in validation:
            scenario="workload2p" if item.get("assertions",{}).get("local_players")==2 else "workload4p"
            manifest_file=ROOT/item["manifest"]
            log_file=Path(item["log"])
            if not log_file.is_absolute(): log_file=ROOT/log_file
            pins_valid=(manifest_file.is_file() and sha(manifest_file)==item.get("manifest_sha256") and
                log_file.is_file() and sha(log_file)==item.get("log_sha256") and
                item.get("elf_sha256")==diagnostics.get(scenario,{}).get("elf_sha256"))
            diagnostics.setdefault(scenario,{})["independent_fixture_validation"]={
                "path":str(validation_path.relative_to(ROOT)),"sha256":sha(validation_path),
                "manifest":item.get("manifest"),"manifest_sha256":item.get("manifest_sha256"),
                "log":item.get("log"),"log_sha256":item.get("log_sha256"),
                "elf_sha256":item.get("elf_sha256"),"pins_valid":pins_valid,
                "scope":item.get("scope"),"assertions":item.get("assertions")}
    return {"format":"hcu-c2-profile-guarded-fit-v1","scope":{"session_profiles":len(matrix["profiles"]),"ui_row_included":True,
      "guarded_owner_fit_claimed":False,"static_floors_are_not_runtime_fit":True,
      "diagnostic_runs_are_not_profile_fits":True},
      "diagnostic_observations":diagnostics,"run_evidence":parsed,"profiles":rows}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matrix",type=Path,default=ROOT/"build/m2-c2-session-map-capacity-2026-10-23/matrix.json")
    ap.add_argument("--manifest",type=Path,default=ROOT/"build/m2-c2-resume-fit/guest/capacity/manifest.json")
    ap.add_argument("--workload2",type=Path,default=ROOT/"build/m2-c2-resume-fit/guest/workload2p/manifest.json")
    ap.add_argument("--workload4",type=Path,default=ROOT/"build/m2-c2-resume-fit/guest/workload4p/manifest.json")
    ap.add_argument("--lifecycle",type=Path,default=ROOT/"build/m2-c2-resume-fit/guest/lifecycle/manifest.json")
    ap.add_argument("--output",type=Path,required=True)
    a=ap.parse_args()
    data=build(a.matrix,a.manifest,a.workload2,a.workload4,a.lifecycle)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    print(f"{len(data['profiles'])} profiles; guarded runtime fits measured: 0")
if __name__=="__main__": main()
