"""Bounded decoder validation for the optional C3 bitmap-defer PINE block."""
from __future__ import annotations
import struct

MAGIC = 0x42445031
VERSION = 1

def capture(read, desc, decode_struct):
    if not desc:
        return {'status': 'not_present'}
    typ = desc['type']
    size = int(typ.get('size', 0))
    if typ.get('tag') not in ('structure_type', 'class_type') or not 0 < size <= 1024:
        raise ValueError('unsafe bitmap-defer probe layout')
    members = {m['name']: m for m in typ.get('members', [])}
    if 'seq' not in members:
        raise ValueError('bitmap-defer probe has no sequence word')
    seq_addr = desc['address'] + members['seq']['offset']
    before = struct.unpack('<I', read(seq_addr, 4))[0]
    if before & 1:
        return {'status': 'torn', 'seq_before': before}
    row = decode_struct(read(desc['address'], size), typ)
    after = struct.unpack('<I', read(seq_addr, 4))[0]
    if before != after or after & 1 or row.get('seq') != after:
        return {'status': 'torn', 'seq_before': before, 'seq_after': after}
    if row.get('magic') != MAGIC or row.get('version') != VERSION or row.get('bytes') != size:
        return {'status': 'invalid', 'magic': row.get('magic'), 'version': row.get('version'),
                'bytes': row.get('bytes'), 'layout_bytes': size}
    return {'status': 'coherent', 'abi': 'hcu_bitmap_defer_probe/v1', 'global_bytes': size, **row}
