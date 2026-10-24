#!/usr/bin/env python3
"""Build a schema-driven inventory of retail actor variants and placements.

The input map files must be decompressed Xbox map images and ``schema_manifest``
must be emitted by hcu_schema_manifest.py. No scenario execution is performed.
"""
from __future__ import annotations

import hashlib
import json
import struct
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "submodules/halo-ps2/tools"))
from halo2ps2 import texconv, tagindex


COMBAT_HINTS = ("combat", "encounter", "guard", "patrol", "squad", "actor")


class RosterError(ValueError):
    pass


def make_recipe(variant, actor, unit, weapon, equipment, major, source_sha, actor_type, melee_supported=False):
    """Construct a spawn recipe only for resolved, combat-capable actor/unit pairs."""
    if not actor or not actor.get('path') or not unit or not unit.get('path'):
        return None
    if actor_type is None or actor_type in (6, 14, 15) or unit.get('group') not in ('bipd','vehi') or not (weapon and weapon.get('path') or melee_supported):
        return None
    return {"variant":variant,"actor":actor,"unit":unit,"ranged_weapon":weapon,
            "equipment":equipment,"major_upgrade":major,"source_map_sha256":source_sha}


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class Walker:
    def __init__(self, map_data, manifest):
        self.m = map_data
        self.data = map_data.region
        self.base = map_data.base
        self.index = map_data.index
        self.by_id = map_data.by_id
        self.defs = manifest["definitions"]
        self.group_defs = {x["group"]: x.get("definition") for x in manifest["groups"]}
        self.edges = []
        self.refs_by_owner = {}

    def u32(self, at):
        if at < 0 or at + 4 > len(self.data):
            raise RosterError(f"schema read outside map at {at:#x}")
        return struct.unpack_from("<I", self.data, at)[0]

    def i32(self, at):
        if at < 0 or at + 4 > len(self.data):
            raise RosterError(f"schema read outside map at {at:#x}")
        return struct.unpack_from("<i", self.data, at)[0]

    def walk(self, entry, defid, at, depth=0):
        if depth > 32: raise RosterError(f"schema nesting too deep at {entry.path}")
        d = self.defs.get(str(defid))
        if d is None: raise RosterError(f"missing definition {defid} for {entry.path}")
        if at < 0 or at + int(d["size"]) > len(self.data):
            raise RosterError(f"definition outside map: {entry.path}/{d['name']}")
        for f in d["fields"]:
            kind, n, stride = f["kind"], int(f["count"]), int(f["size"])
            pos = at + int(f["offset"])
            if kind == "struct":
                for i in range(n): self.walk(entry, f["definition"], pos+i*stride, depth+1)
            elif kind == "block":
                if stride != 12: raise RosterError(f"invalid block stride {stride}")
                for i in range(n):
                    p = pos+i*stride; count=self.i32(p); address=self.u32(p+4)
                    if count < 0 or (count and not address): raise RosterError(f"bad block {entry.path}.{f['name']}")
                    if count:
                        nd=self.defs.get(str(f["definition"]))
                        if not nd: raise RosterError(f"missing nested definition {f['definition']}")
                        target=address-self.base
                        if target < 0 or count*int(nd["size"]) > len(self.data)-target: raise RosterError(f"block outside map {entry.path}.{f['name']}")
                        for j in range(count): self.walk(entry,f["definition"],target+j*int(nd["size"]),depth+1)
            elif kind == "reference":
                if stride != 16: raise RosterError(f"invalid reference stride {stride}")
                for i in range(n):
                    p=pos+i*stride; group=tagindex.fourcc(self.data[p:p+4]); tid=self.u32(p+12)
                    if tid == 0xffffffff or not group: continue
                    target=self.by_id.get(tid)
                    row={"owner":entry.path,"field":f["name"],"group":group,"datum":tid,
                         "path":target.path if target else None}
                    self.edges.append(row); self.refs_by_owner.setdefault(entry.tag_id,[]).append(row)

    def read(self):
        for e in self.index.entries:
            did=self.group_defs.get(e.group)
            if did is not None and e.data_address:
                self.walk(e,did,e.data_address-self.base)

    def direct_ref(self, entry, field_name):
        did=self.group_defs.get(entry.group)
        if did is None or not entry.data_address: return None
        d=self.defs[str(did)]; f=next((x for x in d['fields'] if x['name']==field_name and x['kind']=='reference'),None)
        if f is None: return None
        at=entry.data_address-self.base+int(f['offset']); tid=self.u32(at+12)
        if tid==0xffffffff: return None
        target=self.by_id.get(tid)
        return {'group':target.group if target else None,'datum':tid,'path':target.path if target else None}

    def actor_type(self, entry):
        did=self.group_defs.get('actr')
        f=next((x for x in self.defs[str(did)]['fields'] if x['name']=='type'),None)
        if not f: return None
        at=entry.data_address-self.base+int(f['offset'])
        return struct.unpack_from('<h' if int(f['size'])==2 else '<i',self.data,at)[0]

    def vehicle_seats(self, entry):
        """Decode the compiler-described vehicle unit.seats block and gunner refs."""
        did=self.group_defs.get('vehi'); d=self.defs[str(did)]
        unit=next(f for f in d['fields'] if f['kind']=='struct' and f['name']=='unit.unit')
        ud=self.defs[str(unit['definition'])]; seats=next(f for f in ud['fields'] if f['kind']=='block' and f['name']=='seats')
        p=entry.data_address-self.base+int(unit['offset'])+int(seats['offset'])
        n=self.i32(p); address=self.u32(p+4); sd=self.defs[str(seats['definition'])]
        if n<0 or (n and not address): raise RosterError(f"invalid seats block in {entry.path}")
        out=[]; base=address-self.base
        for i in range(n):
            at=base+i*int(sd['size'])
            for f in sd['fields']:
                if f['kind']=='reference' and f['name']=='built_in_actor_reference':
                    tid=self.u32(at+int(f['offset'])+12)
                    if tid!=0xffffffff:
                        target=self.by_id.get(tid)
                        out.append({'seat_index':i,'datum':tid,'path':target.path if target else None,'group':target.group if target else None})
        return out


