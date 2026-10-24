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
REQUIRED = ("machine-entry", "partition-selected", "profile-runtime", "owner-telemetry", "cache-owner", "arena",
            "render-storage-bound", "map-lifecycle")
OWNER_NAMES = ("game_state", "object_pool", "actor_pool", "widget_pool", "dynamic_simulation", "tags", "bsp",
               "render_chunks", "render_texture", "gs_window", "gs_texture", "streaming", "scratch", "dma",
               "audio_requests")


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
            markers.add("machine-entry")
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
        if "[err]" in line or "HALO_PS2_FAIL" in line or "Address Error" in line:
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
            domain = re.search(r"\bdomain=(\S+)", line)
            if domain: sample["domain"] = domain.group(1)
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


PARTITION_SELECTED = re.compile(r"HALO_PS2_LOCAL partition-selected name=(\S+) version=(\d+) tag=(\d+) bsp=(\d+) texture=(\d+) residency=(\d+) qualified=(\d)")
LOADED = re.compile(r"HALO_PS2_LOCAL production-ce-map-loaded result=(\d) map=(\S+) .*?tag-bytes=(\d+) bsp-bytes=(\d+)")
RELEASED = re.compile(r"HALO_PS2_LOCAL production-ce-map-released result=(\d) map=(\S+) mounted=(\d)")


def rel(path):
    path = Path(path)
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def abspath(value):
    path = Path(value)
    return path if path.is_absolute() else ROOT / path


def matrix_run(row_dir):
    """Synthesize an extract() run record from one matrix row's retained guest manifest."""
    guest = row_dir / "guest" / "manifest.json"
    if not guest.is_file():
        return None, None
    data = json.loads(guest.read_text())
    runs = data.get("runs") or []
    if not runs:
        return None, guest
    run = {**{k: v for k, v in data.items() if k not in ("runs", "elfs")}, **runs[0]}
    run["guest_completed"] = bool(run.get("markers_all_present")) and str(run.get("exit", "")).startswith("release-marker")
    run["guest_terminal"] = "release-marker" if run["guest_completed"] else None
    builds = sorted((row_dir / "link").glob("result-partition-*.json"))
    if builds:
        run["build_result"] = str(builds[0])
    return run, guest


