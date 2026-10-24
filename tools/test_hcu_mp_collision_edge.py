#!/usr/bin/env python3
"""Generate and run a raw-source/CE collision-topology matrix on all 13 MP maps.

Native host ILP32 semantic evidence only. The source oracle selects a
same-material adjacent pair, constructs one strictly-interior offset ray per
face, and checks raw BSP3D plus BSP2D reference routing before asserting the
result from CE collision_test_vector(). No production source is edited.
"""
import contextlib
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/"tools"))
import audit_mp_collision_edge_pairs as source

ORDER=("longest","bloodgulch","beavercreek","prisoner","boardingaction",
       "carousel","chillout","damnation","hangemhigh","putput","ratrace",
       "sidewinder","wizard")
MAPS={"beavercreek","bloodgulch","boardingaction","carousel","chillout",
      "damnation","hangemhigh","longest","prisoner","putput","ratrace",
      "sidewinder","wizard"}

def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def raw_cases():
    maps=ROOT/"build/retail-maps/decompressed"
    cases=[]; identities={}; exact_tie=None; vertex_tie=None; grazing_case=None; exact_zero_case=None
    for name in ORDER:
        path=maps/f"{name}.map"
        header=source.mapinfo.read_header(path); index=source.tagindex.TagIndex.read(path)
        region,_,_=source.read_xbox_tag_region(path)
        locs=source.bsp_tools.locate(index,region,header.decompressed_size)
        if len(locs)!=1: raise SystemExit(f"expected one MP BSP for {name}, got {len(locs)}")
        row=source.audit_bsp(path,locs[0]); identities[name]=sha(path)
        if name=="beavercreek":
            if not row["exact_ties"]:
                raise SystemExit("Beaver Creek source oracle has no exact edge tie")
            exact_tie={**row["exact_ties"][0],"map_id":101+ORDER.index(name),"map":name}
            if not row["vertex_ties"]:
                raise SystemExit("Beaver Creek source oracle has no exact vertex tie")
            vertex_tie={**row["vertex_ties"][0],"map_id":101+ORDER.index(name),"map":name}
            if not row["grazing_cases"]:
                raise SystemExit("Beaver Creek source oracle has no grazing case")
            grazing_case={**row["grazing_cases"][0],"map_id":101+ORDER.index(name),"map":name}
            if not row["exact_zero_cases"]:
                raise SystemExit("Beaver Creek source oracle has no exact-zero case")
            exact_zero_case={**row["exact_zero_cases"][0],"map_id":101+ORDER.index(name),"map":name}
        if len(row["qualified"])!=2: raise SystemExit(f"no full two-face pair for {name}")
        for q in row["qualified"]:
            cases.append({**q,"map_id":101+ORDER.index(name),"map":name})
    if exact_tie is None or vertex_tie is None: raise SystemExit("no source-derived tie case selected")
    return cases,identities,exact_tie,vertex_tie,grazing_case,exact_zero_case

def cfloat(x):
    value=f"{float(x):.9g}"
    if "." not in value and "e" not in value.lower(): value += ".0"
    return value+"f"