def build_roster(map_paths, schema_manifest):
    """Return stable JSON-compatible map roster; unresolved references fail closed."""
    if isinstance(schema_manifest, (str, Path)):
        schema_manifest=json.loads(Path(schema_manifest).read_text())
    if not isinstance(schema_manifest, dict) or not isinstance(schema_manifest.get("groups"),list) or not isinstance(schema_manifest.get("definitions"),dict):
        raise RosterError("invalid HCU schema manifest")
    roots=[]; variants=[]; unique_candidates=[]
    for item in sorted((Path(x) for x in map_paths), key=lambda p:(p.stem,p.as_posix())):
        w=Walker(texconv.MapData.open(item),schema_manifest); w.read()
        map_hash=_sha(item)
        entries=w.index.entries; source={e.tag_id:e for e in entries}
        # actv tags describe variants. Walk their transitive references, preserving identity.
        for a in sorted((e for e in entries if e.group=="actv"),key=lambda e:(e.path,e.tag_id)):
            pending=[a.tag_id]; seen=set(); deps=[]; unresolved=[]
            while pending:
                tid=pending.pop()
                if tid in seen: continue
                seen.add(tid); ent=source.get(tid)
                if ent is None: continue
                for edge in w.refs_by_owner.get(tid,[]):
                    ident={"group":edge["group"],"datum":edge["datum"],"path":edge["path"]}
                    deps.append(ident)
                    if edge["path"] is None: unresolved.append(ident)
                    else:
                        target=next((x for x in entries if x.tag_id==edge["datum"]),None)
                        if target and target.group in {"actv","actr","bipd","vehi","weap","eqip","antr","mode","coll","obje","unit","effe","proj"}: pending.append(target.tag_id)
            deps=sorted({(x["group"],x["datum"],x["path"]):x for x in deps}.values(),key=lambda x:(x["group"],x["path"] or "",x["datum"]))
            actor=w.direct_ref(a,'actor_reference'); unit=w.direct_ref(a,'unit_reference')
            major=w.direct_ref(a,'major_upgrade_reference'); weapon=w.direct_ref(a,'ranged_combat.reference')
            equipment=w.direct_ref(a,'items.equipment_reference')
            actor_entry=w.by_id.get(actor['datum']) if actor and actor['path'] else None
            atype=w.actor_type(actor_entry) if actor_entry else None
            valid_actor=actor_entry is not None and atype not in (None,14)
            valid_unit=unit is not None and unit['path'] is not None and unit['group'] in ('bipd','vehi')
            combat_weapon=weapon is not None and weapon['path'] is not None
            unit_entry=w.by_id.get(unit['datum']) if unit and unit['path'] else None
            melee=bool(unit_entry and any(e['field'].endswith('melee_damage') and e['path'] for e in w.refs_by_owner.get(unit_entry.tag_id,[])))
            if unresolved: disposition='unresolved'
            elif not valid_actor or not valid_unit: disposition='hollow_or_unplaceable'
            elif atype==15: disposition='mounted_weapon_variant'
            elif atype in (0,1,2,3,4,5,7,8,9,10,11,12,13) and (combat_weapon or melee): disposition='combat'
            else: disposition='noncombat'
            recipe=make_recipe({"group":"actv","path":a.path,"datum":a.tag_id},actor,
                     unit,weapon,equipment,major,map_hash,atype,melee) if disposition=='combat' else None
            mounted=[]
            if atype==15:
                for vehicle in (e for e in entries if e.group=='vehi' and e.data_address):
                    for seat in w.vehicle_seats(vehicle):
                        if seat['datum']==a.tag_id:
                            mounted.append({'parent_vehicle':{'group':'vehi','path':vehicle.path,'datum':vehicle.tag_id},
                                'seat_index':seat['seat_index'],'variant':{'group':'actv','path':a.path,'datum':a.tag_id},
                                'source_map_sha256':map_hash})
                if not mounted: disposition='mounted_occupant_unresolved'
                else: disposition='mounted_occupant'
            if recipe: unique_candidates.append(recipe)
            unique_candidates.extend(mounted)
            variants.append({"map":item.stem,"group":"actv","path":a.path,"datum":a.tag_id,
                "source_map_sha256":map_hash,"dependencies":deps,"unresolved":unresolved,
                "actor_type":atype,"actor":actor,"unit":unit,"ranged_weapon":weapon,
                "equipment":equipment,"major_upgrade":major,"placements":[],"recipe":recipe,"mounted_recipes":mounted,"disposition":disposition})
        roots.append({"map":item.stem,"path":str(item),"sha256":map_hash})
    for row in variants:
        relevant=[e for e in row["dependencies"] if e["group"] in ("actv","bipd")]
        row["placements"]=[{"source":"resolved tag dependency","group":x["group"],"path":x["path"],"datum":x["datum"]} for x in relevant]
        if row['disposition']=='combat' and not row['recipe']:
            row['disposition']='hollow_or_unplaceable'
    groups={}
    for recipe in unique_candidates:
        def logical(value):
            if isinstance(value,dict): return {k:logical(v) for k,v in value.items() if k not in ('source_map_sha256','datum')}
            if isinstance(value,list): return [logical(v) for v in value]
            return value
        identity=json.dumps(logical(recipe),sort_keys=True,separators=(',',':'))
        groups.setdefault(identity,[]).append(recipe)
    unique=[]
    for ident,recipes in sorted(groups.items()):
        recipes.sort(key=lambda r:(r['source_map_sha256'],json.dumps(r,sort_keys=True)))
        first=recipes[0]
        first['source_aliases']=sorted({x['map'] for x in variants if x['path']==first.get('variant',{}).get('path')})
        first['source_conflicts']=[r for r in recipes[1:] if r!=recipes[0]]
        unique.append(first)
    return {"format":"hcu-actor-roster-v1","schema_elf_sha256":schema_manifest.get("elf_sha256"),
            "source_roots":roots,"variants":sorted(variants,key=lambda x:(x["map"],x["path"],x["datum"])),"unique_recipes":unique}
