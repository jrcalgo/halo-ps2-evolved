#!/usr/bin/env python3
"""Read-only, bounded PINE collector for the opt-in C3 session trace ABI."""
from __future__ import annotations
import argparse, datetime, hashlib, json, os, queue, signal, socket, struct, subprocess, sys, threading, time, traceback
from collections import deque
from pathlib import Path
HERE=Path(__file__).resolve().parent
VENDOR=Path(__file__).resolve().parents[7]/'build'/'c3'/'pine-probe-bridge-new'/'vendor'
sys.path.insert(0,str(VENDOR))
from elftools.elf.elffile import ELFFile
from elftools.dwarf.dwarf_expr import DWARFExprParser
from hcu_bitmap_defer_probe_decode import capture as capture_bitmap_defer_probe
from hcu_c3_phase_probe import (RING_BYTES, read_coherent as read_phase_probe,
                                read_frame_ring)
from hcu_c3_explosion_event_decode import capture as capture_explosion_event_ring
MAGIC=0x43545243; VERSION=1

def seq_delta(new, old):
    """Unsigned sequence distance with normal uint32 wraparound."""
    return (int(new)-int(old)) & 0xffffffff

def seq_after(old, offset):
    return (int(old)+int(offset)) & 0xffffffff

def next_deadline(previous_deadline, now, interval):
    """Keep cadence bounded after a long pause/overrun; never catch up in a burst."""
    candidate=previous_deadline+interval
    return candidate if candidate>now else now+interval

XINPUT_BUTTONS={1:'dpad_up',2:'dpad_down',4:'dpad_left',8:'dpad_right',16:'start',32:'back',64:'left_stick',128:'right_stick',256:'left_shoulder',512:'right_shoulder',4096:'A',8192:'B',16384:'X',32768:'Y'}
PAD_BUTTONS={0x0001:'select',0x0002:'L3',0x0004:'R3',0x0008:'start',0x0010:'up',0x0020:'right',0x0040:'down',0x0080:'left',0x0100:'L2',0x0200:'R2',0x0400:'L1',0x0800:'R1',0x1000:'triangle',0x2000:'circle',0x4000:'cross',0x8000:'square'}

def decode_buttons(bits):
    return [name for mask,name in XINPUT_BUTTONS.items() if int(bits or 0)&mask]

def decode_pad(bits):
    return [name for mask,name in PAD_BUTTONS.items() if int(bits or 0)&mask]

def counter_delta(new,old): return (int(new or 0)-int(old or 0))&0xffffffff

class Pine:
    def __init__(self,path,timeout=1.5): self.path=Path(path); self.sock=None; self.timeout=timeout; self.latencies=deque(maxlen=512); self.total_requests=0; self.total_latency_ns=0; self.max_latency_ns=0
    def mean_latency(self):
        vals=list(self.latencies)[-100:]
        return sum(vals)//len(vals) if vals else None
    def request(self,payload):
        if self.sock is None:
            self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); self.sock.settimeout(self.timeout); self.sock.connect(str(self.path))
        start=time.monotonic_ns(); self.sock.sendall(struct.pack('<I',len(payload)+4)+payload)
        def exact(n):
            b=bytearray()
            while len(b)<n:
                x=self.sock.recv(n-len(b))
                if not x: raise ConnectionError('PINE disconnected')
                b.extend(x)
            return bytes(b)
        n=struct.unpack('<I',exact(4))[0]
        if n<5 or n>450000: raise ValueError(f'invalid PINE response size {n}')
        r=exact(n-4)
        if r[0]: raise RuntimeError(f'PINE status {r[0]}')
        elapsed=time.monotonic_ns()-start; self.latencies.append(elapsed); self.total_requests+=1; self.total_latency_ns+=elapsed; self.max_latency_ns=max(self.max_latency_ns,elapsed); return r[1:]
    def scalar(self,opcode):return self.request(bytes((opcode,)))
    def vm_status(self):
        data=self.scalar(15)
        if len(data)!=4:raise ValueError('invalid PINE VM status response')
        value=struct.unpack('<I',data)[0]
        # PCSX2 PINE EmuStatus: Running=0, Paused=1, Shutdown=2.
        return value,{0:'running',1:'paused',2:'shutdown'}.get(value,f'unknown_{value}')
    def read64(self,addresses):
        out=[]
        for i in range(0,len(addresses),512):
            batch=addresses[i:i+512]; data=self.request(b''.join(b'\x03'+struct.pack('<I',a) for a in batch))
            if len(data)!=8*len(batch): raise ValueError('PINE read length mismatch')
            out.extend(struct.unpack('<'+'Q'*len(batch),data))
        return out
    def read(self,address,size):
        lo=address&~7; hi=(address+size+7)&~7
        if lo<0 or hi>32*1024*1024 or hi-lo>32*1024: raise ValueError('read outside bounded EE RAM span')
        qs=self.read64(list(range(lo,hi,8))); raw=b''.join(struct.pack('<Q',q) for q in qs)
        return raw[address-lo:address-lo+size]
    def close(self):
        if self.sock:
            try:self.sock.close()
            finally:self.sock=None

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def type_layout(die,parser,seen=None):
    seen=set() if seen is None else seen
    if not die or die.offset in seen:return {'tag':'unknown','size':0}
    seen.add(die.offset)
    while die.tag in ('DW_TAG_typedef','DW_TAG_const_type','DW_TAG_volatile_type','DW_TAG_restrict_type','DW_TAG_atomic_type'):
        ref=die.attributes.get('DW_AT_type')
        if not ref:break
        die=die.get_DIE_from_attribute('DW_AT_type')
    typ={'tag':die.tag.removeprefix('DW_TAG_'),'name':attr(die,'DW_AT_name'),'size':int(die.attributes.get('DW_AT_byte_size').value) if die.attributes.get('DW_AT_byte_size') else 0,'encoding':int(die.attributes['DW_AT_encoding'].value) if die.attributes.get('DW_AT_encoding') else None}
    ref=die.attributes.get('DW_AT_type')
    if ref and die.tag not in ('DW_TAG_structure_type','DW_TAG_union_type','DW_TAG_class_type'):
        typ['element']=type_layout(die.get_DIE_from_attribute('DW_AT_type'),parser,seen.copy())
    if die.tag=='DW_TAG_array_type':
        dimensions=[]
        for sub in (x for x in die.iter_children() if x.tag=='DW_TAG_subrange_type'):
            c=sub.attributes.get('DW_AT_count')
            u=sub.attributes.get('DW_AT_upper_bound')
            lo=sub.attributes.get('DW_AT_lower_bound')
            extent=(int(c.value) if c else
                    int(u.value)-(int(lo.value) if lo else 0)+1 if u else 0)
            dimensions.append(max(0,extent))
        if dimensions:
            # Primitive multidimensional arrays use a flat row-major list.
            typ['dimensions']=dimensions
            count=1
            for extent in dimensions: count*=extent
            typ['count']=count
    if die.tag in ('DW_TAG_structure_type','DW_TAG_union_type','DW_TAG_class_type'):
        typ['members']=[]
        for m in die.iter_children():
            if m.tag!='DW_TAG_member':continue
            l=m.attributes.get('DW_AT_data_member_location'); off=int(l.value) if l and isinstance(l.value,int) else 0
            if l and not isinstance(l.value,int):
                off=next((int(o.args[0]) for o in parser.parse_expr(bytes(l.value)) if o.op_name=='DW_OP_plus_uconst'),0)
            mr=m.attributes.get('DW_AT_type'); typ['members'].append({'name':attr(m,'DW_AT_name'),'offset':off,'type':type_layout(m.get_DIE_from_attribute('DW_AT_type'),parser,seen.copy()) if mr else {'tag':'unknown','size':0}})
    return typ