def summarize_matrix_row(row_dir, profile=None):
    """Read one build/m2-c2-matrix/<row> directory into a compact, provenance-bound fit record."""
    result_path = row_dir / "result.json"
    out = {"row": row_dir.name, "status": "unmeasured", "fit": None, "reasons": []}
    if not result_path.is_file():
        out["reasons"].append("result.json missing")
        return out, None
    result = json.loads(result_path.read_text())
    run, guest_path = matrix_run(row_dir)
    evidence = extract(run, guest_path) if run else None
    prov = (evidence or {}).get("provenance") or {}
    log = abspath(run["halo_lines_saved"]) if run and run.get("halo_lines_saved") else None
    lines = log.read_text(errors="replace").splitlines() if log and log.is_file() else []
    spans = loaded = released = None
    for line in lines:
        m = PARTITION_SELECTED.search(line)
        if m and spans is None:
            spans = dict(name=m.group(1), version=int(m.group(2)), tag=int(m.group(3)), bsp=int(m.group(4)),
                         texture=int(m.group(5)), residency=int(m.group(6)), qualified=int(m.group(7)))
        m = LOADED.search(line)
        if m:
            loaded = dict(result=int(m.group(1)), map=m.group(2), tag_bytes=int(m.group(3)), bsp_bytes=int(m.group(4)))
        m = RELEASED.search(line)
        if m:
            released = dict(result=int(m.group(1)), map=m.group(2), mounted=int(m.group(3)))
    owners = {}
    failures = 0
    for name, samples in ((evidence or {}).get("owners") or {}).items():
        last = samples[-1]
        owners[name] = {k: last[k] for k in ("bound", "capacity", "current", "peak", "failures", "resets")}
        peak = max(x["peak"] for x in samples)
        owners[name]["peak"] = peak
        failures += sum(x["failures"] for x in samples)
    caches = {n: {"peak": max(x["peak"] for x in v), "failures": sum(x["failures"] for x in v)}
              for n, v in ((evidence or {}).get("cache_owners") or {}).items()}
    arenas = {}
    for name, samples in ((evidence or {}).get("arenas") or {}).items():
        arenas[name] = {"capacity": samples[-1]["capacity"], "peak": max(x["peak"] for x in samples),
                        "failures": sum(x["failures"] for x in samples)}
        failures += arenas[name]["failures"]
    failures += sum(v["failures"] for v in caches.values())
    values = result.get("values") or {}
    reserve, boot_end = values.get("reserve"), values.get("boot_end")
    tag_peak = (owners.get("tags") or {}).get("peak")
    bsp_peak = (owners.get("bsp") or {}).get("peak")
    gs = owners.get("game_state") or {}
    streaming_map = arenas.get("streaming_map_owner") or {}
    def margin(cap, peak):
        return cap - peak if cap is not None and peak is not None else None
    margins = {"tag": margin((owners.get("tags") or {}).get("capacity"), tag_peak),
               "bsp": margin((owners.get("bsp") or {}).get("capacity"), bsp_peak),
               "game_state": margin(gs.get("capacity"), gs.get("peak")),
               "residency_streaming_map_owner": margin(streaming_map.get("capacity"), streaming_map.get("peak")),
               "boot_end_below_reserve": margin(reserve, boot_end)}
    reasons = []
    if not result.get("pass"):
        reasons.append("result.json pass=false: " + "; ".join(result.get("reasons") or result.get("failing_checks") or []))
    if evidence is None or not prov.get("elf_hash_valid"):
        reasons.append("ELF sha256 absent or does not match the staged ELF")
    if evidence is not None and not prov.get("build_identity_valid"):
        reasons.append("ELF sha256 does not match the linked build result")
    if evidence is not None and not evidence.get("complete"):
        reasons.append("guest evidence incomplete: " + str(evidence.get("blocker")))
    if spans is None or not spans["qualified"]:
        reasons.append("partition-selected marker missing or unqualified")
    if loaded is None or loaded["result"] != 1:
        reasons.append("production-ce-map-loaded result=1 missing")
    if released is None or released["result"] != 1 or released["mounted"] != 0:
        reasons.append("production-ce-map-released result=1 mounted=0 missing")
    if failures:
        reasons.append(f"{failures} owner/arena/cache failure counts")
    if spans and tag_peak is not None and tag_peak > spans["tag"]:
        reasons.append("tag peak exceeds tag span")
    if spans and bsp_peak is not None and bsp_peak > spans["bsp"]:
        reasons.append("BSP peak exceeds BSP span")
    if None in (reserve, boot_end) or boot_end >= reserve:
        reasons.append("boot end not below reserve")
    for key, value in margins.items():
        if value is not None and value < 0:
            reasons.append(f"negative margin: {key}")
    if profile is not None:
        if profile.get("hcp_package_sha256") != prov.get("profile_package_sha256"):
            reasons.append("guest package sha256 differs from the selected package")
        if not profile.get("hcp_package_sha256_matches_manifest"):
            reasons.append("selected package sha256 does not match its package manifest")
    out.update({"status": "measured", "fit": not reasons, "reasons": reasons,
        "map": result.get("map"), "scenario_mode": prov.get("scenario_mode"),
        "scope": "selected-profile production CE load and release only; no 4-player or bot gameplay workload ticks",
        "checks": result.get("checks"), "failing_checks": result.get("failing_checks"),
        "spans": spans, "loaded": loaded, "released": released,
        "peaks": {"tag": tag_peak, "bsp": bsp_peak, "game_state": gs.get("peak"),
                  "object_pool": (owners.get("object_pool") or {}).get("peak"),
                  "residency_streaming_map_owner": streaming_map.get("peak"),
                  "backing_high": (result.get("peaks") or {}).get("backing_high")},
        "caps": {"tag": (owners.get("tags") or {}).get("capacity"), "bsp": (owners.get("bsp") or {}).get("capacity"),
                 "game_state": gs.get("capacity"), "residency_streaming_map_owner": streaming_map.get("capacity")},
        "margins": margins, "failure_counts_total": failures,
        "reserve": reserve, "boot_end": boot_end, "owners": owners, "cache_owners": caches, "arenas": arenas,
        "provenance": {"elf": prov.get("elf"), "elf_sha256": prov.get("elf_sha256"),
            "staged_elf_sha256": prov.get("staged_elf_sha256"), "elf_hash_valid": prov.get("elf_hash_valid"),
            "linked_hcu_elf_sha256": prov.get("linked_hcu_elf_sha256"), "build_identity_valid": prov.get("build_identity_valid"),
            "package_sha256": prov.get("profile_package_sha256"),
            "package_root": result.get("package_root"),
            "result_json": rel(result_path), "result_json_sha256": sha(result_path),
            "guest_manifest": rel(guest_path) if guest_path else None,
            "emu_log": rel(abspath(run["log"])) if run else None,
            "emu_log_sha256": sha(abspath(run["log"])) if run and abspath(run["log"]).is_file() else None,
            "halo_log": rel(log) if log else None,
            "halo_log_sha256": sha(log) if log and log.is_file() else None,
            "elapsed_seconds": result.get("elapsed_seconds"), "exit": run.get("exit") if run else None}})
    return out, evidence


