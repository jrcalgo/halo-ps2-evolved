#!/usr/bin/env python3
"""Attribute the gameplay ELF's retained code and data to source files.

Inputs are the GNU ld map of the gameplay machine, the closure objects the map
links (build/hcu-ps2-closure/all-no-bootstrap-memory/*.o and result.json) and
the parent objects the map names. The tool:

1. parses every retained input section of the memory map ("Linker script and
   memory map" onward; a section line may wrap its address and object onto the
   next line), keeping .text, .rodata, .data and .bss kinds;
2. attributes each section to its object and then to a source file: closure
   units through result.json (source/a/b.c -> source_a_b.c.o), parent objects
   through their relative path, and rooted.o's sections through the defining
   symbol's object (rooted.o is the LTO-merged reachable image);
3. builds a section-level reference graph from objdump -r of the same objects
   and computes which roots keep each retained function alive;
4. for a set of candidate source files, reports the bytes that would disappear
   if those sources were removed from the reachable set, the roots that reach
   them, and the callers that keep them alive (the edges a compile-time
   exclusion or a rooting change would have to cut).

Sizes in the attribution come from the map. Reachability and the recoverable
estimate use the same objects' section sizes (objdump -h), so they are
estimates of what a cut removes, not a relink.

Usage:
  python3 -I tools/c2_elf_text_attribution.py \
      --map build/hcu-parent-link-probe/hcu-gameplay-machine.map \
      --closure build/hcu-ps2-closure/all-no-bootstrap-memory \
      --objdump build/toolchain/install/ee/bin/mips64r5900el-ps2-elf-objdump \
      --out-json docs/reports/m2-c2-r7-elf-attrib-2026-10-24.json
"""

import argparse
import collections
import fnmatch
import json
import os
import re
import subprocess
import sys

KINDS = (
    ("text", (".text",)),
    ("rodata", (".rodata", ".sdata2")),
    ("data", (".data", ".sdata")),
    ("bss", (".bss", ".sbss")),
)
MAP_HEADER = "Linker script and memory map"
SECTION_RE = re.compile(r"^ (\.\S+|\*?COMMON\*?)$")
ADDR_LINE_RE = re.compile(r"^\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+(\S.*)$")
SYMBOL_ADDR_LINE_RE = re.compile(r"^\s+(0x[0-9a-fA-F]+)\s+(\S+)$")
RELAX_RE = re.compile(r"^\s+(0x[0-9a-fA-F]+) \(size before relaxing\)\s*$")
INLINE_RE = re.compile(r"^ (\.\S+|\*?COMMON\*?)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+(\S.*)$")


def section_kind(name):
    """Return text/rodata/data/bss for a section name, or None."""
    if name.startswith("COMMON") or name.startswith("*COMMON*"):
        return "bss"
    for kind, prefixes in KINDS:
        for prefix in prefixes:
            if name == prefix or name.startswith(prefix + "."):
                return kind
    return None


def parse_map(lines):
    """Return retained input sections [{name, kind, addr, size, path}] of a GNU ld map."""
    start = None
    for i, line in enumerate(lines):
        if line.strip() == MAP_HEADER:
            start = i
            break
    if start is None:
        raise ValueError("no '%s' in map" % MAP_HEADER)
    out = []
    i = start + 1
    n = len(lines)
    while i < n:
        line = lines[i]
        m = INLINE_RE.match(line)
        if m:
            name, addr, size, path = m.group(1), m.group(2), m.group(3), m.group(4)
            i += 1
        else:
            m = SECTION_RE.match(line)
            if m and i + 1 < n:
                a = ADDR_LINE_RE.match(lines[i + 1])
                if a:
                    name, addr, size, path = m.group(1), a.group(1), a.group(2), a.group(3)
                    i += 2
                else:
                    i += 1
                    continue
            else:
                i += 1
                continue
        if name in ("COMMON", "*COMMON*"):
            # -fcommon block: one entry per object, with each symbol on the
            # following lines (address, name). A symbol's size is the distance
            # to the next symbol's address, the last one's to the block's end.
            syms = []
            while i < n:
                sm = SYMBOL_ADDR_LINE_RE.match(lines[i])
                if not sm:
                    break
                syms.append((int(sm.group(1), 16), sm.group(2)))
                i += 1
            block_end = int(addr, 16) + int(size, 16)
            syms.sort()
            if not syms:
                syms = [(int(addr, 16), "?")]
            for k, (saddr, sname) in enumerate(syms):
                send = syms[k + 1][0] if k + 1 < len(syms) else block_end
                if send - saddr > 0:
                    out.append({
                        "name": "COMMON:" + sname,
                        "kind": "bss",
                        "addr": saddr,
                        "size": send - saddr,
                        "path": path.strip(),
                        "relaxed_from_map": False,
                        "common_block": int(addr, 16),
                        "common_block_size": size_v,
                    })
            continue
        kind = section_kind(name)
        size_v = int(size, 16)
        relaxed = False
        # ld reports a mergeable string section (.rodata.str1.N) with the distance
        # to the next merged section and prints the section's own size on a
        # "(size before relaxing)" line. The real size is never larger than that.
        if i < n:
            r = RELAX_RE.match(lines[i])
            if r:
                before = int(r.group(1), 16)
                if before < size_v:
                    size_v = before
                    relaxed = True
                i += 1
        if kind is None or size_v == 0 or path.startswith("*fill*"):
            continue
        out.append({
            "name": name,
            "kind": kind,
            "addr": int(addr, 16),
            "size": size_v,
            "path": path.strip(),
            "relaxed_from_map": relaxed,
        })
    return out