def attr(die,key,_seen=None):
    seen=set() if _seen is None else _seen
    if die.offset in seen:return None
    seen.add(die.offset); a=die.attributes.get(key)
    if a:return a.value.decode(errors='replace') if isinstance(a.value,bytes) else a.value
    for refkey in ('DW_AT_specification','DW_AT_abstract_origin'):
        ref=die.attributes.get(refkey)
        if ref:
            try:
                origin=die.get_DIE_from_attribute(refkey)
                value=attr(origin,key,seen)
                if value is not None:return value
            except Exception:pass
    return None

def find_global(elfpath,name,source=None):
    with open(elfpath,'rb') as f:
        elf=ELFFile(f); dwarf=elf.get_dwarf_info(); parser=DWARFExprParser(dwarf.structs)
        for cu in dwarf.iter_CUs():
            cu_name=attr(cu.get_top_DIE(),'DW_AT_name') or ''
            if source and Path(cu_name).name!=source:continue
            for d in cu.iter_DIEs():
                if d.tag!='DW_TAG_variable' or attr(d,'DW_AT_name')!=name:continue
                loc=d.attributes.get('DW_AT_location')
                if not loc:continue
                addr=next((int(o.args[0]) for o in parser.parse_expr(bytes(loc.value)) if o.op_name=='DW_OP_addr'),None)
                ref=d.attributes.get('DW_AT_type'); type_owner=d
                if not ref:
                    for refkey in ('DW_AT_specification','DW_AT_abstract_origin'):
                        if d.attributes.get(refkey):
                            try:
                                spec=d.get_DIE_from_attribute(refkey)
                                ref=spec.attributes.get('DW_AT_type')
                                if ref:type_owner=spec; break
                            except Exception:pass
                if addr is not None and ref:return addr,type_layout(type_owner.get_DIE_from_attribute('DW_AT_type'),parser)
    raise ValueError(f'DWARF global missing: {name}')

def render_tick_fingerprint(elfpath):
    with open(elfpath,'rb') as f:
        elf=ELFFile(f); dwarf=elf.get_dwarf_info(); addr=None
        for cu in dwarf.iter_CUs():
            for d in cu.iter_DIEs():
                if d.tag=='DW_TAG_subprogram' and attr(d,'DW_AT_name')=='hcu_c3_render_tick':
                    low=d.attributes.get('DW_AT_low_pc')
                    if low:addr=int(low.value); break
            if addr is not None:break
        if addr is None:raise ValueError('DWARF function hcu_c3_render_tick missing')
        for seg in elf.iter_segments():
            if seg['p_type']=='PT_LOAD' and seg['p_vaddr']<=addr and addr+16<=seg['p_vaddr']+seg['p_filesz']:
                off=seg['p_offset']+(addr-seg['p_vaddr']); f.seek(off); code=f.read(16)
                return addr,code
    raise ValueError('render tick is not file-backed')

def member(typ,name):
    return next(m for m in typ.get('members',[]) if m.get('name')==name)

def scalar(raw,typ):
    size=typ.get('size',0); tag=typ.get('tag','')
    if size not in (1,2,4,8): return None
    fmt={1:'B',2:'H',4:'I',8:'Q'}.get(size); enc=typ.get('encoding')
    if enc==4: fmt={4:'f',8:'d'}.get(size,fmt)
    elif enc==5: fmt={1:'b',2:'h',4:'i',8:'q'}.get(size,fmt)
    elif enc==2: fmt='?' if size==1 else fmt
    elif typ.get('tag')=='pointer_type':fmt={4:'I',8:'Q'}.get(size,fmt)
    return struct.unpack('<'+fmt,raw[:size])[0]

def tick_code_ready(live, expected):
    if live==expected: return True
    if live==bytes(len(expected)): return False
    raise ValueError(f'live render tick fingerprint mismatch: {live.hex()} != {expected.hex()}')

def trace_abi_ready(head, expected_bytes):
    values=(head.get('magic'),head.get('version'),head.get('bytes'))
    if values==(0,0,0): return False
    if values!=(MAGIC,VERSION,expected_bytes):
        raise ValueError(f'guest ABI mismatch: magic/version/bytes={values[0]}/{values[1]}/{values[2]}')
    return True

def decode_struct(raw,typ):
    out={}
    for m in typ.get('members',[]):
        n=m.get('name'); mt=m['type']; off=m['offset']; tag=mt.get('tag')
        if not n:continue
        if tag in ('structure_type','class_type'):
            out[n]=decode_struct(raw[off:off+mt['size']],mt)
        elif tag=='array_type':
            el=mt.get('element',{}); es=el.get('size',0); count=mt.get('count',0)
            if es and count and count*es<=len(raw)-off:
                if el.get('tag') in ('structure_type','class_type'): out[n]=[decode_struct(raw[off+i*es:off+(i+1)*es],el) for i in range(count)]
                else: out[n]=[scalar(raw[off+i*es:off+(i+1)*es],el) for i in range(count)]
        else: out[n]=scalar(raw[off:],mt)
    return out

def decode_array(raw, arrtype):
    el=arrtype.get('element',{}); size=el.get('size',0); count=arrtype.get('count',0)
    if not size or count*size>len(raw): return []
    if el.get('tag') in ('structure_type','class_type'):
        return [decode_struct(raw[i*size:(i+1)*size],el) for i in range(count)]
    return [scalar(raw[i*size:(i+1)*size],el) for i in range(count)]

def array_span(arrtype):
    return int(arrtype.get('count',0))*int((arrtype.get('element') or {}).get('size',0))

def optional_global(elfpath,name,source=None):
    try:
        address,typ=find_global(elfpath,name,source)
        return {'address':address,'type':typ}
    except (ValueError,KeyError):
        return None

def optional_symbol(elfpath,name,expected_size):
    """Resolve a fixed-width exported guest block from .symtab when LTO omits DWARF."""
    with open(elfpath,'rb') as f:
        elf=ELFFile(f); symtab=elf.get_section_by_name('.symtab')
        if symtab is None:return None
        matches=[sym for sym in symtab.iter_symbols()
                 if sym.name==name and sym['st_info']['type']=='STT_OBJECT'
                 and int(sym['st_size'])==expected_size]
        if len(matches)!=1:return None
        return {'address':int(matches[0]['st_value']),
                'type':{'tag':'structure_type','size':expected_size,'members':[]},
                'source':'elf_symtab'}

