"""Independent CPU depth/geometry view of a private converted BSP, without textures.

Only the pack decoder is reused. Camera projection, clipping and rasterization
are implemented here and do not call EE, GS, VIF, VU or the runtime renderer.
This checks presentation geometry; it is not an oracle for retail materials.
"""
from array import array
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]


def clip_polygon(vertices, plane):
    if not vertices:
        return []
    output = []
    previous = vertices[-1]
    dp = sum(a*b for a,b in zip(previous,plane[:3])) + plane[3]
    for current in vertices:
        dc = sum(a*b for a,b in zip(current,plane[:3])) + plane[3]
        if (dc >= 0) != (dp >= 0):
            t = dp / (dp-dc)
            output.append(tuple(a+t*(b-a) for a,b in zip(previous,current)))
        if dc >= 0:
            output.append(current)
        previous, dp = current, dc
    return output


def view_vertices(points, camera):
    x,y,z,yaw,pitch = camera
    yaw,pitch = math.radians(yaw),math.radians(pitch)
    cy,sy,cp,sp = math.cos(yaw),math.sin(yaw),math.cos(pitch),math.sin(pitch)
    forward = (cp*cy,cp*sy,sp)
    right = (sy,-cy,0)
    up = (-sp*cy,-sp*sy,cp)
    return [tuple(sum((p[i]-camera[i])*basis[i] for i in range(3)) for basis in (right,up,forward)) for p in points]


def png(path,width,height,rgb):
    def chunk(name,payload):
        return struct.pack('>I',len(payload))+name+payload+struct.pack('>I',zlib.crc32(name+payload))
    rows=b''.join(b'\0'+rgb[y*width*3:(y+1)*width*3] for y in range(height))
    path.write_bytes(b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b''))


def rasterize(triangles,camera,width=512,height=448,*,return_depth=False):
    pixels=bytearray(bytes((100,140,180))*width*height)
    depth=array('f',[0])*(width*height)
    tx=math.tan(math.radians(35));ty=tx/(4/3)
    planes=((0,0,1,-.05),(0,0,-1,4000),(1,0,tx,0),(-1,0,tx,0),(0,1,ty,0),(0,-1,ty,0))
    submitted=fragments=0
    for triangle in triangles:
        polygon=view_vertices(triangle,camera)
        for plane in planes:
            polygon=clip_polygon(polygon,plane)
        if len(polygon)<3: continue
        ab=[triangle[1][i]-triangle[0][i] for i in range(3)]
        ac=[triangle[2][i]-triangle[0][i] for i in range(3)]
        normal=(ab[1]*ac[2]-ab[2]*ac[1],ab[2]*ac[0]-ab[0]*ac[2],ab[0]*ac[1]-ab[1]*ac[0])
        length=math.sqrt(sum(n*n for n in normal)) or 1
        shade=int(55+170*abs(normal[2])/length)
        colour=bytes((shade,shade,min(255,shade+12)))
        projected=[(width*.5*(1+v[0]/(v[2]*tx)),height*.5*(1-v[1]/(v[2]*ty)),1/v[2]) for v in polygon]
        for i in range(1,len(projected)-1):
            a,b,c=projected[0],projected[i],projected[i+1]
            area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0])
            if abs(area)<1e-8: continue
            submitted+=1
            x0=max(0,math.floor(min(a[0],b[0],c[0])));x1=min(width-1,math.ceil(max(a[0],b[0],c[0])))
            y0=max(0,math.floor(min(a[1],b[1],c[1])));y1=min(height-1,math.ceil(max(a[1],b[1],c[1])))
            for y in range(y0,y1+1):
                for x in range(x0,x1+1):
                    px,py=x+.5,y+.5
                    u=((b[0]-px)*(c[1]-py)-(b[1]-py)*(c[0]-px))/area
                    v=((c[0]-px)*(a[1]-py)-(c[1]-py)*(a[0]-px))/area
                    w=1-u-v
                    if min(u,v,w)<-1e-7: continue
                    q=u*a[2]+v*b[2]+w*c[2];index=y*width+x
                    if q>depth[index]:
                        depth[index]=q;pixels[index*3:index*3+3]=colour;fragments+=1
    stats={"submitted_clipped_triangles":submitted,"depth_updates":fragments,"covered_pixels":sum(q>0 for q in depth)}
    return (pixels,stats,depth) if return_depth else (pixels,stats)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--camera',type=float,nargs=5,default=[65,-95,9,-70,-5])
    parser.add_argument('--output',type=Path,default=ROOT/'build/reference/bloodgulch-geometry.png')
    args=parser.parse_args()
    output=args.output.resolve()
    if ROOT/'build' not in output.parents:
        raise RuntimeError('Retail-derived reference output must remain under ignored build/')
    sys.path.insert(0,str(ROOT/'submodules/halo-ps2/tools'))
    from halo2ps2 import hp2,bspconv
    pack=ROOT/'data/retail/convert/bloodgulch/run-a/bloodgulch.hp2'
    section=bspconv.parse_section(hp2.parse(pack.read_bytes()).read('BSP0'))
    triangles=[]
    for batch in section.batches:
        vertices=bspconv.decode_batch(section,batch)
        triangles.extend([[v['pos'] for v in vertices[i:i+3]] for i in range(0,len(vertices),3)])
    pixels,stats=rasterize(triangles,args.camera)
    output.parent.mkdir(parents=True,exist_ok=True);png(output,512,448,pixels)
    result={"status":"rendered","camera":args.camera,"dimensions":[512,448],"hfov_degrees":70,"display_aspect":4/3,
            "source_pack_sha256":hashlib.sha256(pack.read_bytes()).hexdigest(),"source_triangles":len(triangles),**stats,
            "png_sha256":hashlib.sha256(output.read_bytes()).hexdigest(),"rgb_sha256":hashlib.sha256(pixels).hexdigest(),
            "limits":"Independent geometry/depth reference from converted BSP; no retail texture, sky, gameplay or hardware-performance equivalence."}
    output.with_suffix('.json').write_text(json.dumps(result,indent=2)+'\n');print(output)


if __name__=='__main__':
    try: main()
    except (OSError,RuntimeError,ValueError) as error: sys.exit(f'Reference render failed: {error}')