def elf_symbol_sizes(nm, elf):
    """{name: (addr, size)} for the final ELF's data symbols (nm -S)."""
    out = {}
    for line in run([nm, "-S", elf]).splitlines():
        tok = line.split()
        if len(tok) == 4 and tok[2] in ("b", "B", "d", "D", "r", "R") and re.match(r"^[0-9a-fA-F]+$", tok[0]):
            out.setdefault(tok[3], (int(tok[0], 16), int(tok[1], 16)))
    return out


def declared_common_sizes(sections, objdump, closure, closure_name, elf_syms=None):
    """Set each -fcommon symbol's size to its object's declared size.

    The map lists a COMMON block's symbols with addresses whose gaps do not
    match the block header's size, so a piece's own size is unreliable. A
    symbol takes its declared size (objdump -t) when that is no larger than
    its piece.
    """
    declared = {}
    names = set(CLOSURE_NAMES) | {closure_name, os.path.basename(closure)}
    for b in os.listdir(closure):
        path = os.path.join(closure, b)
        if not b.endswith(".o") or os.path.basename(os.path.dirname(path)) not in names:
            continue
        _, _, commons = object_symbols(objdump, path)
        for name, size in commons.items():
            declared.setdefault(name, size)
    out = []
    for sec in sections:
        if sec["name"].startswith("COMMON:"):
            sym = sec["name"][len("COMMON:"):]
            # The final ELF's own symbol size is exact when the address agrees
            # (the object declarations can be smaller than the linked symbol).
            hit = (elf_syms or {}).get(sym)
            if hit is not None and hit[0] == sec["addr"]:
                sec = dict(sec, size=hit[1], size_source="elf")
            else:
                want = declared.get(sym)
                if want is not None and want <= sec["size"]:
                    sec = dict(sec, size=want, size_source="declared")
        out.append(sec)
    return out


def map_output_totals(lines):
    """Output-section sizes the map header states, {kind: bytes}."""
    totals = {}
    for line in lines:
        m = re.match(r"^\.(text|rodata|data|bss)\s+(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s*$", line)
        if m and m.group(1) not in totals:
            totals[m.group(1)] = int(m.group(3), 16)
    return totals


def reconcile(sections, totals):
    """Add one residual entry per kind so the attributed bytes equal the map's header totals."""
    out = list(sections)
    for kind, want in totals.items():
        have = sum(s["size"] for s in sections if s["kind"] == kind)
        if want > have:
            out.append({
                "name": "map-residual:" + kind,
                "kind": kind,
                "addr": 0,
                "size": want - have,
                "path": "map-residual",
                "relaxed_from_map": False,
            })
    return out


def unit_map_from_result(result_path):
    """Map closure object basename -> source path from result.json units."""
    with open(result_path, encoding="utf-8") as f:
        data = json.load(f)
    out = {}
    for source in data.get("units", {}):
        out[source.replace("/", "_") + ".o"] = source
    return out


CLOSURE_NAMES = set()