def capture_array(p, desc):
    if not desc or desc['type'].get('tag')!='array_type': return []
    t=desc['type']; size=array_span(t)
    if size>24*1024: raise ValueError('refusing oversized debug-described array')
    return decode_array(p.read(desc['address'],size),t)

def scalar_at(p, desc, offset=0):
    if not desc:return None
    t=desc['type']; return scalar(p.read(desc['address']+offset,t.get('size',4)),t)

def safe_cstring(p,address,limit=96):
    if not address:return None
    try:
        raw=p.read(int(address),limit); end=raw.find(b'\0')
        return raw[:end if end>=0 else limit].decode('utf-8','replace')
    except Exception:return None

def capture_model_entries(p, globals_):
    slots=capture_array(p,globals_.get('s_slots')); meta=capture_array(p,globals_.get('s_meta'))
    pins=capture_array(p,globals_.get('s_slot_pins')); count=scalar_at(p,globals_.get('s_slot_count'))
    if count is None:return {'status':'unavailable','reason':'slot_count_missing','entries':[]}
    if not globals_.get('s_slots') or not globals_.get('s_meta') or not globals_.get('s_slot_pins'):
        return {'status':'unavailable','reason':'model_slots_meta_or_pins_missing','entries':[]}
    out=[]; slot_array=globals_['s_slots']['type']; slot_elem=slot_array.get('element',{}); slot_members={m['name']:m for m in slot_elem.get('members',[])}
    entry_ptr_type=slot_members.get('entry',{}).get('type',{}); table_type=entry_ptr_type.get('element',{})
    for i in range(min(int(count),len(slots),len(meta))):
        s=slots[i]; m=meta[i]
        pointer=s.get('entry'); table={}
        if pointer and table_type.get('size'):
            try:table=decode_struct(p.read(pointer,table_type['size']),table_type)
            except Exception:table={}
        out.append({'slot':i,'resource_id':m.get('resource_id'),'source_datum':m.get('source_datum'),'resource_type':'model','name':safe_cstring(p,table.get('path')),'model_chunk':table.get('model_chunk'),'texture_chunk':table.get('texture_chunk'),'loaded':bool(m.get('loaded') or s.get('loaded')),'refused':bool(s.get('refused')),'model_bytes':s.get('model_size') or m.get('model_bytes'),'texture_bytes':s.get('tex_size') or m.get('texture_bytes'),'texture_count':m.get('texture_count'),'node_count':m.get('node_count'),'pool_offset':s.get('pool_off'),'pool_bytes':s.get('pool_size'),'last_used_frame':s.get('last_used'),'snapshot_pins':pins[i] if i<len(pins) else None})
    required=('resource_id','source_datum','model_bytes','texture_bytes','texture_count')
    complete=bool(out) and all(all(e.get(k) is not None for k in required) for e in out)
    return {'status':'ok' if complete else 'incomplete','reason':None if complete else 'required_model_metadata_missing','entries':out}

def capture_gs_cache(p, desc):
    if not desc:return {'status':'unavailable','entries':[],'summary':None}
    t=desc['type']; mm={m['name']:m for m in t.get('members',[])}
    if 'entry' not in mm:return {'status':'unavailable','entries':[],'summary':None}
    em=mm['entry']; entries=decode_array(p.read(desc['address']+em['offset'],array_span(em['type'])),em['type'])
    kicks=[]
    if 'last_kick' in mm:
        km=mm['last_kick']; kicks=decode_array(p.read(desc['address']+km['offset'],array_span(km['type'])),km['type'])
    summary={}
    for name in ('total_pages','clut_slots','max_keys','gpu_in_flight','hits','misses','evictions','deferred','failed','upload_bytes','budget_bytes','next_kick','fence_done'):
        if name in mm:
            m=mm[name]; summary[name]=scalar(p.read(desc['address']+m['offset'],m['type']['size']),m['type'])
    valid_pages=0; out=[]
    for i,e in enumerate(entries):
        valid=bool(e.get('valid')); pages=e.get('pages') or 0
        if valid:valid_pages+=pages
        kick=kicks[i] if i<len(kicks) else None; done=summary.get('fence_done')
        complete=None if done is None or kick is None else (True if kick==0 else ((done-kick)&0xffffffff)<0x80000000)
        out.append({'slot':i,'resource_id':e.get('key') if valid else None,'resource_type':'texture','valid':valid,'pending_upload':bool(e.get('pending_upload')),'last_used_frame':e.get('last_used'),'first_gs_page':e.get('first_page'),'pages':pages if valid else 0,'bytes':pages*8192 if valid else 0,'clut_slot':e.get('clut_slot') if valid else None,'last_kick':kick,'fence_done':done,'fence_complete':complete})
    summary['valid_pages']=valid_pages; summary['used_bytes']=valid_pages*8192
    return {'status':'ok','entries':out,'summary':summary}

