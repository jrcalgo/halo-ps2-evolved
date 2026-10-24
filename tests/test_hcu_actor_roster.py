import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import hcu_actor_roster as roster


def manifest(kind="reference"):
    return {"elf_sha256":"abc", "groups":[{"group":"actv","definition":1}],
            "definitions":{"1":{"name":"actor","size":16,"fields":[
                {"kind":kind,"name":"actor_reference","size":16,"count":1,"offset":0}]}}}


def test_manifest_validation_fails_closed():
    with pytest.raises(roster.RosterError):
        roster.build_roster([], {})


def test_reference_walker_preserves_resolved_and_unresolved_identity():
    entry=SimpleNamespace(tag_id=7,path="characters\\elite\\combat",group="actv",data_address=0x1000)
    data=bytearray(16)
    data[0:4]=b"dpib"; data[12:16]=(8).to_bytes(4,"little")
    fake=SimpleNamespace(region=data,base=0x1000,index=SimpleNamespace(entries=[entry]),by_id={8:SimpleNamespace(tag_id=8,path="characters\\elite\\elite",group="bipd")})
    w=roster.Walker(fake,manifest()); w.read()
    assert w.edges == [{"owner":entry.path,"field":"actor_reference","group":"bipd","datum":8,"path":"characters\\elite\\elite"}]


def test_bad_reference_stride_rejected():
    entry=SimpleNamespace(tag_id=7,path="bad",group="actv",data_address=0x1000)
    fake=SimpleNamespace(region=bytearray(16),base=0x1000,index=SimpleNamespace(entries=[entry]),by_id={})
    bad=manifest(); bad["definitions"]["1"]["fields"][0]["size"]=12
    with pytest.raises(roster.RosterError): roster.Walker(fake,bad).read()


def test_recipe_requires_real_actor_and_unit_and_emits_recipe():
    actor={"group":"actr","datum":1,"path":"actors\\marine"}
    unit={"group":"bipd","datum":2,"path":"characters\\marine"}
    recipe=roster.make_recipe({"group":"actv","datum":3,"path":"variants\\marine"},actor,unit,None,None,None,"deadbeef",7,True)
    assert recipe and recipe["ranged_weapon"] is None and recipe["actor"]["datum"]==1
    assert roster.make_recipe({"group":"actv"},None,unit,None,None,None,"x",7) is None
    assert roster.make_recipe({"group":"actv"},actor,None,None,None,None,"x",7) is None
    assert roster.make_recipe({"group":"actv"},actor,unit,None,None,None,"x",6,True) is None