def load_matrix(matrix_dir, profiles_by_name):
    """Return (summaries, evidence-by-row) for every row directory under matrix_dir."""
    summaries, evidences = {}, {}
    if not matrix_dir or not Path(matrix_dir).is_dir():
        return summaries, evidences
    for row_dir in sorted(p for p in Path(matrix_dir).iterdir() if p.is_dir()):
        summary, evidence = summarize_matrix_row(row_dir, profiles_by_name.get(row_dir.name))
        summaries[row_dir.name] = summary
        if evidence is not None:
            evidences[row_dir.name] = evidence
    return summaries, evidences


def build(matrix_path, manifest_path, workload2_path, workload4_path, lifecycle_path, matrix_dir=None, reuse_dir=None):
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
    ui_manifest = None
    ui_result = Path(matrix_dir) / "ui" / "result.json" if matrix_dir else None
    if ui_result and ui_result.is_file():
        # Bind to the package tree the ui matrix row actually staged.
        root = json.loads(ui_result.read_text()).get("package_root")
        if root and (abspath(root) / "ui" / "ui.hcp").is_file():
            ui_package = abspath(root) / "ui" / "ui.hcp"
            ui_manifest = abspath(root) / "ui" / "ui.json"
    ui_manifest_data = json.loads(ui_manifest.read_text()) if ui_manifest and ui_manifest.is_file() else {}
    ui_sha = sha(ui_package) if ui_package.is_file() else None
    profile_inputs.append({"name":"ui", "map":"ui", "local_players":0, "spartan_bots":0,
        "hcp_package_path":rel(ui_package), "hcp_package_sha256":ui_sha,
        "hcp_package_sha256_matches_manifest":bool(ui_sha and ui_sha == ui_manifest_data.get("package_sha256")),
        "hcp_manifest_sha256":sha(ui_manifest) if ui_manifest and ui_manifest.is_file() else None,
        "profile_id":ui_manifest_data.get("profile", {}).get("id"),
        "resident_ce_bytes":None,"bsp_payload_bytes":None,
        "claims_bitmap_payload_capacity_floor_bytes":None,"ctag_relocation_staging_bytes":None})
    matrix_summaries, matrix_evidence = load_matrix(matrix_dir, {p["name"]: p for p in profile_inputs})
    selected_names = {p["name"] for p in matrix["profiles"]}
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
            for evidence in list(parsed.values()) + ([matrix_evidence[name]] if name in matrix_evidence else []):
                found = matched_owner(p, evidence, owner, (evidence.get("provenance") or {}).get("scenario"))
                if found:
                    sample, provenance = found
                    break
            measurements[owner] = ({"status":"measured", **sample,
                                    "expected_static_capacity":known_caps.get(owner),
                                    "qualifies_fit":owner_qualifies_fit(sample,known_caps.get(owner)),
                                    "provenance":{k:v for k,v in provenance.items() if k not in ("map_file_sha256","observed_markers")}}
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
            "owner_measurements":measurements,
            "profile_specific_guest_fit":("measured_pass" if name in matrix_summaries and matrix_summaries[name]["fit"] else
                "measured_fail" if name in matrix_summaries else "not_measured"),
            "matrix_row":matrix_summaries.get(name),
            "missing_behavior":(["live 4-player and 4-bot gameplay workload peaks (matrix run is load and release only)", "renderer drain with in-flight readers (C3.10/C3.11)"]
                if name in matrix_summaries else ["profile-specific map registration and mount", "live 2-player and 4-player gameplay peaks", "owner reset/failure behavior", "renderer drain/UI lifecycle"])})
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
    measured_pass = sorted(n for n in selected_names if n in matrix_summaries and matrix_summaries[n]["fit"])
    measured_fail = sorted(n for n in selected_names if n in matrix_summaries and not matrix_summaries[n]["fit"])
    unmeasured = sorted(n for n in selected_names if n not in matrix_summaries) + ([] if "ui" in matrix_summaries else ["ui"])
    if "ui" in matrix_summaries:
        (measured_pass if matrix_summaries["ui"]["fit"] else measured_fail).append("ui")
        measured_pass.sort(); measured_fail.sort()
    extra = {n: v for n, v in matrix_summaries.items() if n not in selected_names and n != "ui"}
    return {"format":"hcu-c2-profile-guarded-fit-v1","scope":{"session_profiles":len(matrix["profiles"]),"ui_row_included":True,
      "guarded_owner_fit_claimed":bool(measured_pass),
      "guarded_owner_fit_scope":"selected-profile production CE load and release in PCSX2; no 4-player or bot gameplay workload ticks",
      "static_floors_are_not_runtime_fit":True,
      "diagnostic_runs_are_not_profile_fits":True,
      "matrix_dir":rel(matrix_dir) if matrix_dir else None,
      "measured_pass_count":len(measured_pass),"measured_fail":measured_fail,
      "unmeasured_rows":unmeasured,"extra_diagnostic_rows":sorted(extra)},
      "extra_diagnostic_rows":extra,
      "reuse_evidence":summarize_reuse(reuse_dir),
      "diagnostic_observations":diagnostics,"run_evidence":parsed,"profiles":rows}