def capture_rejection(p, desc):
    if not desc:return {'status':'unavailable'}
    size=desc['type'].get('size',0)
    if not size or size>512:return {'status':'unavailable'}
    raw=p.read(desc['address'],size)
    words=list(struct.unpack('<'+'I'*(len(raw)//4),raw[:len(raw)//4*4]))
    detail=decode_struct(raw,desc['type']) if desc['type'].get('tag') in ('structure_type','class_type') else None
    return {'status':'ok','words':words,'detail':detail}

def capture_snapshot_stats(p,desc):
    if not desc:return {'status':'unavailable'}
    try:return {'status':'ok',**decode_struct(p.read(desc['address'],desc['type']['size']),desc['type'])}
    except Exception as e:return {'status':'read_error','error':str(e)}

def read_ring(p,base,offset,capacity,element_type,previous_seq,current_seq):
    """Read newly published records in contiguous wrapped batches, then validate row seqlocks."""
    delta=seq_delta(current_seq,previous_seq); first=max(1,delta-capacity+1); seqs=[seq_after(previous_seq,j) for j in range(first,delta+1)]
    item_size=element_type['size']; groups=[]
    for n in seqs:
        idx=(n-1)%capacity
        if groups and idx==groups[-1][1]+1:
            groups[-1][1]=idx; groups[-1][3].append(n)
        else:groups.append([idx,idx,item_size,[n]])
    out=[]
    for first_idx,last_idx,_,group_seqs in groups:
        raw=p.read(base+offset+first_idx*item_size,(last_idx-first_idx+1)*item_size)
        for j,n in enumerate(group_seqs):
            row=decode_struct(raw[j*item_size:(j+1)*item_size],element_type)
            if row.get('seq')==((2*n)&0xffffffff) and not(row.get('seq',0)&1):out.append((n,row))
    return out

def append_row(q,row,drop):
    try:q.put_nowait(row); return drop
    except queue.Full:return drop+1

def write_jsonl(path, row):
    with path.open('a',buffering=1) as f:
        f.write(json.dumps(row,separators=(',',':'),allow_nan=False)+'\n')

def writer(q,path,stop,health):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('a',buffering=1) as f:
        while not stop.is_set() or not q.empty():
            try:r=q.get(timeout=.2)
            except queue.Empty:continue
            try:f.write(json.dumps(r,separators=(',',':'),allow_nan=False)+'\n')
            except Exception:health['writer_errors']+=1

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--elf',type=Path,required=True); ap.add_argument('--sha256'); ap.add_argument('--socket',type=Path,required=True); ap.add_argument('--out',type=Path,required=True); ap.add_argument('--interval',type=float,default=.2); ap.add_argument('--queue-size',type=int,default=64); ap.add_argument('--duration',type=float,default=0); ap.add_argument('--abi-startup-wait',type=float,default=0); a=ap.parse_args()
    if not 1<=a.queue_size<=128:raise SystemExit('--queue-size must be between 1 and 128')
    digest=sha(a.elf)
    if a.sha256 and digest.lower()!=a.sha256.lower():raise SystemExit(f'ELF SHA mismatch: {digest}')
    base,typ=find_global(a.elf,'g_hcu_c3_session_trace','hcu_main.c')
    if typ.get('size',0)>24*1024:raise SystemExit('trace ABI exceeds 24 KiB cap')
    members={m['name']:m for m in typ['members']}; fcap=member(typ,'frames')['type'].get('count'); icap=member(typ,'inputs')['type'].get('count'); ecap=member(typ,'events')['type'].get('count')
    if not (0<fcap<=128 and 0<icap<=256 and 0<ecap<=256):raise SystemExit(f'unsafe/unexpected ring capacities {fcap}/{icap}/{ecap}')
    globals_={'s_slots':optional_global(a.elf,'s_slots','hcu_render_objects.c'),'s_meta':optional_global(a.elf,'s_meta','hcu_render_objects.c'),'s_slot_pins':optional_global(a.elf,'s_slot_pins','hcu_render_objects.c'),'s_slot_count':optional_global(a.elf,'s_slot_count','hcu_render_objects.c'),'s_tc':optional_global(a.elf,'s_tc','bsp_render.c'),'hcu_snapshot_bank_last_rejection':optional_global(a.elf,'hcu_snapshot_bank_last_rejection','hcu_snapshot_bank.c'),'s_stats':optional_global(a.elf,'s_stats','hcu_snapshot_bank.c'),'bitmap_defer_probe':optional_global(a.elf,'g_hcu_bitmap_defer_probe','texcache.c'),'phase_probe':optional_global(a.elf,'g_hcu_c3_phase_probe','hcu_main.c'),'explosion_event_ring':optional_global(a.elf,'hcu_c3_explosion_event_block_v1','main.c')}
    q=queue.Queue(a.queue_size); stop=threading.Event(); health={'writer_errors':0}; wt=threading.Thread(target=writer,args=(q,a.out,stop,health),daemon=True); wt.start(); p=Pine(a.socket); last_frame=last_input=last_event=0; dropped=0; batch=0; start=time.monotonic(); deadline=start; rows=0; previous_poll_mono_ns=None; previous_frame_write_seq=None; last_memory_capture=0.0; current_entryset_id=None; latest_action=None; latest_input_state=None; last_cache_totals=None; previous_bitmap_totals=None; last_rejection_state=None; prev_input=None; last_vm_status=None; last_vm_state='unknown'; last_vm_status_mono_ns=None; poll_durations=deque(maxlen=512); skipped_initial_history=None; explosion_last_sequence=0
    def enqueue(row):
        nonlocal dropped
        dropped=append_row(q,row,dropped)
    tick_addr,tick_code=render_tick_fingerprint(a.elf)
    if a.abi_startup_wait and not 0 < a.abi_startup_wait <= 180:
        raise SystemExit('--abi-startup-wait must be in (0, 180]')
    startup_deadline=time.monotonic()+a.abi_startup_wait if a.abi_startup_wait else None
    while True:
        live_code=p.read(tick_addr,len(tick_code))
        try: code_ready=tick_code_ready(live_code,tick_code)
        except ValueError as error:
            p.close(); stop.set(); wt.join(timeout=5); raise SystemExit(str(error))
        if code_ready: break
        if startup_deadline is None or time.monotonic()>=startup_deadline:
            p.close(); stop.set(); wt.join(timeout=5)
            raise SystemExit(f'render tick code remained uninitialized after {a.abi_startup_wait}s')
        time.sleep(.05)
    if a.abi_startup_wait:
        header_bytes=members['frames']['offset']
        while True:
            initial=decode_struct(p.read(base,header_bytes),typ)
            if trace_abi_ready(initial,typ['size']): break
            if time.monotonic()>=startup_deadline:
                p.close(); stop.set(); wt.join(timeout=5)
                raise SystemExit(f'trace ABI remained uninitialized after {a.abi_startup_wait}s')
            time.sleep(.05)
    defer_desc=globals_.get('bitmap_defer_probe')
    phase_desc=globals_.get('phase_probe')
    frame_ring_desc=(optional_global(a.elf,'g_hcu_c3_frame_probe_ring','hcu_main.c') or
                     optional_symbol(a.elf,'g_hcu_c3_frame_probe_ring',RING_BYTES))
    frame_ring_last_sequence=0
    explosion_desc=globals_.get('explosion_event_ring') or optional_symbol(
        a.elf,'hcu_c3_explosion_event_block_v1',788)
    enqueue({'kind':'identity','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'elf_sha256':digest,'elf':str(a.elf),'abi':'hcu_session_trace/v1','global_address':hex(base),'global_bytes':typ['size'],'bitmap_defer_probe':({'abi':'hcu_bitmap_defer_probe/v1','global_address':hex(defer_desc['address']),'global_bytes':defer_desc['type']['size']} if defer_desc else None),'phase_probe':({'abi':'hcu_c3_phase_probe/v1','global_address':hex(phase_desc['address']),'global_bytes':phase_desc['type']['size']} if phase_desc else None),'explosion_event_ring':({'abi':'hcu_c3_explosion_event_ring/v1','global_address':hex(explosion_desc['address']),'global_bytes':explosion_desc['type']['size']} if explosion_desc else None),'render_tick_address':hex(tick_addr),'render_tick_fingerprint':tick_code.hex(),'live_render_tick_fingerprint':live_code.hex(),'live_code_match':True,'read_only':True,'collector_pid':os.getpid()})
    if frame_ring_desc:
        enqueue({'kind':'probe_identity','utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 'abi':'hcu_c3_frame_probe_ring/v1',
                 'global_address':hex(frame_ring_desc['address']),
                 'global_bytes':frame_ring_desc['type']['size']})
    try:
        while not a.duration or time.monotonic()-start<a.duration:
            cycle=time.monotonic_ns(); cpu_start=time.thread_time_ns(); rpc_count_before=p.total_requests; rpc_time_before=p.total_latency_ns; retries=0; snap=None; hdr=None
            while retries<=2:
                before=struct.unpack('<I',p.read(base+members['seq']['offset'],4))[0]
                if before&1: retries+=1; continue
                # Header through inputs capacity, excluding the large rings.
                hsize=members['frames']['offset']
                head=decode_struct(p.read(base,hsize),typ)
                if head.get('magic')!=MAGIC or head.get('version')!=VERSION or head.get('bytes')!=typ['size']:
                    raise ValueError(f'guest ABI mismatch: magic/version/bytes={head.get("magic")}/{head.get("version")}/{head.get("bytes")}')
                fw=head['frame_write_seq']; iw=head['input_write_seq']; ew=head['event_write_seq']; frame_drop=head.get('frame_overwrites',0); input_drop=head.get('input_overwrites',0)
                if previous_frame_write_seq is None and last_input==0 and last_event==0:
                    # Start at the current guest frontier: pre-collector ring contents
                    # are history, not collector loss, and must not burst-fill the queue.
                    skipped_initial_history={'frames':min(fw,fcap),'inputs':min(iw,icap),'model_events':min(ew,ecap)}
                    if fw:last_frame=seq_after(fw,0xffffffff)
                    last_input=iw; last_event=ew
                newf=min(seq_delta(fw,last_frame),fcap); newi=min(seq_delta(iw,last_input),icap)
                fs=member(typ,'frames'); ins=member(typ,'inputs'); er=member(typ,'events')
                rb=read_ring(p,base,fs['offset'],fcap,fs['type']['element'],last_frame,fw)
                ev=read_ring(p,base,ins['offset'],icap,ins['type']['element'],last_input,iw)
                cacheev=read_ring(p,base,er['offset'],ecap,er['type']['element'],last_event,ew)
                retries+=max(0,min(seq_delta(fw,last_frame),fcap)-len(rb))+max(0,min(seq_delta(iw,last_input),icap)-len(ev))+max(0,min(seq_delta(ew,last_event),ecap)-len(cacheev))
                after=struct.unpack('<I',p.read(base+members['seq']['offset'],4))[0]
                if before==after and not(after&1):hdr=head; snap=(rb,ev,cacheev); break
                retries+=1
            now=time.monotonic_ns(); utc=datetime.datetime.now(datetime.timezone.utc).isoformat(); batch+=1; poll_ns=now-cycle; poll_durations.append(poll_ns); rpc_count_window=p.total_requests-rpc_count_before; rpc_time_window=p.total_latency_ns-rpc_time_before
            if snap is None:
                enqueue({'kind':'collector_health','utc':utc,'mono_ns':now,'coherence':'torn','retry_count':retries,'skipped_initial_history':skipped_initial_history,'pine_latency_ns':p.latencies[-1] if p.latencies else None,'queue_depth':q.qsize(),'queue_drops':dropped}); time.sleep(a.interval); continue
            frames,events,cache_events=snap; frame_total=seq_delta(hdr['frame_write_seq'],last_frame); input_total=seq_delta(hdr['input_write_seq'],last_input); event_total=seq_delta(hdr['event_write_seq'],last_event)
            bitmap_defer_probe=capture_bitmap_defer_probe(p.read, defer_desc, decode_struct)
            if bitmap_defer_probe.get('status')=='coherent':
                bitmap_defer_probe['matches_trace_frame']=bitmap_defer_probe.get('frame')==hdr.get('frame')
                bitmap_defer_probe['matches_trace_tick']=bitmap_defer_probe.get('tick')==hdr.get('tick')
            phase_probe={'status':'not_present'}
            if phase_desc:
                try:
                    phase_probe={'status':'coherent','abi':'hcu_c3_phase_probe/v1',**read_phase_probe(p.read,phase_desc['address'])}
                    phase_probe['matches_trace_frame']=phase_probe.get('frame')==hdr.get('frame')
                except (TimeoutError,ValueError) as error:
                    phase_probe={'status':'invalid_or_torn','error':str(error)}
            if frame_ring_desc:
                try:
                    ring=read_frame_ring(p.read,frame_ring_desc['address'],frame_ring_last_sequence)
                    for frame_probe in ring['frames']:
                        enqueue({'kind':'c3_frame_probe','utc':utc,'mono_ns':now,
                                 'elf_sha256':digest,'probe':frame_probe,
                                 'ring_write_sequence':ring['write_sequence'],
                                 'ring_overwrites':ring['overwrites'],
                                 'lost_since_last_read':ring['lost_since_last_read']})
                    if ring['lost_since_last_read']:
                        enqueue({'kind':'collector_health','utc':utc,'mono_ns':now,
                                 'c3_frame_ring_loss':ring['lost_since_last_read']})
                    frame_ring_last_sequence=ring['write_sequence']
                except (TimeoutError,ValueError) as error:
                    enqueue({'kind':'collector_health','utc':utc,'mono_ns':now,
                             'c3_frame_ring_status':'invalid_or_torn','error':str(error)})
            explosion_event_ring=capture_explosion_event_ring(p.read, explosion_desc)
            new_explosion_events=[]
            if explosion_event_ring.get('status')=='coherent':
                frontier=int(explosion_event_ring.get('write_sequence',0))
                prior_frontier=explosion_last_sequence
                new_explosion_events=[event for event in explosion_event_ring.get('events',[])
                                      if prior_frontier < int(event['seq']) <= frontier]
                for event in new_explosion_events:
                    kind=event['kind']; phase=int(event['phase']); generation=int(event['generation'])
                    projectile=int(event['projectile_index']); owner=int(event['owner_index'])
                    if kind=='launch':
                        event_type={8:'frag',9:'plasma',10:'rocket'}.get(phase,'unknown')
                        marker=f"c3-explosion-projectile type={event_type} state={'launched' if event_type=='rocket' else 'created'} projectile={projectile} generation={generation} owner={owner}"
                    else:
                        marker=f"c3-explosion-detonation event={int(event['seq'])} phase={phase} projectile={projectile} generation={generation} owner={owner}"
                    enqueue({'kind':'native_marker','utc':utc,'mono_ns':now,'marker':marker,'event':event})
                    if kind=='detonate' and phase==10:
                        observed=1 if int(event['flags']) & 9 else 0
                        pos=event['position']
                        marker=(f"c3-explosion-impact rocket projectile={projectile} generation={generation} "
                                f"position={pos[0]:.3f},{pos[1]:.3f},{pos[2]:.3f} impact-observed={observed}")
                        enqueue({'kind':'native_marker','utc':utc,'mono_ns':now,'marker':marker,'event':event})
                if new_explosion_events:
                    explosion_last_sequence=max(int(event['seq']) for event in new_explosion_events)
                explosion_event_ring['new_events']=new_explosion_events
                explosion_event_ring['read_sequence_gap']=max(0,frontier-prior_frontier-len(new_explosion_events))
                explosion_last_sequence=max(explosion_last_sequence,frontier)
            ring_lost_f=max(0,frame_total-len(frames)); ring_lost_i=max(0,input_total-len(events)); ring_lost_e=max(0,event_total-len(cache_events))
            if batch==1 or batch%5==0:
                try:last_vm_status,last_vm_state=p.vm_status();last_vm_status_mono_ns=now
                except (OSError,ValueError,RuntimeError):last_vm_status=None;last_vm_state='unavailable';last_vm_status_mono_ns=now
            fresh_frame=frames[-1][1] if frames else None
            if fresh_frame:
                last_cache_totals={k:fresh_frame.get(k) for k in ('cache_resident','cache_loads','cache_misses','cache_evictions','cache_pool_used','cache_pool_capacity','cache_pool_refusals','cache_fence_blocked')}
            input_actions={}
            for input_seq,ir in events:
                raw_down=decode_pad(ir.get('edge_down')); raw_up=decode_pad(ir.get('edge_up')); current_eff=int(ir.get('effective_buttons') or 0)
                eff_down=eff_up=[]; analog_changes={}; action_names=[f'PAD_{x}_DOWN' for x in raw_down]+[f'PAD_{x}_UP' for x in raw_up]
                if prev_input is not None:
                    changed=current_eff^int(prev_input.get('effective_buttons') or 0); eff_down=decode_buttons(changed&current_eff); eff_up=decode_buttons(changed&~current_eff)
                    action_names += [f'XINPUT_{x}_DOWN' for x in eff_down]+[f'XINPUT_{x}_UP' for x in eff_up]
                    # Stick center is not exactly zero on every controller. Treat
                    # small signed values as neutral; labels describe controls,
                    # not game actions or accepted gameplay commands.
                    for axis in ('effective_lx','effective_ly','effective_rx','effective_ry'):
                        was=abs(int(prev_input.get(axis) or 0))>4096; now_active=abs(int(ir.get(axis) or 0))>4096
                        if was!=now_active: action_names.append(f'{axis.upper()}_'+('ACTIVE' if now_active else 'NEUTRAL'))
                    for key in ('analog_buttons_low','analog_buttons_high'):
                        old=int(prev_input.get(key) or 0); new=int(ir.get(key) or 0)
                        for b in range(4):
                            ov=(old>>(8*b))&255; nv=(new>>(8*b))&255
                            if (ov>0)!=(nv>0):
                                names=('A','B','X','Y') if key.endswith('low') else ('BLACK','WHITE','LT','RT')
                                analog_changes[f'{key}_{names[b]}']='pressed' if nv else 'released'; action_names.append(f'{key}_{names[b]}_'+('PRESSED' if nv else 'RELEASED'))
                action={'raw_pad_down':raw_down,'raw_pad_up':raw_up,'effective_down':eff_down,'effective_up':eff_up,'analog_changes':analog_changes,'effective_buttons':decode_buttons(current_eff),'frame':ir.get('frame')}
                if action_names:latest_action=action
                input_actions[input_seq]=action_names
                latest_input_state={'raw_buttons':ir.get('raw_buttons'),'raw_pad_buttons':decode_pad(ir.get('raw_buttons')),'effective_buttons':ir.get('effective_buttons'),'decoded_buttons':decode_buttons(ir.get('effective_buttons')),'connected':ir.get('connected'),'raw_axes':ir.get('axes'),'effective_axes':{'lx':ir.get('effective_lx'),'ly':ir.get('effective_ly'),'rx':ir.get('effective_rx'),'ry':ir.get('effective_ry')},'analog_buttons_low':ir.get('analog_buttons_low'),'analog_buttons_high':ir.get('analog_buttons_high')}
                prev_input=ir
            capture_memory=(time.monotonic()-last_memory_capture>=1.0 or current_entryset_id is None)
            entryset_row=None
            if capture_memory:
                current_entryset_id=f'entryset-{batch}'; last_memory_capture=time.monotonic()
                model_snap=capture_model_entries(p,globals_); gs_snap=capture_gs_cache(p,globals_.get('s_tc')); reject_snap=last_rejection_state
                entryset_row={'kind':'entryset','sample_id':batch,'fps_sample_id':batch,'entryset_id':current_entryset_id,'refresh_hz':1,'coherence':'best_effort_static_reads','models':model_snap,'gs_texture_cache':gs_snap,'snapshot_last_rejection':reject_snap}
            probe_mask=fresh_frame.get('probe_valid',0) if fresh_frame else 0
            probe_details=({'parent_perf':{'valid':bool(probe_mask&1),'frame':fresh_frame.get('perf_probe_frame'),'frame_cycles':fresh_frame.get('frame_cycles'),'bsp_wait_cycles':fresh_frame.get('bsp_wait_cycles'),'previous_kick_wait_cycles':fresh_frame.get('previous_kick_wait_cycles')},'object_fp':{'valid':bool(probe_mask&2),'frame':fresh_frame.get('object_probe_frame'),'view':fresh_frame.get('object_probe_view'),'world_cycles':fresh_frame.get('object_world_cycles'),'fp_cycles':fresh_frame.get('object_fp_cycles'),'fp_overhead_cycles':fresh_frame.get('object_fp_overhead_cycles'),'drawn':fresh_frame.get('object_drawn'),'triangles':fresh_frame.get('object_triangles'),'skinned_nodes':fresh_frame.get('object_skinned_nodes'),'failures':fresh_frame.get('object_failures')},'video':{'valid':bool(probe_mask&4),'frame':fresh_frame.get('video_probe_frame'),'present_cycles':fresh_frame.get('video_present_cycles'),'wait_cycles':fresh_frame.get('video_wait_cycles'),'select_cycles':fresh_frame.get('video_select_cycles')},'scope':{'valid':bool(probe_mask&8),'frame':fresh_frame.get('scope_probe_frame'),'scope_valid':fresh_frame.get('scope_valid'),'requests':fresh_frame.get('scope_requests'),'views':fresh_frame.get('scope_views'),'tiles':fresh_frame.get('scope_tiles'),'copy_attempts':fresh_frame.get('scope_copy_attempts'),'copy_queued':fresh_frame.get('scope_copy_queued'),'fence_refusals':fresh_frame.get('scope_fence_refusals'),'capacity_refusals':fresh_frame.get('scope_capacity_refusals'),'copy_refusals':fresh_frame.get('scope_copy_refusals'),'emitted_qw':fresh_frame.get('scope_emitted_qw'),'backend_cycles':fresh_frame.get('scope_backend_cycles'),'backend_status':fresh_frame.get('scope_backend_status'),'bitmap_hits_total':fresh_frame.get('bitmap_hits_total'),'bitmap_misses_total':fresh_frame.get('bitmap_misses_total'),'source_reads_total':fresh_frame.get('bitmap_source_reads_total'),'source_bytes_total':fresh_frame.get('bitmap_source_bytes_total'),'hash_checks_total':fresh_frame.get('bitmap_hash_checks_total'),'parses_total':fresh_frame.get('bitmap_parses_total'),'read_calls_total':fresh_frame.get('bitmap_read_calls_total'),'read_bytes_total':fresh_frame.get('bitmap_read_bytes_total'),'read_cycles_total':fresh_frame.get('bitmap_read_cycles_total'),'hash_cycles_total':fresh_frame.get('bitmap_hash_cycles_total'),'parse_cycles_total':fresh_frame.get('bitmap_parse_cycles_total'),'source_cycles_total':fresh_frame.get('bitmap_source_cycles_total'),'deferred_total':fresh_frame.get('bitmap_deferred_total')}} if fresh_frame else None)
            bitmap_totals={k:v for k,v in (fresh_frame or {}).items() if k.startswith('bitmap_') and k.endswith('_total')}
            bitmap_deltas={k.replace('_total',''):counter_delta(v,(previous_bitmap_totals or {}).get(k,v)) for k,v in bitmap_totals.items()} if previous_bitmap_totals is not None else None
            if bitmap_totals:previous_bitmap_totals=bitmap_totals
            last_rejection_state=capture_rejection(p,globals_.get('hcu_snapshot_bank_last_rejection'))
            snapshot_stats=capture_snapshot_stats(p,globals_.get('s_stats'))
            # End the FPS/observer window after every PINE read, including the
            # once-per-second model/GS entry capture and status query.
            now=time.monotonic_ns(); utc=datetime.datetime.now(datetime.timezone.utc).isoformat()
            poll_ns=now-cycle; poll_durations[-1]=poll_ns
            rpc_count_window=p.total_requests-rpc_count_before; rpc_time_window=p.total_latency_ns-rpc_time_before
            fps_delta=seq_delta(hdr['frame_write_seq'],previous_frame_write_seq) if previous_frame_write_seq is not None else None
            fps_window_sec=(now-previous_poll_mono_ns)/1e9 if previous_poll_mono_ns is not None else None
            fps_wall=(fps_delta/fps_window_sec) if fps_delta is not None and fps_window_sec and fps_window_sec>0 else None
            fps_window={'sample_id':batch,'window_start_mono_ns':previous_poll_mono_ns,'window_end_mono_ns':now,'frame_delta':fps_delta,'wall_seconds':fps_window_sec,'fps':fps_wall,'unit':'render frames / host monotonic wall second','pause_state':'no_frame_advance' if fps_delta==0 else 'unknown'}
            fps_window['vm_state']=last_vm_state
            if last_vm_state=='paused':fps_window['pause_state']='pcsx2_paused'
            elif last_vm_state=='running' and fps_delta==0:fps_window['pause_state']='running_no_frame_advance'
            elif last_vm_state=='shutdown':fps_window['pause_state']='pcsx2_shutdown'
            if entryset_row:
                entryset_row.update({'utc':utc,'mono_ns':now,'snapshot_last_rejection':last_rejection_state})
                enqueue(entryset_row)
            axes_now=(latest_input_state or {}).get('axes') or 0; analow=(latest_input_state or {}).get('analog_buttons_low') or 0; anahi=(latest_input_state or {}).get('analog_buttons_high') or 0
            enqueue({'kind':'sample','utc':utc,'mono_ns':now,'sample_id':batch,'elf_sha256':digest,'freshness':'fresh' if frames else 'stale','coherence':'coherent','skipped_initial_history':skipped_initial_history if batch==1 else None,'vm_status':last_vm_status,'vm_state':last_vm_state,'vm_status_age_sec':(now-last_vm_status_mono_ns)/1e9 if last_vm_status_mono_ns else None,'fps_wall_window':fps_window,'render_frame':hdr.get('frame'),'tick':hdr.get('tick'),'map_generation':fresh_frame.get('map_generation') if fresh_frame else None,'heading_yaw':fresh_frame.get('camera_yaw') if fresh_frame else None,'camera_hfov':fresh_frame.get('camera_hfov') if fresh_frame else None,'held_weapon_id':fresh_frame.get('fp_weapon_resource_id') if fresh_frame else None,'held_hands_id':fresh_frame.get('fp_hands_resource_id') if fresh_frame else None,'native_zoom_level':fresh_frame.get('native_zoom_level') if fresh_frame else None,'native_zoom_valid':bool(fresh_frame and fresh_frame.get('state_valid',0)&16),'latest_action':latest_action,'latest_input_state':latest_input_state or {'raw_buttons':hdr.get('raw_buttons'),'effective_buttons':hdr.get('effective_buttons'),'connected':hdr.get('connected')},'decoded_buttons':decode_buttons((latest_input_state or {}).get('effective_buttons')),'analog_buttons_low':analow,'analog_intent':{'black':anahi&255,'white':(anahi>>8)&255,'left_trigger':(anahi>>16)&255,'right_trigger':(anahi>>24)&255},'probes':probe_details,'bitmap_defer_probe':bitmap_defer_probe,'phase_probe':phase_probe,'explosion_event_ring':explosion_event_ring,'bitmap_counter_deltas':bitmap_deltas,'snapshot_bank':snapshot_stats,'snapshot_last_rejection':last_rejection_state,'cache_totals':last_cache_totals,'cache_events':{'MODEL_LOAD':sum(1 for _,e in cache_events if e.get('type')==1),'MODEL_EVICT':sum(1 for _,e in cache_events if e.get('type')==2),'POOL_REFUSED':sum(1 for _,e in cache_events if e.get('type')==4),'FENCE_REFUSED':sum(1 for _,e in cache_events if e.get('type')==5)},'entryset_id':current_entryset_id,'collector':{'queue_depth':q.qsize(),'queue_drops':dropped,'pine_rpc_count_window':rpc_count_window,'pine_rpc_time_ns_window':rpc_time_window,'pine_rpc_time_ns_per_sec':rpc_time_window/(fps_window_sec or a.interval),'poll_elapsed_ns':poll_ns,'poll_worst_recent_ns':max(poll_durations) if poll_durations else poll_ns,'pine_last_latency_ns':p.latencies[-1] if p.latencies else None,'pine_mean_latency_ns':p.mean_latency(),'sample_cpu_ns':time.thread_time_ns()-cpu_start}})
            for n,r in frames:
                fr=r.get('frame'); row={'kind':'frame','sample_id':batch,'fps_wall_window':fps_window,'utc':utc,'mono_ns':now,'sample_seq':n,'elf_sha256':digest,'map_generation':r.get('map_generation'),'render_frame':fr,'tick':r.get('tick'),'game_frame_tick':hdr.get('tick'),'guest_frame_overwrites':hdr.get('frame_overwrites'),'guest_input_overwrites':hdr.get('input_overwrites'),'guest_event_overwrites':hdr.get('event_overwrites'),'collector_frame_ring_loss':ring_lost_f,'collector_event_ring_loss':ring_lost_i,'collector_model_event_ring_loss':ring_lost_e,'coherence':'coherent','freshness':'fresh','frame_advanced':True,'paused':None,'pause_state':'unknown','entryset_id':current_entryset_id,'latest_action':latest_action,'timing':{k:v for k,v in r.items() if k.endswith('_cycles') or k.endswith('_ticks')},'camera':{'state_valid':r.get('state_valid',0),'position':[r.get('camera_x'),r.get('camera_y'),r.get('camera_z')],'yaw':r.get('camera_yaw'),'pitch':r.get('camera_pitch'),'hfov':r.get('camera_hfov')},'held_resources':{'state_valid':r.get('state_valid',0),'weapon_resource_id':r.get('fp_weapon_resource_id'),'hands_resource_id':r.get('fp_hands_resource_id'),'native_zoom_level':r.get('native_zoom_level'),'native_zoom_valid':bool(r.get('state_valid',0)&16)},'input':{'raw_buttons':r.get('raw_buttons'),'effective_buttons':r.get('effective_buttons'),'decoded_buttons':decode_buttons(r.get('effective_buttons')),'connected':r.get('connected'),'edge_down':r.get('edge_down'),'edge_up':r.get('edge_up')},'probes':{k:v for k,v in r.items() if ('scope_' in k or 'bitmap_' in k or 'video_' in k or 'object_' in k or 'perf_' in k or k in ('probe_valid',))},'cache':{'valid':bool((r.get('state_valid',0)&8)),'resident':r.get('cache_resident'),'loads':r.get('cache_loads'),'misses':r.get('cache_misses'),'evictions':r.get('cache_evictions'),'pool_used':r.get('cache_pool_used'),'pool_capacity':r.get('cache_pool_capacity'),'pool_refusals':r.get('cache_pool_refusals'),'fence_blocked':r.get('cache_fence_blocked')},'collector':{'pine_batch_latency_ns':p.latencies[-1] if p.latencies else None,'pine_mean_latency_ns':p.mean_latency(),'sample_cpu_ns':time.thread_time_ns()-cpu_start,'queue_depth':q.qsize(),'queue_drops':dropped}}
                enqueue(row); rows+=1
            if not frames:
                # Keep wall-time zero-FPS evidence while the guest frame counter is
                # stationary. We cannot infer that this is a pause rather than a stall.
                enqueue({'kind':'frame','sample_id':batch,'fps_wall_window':fps_window,'utc':utc,'mono_ns':now,'sample_seq':None,'elf_sha256':digest,'map_generation':None,'render_frame':hdr.get('frame'),'tick':None,'game_frame_tick':hdr.get('tick'),'coherence':'coherent','freshness':'stale','frame_advanced':False,'paused':None,'pause_state':'frame_counter_not_advanced','entryset_id':current_entryset_id,'latest_action':latest_action,'timing':None,'input':latest_input_state,'player':None,'cache':last_cache_totals,'collector_frame_ring_loss':ring_lost_f,'collector_event_ring_loss':ring_lost_i,'collector_model_event_ring_loss':ring_lost_e})
            for n,r in events:
                axes=r.get('axes') or 0; analoglo=r.get('analog_buttons_low') or 0; analoghi=r.get('analog_buttons_high') or 0
                down=decode_pad(r.get('edge_down')); up=decode_pad(r.get('edge_up')); analog_names=('A','B','X','Y')
                low=[(analoglo>>(8*i))&255 for i in range(4)]; high=[(analoghi>>(8*i))&255 for i in range(4)]
                acts=[f'button_down:{x}' for x in down]+[f'button_up:{x}' for x in up]
                enqueue({'kind':'event','source':'controller_sample','sample_id':batch,'fps_sample_id':batch,'entryset_id':current_entryset_id,'utc':utc,'mono_ns':now,'event_seq':n,'frame':r.get('frame'),'tick':r.get('tick'),'action':'input_sample','actions':input_actions.get(n,[]),'raw_buttons':r.get('raw_buttons'),'raw_pad_buttons':decode_pad(r.get('raw_buttons')),'effective_buttons':r.get('effective_buttons'),'decoded_buttons':decode_buttons(r.get('effective_buttons')),'edge_down_raw_pad':r.get('edge_down'),'edge_up_raw_pad':r.get('edge_up'),'connected':r.get('connected'),'axes_raw':{'lx':axes&255,'ly':(axes>>8)&255,'rx':(axes>>16)&255,'ry':(axes>>24)&255},'axes_effective':{'lx':r.get('effective_lx'),'ly':r.get('effective_ly'),'rx':r.get('effective_rx'),'ry':r.get('effective_ry')},'analog_buttons':dict(zip(analog_names,low)),'analog_intent':{'black':high[0],'white':high[1],'left_trigger':high[2],'right_trigger':high[3]},'accepted_shot_observed':False,'coherence':'coherent'})
            for n,r in cache_events:
                names={1:'MODEL_LOAD',2:'MODEL_EVICT',3:'MODEL_REFUSED',4:'POOL_REFUSED',5:'FENCE_REFUSED'}
                enqueue({'kind':'event','source':'model_cache','sample_id':batch,'fps_sample_id':batch,'entryset_id':current_entryset_id,'utc':utc,'mono_ns':now,'event_seq':n,'frame':r.get('frame'),'tick':r.get('tick'),'action':names.get(r.get('type'),'unknown_cache_event'),'event_type':names.get(r.get('type'),'unknown'),'entry_index':r.get('entry_index'),'source_datum':r.get('source_datum'),'bytes':r.get('bytes'),'reason':r.get('reason'),'generation':r.get('generation'),'coherence':'coherent'})
            last_frame=hdr['frame_write_seq']; last_input=hdr['input_write_seq']; last_event=hdr['event_write_seq']
            previous_poll_mono_ns=now; previous_frame_write_seq=hdr['frame_write_seq']
            enqueue({'kind':'collector_health','utc':utc,'mono_ns':now,'batch':batch,'pine_rpc_count_window':rpc_count_window,'pine_rpc_count_total':p.total_requests,'pine_rpc_time_ns_window':rpc_time_window,'pine_rpc_time_ns_total':p.total_latency_ns,'pine_rpc_worst_ns':p.max_latency_ns,'pine_last_latency_ns':p.latencies[-1] if p.latencies else None,'pine_mean_latency_ns':p.mean_latency(),'poll_elapsed_ns':poll_ns,'poll_worst_recent_ns':max(poll_durations) if poll_durations else poll_ns,'guest_frame_overwrites':hdr.get('frame_overwrites'),'guest_input_overwrites':hdr.get('input_overwrites'),'guest_event_overwrites':hdr.get('event_overwrites'),'collector_frame_ring_loss':ring_lost_f,'collector_event_ring_loss':ring_lost_i,'collector_model_event_ring_loss':ring_lost_e,'queue_depth':q.qsize(),'queue_drops':dropped,'writer_errors':health['writer_errors'],'sample_cpu_ns':time.thread_time_ns()-cpu_start,'log_bytes':a.out.stat().st_size if a.out.exists() else 0,'elapsed_sec':round(time.monotonic()-start,3)})
            deadline=next_deadline(deadline,time.monotonic(),a.interval); time.sleep(max(0,deadline-time.monotonic()))
    except KeyboardInterrupt:pass
    finally:
        p.close(); stop.set(); wt.join(timeout=10)
        if wt.is_alive(): print('writer did not flush within 10 seconds',file=sys.stderr)
if __name__=='__main__':main()
