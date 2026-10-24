#!/usr/bin/env python3
"""Source-only screen for reproducible stock-MP shared-edge collision rays.

This deliberately does not call CE and cannot approve a runtime golden. It
requires each offset ray to have exactly one raw polygon intersection and the
serialized BSP3D/BSP2D traversal to select that same face.
"""
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

ROOT = Path(__file__).resolve().parents[1]
MAPS = {
    "beavercreek": "beavercreek", "bloodgulch": "bloodgulch",
    "boardingaction": "boardingaction", "carousel": "carousel",
    "chillout": "chillout", "damnation": "damnation",
    "hangemhigh": "hangemhigh", "longest": "longest",
    "prisoner": "prisoner", "putput": "putput", "ratrace": "ratrace",
    "sidewinder": "sidewinder", "wizard": "wizard",
}

sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT))
from halo2ps2 import bsp as bsp_tools, mapinfo, tagindex
from tools.ctag_schema_walk import read_xbox_tag_region


def f32(x):
    return struct.unpack("<f", struct.pack("<f", x))[0]


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def inside(poly, p, n, tol=1e-7):
    drop = max(range(3), key=lambda i: abs(n[i]))
    axes = [i for i in range(3) if i != drop]
    sign = 0
    for a, b in zip(poly, poly[1:] + poly[:1]):
        c = ((b[axes[0]]-a[axes[0]])*(p[axes[1]]-a[axes[1]]) -
             (b[axes[1]]-a[axes[1]])*(p[axes[0]]-a[axes[0]]))
        if abs(c) <= tol:
            return False
        s = 1 if c > 0 else -1
        if sign and s != sign:
            return False
        sign = s
    return True

def inside_inclusive(poly, p, n, tol=2e-5):
    """Inclusive polygon test for exact edge/vertex contact; nondegenerate only."""
    drop=max(range(3),key=lambda i:abs(n[i])); axes=[i for i in range(3) if i!=drop]
    signs=[]
    for a,b in zip(poly,poly[1:]+poly[:1]):
        cross=((b[axes[0]]-a[axes[0]])*(p[axes[1]]-a[axes[1]])-
               (b[axes[1]]-a[axes[1]])*(p[axes[0]]-a[axes[0]]))
        if abs(cross)>tol: signs.append(1 if cross>0 else -1)
    return bool(signs) and all(s==signs[0] for s in signs)