def summarize_reuse(reuse_dir):
    """Summarize multi-cycle runs (build/m2-c2-gaps-reuse/*_result.json) as storage-reuse evidence."""
    out = {"dir": rel(reuse_dir) if reuse_dir else None, "runs": [], "passing_runs": [], "failing_runs": []}
    if not reuse_dir or not Path(reuse_dir).is_dir():
        out.update(rows_with_reuse_evidence=[], max_cycles_by_row={}, reuse_shown=False)
        return out
    for path in sorted(Path(reuse_dir).glob("*_result.json")):
        r = json.loads(path.read_text())
        cc = r.get("cycle_checks") or {}
        checks = cc.get("checks") or {}
        per = cc.get("per_cycle") or []
        last = per[-1].get("at_release", {}) if per else {}
        completed = sum(1 for i in range(1, (r.get("cycles") or 0) + 1) if checks.get(f"cycle_{i}_released"))
        rec = {"file": rel(path), "sha256": sha(path), "row": r.get("row"), "map": r.get("map"),
               "cycles_requested": r.get("cycles"), "cycles_completed": completed, "ticks_per_cycle": r.get("ticks"),
               "pass": bool(r.get("pass")), "elapsed_seconds": r.get("elapsed_seconds"),
               "failing_checks": r.get("failing_checks"),
               "storage_reused_cycles_2_to_n": checks.get("storage_reused_cycles_2_to_n"),
               "cycle1_vs_cycle2_differences": cc.get("cycle1_vs_cycle2_differences"),
               "release_backing": last.get("backing"),
               "release_owner_failures": sum(v.get("failures", 0) for v in (last.get("owners") or {}).values()),
               "release_cache": last.get("cache"),
               "elf": r.get("elf"), "package_root": r.get("package_root")}
        out["runs"].append(rec)
        (out["passing_runs"] if rec["pass"] else out["failing_runs"]).append(rec["file"])
    # A reuse claim needs a passing run with >=2 complete cycles, identical storage in cycles 2..N and zero failures.
    ok = [r for r in out["runs"] if r["pass"] and r["cycles_completed"] >= 2 and r["storage_reused_cycles_2_to_n"]
          and not r["release_owner_failures"]]
    out["rows_with_reuse_evidence"] = sorted({r["row"] for r in ok})
    out["max_cycles_by_row"] = {n: max(r["cycles_completed"] for r in ok if r["row"] == n) for n in out["rows_with_reuse_evidence"]}
    out["reuse_shown"] = bool(ok)
    return out


