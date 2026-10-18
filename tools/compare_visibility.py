"""Qualify paired M11 GS readbacks at one fixed camera; not full M11 acceptance."""
import configparser
import hashlib
import json
from pathlib import Path
import re
import sys
from test_emulator import ROOT,OUTPUT,sha,save
from render_reference import png


def framebuffer(text, expected_frame=120):
    headers=re.findall(r'\[fb\] begin frame=(\d+) w=(\d+) h=(\d+) psm=(\d+) addr=(\d+) ret=(-?\d+)',text)
    if len(headers)!=1 or tuple(map(int,headers[0][:4]))!=(expected_frame,512,448,10) or int(headers[0][5])!=1:
        raise RuntimeError('Expected one successful 512x448 PSMCT16S framebuffer readback')
    if '[fb] guards=ok bytes=458752' not in text:
        raise RuntimeError('Framebuffer DMA bounds were not checked')
    rows=re.findall(r'\[fb\] (\d+) ([0-9a-f]+)',text)
    if [int(n) for n,_ in rows]!=list(range(448)) or any(len(v)!=2048 for _,v in rows):
        raise RuntimeError('Framebuffer rows missing, duplicated or truncated')
    if re.findall(r'\[fb\] end frame=(\d+)',text)!=[str(expected_frame)]:
        raise RuntimeError('Framebuffer readback did not finish')
    return b''.join(bytes.fromhex(v) for _,v in rows)


def qualify():
    elf=sha(ROOT/'build/world-portal-elf/world.elf');pack=json.loads((ROOT/'build/convert/bloodgulch.json').read_text())['pack_sha256']
    runs=[];images=[]
    for mode in ('recompiler','interpreter'):
        pair=[]
        for visibility in ('conservative','portal'):
            candidates=[]
            for p in (OUTPUT/'runs').glob('world-portal-'+mode+'-*/result.json'):
                r=json.loads(p.read_text())
                if r.get('status')=='diagnostic-completed' and r.get('visibility')==visibility and r.get('elf_sha256')==elf and r.get('pack_sha256')==pack:
                    candidates.append((p.stat().st_mtime,r))
            if not candidates:raise RuntimeError('No current completed '+mode+' '+visibility+' readback')
            r=max(candidates,key=lambda v:v[0])[1];run=Path(r['run_directory'])
            if not r['visible'] or r['camera']!=[65,-80,9,-90,-5] or sha(run/'boot/world.elf')!=elf:
                raise RuntimeError('Visible staged ELF or camera differs')
            for name,digest in r['source_sha256'].items():
                if sha(ROOT/name)!=digest:raise RuntimeError('Visibility source changed: '+name)
            if r['runner_sha256']!=sha(ROOT/'tools/run_world_viewer.py') or sha(run/'boot/halo.cfg')!=r['config_sha256']:
                raise RuntimeError('Runner/configuration identity changed')
            cfg=(run/'boot/halo.cfg').read_text()
            if 'overlay 0\n' not in cfg or 'fbdump 120\n' not in cfg or ('debug 64\n' in cfg)!=(visibility=='conservative'):
                raise RuntimeError('Comparison configuration differs')
            ini=configparser.ConfigParser(interpolation=None);ini.read(run/'data/PCSX2/inis/PCSX2.ini')
            if any(ini.getboolean('EmuCore/CPU/Recompiler',k)!=(mode=='recompiler') for k in ('EnableEE','EnableIOP','EnableVU0','EnableVU1')):
                raise RuntimeError('CPU execution flags differ')
            if sha(run/'data/PCSX2/bios/SCPH-30001.bin')!=r['bios_sha256']:
                raise RuntimeError('Isolated BIOS changed')
            for kind,suffix in {'bsp':'.hp2','textures':'.tex.hp2','objects':'.obj.hp2'}.items():
                if sha(run/'boot'/('bloodgulch'+suffix))!=pack[kind]:raise RuntimeError('Staged pack changed')
            text=Path(r['log']).read_text(errors='replace')
            if '[err]' in text or ' OVERFLOW' in text or '[done] frames=181' not in text:raise RuntimeError('Viewer failed or did not finish')
            raw=framebuffer(text);pair.append(raw);images.append(raw)
            stats=re.findall(r'\[prof\].*?batches=(\d+).*?portals=(\d+)/(\d+).*?fail=(\d+).*?skip=(\d+) drop=(\d+)',text)
            if not stats or any(int(v[3]) or int(v[4]) or int(v[5]) for v in stats):raise RuntimeError('Resource failure in comparison')
            if visibility=='portal' and not any(int(v[2])>0 for v in stats):raise RuntimeError('Portal traversal was not active')
            if visibility=='conservative' and any(int(v[2]) for v in stats):raise RuntimeError('Baseline used portal traversal')
            (run/'framebuffer-120.rgb16').write_bytes(raw)
            rgb=bytearray()
            for i in range(0,len(raw),2):
                v=raw[i]|raw[i+1]<<8;rgb.extend(((v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31))
            png(run/'framebuffer-120.png',512,448,rgb)
            runs.append({'mode':mode,'visibility':visibility,'run_directory':str(run),'raw_sha256':hashlib.sha256(raw).hexdigest(),
                         'log_sha256':sha(r['log']),'result_sha256':sha(run/'result.json'),'batches':int(stats[-1][0]),'portals_tested':int(stats[-1][2])})
        if pair[0]!=pair[1]:raise RuntimeError('Culling changed raw GS pixels in '+mode)
    cross_pixels=sum(images[0][i:i+2]!=images[2][i:i+2] for i in range(0,len(images[0]),2))
    report={'status':'paired-comparison-passed','cross_mode_equal':cross_pixels==0,'cross_mode_different_pixels':cross_pixels,'elf_sha256':elf,'pack_sha256':pack,'runs':runs,'qualifier_sha256':sha(Path(__file__)),
            'limits':'Exact culling on/off equality is required within each CPU mode. Cross-mode pixel differences are recorded separately, not attributed to culling or declared correct. One camera only; full route, cache churn, streaming, unload and physical-console acceptance remain open.'}
    save(ROOT/'build/visibility/framebuffer-comparison.json',report)
    print('M11 culling pairs match exactly within each CPU mode; cross-mode differing pixels: '+str(cross_pixels)+'; remaining milestone gates are open')


if __name__=='__main__':
    try:qualify()
    except (OSError,RuntimeError,ValueError,KeyError) as e:sys.exit('Visibility comparison failed: '+str(e))