def audit_bsp(path, location):
    with path.open("rb") as f:
        f.seek(location.file_offset)
        image = f.read(location.size)
    root = struct.unpack_from("<I", image, 0)[0] - location.address
    def block(base, field, stride):
        count, address = struct.unpack_from("<II", image, base + field)
        off = address - location.address
        if count and (off < 0 or off + count*stride > len(image)):
            raise ValueError("raw block extent invalid")
        return count, off, stride
    materials = block(root, 0xA4, 20)
    cbsp = block(root, 0xB0, 96)
    if cbsp[0] != 1:
        raise ValueError("expected one collision BSP")
    base = cbsp[1]
    nodes, planes = block(base, 0x00, 12), block(base, 0x0C, 16)
    leaves, refs = block(base, 0x18, 8), block(base, 0x24, 8)
    b2nodes = block(base, 0x30, 20)
    surfaces, edges, vertices = (block(base, o, s) for o, s in
                                 ((0x3C, 12), (0x48, 24), (0x54, 16)))
    mats = [struct.unpack_from("<h", image, materials[1]+i*20+18)[0]
            for i in range(materials[0])]
    polys = []
    for si in range(surfaces[0]):
        so = surfaces[1]+si*12
        designator, first, flags, breakable, mi = struct.unpack_from("<iiBBh", image, so)
        ei, seen, points = first, set(), []
        for _ in range(9):
            if ei in seen or not 0 <= ei < edges[0]:
                points=[]; break
            seen.add(ei)
            eo=edges[1]+ei*24
            v0,v1,e0,e1,s0,s1=struct.unpack_from("<6i",image,eo)
            rev=int(s1==si)
            if (s0,s1)[rev] != si:
                points=[]; break
            vi=(v0,v1)[rev]
            if not 0 <= vi < vertices[0]:
                points=[]; break
            points.append(struct.unpack_from("<3f",image,vertices[1]+vi*16))
            ei=(e0,e1)[rev]
            if ei == first: break
        if len(points)<3 or ei != first:
            polys.append(None); continue
        pi=designator&0x7fffffff
        if not 0 <= pi < planes[0]:
            polys.append(None); continue
        plane=struct.unpack_from("<4f",image,planes[1]+pi*16)
        polys.append(dict(i=si, d=designator, flags=flags, br=breakable,
                          mi=mi, plane=plane, poly=points))
    def leaf(p):
        ix=0
        for _ in range(nodes[0]+1):
            if ix & 0x80000000:
                li=ix&0x7fffffff
                return li if li<leaves[0] else -1
            if not 0<=ix<nodes[0]: return -1
            pi,bk,fr=struct.unpack_from("<3I",image,nodes[1]+ix*12)
            pl=struct.unpack_from("<4f",image,planes[1]+pi*16)
            ix=fr if dot(pl[:3],p)-pl[3]>=0 else bk
            if ix==0xffffffff: return -1
        return -1
    def choose(li, d, point):
        pi=d&0x7fffffff
        plane=struct.unpack_from("<4f",image,planes[1]+pi*16)
        normal=plane[:3]; drop=max(range(3),key=lambda i:abs(normal[i]))
        proj=drop; sign=normal[proj]>0
        sign=sign != bool(d&0x80000000)
        lo=leaves[1]+li*8
        _fl,nref,first=struct.unpack_from("<HhI",image,lo)
        mappings=(((2,1),(1,2)),((0,2),(2,0)),((1,0),(0,1)))
        x,y=mappings[proj][int(sign)]; p2=(point[x],point[y])
        for ri in range(first,first+nref):
            rd,ni=struct.unpack_from("<II",image,refs[1]+ri*8)
            if rd&0x7fffffff != pi: continue
            rs=(normal[proj]>0)!=bool(rd&0x80000000)
            x,y=mappings[proj][int(rs)]; p2=(point[x],point[y])
            for _ in range(b2nodes[0]+1):
                if ni&0x80000000:
                    return (ni&0x7fffffff) if (ni&0x7fffffff)<surfaces[0] else -1
                if ni>=b2nodes[0]: return -1
                a,b,dist,c0,c1=struct.unpack_from("<3fII",image,b2nodes[1]+ni*20)
                ni=c1 if a*p2[0]+b*p2[1]-dist>=0 else c0
        return -1
    def hits(start, vec):
        out=[]
        for row in polys:
            if row is None: return []
            pl=row["plane"]; den=dot(pl[:3],vec)
            if abs(den)<1e-9: continue
            t=(pl[3]-dot(pl[:3],start))/den
            if 0<=t<=1:
                p=tuple(f32(start[k]+f32(t)*vec[k]) for k in range(3))
                if inside(row["poly"],p,pl[:3]): out.append((t,row["i"],p))
        return sorted(out)
    def inclusive_hits(start,vec):
        out=[]
        for row in polys:
            if row is None: return []
            pl=row["plane"]; den=dot(pl[:3],vec)
            if abs(den)<1e-8: continue
            t=(pl[3]-dot(pl[:3],start))/den
            if not 0<=t<=1: continue
            p=tuple(f32(start[k]+f32(t)*vec[k]) for k in range(3))
            err=abs(dot(pl[:3],p)-pl[3])
            if err<=2e-4 and inside_inclusive(row["poly"],p,pl[:3]):
                out.append((t,row["i"],p))
        return sorted(out)
    # Pair adjacency comes from serialized edge records (the two surface refs),
    # and shared endpoints are checked again from decoded polygons.
    pairs={}
    for ei in range(edges[0]):
        v0,v1,_e0,_e1,s0,s1=struct.unpack_from("<6i",image,edges[1]+ei*24)
        if 0<=s0<len(polys) and 0<=s1<len(polys) and s0!=s1:
            pairs.setdefault(tuple(sorted((s0,s1))),set()).add(tuple(sorted((v0,v1))))
    result={"source_sha256":hashlib.sha256(image).hexdigest(),"surface_count":len(polys),
            "decoded_surface_count":sum(p is not None for p in polys),
            "candidate_pairs":0,"tested_pairs":0,"qualified":[],"exact_ties":[]}
    for (a,b), evs in pairs.items():
        A,B=polys[a],polys[b]
        if (A is None or B is None or A["flags"] or B["flags"] or
            A["mi"]!=B["mi"] or not 0<=A["mi"]<len(mats) or not 0<=mats[A["mi"]]<32):
            continue
        shared=set(A["poly"]) & set(B["poly"])
        if len(shared)!=2: continue
        result["candidate_pairs"]+=1
        p0,p1=tuple(shared); mid=tuple((p0[k]+p1[k])*0.5 for k in range(3))
        # Exact shared-edge ray: unlike the offset fixture, the expected raw
        # answer is an adjacent-face set. Never choose one face based on CE.
        pl=A["plane"]; an=pl[:3]; amag=math.sqrt(dot(an,an))
        if .9<amag<1.1:
            an=tuple(v/amag for v in an)
            tie_start=tuple(f32(mid[k]+.5*an[k]) for k in range(3))
            tie_vec=tuple(f32(-an[k]) for k in range(3))
            tie_hits=inclusive_hits(tie_start,tie_vec)
            tied_ids=sorted({h[1] for h in tie_hits
                             if any(abs(h[0]-other[0])<2e-5 for other in tie_hits)})
            # Include only the simultaneous first-contact set; other later
            # intersections on the same ray are irrelevant.
            if tie_hits:
                first_t=tie_hits[0][0]
                tied_ids=sorted({h[1] for h in tie_hits if abs(h[0]-first_t)<2e-5})
                tie_point=tuple(f32(mid[k]) for k in range(3))
                li=leaf(tie_start); end=tuple(tie_start[k]+tie_vec[k] for k in range(3))
                allowed=[]
                if li>=0 and leaf(end)==-1 and set((a,b)).issubset(tied_ids):
                    for face in tied_ids:
                        row=polys[face]
                        if row is not None and choose(li,row["d"],tie_point)==face:
                            allowed.append(face)
                if (li>=0 and leaf(end)==-1 and set((a,b)).issubset(tied_ids) and
                    set(tied_ids).issubset({p["i"] for p in polys if p is not None}) and
                    all(polys[x]["flags"]==0 and polys[x]["mi"]==A["mi"] and
                        0<=polys[x]["mi"]<len(mats) and 0<=mats[polys[x]["mi"]]<32
                        for x in tied_ids) and allowed):
                    result["exact_ties"].append({"pair":[a,b],"adjacent_set":tied_ids,
                        "allowed_selected_faces":sorted(set(allowed)),"start":tie_start,
                        "vector":tie_vec,"t":first_t,"point":tie_point,"leaf":li,
                        "material_index":A["mi"],"material_type":mats[A["mi"]],
                        "plane_designator":A["d"],
                        "allowed_face_designators":{str(face):polys[face]["d"]
                            for face in sorted(set(allowed))}})
        pair_success=[]
        for row in (A,B):
            pl=row["plane"]; n=pl[:3]; mag=math.sqrt(dot(n,n))
            if not .9<mag<1.1: continue
            n=tuple(v/mag for v in n)
            center=tuple(sum(v[k] for v in row["poly"])/len(row["poly"]) for k in range(3))
            inward=tuple(center[k]-mid[k] for k in range(3)); proj=dot(inward,n)
            inward=tuple(inward[k]-proj*n[k] for k in range(3)); il=math.sqrt(dot(inward,inward))
            if il<1e-5: continue
            inward=tuple(v/il for v in inward)
            for eps in (0.01,0.02,0.05):
                contact=tuple(f32(mid[k]+eps*inward[k]) for k in range(3))
                if not inside(row["poly"],contact,n): continue
                for direction in (1.,-1.):
                    start=tuple(f32(contact[k]+direction*n[k]*.5) for k in range(3))
                    vec=tuple(f32(-direction*n[k]) for k in range(3))
                    raw=hits(start,vec)
                    if len(raw)!=1 or raw[0][1]!=row["i"] or not .1<raw[0][0]<.9: continue
                    li=leaf(start); end=tuple(start[k]+vec[k] for k in range(3))
                    if li<0 or leaf(end)!=-1 or choose(li,row["d"],raw[0][2])!=row["i"]: continue
                    result["tested_pairs"]+=1
                    pair_success.append({"pair":[a,b],"target":row["i"],"epsilon":eps,
                        "start":start,"vector":vec,"t":raw[0][0],"point":raw[0][2],
                        "leaf":li,"selected":choose(li,row["d"],raw[0][2]),
                        "plane_designator":row["d"],"material_index":row["mi"],
                        "material_type":mats[row["mi"]]})
                    break
                if pair_success and pair_success[-1]["target"] == row["i"]:
                    break
        if len(pair_success)==2 and {x["target"] for x in pair_success}=={a,b}:
            result["qualified"]=pair_success
            break
    # Independent exact-vertex scan. Group decoded polygon corners by their
    # serialized float32 coordinates, then require at least three distinct
    # incident faces to be simultaneous raw first contacts for the ray.
    vertex_faces={}
    for row in polys:
        if row is not None:
            for vertex in row["poly"]:
                vertex_faces.setdefault(tuple(vertex),set()).add(row["i"])
    result["vertex_ties"]=[]
    for vertex, incident in vertex_faces.items():
        if len(incident)<3: continue
        for face in sorted(incident):
            row=polys[face]
            if row is None or row["flags"] or not 0<=row["mi"]<len(mats) or not 0<=mats[row["mi"]]<32:
                continue
            pl=row["plane"]; n=pl[:3]; mag=math.sqrt(dot(n,n))
            if not .9<mag<1.1: continue
            n=tuple(v/mag for v in n)
            start=tuple(f32(vertex[k]+.5*n[k]) for k in range(3))
            vec=tuple(f32(-n[k]) for k in range(3))
            raw=inclusive_hits(start,vec)
            if not raw: continue
            first_t=raw[0][0]
            tied=sorted({h[1] for h in raw if abs(h[0]-first_t)<2e-5})
            if len(tied)<3 or not set(tied).issubset(incident): continue
            if any(polys[x] is None or polys[x]["flags"] or
                   not 0<=polys[x]["mi"]<len(mats) or not 0<=mats[polys[x]["mi"]]<32
                   for x in tied): continue
            end=tuple(start[k]+vec[k] for k in range(3)); li=leaf(start)
            if li<0 or leaf(end)!=-1: continue
            allowed=[x for x in tied if choose(li,polys[x]["d"],vertex)==x]
            if not allowed: continue
            result["vertex_ties"].append({"vertex":vertex,"incident_surface_set":sorted(incident),
                "raw_contact_set":tied,"allowed_selected_faces":allowed,"target_face":face,
                "start":start,"vector":vec,"t":first_t,"leaf":li,
                "material_index":row["mi"],"material_type":mats[row["mi"]],
                "face_materials":{str(x):{"material_index":polys[x]["mi"],
                    "material_type":mats[polys[x]["mi"]],"plane_designator":polys[x]["d"]}
                    for x in tied}})
            break
        if result["vertex_ties"]: break
    # Search for a strict-interior boundary start near the raw polygon plane,
    # a topology not exercised by the offset/tie rays. Solve one coordinate
    # from the serialized plane and retain only cases whose float32 start is
    # still strictly inside the decoded polygon, has |t| < 1e-7, and whose
    # independent all-surface/BSP2D oracle has exactly one first hit. Keep the
    # nonzero residual/t value in the golden: float32 rounding means this is a
    # near-zero boundary query, not a mathematically exact t == 0 claim.
    result["exact_zero_cases"]=[]
    for row in polys:
        if row is None or row["flags"] or not 0<=row["mi"]<len(mats) or not 0<=mats[row["mi"]]<32:
            continue
        n=row["plane"][:3]; mag=math.sqrt(dot(n,n))
        if not .9<mag<1.1: continue
        axis=max(range(3),key=lambda i:abs(n[i]))
        if abs(n[axis])<1e-5: continue
        center=tuple(f32(sum(v[k] for v in row["poly"])/len(row["poly"])) for k in range(3))
        start=list(center)
        start[axis]=f32((row["plane"][3]-sum(n[k]*start[k] for k in range(3) if k!=axis))/n[axis])
        start=tuple(start)
        if not inside(row["poly"],start,n): continue
        for sign in (-1.,1.):
            vector=tuple(f32(sign*n[k]/mag) for k in range(3))
            raw=hits(start,vector)
            if len(raw)!=1 or raw[0][1]!=row["i"] or abs(raw[0][0])>1e-7: continue
            li=leaf(start); end=tuple(start[k]+vector[k] for k in range(3))
            if li<0 or choose(li,row["d"],start)!=row["i"]: continue
            result["exact_zero_cases"].append({"surface":row["i"],"start":start,
                "vector":vector,"t":raw[0][0],"leaf":li,"material_index":row["mi"],
                "material_type":mats[row["mi"]],"plane_designator":row["d"],
                "plane_residual":dot(n,start)-row["plane"][3],"direction_sign":sign})
            break
        if result["exact_zero_cases"]: break
    # Search for one reproducible shallow-incidence (grazing) segment per BSP.
    # Its contact is inset from a serialized edge, while the vector is almost
    # tangent to the target plane. The all-surface oracle must still find one
    # unique first polygon and the raw leaf's BSP2D must route to it.
    result["grazing_cases"]=[]
    for row in polys:
        if row is None or row["flags"] or not 0<=row["mi"]<len(mats) or not 0<=mats[row["mi"]]<32:
            continue
        pl=row["plane"]; n=pl[:3]; mag=math.sqrt(dot(n,n))
        if not .9<mag<1.1: continue
        n=tuple(v/mag for v in n); poly=row["poly"]
        center=tuple(sum(v[k] for v in poly)/len(poly) for k in range(3))
        for edge_index,(p0,p1) in enumerate(zip(poly,poly[1:]+poly[:1])):
            midpoint=tuple((p0[k]+p1[k])*.5 for k in range(3))
            inward=tuple(center[k]-midpoint[k] for k in range(3))
            projection=dot(inward,n)
            inward=tuple(inward[k]-projection*n[k] for k in range(3))
            il=math.sqrt(dot(inward,inward))
            if il<1e-5: continue
            inward=tuple(v/il for v in inward)
            edge=tuple(p1[k]-p0[k] for k in range(3))
            edge_projection=dot(edge,n)
            tangent=tuple(edge[k]-edge_projection*n[k] for k in range(3))
            tl=math.sqrt(dot(tangent,tangent))
            if tl<1e-5: continue
            tangent=tuple(v/tl for v in tangent)
            for epsilon in (.01,.02,.05):
                contact=tuple(f32(midpoint[k]+epsilon*inward[k]) for k in range(3))
                if not inside(poly,contact,n): continue
                for alpha in (.025,.05,.1):
                    tangent_scale=math.sqrt(1.0-alpha*alpha)
                    for sign in (-1.,1.):
                        vector=tuple(f32(sign*tangent[k]*tangent_scale-n[k]*alpha)
                                     for k in range(3))
                        start=tuple(f32(contact[k]-vector[k]*.5) for k in range(3))
                        raw=hits(start,vector)
                        if len(raw)!=1 or raw[0][1]!=row["i"] or not .1<raw[0][0]<.9:
                            continue
                        hit_point=raw[0][2]; li=leaf(start)
                        if li<0 or choose(li,row["d"],hit_point)!=row["i"]:
                            continue
                        end=tuple(start[k]+vector[k] for k in range(3))
                        if leaf(end)!=-1: continue
                        result["grazing_cases"].append({"surface":row["i"],
                            "edge_vertex_indices":[edge_index,(edge_index+1)%len(poly)],
                            "epsilon":epsilon,"incidence_cosine":alpha,"direction_sign":sign,
                            "start":start,"vector":vector,"point":hit_point,
                            "t":raw[0][0],"leaf":li,"material_index":row["mi"],
                            "material_type":mats[row["mi"]],
                            "plane_designator":row["d"]})
                        break
                    if result["grazing_cases"]: break
                if result["grazing_cases"]: break
            if result["grazing_cases"]: break
        if result["grazing_cases"]: break
    return result


def main():
    maps=ROOT/"build/retail-maps/decompressed"
    out={}
    for name in MAPS:
        path=maps/f"{name}.map"
        if not path.is_file():
            print(f"missing map: {path}",file=sys.stderr); return 2
        header=mapinfo.read_header(path); index=tagindex.TagIndex.read(path)
        region,_,_=read_xbox_tag_region(path)
        locations=bsp_tools.locate(index,region,header.decompressed_size)
        # screen every structure BSP, preserving exact internal source path
        rows=[]
        for li,loc in enumerate(locations):
            row=audit_bsp(path,loc); row.update(bsp_index=li,bsp_path=loc.path)
            rows.append(row)
        out[name]={"map_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bsps":rows}
    print(json.dumps(out,indent=2,sort_keys=True))
    return 0

if __name__=="__main__": raise SystemExit(main())