def build_matrix_report(data):
    """Flatten the fit table's matrix rows into the per-row matrix report."""
    rows = []
    def row_of(name, m, selected):
        c = m.get("checks") or {}
        return {"row": name, "selected_session_package": selected, "map": m.get("map"),
            "booted": bool(c.get("partition_selected") and c.get("memory_ready") and c.get("profile_runtime")),
            "map_loaded": bool(c.get("map_loaded")), "released": bool(c.get("map_released")),
            "failures_zero": bool(c.get("failures_zero")) and m.get("failure_counts_total") == 0,
            "below_reserve": bool(c.get("boot_end_below_reserve")),
            "pass": bool(m.get("fit")), "reasons": m.get("reasons"),
            "spans": m.get("spans"), "peaks": m.get("peaks"), "caps": m.get("caps"), "margins": m.get("margins"),
            "failure_counts_total": m.get("failure_counts_total"), "reserve": m.get("reserve"), "boot_end": m.get("boot_end"),
            "provenance": m.get("provenance")}
    for prof in data["profiles"]:
        if prof["profile"] == "ui" and not prof["matrix_row"]:
            rows.append({"row": "ui", "selected_session_package": False, "pass": None, "status": "unmeasured",
                "reasons": ["no matrix row was run for the separate UI lifecycle package"]})
        elif prof["matrix_row"]:
            rows.append(row_of(prof["profile"], prof["matrix_row"], prof["profile"] != "ui"))
        else:
            rows.append({"row": prof["profile"], "selected_session_package": True, "pass": None, "status": "unmeasured",
                "reasons": ["no matrix result.json"]})
    for name, m in sorted(data["extra_diagnostic_rows"].items()):
        rows.append(row_of(name, m, False))
    sel = [r for r in rows if r["selected_session_package"]]
    sel_pass = [r for r in sel if r["pass"]]
    failing = [r["row"] for r in rows if r["pass"] is False]
    unmeasured = [r["row"] for r in rows if r["pass"] is None]
    measured = [r for r in rows if r.get("peaks")]
    def span(key, sub):
        vals = [r[key][sub] for r in sel if r.get("pass") and r.get(key)]
        return {"min": min(vals), "max": max(vals)} if vals else None
    return {"format": "hcu-c2-profile-matrix-v1", "date": "2026-10-24",
        "scope": "Selected-profile production loader in PCSX2 (interpreter): boot, guarded-partition registration, real CE scenario+BSP load, owner release. No 4-player or bot gameplay ticks and no integrated renderer readers.",
        "selected_session_rows": len(sel), "selected_session_rows_passed": len(sel_pass),
        "failing_rows": failing, "unmeasured_rows": unmeasured,
        "margin_ranges_passing_rows": {k: span("margins", k) for k in ("tag", "bsp", "game_state", "residency_streaming_map_owner", "boot_end_below_reserve")},
        "all_selected_session_rows_passed": len(sel) == len(sel_pass) and bool(sel),
        "ui_row_passed": any(r["row"] == "ui" and r["pass"] for r in rows),
        "reuse_evidence": data.get("reuse_evidence"),
        "exit_met": (not failing and not unmeasured and bool(sel) and len(sel) == len(sel_pass)
                     and any(r["row"] == "ui" and r["pass"] for r in rows)
                     and bool((data.get("reuse_evidence") or {}).get("reuse_shown"))),
        "rows": rows}


