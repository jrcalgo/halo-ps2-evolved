"""Losslessly pack an embedded IRX with the engine's existing LZ4 codec."""
import argparse
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "submodules/halo-ps2/tools"))
from halo2ps2.hp2 import lz4_compress, lz4_decompress

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path)
parser.add_argument("output", type=Path)
args = parser.parse_args()
raw = args.source.read_bytes()
if not 0 < len(raw) <= 16384:
    parser.error("IRX exceeds the fixed unpacking scratch budget")
packed = lz4_compress(raw)
assert lz4_decompress(packed, len(raw)) == raw
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_bytes(packed)