def main():
    cases,identities,exact_tie,vertex_tie,grazing_case,exact_zero_case=raw_cases()
    out=ROOT/"build"/f"m2-mp-edge-runtime-{time.time_ns()}"
    out.mkdir(parents=True,exist_ok=True)
    # Keep generated source, exact run log and executable for independent audit.
    header=["typedef struct hcu_mp_edge_golden { unsigned map_id; int adjacent0, adjacent1;"
            " int surface, material_index, material_type, plane_designator, leaf;"
            " float t, start[3], vector[3]; } hcu_mp_edge_golden;",
            "static const hcu_mp_edge_golden hcu_mp_edge_goldens[] = {"]
    for q in cases:
        a,b=q["pair"]
        header.append("{%du,%d,%d,%d,%d,%d,%d,%d,%s,{%s},{%s}}," % (
            q["map_id"],a,b,q["target"],q["material_index"],q["material_type"],
            q["plane_designator"],q["leaf"],cfloat(q["t"]),
            ",".join(cfloat(v) for v in q["start"]),
            ",".join(cfloat(v) for v in q["vector"])))
    header += ["};", "#define HCU_MP_EDGE_GOLDEN_COUNT (sizeof(hcu_mp_edge_goldens)/sizeof(hcu_mp_edge_goldens[0]))"]
    tie=exact_tie
    header += ["typedef struct hcu_mp_exact_tie_golden { unsigned map_id; int adjacent0, adjacent1;"
        " int material_index, material_type, leaf; float t, start[3], vector[3]; } hcu_mp_exact_tie_golden;",
        "static const hcu_mp_exact_tie_golden hcu_mp_exact_tie = {%du,%d,%d,%d,%d,%d,%s,{%s},{%s}};" % (
            tie["map_id"],tie["pair"][0],tie["pair"][1],tie["material_index"],tie["material_type"],
            tie["leaf"],cfloat(tie["t"]),",".join(cfloat(v) for v in tie["start"]),
            ",".join(cfloat(v) for v in tie["vector"])),
        "static const int hcu_mp_exact_tie_allowed[] = {"+
            ",".join(str(v) for v in tie["allowed_selected_faces"])+"};"]
    vtx=vertex_tie
    header += ["typedef struct hcu_mp_vertex_tie_golden { unsigned map_id; int contact_count;"
        " int material_index, material_type, leaf; float t, start[3], vector[3]; } hcu_mp_vertex_tie_golden;",
        "static const hcu_mp_vertex_tie_golden hcu_mp_vertex_tie = {%du,%d,%d,%d,%d,%s,{%s},{%s}};" % (
            vtx["map_id"],len(vtx["raw_contact_set"]),vtx["material_index"],
            vtx["material_type"],vtx["leaf"],cfloat(vtx["t"]),
            ",".join(cfloat(x) for x in vtx["start"]),
            ",".join(cfloat(x) for x in vtx["vector"])),
        "static const int hcu_mp_vertex_tie_contact[] = {"+
            ",".join(str(x) for x in vtx["raw_contact_set"])+"};",
        "static const int hcu_mp_vertex_tie_allowed[] = {"+
            ",".join(str(x) for x in vtx["allowed_selected_faces"])+"};"]
    graze=grazing_case
    header += ["typedef struct hcu_mp_grazing_golden { unsigned map_id; int surface, material_index, material_type, plane_designator, leaf; float incidence_cosine, t, start[3], vector[3]; } hcu_mp_grazing_golden;",
        "static const hcu_mp_grazing_golden hcu_mp_grazing = {%du,%d,%d,%d,%d,%d,%s,%s,{%s},{%s}};" % (
            graze["map_id"],graze["surface"],graze["material_index"],graze["material_type"],
            graze["plane_designator"],graze["leaf"],cfloat(graze["incidence_cosine"]),cfloat(graze["t"]),
            ",".join(cfloat(v) for v in graze["start"]),
            ",".join(cfloat(v) for v in graze["vector"])),
        "static const float hcu_mp_grazing_epsilon = %s;" % cfloat(graze["epsilon"])]
    zero=exact_zero_case
    header += ["typedef struct hcu_mp_exact_zero_golden { unsigned map_id; int surface, material_index, material_type, plane_designator, leaf; float t, plane_residual, start[3], vector[3]; } hcu_mp_exact_zero_golden;",
        "static const hcu_mp_exact_zero_golden hcu_mp_exact_zero = {%du,%d,%d,%d,%d,%d,%s,%s,{%s},{%s}};" % (
            zero["map_id"],zero["surface"],zero["material_index"],zero["material_type"],
            zero["plane_designator"],zero["leaf"],cfloat(zero["t"]),cfloat(zero["plane_residual"]),
            ",".join(cfloat(v) for v in zero["start"]),
            ",".join(cfloat(v) for v in zero["vector"]))]
    (out/"hcu_mp_edge_golden.h").write_text("\n".join(header)+"\n")

    test_src=(ROOT/"tests/test_hcu_mp_capacity.py").read_text()
    test_src=test_src.replace(
        "ROOT = Path(__file__).resolve().parents[1]",
        f"ROOT = Path({str(ROOT)!r})")
    # Preserve the test's TemporaryDirectory: the native test must be runnable
    # once in the sandbox (which skips ILP32) and again outside it. Only the
    # explicitly copied acceptance artifacts below persist under `out`.
    old_sources='''            sources = [ROOT / "tests/hcu_mp_capacity_main.c",'''
    injection='''            main_source = (ROOT / "tests/hcu_mp_capacity_main.c").read_text()
            main_source = main_source.replace(
                '#include "hcu_mp_lifecycle_generated.h"',
                '#include "hcu_mp_lifecycle_generated.h"\\n#include "hcu_mp_edge_golden.h"')
            query = r"""
static void assert_mp_shared_edge(unsigned map_id)
{
    unsigned i, matched=0;
    for (i=0; i<HCU_MP_EDGE_GOLDEN_COUNT; ++i) {
        const hcu_mp_edge_golden *g=&hcu_mp_edge_goldens[i];
        real_point3d start; real_vector3d vector; struct collision_result result;
        if (g->map_id != map_id) continue;
        start=(real_point3d){g->start[0],g->start[1],g->start[2]};
        vector=(real_vector3d){g->vector[0],g->vector[1],g->vector[2]};
        memset(&result,0xCD,sizeof(result));
        assert(collision_test_vector(FLAG(_collision_test_structure_bit) |
            FLAG(_collision_test_front_facing_surfaces_bit), &start,&vector,NONE,&result));
        assert(result.type == _collision_result_structure);
        assert(result.surface_index == g->surface);
        assert(result.surface_index == g->adjacent0 || result.surface_index == g->adjacent1);
        assert(result.material_index == g->material_index);
        assert(result.material_type == g->material_type);
        assert(result.plane_designator == g->plane_designator);
        assert(result.start_location.leaf_index == g->leaf);
        assert(fabsf(result.t-g->t) < 0.0002f);
        ++matched;
        printf("mp-shared-edge map=%u adjacent=%d,%d selected=%d leaf=%d t=%.7g status=passed\\n",
            map_id,g->adjacent0,g->adjacent1,result.surface_index,
            result.start_location.leaf_index,result.t);
    }
    assert(matched == 2);
}
static void assert_mp_exact_edge_tie(unsigned map_id)
{
    real_point3d start; real_vector3d vector; struct collision_result result;
    unsigned i, valid=0;
    if (map_id != hcu_mp_exact_tie.map_id) return;
    start=(real_point3d){hcu_mp_exact_tie.start[0],hcu_mp_exact_tie.start[1],hcu_mp_exact_tie.start[2]};
    vector=(real_vector3d){hcu_mp_exact_tie.vector[0],hcu_mp_exact_tie.vector[1],hcu_mp_exact_tie.vector[2]};
    memset(&result,0xCD,sizeof(result));
    assert(collision_test_vector(FLAG(_collision_test_structure_bit) |
        FLAG(_collision_test_front_facing_surfaces_bit),&start,&vector,NONE,&result));
    assert(result.type == _collision_result_structure);
    assert(result.surface_index == hcu_mp_exact_tie.adjacent0 ||
        result.surface_index == hcu_mp_exact_tie.adjacent1);
    assert(result.material_index == hcu_mp_exact_tie.material_index);
    assert(result.material_type == hcu_mp_exact_tie.material_type);
    assert(result.start_location.leaf_index == hcu_mp_exact_tie.leaf);
    assert(fabsf(result.t-hcu_mp_exact_tie.t) < 0.0002f);
    for (i=0;i<sizeof(hcu_mp_exact_tie_allowed)/sizeof(hcu_mp_exact_tie_allowed[0]);++i)
        if (result.surface_index == hcu_mp_exact_tie_allowed[i]) valid=1;
    assert(valid);
    printf("mp-exact-edge-tie map=%u adjacent=%d,%d selected=%ld leaf=%ld t=%.7g status=passed\\n",
        map_id,hcu_mp_exact_tie.adjacent0,hcu_mp_exact_tie.adjacent1,
        result.surface_index,result.start_location.leaf_index,result.t);
}
static void assert_mp_exact_vertex_tie(unsigned map_id)
{
    real_point3d start; real_vector3d vector; struct collision_result result;
    unsigned i, contact=0, allowed=0;
    if (map_id != hcu_mp_vertex_tie.map_id) return;
    start=(real_point3d){hcu_mp_vertex_tie.start[0],hcu_mp_vertex_tie.start[1],hcu_mp_vertex_tie.start[2]};
    vector=(real_vector3d){hcu_mp_vertex_tie.vector[0],hcu_mp_vertex_tie.vector[1],hcu_mp_vertex_tie.vector[2]};
    memset(&result,0xCD,sizeof(result));
    assert(collision_test_vector(FLAG(_collision_test_structure_bit) |
        FLAG(_collision_test_front_facing_surfaces_bit),&start,&vector,NONE,&result));
    assert(result.type == _collision_result_structure);
    assert(result.material_index == hcu_mp_vertex_tie.material_index);
    assert(result.material_type == hcu_mp_vertex_tie.material_type);
    assert(result.start_location.leaf_index == hcu_mp_vertex_tie.leaf);
    assert(fabsf(result.t-hcu_mp_vertex_tie.t) < 0.0002f);
    for (i=0;i<sizeof(hcu_mp_vertex_tie_contact)/sizeof(hcu_mp_vertex_tie_contact[0]);++i)
        if (result.surface_index == hcu_mp_vertex_tie_contact[i]) contact=1;
    for (i=0;i<sizeof(hcu_mp_vertex_tie_allowed)/sizeof(hcu_mp_vertex_tie_allowed[0]);++i)
        if (result.surface_index == hcu_mp_vertex_tie_allowed[i]) allowed=1;
    assert(contact && allowed && hcu_mp_vertex_tie.contact_count >= 3);
    printf("mp-exact-vertex-tie map=%u contact_faces=%d selected=%ld leaf=%ld t=%.7g status=passed\\n",
        map_id,hcu_mp_vertex_tie.contact_count,result.surface_index,
        result.start_location.leaf_index,result.t);
}
static void assert_mp_grazing(unsigned map_id)
{
    real_point3d start; real_vector3d vector; struct collision_result result;
    if (map_id != hcu_mp_grazing.map_id) return;
    start=(real_point3d){hcu_mp_grazing.start[0],hcu_mp_grazing.start[1],hcu_mp_grazing.start[2]};
    vector=(real_vector3d){hcu_mp_grazing.vector[0],hcu_mp_grazing.vector[1],hcu_mp_grazing.vector[2]};
    memset(&result,0xCD,sizeof(result));
    assert(collision_test_vector(FLAG(_collision_test_structure_bit) |
        FLAG(_collision_test_front_facing_surfaces_bit),&start,&vector,NONE,&result));
    assert(result.type == _collision_result_structure);
    assert(result.surface_index == hcu_mp_grazing.surface);
    assert(result.material_index == hcu_mp_grazing.material_index);
    assert(result.material_type == hcu_mp_grazing.material_type);
    assert(result.plane_designator == hcu_mp_grazing.plane_designator);
    assert(result.start_location.leaf_index == hcu_mp_grazing.leaf);
    assert(fabsf(result.t-hcu_mp_grazing.t) < 0.0002f);
    printf("mp-grazing map=%u surface=%ld leaf=%ld incidence_cosine=%.4f t=%.7g status=passed\\n",
        map_id,result.surface_index,result.start_location.leaf_index,
        hcu_mp_grazing.incidence_cosine,result.t);
}
static void assert_mp_exact_zero(unsigned map_id)
{
    real_point3d start; real_vector3d vector; struct collision_result result;
    if (map_id != hcu_mp_exact_zero.map_id) return;
    start=(real_point3d){hcu_mp_exact_zero.start[0],hcu_mp_exact_zero.start[1],hcu_mp_exact_zero.start[2]};
    vector=(real_vector3d){hcu_mp_exact_zero.vector[0],hcu_mp_exact_zero.vector[1],hcu_mp_exact_zero.vector[2]};
    memset(&result,0xCD,sizeof(result));
    assert(collision_test_vector(FLAG(_collision_test_structure_bit) |
        FLAG(_collision_test_front_facing_surfaces_bit),&start,&vector,NONE,&result));
    assert(result.type == _collision_result_structure);
    assert(result.surface_index == hcu_mp_exact_zero.surface);
    assert(result.material_index == hcu_mp_exact_zero.material_index);
    assert(result.material_type == hcu_mp_exact_zero.material_type);
    assert(result.plane_designator == hcu_mp_exact_zero.plane_designator);
    assert(result.start_location.leaf_index == hcu_mp_exact_zero.leaf);
    assert(fabsf(result.t-hcu_mp_exact_zero.t) < 0.0002f);
            printf("mp-near-zero-boundary map=%u surface=%ld leaf=%ld raw_t=%.9g residual=%.9g ce_t=%.9g status=passed\\n",
        map_id,result.surface_index,result.start_location.leaf_index,
        hcu_mp_exact_zero.t,hcu_mp_exact_zero.plane_residual,result.t);
}
"""
            anchor = "static void mp_query(unsigned map_id)\\n{"
            if main_source.count(anchor) != 1:
                raise AssertionError("mp_query insertion seam changed")
            main_source = main_source.replace(anchor, query + "\\n" + anchor)
            call_anchor = "map_index = map_id - 101u;"
            if main_source.count(call_anchor) != 1:
                raise AssertionError("map id insertion seam changed")
            main_source = main_source.replace(call_anchor,
                call_anchor + "\\n\\tassert_mp_shared_edge(map_id);\\n\\tassert_mp_exact_edge_tie(map_id);\\n\\tassert_mp_exact_vertex_tie(map_id);\\n\\tassert_mp_grazing(map_id);\\n\\tassert_mp_exact_zero(map_id);")
            generated_main = temp / "hcu_mp_capacity_edge_main.c"
            generated_main.write_text(main_source)
            sources = [generated_main,'''
    if test_src.count(old_sources)!=1: raise SystemExit("fixture source-list seam changed")
    test_src=test_src.replace(old_sources,injection)
    generated_header_copy=(f"            shutil.copy2(ROOT / {str((out / 'hcu_mp_edge_golden.h').relative_to(ROOT))!r}, "
                          "temp / 'hcu_mp_edge_golden.h')\n")
    if test_src.count("            generated_main.write_text(main_source)\n") != 1:
        raise SystemExit("generated header copy seam changed")
    test_src=test_src.replace("            generated_main.write_text(main_source)\n",
        "            generated_main.write_text(main_source)\n" + generated_header_copy)
    generated_test=out/"test_hcu_mp_edge_generated.py"
    generated_test.write_text(test_src)
    retained=out/"retained"
    retained.mkdir(parents=True,exist_ok=True)
    proc=subprocess.run([sys.executable,"-m","unittest","-v",
        f"{generated_test.stem}.MultiplayerHostCollisionMatrix.test_host_sized_13_map_lifecycle_and_collision"],
        cwd=ROOT,env={**__import__("os").environ,
            "HCU_MP_CAPACITY_RETENTION_DIR":str(retained.relative_to(ROOT)),
            "PYTHONPATH":str(ROOT/"tests")+":"+str(ROOT/"tools")+":"+str(ROOT/"submodules/halo-ps2/tools")+":"+str(out)},
        capture_output=True,text=True)
    (out/"native-run.log").write_text(proc.stdout+proc.stderr)
    if proc.returncode == 0:
        shutil.copy2(out/"hcu_mp_edge_golden.h",retained/"hcu_mp_edge_golden.h")
    manifest={"schema":"hcu-mp-shared-edge-ce-runtime-v1","scope":"13 stock multiplayer maps; campaign excluded",
        "source_map_sha256":identities,"cases":cases,"exact_tie_case":exact_tie,
        "vertex_tie_case":vertex_tie,"grazing_case":grazing_case,
        "near_zero_boundary_case":exact_zero_case,"diagnostic_host_ilp32_only":True,
        "not_ps2_ram_or_ee_evidence":True,"test_sha256":sha(generated_test),
        "golden_sha256":sha(out/"hcu_mp_edge_golden.h"),"runner_exit_code":proc.returncode,
        "runner_stdout_sha256":hashlib.sha256(proc.stdout.encode()).hexdigest(),
        "runner_stderr_sha256":hashlib.sha256(proc.stderr.encode()).hexdigest(),
        "native_log_sha256":sha(out/"native-run.log"),
        "retained_run_log_sha256":sha(retained/"run.log") if (retained/"run.log").is_file() else None,
        "retained_elf_sha256":sha(retained/"mp-weather-wind-location") if (retained/"mp-weather-wind-location").is_file() else None,
        "retained_linkmap_sha256":sha(retained/"mp-weather-wind-location.map") if (retained/"mp-weather-wind-location.map").is_file() else None,
        "retained_golden_sha256":sha(retained/"hcu_mp_edge_golden.h") if (retained/"hcu_mp_edge_golden.h").is_file() else None,
        "parent_head":subprocess.check_output(["git","rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "hcu_head":subprocess.check_output(["git","-C",str(ROOT/"submodules/halo-ce-universal"),"rev-parse","HEAD"],cwd=ROOT,text=True).strip(),
        "halo_ps2_head":subprocess.check_output(["git","-C",str(ROOT/"submodules/halo-ps2"),"rev-parse","HEAD"],cwd=ROOT,text=True).strip()}
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n")
    print(proc.stdout,end=""); print(proc.stderr,end="",file=sys.stderr)
    print("artifacts",out.relative_to(ROOT),"manifest_sha256",sha(out/"manifest.json"))
    return proc.returncode

if __name__=="__main__": raise SystemExit(main())