def source_for(path, closure_dir, parent_marker, units, sym_owner=None, section=None):
    """Attribute an object path (and section for rooted.o) to a source label.

    A closure object is one whose directory has the closure's name (the map
    names the original build directory; a snapshot keeps the same name for it).
    """
    base = os.path.basename(path)
    names = CLOSURE_NAMES | {os.path.basename(closure_dir)}
    if os.path.basename(os.path.dirname(path)) in names:
        if base == "rooted.o":
            owner = sym_owner(section) if sym_owner else None
            if owner is None:
                return "rooted.o:unresolved"
            return source_for(owner, closure_dir, parent_marker, units)
        if base in units:
            return units[base]
        return "closure:" + base
    if parent_marker and parent_marker in path:
        rel = path.split(parent_marker, 1)[1].lstrip(os.sep)
        rel = rel[:-2] + ".c" if rel.endswith(".o") else rel
        return "parent:" + rel
    if "/toolchain/install/ps2sdk/" in path:
        return "sdk:" + os.path.basename(os.path.dirname(path))
    if "/toolchain/install/ee/" in path:
        return "gcc-lib:" + base
    return "other:" + base


def closure_abs(path):
    return os.path.abspath(path)


def run(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError("%s failed: %s" % (" ".join(cmd), proc.stderr.strip()))
    return proc.stdout


def object_symbols(objdump, path):
    """Return (defs, globals, commons) for an object.

    defs {symbol: section}; a -fcommon symbol's section is "COMMON:<name>" and
    commons {name: size} gives its size from the object's symbol table.
    """
    defs = {}
    globals_ = {}
    commons = {}
    text = run([objdump, "-t", path])
    for line in text.splitlines():
        tok = line.split()
        if len(tok) < 4 or not re.match(r"^[0-9a-fA-F]{8}$", tok[0]):
            continue
        name = tok[-1]
        section = tok[-3]
        if section in ("*UND*", "*ABS*"):
            continue
        if section == "*COM*":
            section = "COMMON:" + name
            commons[name] = int(tok[-2], 16)
        defs[name] = section
        if " g " in line or " w " in line or "\tg " in line:
            globals_[name] = section
    return defs, globals_, commons


def object_section_sizes(objdump, path):
    text = run([objdump, "-h", path])
    sizes = {}
    for line in text.splitlines():
        tok = line.split()
        if len(tok) >= 3 and tok[0].isdigit():
            try:
                sizes[tok[1]] = int(tok[2], 16)
            except ValueError:
                pass
    return sizes


def object_relocations(objdump, path):
    """Return {section: [value, ...]} of the relocations of each section."""
    text = run([objdump, "-r", path])
    rel = collections.defaultdict(list)
    current = None
    for line in text.splitlines():
        m = re.match(r"^RELOCATION RECORDS FOR \[(.+)\]:$", line)
        if m:
            current = m.group(1)
            continue
        if current is None:
            continue
        tok = line.split()
        if len(tok) == 3 and re.match(r"^[0-9a-fA-F]{8}$", tok[0]):
            value = tok[2]
            value = re.sub(r"\+0x[0-9a-fA-F]+$", "", value)
            rel[current].append(value)
    return rel


# Closure objects that duplicate other units' functions (d20-game-init-closure.o
# defines 2,263 of them; layer.o and rooted.o are merged images). They are never
# a symbol's home, so each symbol resolves to its per-unit object.
AGGREGATE_OBJECTS = ("d20-game-init-closure.o", "layer.o", "rooted.o")


def build_graph(objdump, paths):
    """Section-level reference graph over the given objects.

    Nodes are (object path, section name). Only code and data sections keep
    edges; .pdr, .reginfo and debug sections are ignored. Global symbols are
    taken from the first per-unit object defining them; a symbol that only a
    file defines locally falls back to that file's definition.
    """
    local_defs = {}
    global_defs = {}
    any_defs = {}
    sizes = {}
    relocs = {}
    for path in paths:
        if os.path.basename(path) in AGGREGATE_OBJECTS:
            continue
        defs, globs, commons = object_symbols(objdump, path)
        local_defs[path] = defs
        for name, sec in globs.items():
            global_defs.setdefault(name, (path, sec))
        for name, sec in defs.items():
            any_defs.setdefault(name, (path, sec))
        sizes[path] = object_section_sizes(objdump, path)
        for name, size in commons.items():
            sizes[path]["COMMON:" + name] = size
        relocs[path] = object_relocations(objdump, path)
    for name, hit in any_defs.items():
        global_defs.setdefault(name, hit)
    edges = collections.defaultdict(set)
    for path, by_sec in relocs.items():
        for sec, values in by_sec.items():
            if section_kind(sec) is None:
                continue
            src = (path, sec)
            for value in values:
                target = None
                if value in local_defs[path]:
                    target = (path, local_defs[path][value])
                elif value.startswith(".") and value in sizes[path]:
                    target = (path, value)
                elif value in global_defs:
                    target = global_defs[value]
                if target is not None and target != src:
                    edges[src].add(target)
    return edges, global_defs, sizes


def reach(edges, roots):
    """BFS from roots; return (visited set, parent map)."""
    parent = {r: None for r in roots}
    queue = collections.deque(roots)
    while queue:
        node = queue.popleft()
        for nxt in edges.get(node, ()):
            if nxt not in parent:
                parent[nxt] = node
                queue.append(nxt)
    return set(parent), parent


def path_to(parent, node):
    chain = []
    while node is not None:
        chain.append(node)
        node = parent[node]
    return list(reversed(chain))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--map", required=True)
    ap.add_argument("--closure", required=True)
    ap.add_argument("--result", default=None)
    ap.add_argument("--parent-marker", default="/parent-hcu-gameplay-")
    ap.add_argument("--closure-name", default="all-no-bootstrap-memory",
                    help="directory name the map uses for the closure objects (also the snapshot's)")
    ap.add_argument("--objdump", required=True)
    ap.add_argument("--nm", default=None, help="nm for the ELF symbol sizes (default: next to --objdump)")
    ap.add_argument("--elf", default=None, help="final ELF: its symbol sizes fix COMMON symbol sizes")
    ap.add_argument("--out-json", required=True)
    ap.add_argument("--candidates", default=None,
                    help="JSON file with {'classes': {label: [glob pattern over source labels, ...]}}")
    args = ap.parse_args(argv)
    CLOSURE_NAMES.add(args.closure_name)

    with open(args.map, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    sections = parse_map(lines)
    elf_syms = None
    if args.elf:
        elf_syms = elf_symbol_sizes(args.nm or args.objdump.replace("objdump", "nm"), args.elf)
    sections = declared_common_sizes(sections, args.objdump, closure_abs(args.closure), args.closure_name, elf_syms)
    sections = reconcile(sections, map_output_totals(lines))
    closure = os.path.abspath(args.closure)
    result_path = args.result or os.path.join(closure, "result.json")
    units = unit_map_from_result(result_path)
    with open(result_path, encoding="utf-8") as f:
        rooted = json.load(f)["rooted_link"]["roots"]

    # The graph needs every closure unit (rooted.o merged them, so most of them
    # never appear as map sections) plus the parent objects the map names.
    closure_units = sorted(os.path.join(closure, b) for b in os.listdir(closure)
                           if b.endswith(".o") and b != "rooted.o")
    map_objects = {s["path"] for s in sections if s["path"].endswith(".o") and os.path.exists(s["path"])}
    objects = sorted(set(closure_units) | map_objects)
    graph_objects = [p for p in objects if os.path.basename(p) not in AGGREGATE_OBJECTS]
    edges, gdefs, sizes = build_graph(args.objdump, graph_objects)

    def sym_owner(section):
        """rooted.o section (.text.NAME) -> defining closure/parent object."""
        if not section:
            return None
        if section.startswith("COMMON:"):
            sym = section[len("COMMON:"):]
        else:
            sym = re.sub(r"^\.(text|rodata|data|bss|sdata|sbss)(\.|$)", "", section)
        if not sym:
            return None
        hit = gdefs.get(sym)
        return hit[0] if hit else None

    attribution = []
    for s in sections:
        src = source_for(s["path"], closure, args.parent_marker, units,
                         sym_owner=sym_owner, section=s["name"])
        attribution.append(dict(s, source=src, object=os.path.basename(s["path"])))

    by_source = collections.defaultdict(lambda: collections.Counter())
    by_function = []
    for a in attribution:
        by_source[a["source"]][a["kind"]] += a["size"]
        if a["kind"] == "text" and a["name"].startswith(".text."):
            by_function.append({"function": a["name"][6:], "size": a["size"], "source": a["source"]})

    totals = collections.Counter()
    for a in attribution:
        totals[a["kind"]] += a["size"]

    top_sources = {}
    for kind in ("text", "rodata", "data", "bss"):
        ranked = sorted(by_source.items(), key=lambda kv: -kv[1][kind])
        top_sources[kind] = [{"source": k, "bytes": v[kind]} for k, v in ranked[:60] if v[kind] > 0]
    total_source = sorted(by_source.items(), key=lambda kv: -sum(kv[1].values()))
    top_sources["all"] = [{"source": k, "bytes": dict(v)} for k, v in total_source[:60]]
    top_functions = sorted(by_function, key=lambda f: -f["size"])[:60]

    report = {
        "format": "hcu-c2-r7-elf-attrib-v1",
        "map": os.path.abspath(args.map),
        "retained_sections": len(attribution),
        "retained_bytes_by_kind": dict(totals),
        "objects_resolved_on_disk": len(objects),
        "top_sources": top_sources,
        "top_functions": top_functions,
        "sections": attribution,
    }

    # Reachability and candidate analysis.
    roots = [gdefs[r] for r in rooted if r in gdefs]
    unresolved_roots = [r for r in rooted if r not in gdefs]
    node_source = {}

    def node_src(node):
        if node not in node_source:
            node_source[node] = source_for(node[0], closure, args.parent_marker, units,
                                           sym_owner=sym_owner, section=node[1])
        return node_source[node]

    all_visited, parent = reach(edges, roots)
    report["reachability"] = {
        "roots_total": len(rooted),
        "roots_resolved": len(roots),
        "roots_unresolved": unresolved_roots,
        "reachable_nodes": len(all_visited),
    }

    if args.candidates:
        with open(args.candidates, encoding="utf-8") as f:
            cand = json.load(f)["classes"]
        cand_results = {}
        all_labels = {node_src(n) for n in all_visited}
        for label, patterns in cand.items():
            src_set = {lab for lab in all_labels if any(fnmatch.fnmatch(lab, pat) for pat in patterns)}
            blocked = {n for n in all_visited if node_src(n) in src_set}
            blocked_edges = {k: {v for v in vs if v not in blocked} for k, vs in edges.items() if k not in blocked}
            keep_visited, _ = reach(blocked_edges, [r for r in roots if r not in blocked])
            def size_of(n):
                return sizes.get(n[0], {}).get(n[1], 0)
            full_bytes = sum(size_of(n) for n in all_visited if node_src(n) in src_set)
            removed = sum(size_of(n) for n in all_visited - keep_visited)
            # Callers outside the set that reference the set and are reachable.
            keepers = collections.Counter()
            for k, vs in edges.items():
                if k in blocked or k not in all_visited:
                    continue
                for v in vs:
                    if v in blocked:
                        keepers[node_src(k)] += 1
            rooted_by = []
            for r in roots:
                if r in blocked:
                    continue
            # Per blocked node the nearest root path, for the report.
            keeper_paths = []
            for n in sorted(blocked, key=lambda x: -size_of(x))[:20]:
                if n in parent:
                    keeper_paths.append({"node": n[1], "object": os.path.basename(n[0]),
                                         "path": [p[1] for p in path_to(parent, n)]})
            removed_nodes = all_visited - keep_visited
            by_src = collections.Counter()
            for n in removed_nodes:
                by_src[node_src(n)] += size_of(n)
            cand_results[label] = {
                "sources": sorted(src_set),
                "candidate_bytes_reachable": full_bytes,
                "bytes_removed_if_blocked": removed,
                "removed_by_source": by_src.most_common(25),
                "external_callers_into_set": keepers.most_common(40),
                "example_root_paths": keeper_paths,
            }
        # Union over every class, so overlapping classes are not counted twice.
        union_blocked = set()
        union_sources = set()
        for label, patterns in cand.items():
            union_sources |= {lab for lab in all_labels if any(fnmatch.fnmatch(lab, pat) for pat in patterns)}
        union_blocked = {n for n in all_visited if node_src(n) in union_sources}
        union_edges = {k: {v for v in vs if v not in union_blocked} for k, vs in edges.items() if k not in union_blocked}
        union_keep, _ = reach(union_edges, [r for r in roots if r not in union_blocked])
        union_removed = sum(sizes.get(n[0], {}).get(n[1], 0) for n in all_visited - union_keep)
        cand_results["union_of_classes"] = {
            "sources": sorted(union_sources),
            "bytes_removed_if_blocked": union_removed,
        }
        report["candidate_analysis"] = cand_results

    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
        f.write("\n")
    print("retained sections: %d; bytes by kind: %s" % (len(attribution), dict(totals)))
    print("reachable nodes: %d; roots resolved: %d of %d" % (len(all_visited), len(roots), len(rooted)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