def write_matrix_markdown(report, path):
    f = lambda v: "n/a" if v is None else f"{v:,}"
    out = ["# C2 profile boot and fit matrix (2026-10-24)", "",
        "Generated by `tools/c2_profile_fit_table.py` from `build/m2-c2-matrix/*/result.json`, each row's guest manifest, ELF/package hashes and halo log. Machine-readable twin: `m2-c2-profile-matrix-2026-10-24.json`.", "",
        f"Scope: {report['scope']}", "",
        f"Result: {report['selected_session_rows_passed']} of {report['selected_session_rows']} selected session rows passed. Failing rows: {', '.join(report['failing_rows']) or 'none'}. Unmeasured rows: {', '.join(report['unmeasured_rows']) or 'none'}. C2 exit met: {str(report['exit_met']).lower()}.", "",
        "Margins are cap minus peak in bytes (tag/BSP/game-state caps are the guest owner-telemetry caps; residency is the `streaming_map_owner` arena; reserve is the 0x1a40000 reserve start minus boot end).", "",
        "| Row | Booted | Loaded | Released | Failures 0 | Below reserve | Tag peak | Tag margin | BSP peak | BSP margin | Game-state peak | GS margin | Residency peak | Residency margin | Reserve margin | Result |",
        "|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    yn = lambda v: "yes" if v else "no"
    for r in report["rows"]:
        if r.get("peaks") is None:
            out.append(f"| {r['row']} | - | - | - | - | - | - | - | - | - | - | - | - | - | - | unmeasured |")
            continue
        p, m = r["peaks"], r["margins"]
        res = "pass" if r["pass"] else "FAIL"
        if r["row"] == "ui":
            res += " (UI lifecycle package)"
        elif not r["selected_session_package"]:
            res += " (extra diagnostic)"
        out.append(f"| {r['row']} | {yn(r['booted'])} | {yn(r['map_loaded'])} | {yn(r['released'])} | {yn(r['failures_zero'])} | {yn(r['below_reserve'])} | "
            f"{f(p['tag'])} | {f(m['tag'])} | {f(p['bsp'])} | {f(m['bsp'])} | {f(p['game_state'])} | {f(m['game_state'])} | "
            f"{f(p['residency_streaming_map_owner'])} | {f(m['residency_streaming_map_owner'])} | {f(m['boot_end_below_reserve'])} | {res} |")
    out += ["", "## Failing and unmeasured rows", ""]
    bad = [r for r in report["rows"] if r["pass"] is not True]
    for r in bad:
        out.append(f"- `{r['row']}`: " + " | ".join(r["reasons"] or []))
    if not bad:
        out.append("None.")
    reuse = report.get("reuse_evidence") or {}
    out += ["", "## Repeated load/release (storage reuse)", "",
        f"Reuse shown: {str(bool(reuse.get('reuse_shown'))).lower()}. Rows with passing multi-cycle evidence: {', '.join(reuse.get('rows_with_reuse_evidence') or []) or 'none'}.", "",
        "| Run | Cycles done / requested | Ticks per cycle | Elapsed s | Storage identical cycles 2..N | Owner failures at release | Backing used / high at release | Result |",
        "|---|---:|---:|---:|---|---:|---|---|"]
    for r in reuse.get("runs") or []:
        b = r.get("release_backing") or {}
        out.append(f"| {r['row']} ({Path(r['file']).name}) | {r['cycles_completed']} / {r['cycles_requested']} | {r['ticks_per_cycle']} | {r['elapsed_seconds']} | "
            f"{r['storage_reused_cycles_2_to_n']} | {r['release_owner_failures']} | {f(b.get('backing_used'))} / {f(b.get('backing_high'))} | {'pass' if r['pass'] else 'FAIL'} |")
    out += ["", "## Provenance", "", "Per-row ELF SHA-256, package SHA-256, result.json SHA-256 and log paths are in the JSON `rows[].provenance` and in `m2-c2-profile-guarded-fit-2026-10-24.json` under `profiles[].matrix_row.provenance`.", ""]
    Path(path).write_text("\n".join(out))


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--matrix",type=Path,default=ROOT/"build/m2-c2-session-map-capacity-2026-10-23/matrix.json")
    ap.add_argument("--manifest",type=Path,default=ROOT/"build/m2-c2-resume-fit/guest/capacity/manifest.json")
    ap.add_argument("--workload2",type=Path,default=ROOT/"build/m2-c2-resume-fit/guest/workload2p/manifest.json")
    ap.add_argument("--workload4",type=Path,default=ROOT/"build/m2-c2-resume-fit/guest/workload4p/manifest.json")
    ap.add_argument("--lifecycle",type=Path,default=ROOT/"build/m2-c2-resume-fit/guest/lifecycle/manifest.json")
    ap.add_argument("--matrix-dir",type=Path,default=ROOT/"build/m2-c2-matrix")
    ap.add_argument("--reuse-dir",type=Path,default=ROOT/"build/m2-c2-gaps-reuse")
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--matrix-report",type=Path,help="write the per-row matrix report JSON here (a .md twin is written beside it)")
    a=ap.parse_args()
    data=build(a.matrix,a.manifest,a.workload2,a.workload4,a.lifecycle,a.matrix_dir,a.reuse_dir)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(data,indent=2,sort_keys=True)+"\n")
    if a.matrix_report:
        rep=build_matrix_report(data)
        a.matrix_report.write_text(json.dumps(rep,indent=2,sort_keys=True)+"\n")
        write_matrix_markdown(rep,a.matrix_report.with_suffix(".md"))
    sc=data["scope"]
    print(f"{len(data['profiles'])} profiles; guarded runtime fits measured pass: {sc['measured_pass_count']}; "
          f"measured fail: {len(sc['measured_fail'])}; unmeasured: {len(sc['unmeasured_rows'])}; extra diagnostic rows: {len(sc['extra_diagnostic_rows'])}")
if __name__=="__main__": main()
