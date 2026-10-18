"""M11 host topology/visibility audit of the private converted BSP; no EE claim."""
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import uuid
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'submodules/halo-ps2/tools'),str(ROOT/'tools')]
from halo2ps2 import hp2,bspconv
from render_reference import rasterize,png
from run_world_viewer import ROUTE


def topology(s):
    errors=[]; graph=[set() for _ in s.clusters]; members=[set() for _ in s.batches]
    for ci,c in enumerate(s.clusters):
        for bi in s.cluster_batches[c['first_batch']:c['first_batch']+c['batch_count']]: members[bi].add(ci)
        for pi in s.cluster_portals[c['first_portal']:c['first_portal']+c['portal_count']]:
            if ci not in (s.portals[pi]['a'],s.portals[pi]['b']): errors.append(['nonincident_portal',ci,pi])
    for bi,cs in enumerate(members):
        if not cs: errors.append(['unowned_batch',bi])
        verts=bspconv.decode_batch(s,s.batches[bi])
        for ci in cs:
            c=s.clusters[ci]
            if any(not c['min'][k]-.002 <= v['pos'][k] <= c['max'][k]+.002 for v in verts for k in range(3)):
                errors.append(['batch_outside_cluster_bounds',bi,ci])
    side_checks=[]
    for pi,p in enumerate(s.portals):
        sides={c for c in (p['a'],p['b']) if c!=bspconv.NO_CLUSTER}
        for ci in sides:
            c=s.clusters[ci]; links=s.cluster_portals[c['first_portal']:c['first_portal']+c['portal_count']]
            if links.count(pi)!=1: errors.append(['nonreciprocal_portal',pi,ci])
            graph[ci].update(sides-{ci})
        vs=s.portal_vertices[p['first_vertex']:p['first_vertex']+p['vertex_count']]
        n=p['plane'][:3];d=p['plane'][3]
        if not vs or abs(math.sqrt(sum(x*x for x in n))-1)>.002 or any(abs(sum(n[k]*v[k] for k in range(3))-d)>.002 for v in vs):
            errors.append(['invalid_portal_plane',pi])
        if vs:
            centre=[sum(v[k] for v in vs)/len(vs) for k in range(3)]
            found=[bspconv.find_cluster(s,tuple(centre[k]+sign*.05*n[k] for k in range(3))) for sign in (1,-1)]
            expected=[-1 if p[k]==bspconv.NO_CLUSTER else p[k] for k in ('a','b')]
            side_checks.append({'portal':pi,'expected':expected,'observed':found})
            if found!=expected: errors.append(['portal_point_location',pi,expected,found])
    unseen=set(range(len(graph)));components=[]
    while unseen:
        pending=[min(unseen)];component=set()
        while pending:
            c=pending.pop()
            if c in component:continue
            component.add(c);pending.extend(graph[c]-component)
        unseen-=component;components.append(sorted(component))
    return {'errors':errors,'components':components,'portal_side_checks':side_checks,
            'clusters':len(s.clusters),'portals':len(s.portals),'batches':len(s.batches)}


def main():
    out=ROOT/'build/visibility/runs'/uuid.uuid4().hex;out.mkdir(parents=True,exist_ok=True)
    converted=json.loads((ROOT/'build/convert/bloodgulch.json').read_text());pack=ROOT/converted['pack_directory']/'bloodgulch.hp2'
    raw=hp2.parse(pack.read_bytes()).read('BSP0');section=out/'bsp0.bin';section.write_bytes(raw)
    s=bspconv.parse_section(raw);report={'run_directory':str(out),'status':'incomplete','topology':topology(s),'pack_sha256':hashlib.sha256(pack.read_bytes()).hexdigest(),'views':[]}
    engine=ROOT/'submodules/halo-ps2/engine/src';exe=out/'probe'
    sources=[ROOT/'tests/visibility/probe.c',*[engine/p for p in ('core/mem.c','world/bsp.c','render/camera.c','render/vis.c')]]
    vis_object=out/'vis.o'
    flags=['cc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I'+str(engine)]
    subprocess.run([*flags,'-Dvis_run=halo_upstream_vis_run','-c',str(engine/'render/vis.c'),'-o',str(vis_object)],check=True)
    sources.append(ROOT/'src/world/visibility_portal.c')
    subprocess.run([*flags,*map(str,[p for p in sources if p!=engine/'render/vis.c']),str(vis_object),'-lm','-o',str(exe)],check=True)
    report['source_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    decoded=[bspconv.decode_batch(s,b) for b in s.batches]
    def draw(indices,camera):
        triangles=[]
        for bi in indices:
            v=decoded[bi];triangles.extend([[q['pos'] for q in v[i:i+3]] for i in range(0,len(v),3)])
        pixels,_,depth=rasterize(triangles,camera,128,112,return_depth=True)
        return pixels,depth
    # Include ground-level samples: aerial route cameras alone mostly use outside-map fallback.
    cameras=[list(k[1:]) for k in ROUTE]+[[65,y,9,yaw,-5] for y in (-80,-110,-140,-165) for yaw in (-90,0,90,180)]
    for p in s.portals:
        n=p['plane'][:3];vs=s.portal_vertices[p['first_vertex']:p['first_vertex']+p['vertex_count']]
        centre=[sum(v[k] for v in vs)/len(vs) for k in range(3)]
        for sign in (-1,1):
            for distance in (.001,.05,.5):
                pos=[centre[k]+sign*distance*n[k] for k in range(3)]
                direction=[-sign*x for x in n]
                yaw=math.degrees(math.atan2(direction[1],direction[0]))
                pitch=math.degrees(math.atan2(direction[2],math.hypot(*direction[:2])))
                cameras.append(pos+[yaw,pitch])
    for i,cam in enumerate(cameras):
        results=[json.loads(subprocess.check_output([str(exe),str(section),*map(str,cam),str(force)],text=True)) for force in (1,0)]
        (baseline,base_depth),(portal,portal_depth)=[draw(r['batches'],cam) for r in results]
        depth_difference=sum(abs(a-b)>1e-6 for a,b in zip(base_depth,portal_depth))
        differing=sum(baseline[k:k+3]!=portal[k:k+3] for k in range(0,len(baseline),3))
        report['views'].append({'camera':cam,'baseline':results[0],'portal':results[1],'different_pixels':differing,'different_depth_pixels':depth_difference})
        if differing or depth_difference:
            png(out/('baseline-%02d.png'%i),128,112,baseline);png(out/('portal-%02d.png'%i),128,112,portal)
    report['status']='passed' if not report['topology']['errors'] and not any(v['different_pixels'] or v['different_depth_pixels'] for v in report['views']) else 'failed'
    report['limits']='Host topology and independent geometry-image comparison only; no EE visibility, texture churn or streaming acceptance.'
    (out/'audit.json').write_text(json.dumps(report,indent=2)+'\n')
    (ROOT/'build/visibility/audit.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({'status':report['status'],'topology_errors':report['topology']['errors'],'different_view_count':sum(bool(v['different_pixels'] or v['different_depth_pixels']) for v in report['views']),'different_views_first_12':[(i,v['different_pixels'],v['portal']['camera_cluster']) for i,v in enumerate(report['views']) if v['different_pixels'] or v['different_depth_pixels']][:12],'portal_active_views':sum(v['portal']['portals_tested']>0 for v in report['views'])},indent=2))
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':
    sys.exit(main())
