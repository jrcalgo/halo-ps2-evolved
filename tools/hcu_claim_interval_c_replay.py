"""Compile the allocation-free C candidate and replay real CE claim traces."""
import argparse
import ctypes as ct
import json
from pathlib import Path
import subprocess
import tempfile
import time


ROOT = Path(__file__).resolve().parents[1]
PORT = ROOT / "submodules/halo-ce-universal/port/ps2"


class Entry(ct.Structure):
    _fields_ = [("first", ct.c_uint32), ("end", ct.c_uint32)]


class Context(ct.Structure):
    _fields_ = [("entries", ct.POINTER(Entry)), ("capacity", ct.c_uint32),
                ("count", ct.c_uint32), ("high_water", ct.c_uint32),
                ("span", ct.c_uint32), ("comparisons", ct.c_uint64),
                ("moved_records", ct.c_uint64)]


def compile_library(directory):
    library = Path(directory) / "claims.so"
    subprocess.run(["gcc", "-shared", "-fPIC", "-O2", "-std=gnu89", "-Wall", "-Wextra",
                    "-Werror", "-I" + str(PORT / "include"),
                    str(PORT / "src/ps2_claim_intervals.c"), "-o", str(library)], check=True)
    lib = ct.CDLL(str(library))
    lib.ps2_claim_intervals_init.argtypes = [ct.POINTER(Context), ct.POINTER(Entry), ct.c_uint32, ct.c_uint32]
    lib.ps2_claim_intervals_reset.argtypes = [ct.POINTER(Context)]
    lib.ps2_claim_intervals_reset.restype = None
    for name in ("claim", "unclaim", "any"):
        function = getattr(lib, "ps2_claim_intervals_" + name)
        function.argtypes = [ct.POINTER(Context), ct.c_uint32, ct.c_uint32]
        function.restype = ct.c_int
    return lib


def replay(trace, capacity=8192):
    started = time.perf_counter()
    with tempfile.TemporaryDirectory(prefix="hcu-c-claims-") as temp:
        lib = compile_library(temp)
        entries = (Entry * capacity)()
        context = Context()
        operations = 0
        bitmap_peak = 0
        counts = {}
        for line in Path(trace).read_text().splitlines():
            op, *values = line.split()
            nums = list(map(int, values))
            counts[op] = counts.get(op, 0) + 1
            if op == "R":
                # Preserve cumulative high-water/counters across independent domains.
                peak, comparisons, moved = context.high_water, context.comparisons, context.moved_records
                assert lib.ps2_claim_intervals_init(ct.byref(context), entries, capacity, nums[0]) == 1
                context.high_water, context.comparisons, context.moved_records = peak, comparisons, moved
                bitmap_peak = max(bitmap_peak, (nums[0] + 31) // 32 * 4)
            elif op == "U":
                assert lib.ps2_claim_intervals_unclaim(ct.byref(context), *nums) == 1
            else:
                first, size, expected = nums
                assert op in ("C", "P", "Q"), line
                name = "claim" if op == "C" else "any"
                actual = getattr(lib, "ps2_claim_intervals_" + name)(ct.byref(context), first, size)
                if actual != expected:
                    raise AssertionError((operations, line, actual))
            operations += 1
        if not counts.get("R") or not counts.get("C"):
            raise AssertionError("empty/incomplete trace")
        return dict(operations=operations, operation_counts=counts,
                    maximum_intervals=context.high_water,
                    reserved_entry_bytes=ct.sizeof(entries),
                    host_context_bytes=ct.sizeof(context),
                    caller_storage_host_bytes=ct.sizeof(entries) + ct.sizeof(context),
                    exact_bitmap_peak_bytes=bitmap_peak,
                    binary_search_and_clear_comparisons=context.comparisons,
                    moved_records=context.moved_records,
                    moved_bytes=context.moved_records * ct.sizeof(Entry),
                    host_compile_and_replay_seconds=time.perf_counter() - started,
                    limitation="host C implementation through ctypes; target cycles and ILP32 context size need qualification")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("trace", type=Path)
    parser.add_argument("--capacity", type=int, default=8192)
    args = parser.parse_args()
    print(json.dumps(replay(args.trace, args.capacity), indent=2))
