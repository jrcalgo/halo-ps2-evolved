"""Recheck current M10 retained runtime evidence; visual review remains separate."""
import configparser
import json
from pathlib import Path
import re
import sys
from test_emulator import ROOT, OUTPUT, sha, save
from run_world_viewer import ROUTE


def observe(text, kind):
    if '[err]' in text or ' OVERFLOW' in text or '[cfg] no host:halo.cfg' in text:
        raise RuntimeError('World viewer reported a runtime/configuration error')
    done = re.search(r'\[done\] frames=(\d+) dropped=(\d+)', text)
    profiles = re.findall(r'\[prof\] frames=(\d+).*?ee prep avg=([\d.]+).*?tris=(\d+) batches=(\d+).*?tex hit=(\d+) up=(\d+)/(\d+)KB.*?fail=(\d+).*?chain=(\d+)qw.*?skip=(\d+) drop=(\d+)', text)
    minimum = {'route':9000, 'freecam':3000, 'fixed':180}[kind]
    if not done or int(done[1]) < minimum or not profiles or int(profiles[-1][0]) < minimum:
        raise RuntimeError('Requested world scenario did not finish')
    if any(int(b[0]) <= int(a[0]) for a,b in zip(profiles,profiles[1:])):
        raise RuntimeError('World frame counters did not progress')
    if any(int(p[7]) or int(p[9]) or int(p[10]) for p in profiles):
        raise RuntimeError('Texture failure or clipped-geometry loss was logged')
    if max(int(p[8]) for p in profiles) > 32768:
        raise RuntimeError('World DMA chain exceeded capacity')
    if 'sky model: drawn' not in text or 'lightmap page slots' not in text:
        raise RuntimeError('Sky or lightmap initialization missing')
    out = {'frames':int(done[1]), 'dropped':int(done[2]),
           'chain_high_qwords':max(int(p[8]) for p in profiles),
           'ee_prep_avg_ms_range':[min(float(p[1]) for p in profiles),max(float(p[1]) for p in profiles)],
           'triangle_range':[min(int(p[2]) for p in profiles),max(int(p[2]) for p in profiles)],
           'texture_upload_kb_max_window':max(int(p[6]) for p in profiles)}
    if kind == 'route' and 'scripted path: 12 keys, 300.0 s loop' not in text:
        raise RuntimeError('Five-minute camera path is missing')
    if kind == 'freecam':
        if 'scripted path:' in text:
            raise RuntimeError('Pad flight used a scripted camera')
        positions = [tuple(map(float,p)) for p in re.findall(r'\[cam\] pos (-?\d+\.\d+) (-?\d+\.\d+) (-?\d+\.\d+)',text)]
        if len(positions) < 8:
            raise RuntimeError('Pad camera positions missing')
        lo = [min(p[k] for p in positions) for k in range(3)]
        hi = [max(p[k] for p in positions) for k in range(3)]
        if lo[0]>40 or hi[0]<110 or lo[1]>-150 or hi[1]<-70 or hi[2]-lo[2]<6:
            raise RuntimeError('Pad flight did not cover map sides and height')
        out['camera_bounds'] = [lo,hi]
    return out


def qualify():
    elf = sha(ROOT/'build/world-elf/world.elf')
    converted = json.loads((ROOT/'build/convert/bloodgulch.json').read_text())
    packs = ROOT/converted['pack_directory']
    expected = converted['pack_sha256']
    for name,suffix in {'bsp':'.hp2','textures':'.tex.hp2','objects':'.obj.hp2'}.items():
        if sha(packs/('bloodgulch'+suffix)) != expected[name]:
            raise RuntimeError('Current pack differs from conversion report')
    runs = []
    for kind,mode,status in [('fixed','recompiler','diagnostic-completed'),('freecam','recompiler','freecam-completed'),
                             ('route','recompiler','route-completed'),('route','interpreter','route-completed')]:
        candidates = []
        for path in (OUTPUT/'runs').glob('world-'+mode+'-*/result.json'):
            r=json.loads(path.read_text())
            if r.get('status')==status and r.get('elf_sha256')==elf and r.get('pack_sha256')==expected:
                candidates.append((path.stat().st_mtime,r))
        if not candidates:
            raise RuntimeError('No current passing '+kind+' '+mode+' run')
        r=max(candidates,key=lambda x:x[0])[1]; run=Path(r['run_directory'])
        if not r.get('visible') or sha(run/'boot/world.elf')!=elf:
            raise RuntimeError('Visible staged ELF identity missing')
        for name,suffix in {'bsp':'.hp2','textures':'.tex.hp2','objects':'.obj.hp2'}.items():
            if sha(run/'boot'/('bloodgulch'+suffix)) != expected[name]:
                raise RuntimeError('Retained staged pack changed: '+name)
        if sha(Path(r['command'][0]).resolve()) != r['emulator_sha256']:
            raise RuntimeError('Emulator executable changed')
        for name,digest in r['source_sha256'].items():
            if sha(ROOT/name)!=digest:
                raise RuntimeError('World source changed: '+name)
        if r.get('runner_sha256') != sha(ROOT/'tools/run_world_viewer.py'):
            raise RuntimeError('World runner identity changed')
        if sha(run/'boot/halo.cfg')!=r['config_sha256']:
            raise RuntimeError('World configuration changed')
        if sha(run/'data/PCSX2/bios/SCPH-30001.bin')!=r['bios_sha256']:
            raise RuntimeError('Isolated BIOS copy changed')
        ini=configparser.ConfigParser(interpolation=None);ini.read(run/'data/PCSX2/inis/PCSX2.ini')
        if any(ini.getboolean('EmuCore/CPU/Recompiler',k)!=(mode=='recompiler') for k in ('EnableEE','EnableIOP','EnableVU0','EnableVU1')):
            raise RuntimeError('World CPU configuration differs')
        cfg=(run/'boot/halo.cfg').read_text()
        if kind=='route':
            keys=[tuple(map(float,line.split()[1:])) for line in cfg.splitlines() if line.startswith('pathkey ')]
            if keys!=ROUTE:
                raise RuntimeError('Route waypoints changed')
        if kind=='fixed' and r.get('camera')!=[65,-95,9,-70,-5]:
            raise RuntimeError('Reference camera differs')
        if kind=='freecam' and len(r.get('pad_waypoints',[]))!=5:
            raise RuntimeError('Pad waypoints did not finish')
        captures=r['captures']
        if len(captures)<(12 if kind=='route' else 2) or any(not Path(p).read_bytes().startswith(b'\x89PNG\r\n\x1a\n') for p in captures):
            raise RuntimeError('World captures missing')
        observed=observe(Path(r['log']).read_text(errors='replace'),kind)
        runs.append({'kind':kind,'mode':mode,'run_directory':str(run),'observed':observed,
                     'log_sha256':sha(r['log']),'result_sha256':sha(run/'result.json'),
                     'captures':{Path(p).name:sha(p) for p in captures}})
    save(OUTPUT/'world-qualification.json',{'status':'passed','scenario':'M10-world','elf_sha256':elf,
         'pack_sha256':expected,'runs':runs,'qualifier_sha256':sha(Path(__file__)),
         'limits':'Retained technical evidence only. Visual review is separate. Emulator timings are not physical-console performance.'})
    print('M10 retained technical evidence passed; visual review is separate')


if __name__=='__main__':
    try: qualify()
    except (OSError,RuntimeError,ValueError,KeyError) as e: sys.exit('World qualification failed: '+str(e))
