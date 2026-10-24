"""Bounded exact claims candidate and optional real CE-validator trace replay.

The retail mode instruments a temporary copy of the actual validator included
by the existing native transaction fixture. Production sources stay untouched.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest


class CapacityError(Exception):
    pass


class Intervals:
    def __init__(self, capacity=65536):
        self.capacity = capacity
        self.ranges = []
        self.peak = 0
        self.work = 0

    @staticmethod
    def bounds(first, size):
        if first < 0 or size < 0 or first > 0xffffffff or size > 0xffffffff - first:
            raise ValueError("range exceeds checked 32-bit claims address space")

    def commit(self, result):
        if len(result) > self.capacity:
            raise CapacityError("bounded interval table exhausted")
        self.work += len(result)
        self.ranges = result
        self.peak = max(self.peak, len(result))

    def any(self, first, size):
        self.bounds(first, size)
        if not size:
            return False
        i = bisect.bisect_left(self.ranges, (first + size,))
        self.work += max(1, len(self.ranges).bit_length())
        return bool(i and self.ranges[i - 1][1] > first)

    def claim(self, first, size):
        self.bounds(first, size)
        if not size:
            return True
        end = first + size
        i = bisect.bisect_right(self.ranges, (first, 1 << 64))
        self.work += max(1, len(self.ranges).bit_length())
        if i and self.ranges[i - 1][1] > first:
            return False
        valid = not (i < len(self.ranges) and self.ranges[i][0] < end)
        # CE checks aligned complete 32-byte words before setting their bits.
        if not valid:
            conflict = self.ranges[i][0]
            word_first = conflict & ~31
            if word_first >= first and end - word_first >= 32:
                conflict = word_first
            end = conflict
        if end > first:
            start = i
            if i and self.ranges[i - 1][1] == first:
                start -= 1
                first = self.ranges[start][0]
            stop = i
            if i < len(self.ranges) and self.ranges[i][0] == end:
                end = self.ranges[i][1]
                stop += 1
            self.commit(self.ranges[:start] + [(first, end)] + self.ranges[stop:])
        return valid

    def clear(self, first, size):
        self.bounds(first, size)
        self.work += len(self.ranges)
        end = first + size
        result = []
        for a, b in self.ranges:
            if b <= first or a >= end:
                result.append((a, b))
            else:
                if a < first:
                    result.append((a, first))
                if b > end:
                    result.append((end, b))
        self.commit(result)


def replay(path, capacity=65536):
    started = time.perf_counter()
    candidate = Intervals(capacity)
    count = 0
    bitmap_peak = 0
    operation_counts = {}
    for line in Path(path).read_text().splitlines():
        op, *values = line.split()
        operation_counts[op] = operation_counts.get(op, 0) + 1
        nums = list(map(int, values))
        if op == "R":
            candidate.ranges = []
            bitmap_peak = max(bitmap_peak, (nums[0] + 31) // 32 * 4)
        elif op == "U":
            candidate.clear(*nums)
        elif op in ("C", "Q", "P"):
            first, size, expected = nums
            actual = candidate.claim(first, size) if op == "C" else candidate.any(first, size)
            if actual != bool(expected):
                raise AssertionError((count, line, actual, candidate.ranges[:5]))
        else:
            raise AssertionError(line)
        count += 1
    if not operation_counts.get("R") or not operation_counts.get("C"):
        raise AssertionError("trace contains no complete validator claim domain")
    return dict(operations=count, maximum_intervals=candidate.peak,
                operation_counts=operation_counts,
                table_payload_peak_bytes=candidate.peak * 8,
                bounded_table_payload_bytes=capacity * 8,
                exact_bitmap_peak_bytes=bitmap_peak,
                comparison_and_copy_work=candidate.work,
                host_python_replay_seconds=time.perf_counter() - started,
                limitation="Python diagnostic; no EE cycle or target-memory claim")


def instrument(source, trace):
    for seam in ("static boolean claim(\n", "static void unclaim(\n",
                 "boolean tag_validate_claimed(\n", "boolean tag_validate_any_claimed(\n",
                 "/* unclaims the size bytes", "/* whether a string ends"):
        if source.count(seam) != 1:
            raise ValueError("validator instrumentation seam changed: " + seam)
    source = source.replace("static boolean claim(\n", "static boolean claim_actual(\n", 1)
    source = source.replace("static void unclaim(\n", "static void unclaim_actual(\n", 1)
    source = source.replace("boolean tag_validate_claimed(\n", "boolean tag_validate_claimed_actual(\n", 1)
    source = source.replace("boolean tag_validate_any_claimed(\n", "boolean tag_validate_any_claimed_actual(\n", 1)
    source = source.replace("memset(tag_validate_claims, 0, tag_validate_claims_size);",
                            'memset(tag_validate_claims, 0, tag_validate_claims_size);\n'
                            'claim_trace(\'R\', tag_validate_globals.claims_address_space_size, 0, 0);')
    declarations = "\nstatic void claim_trace(int, unsigned long, unsigned long, int);\n"
    source = source.replace("/* ---------- constants */", declarations + "\n/* ---------- constants */", 1)
    wrapper = r'''
static boolean claim(void const *address, unsigned long size)
{
    unsigned long offset; boolean valid_offset = claim_address_offset(address, size, &offset);
    boolean result = claim_actual(address, size);
    if (valid_offset) claim_trace('C', offset, size, result);
    return result;
}
'''
    source = source.replace("/* unclaims the size bytes", wrapper + "\n/* unclaims the size bytes", 1)
    wrapper = r'''
static void unclaim(unsigned long first, unsigned long size)
{
    unclaim_actual(first, size); claim_trace('U', first, size, 0);
}
'''
    source = source.replace("/* whether a string ends", wrapper + "\n/* whether a string ends", 1)
    source += r'''
boolean tag_validate_claimed(void const *address)
{
    unsigned long offset; boolean result = tag_validate_claimed_actual(address);
    if (claim_address_offset(address, 1, &offset)) claim_trace('P', offset, 1, result);
    return result;
}
boolean tag_validate_any_claimed(void const *address, unsigned long size)
{
    unsigned long offset; boolean result = tag_validate_any_claimed_actual(address, size);
    if (claim_address_offset(address, size, &offset)) claim_trace('Q', offset, size, result);
    return result;
}
'''
    source += '\nstatic void claim_trace(int op, unsigned long a, unsigned long b, int result)\n{\n'
    source += 'static FILE *file; if (!file) file=fopen(' + json.dumps(str(trace)) + ', "a");\n'
    source += 'if (!file) abort();\nif(op==\'R\') fprintf(file,"R %lu\\n",a);\n'
    source += 'else if(op==\'U\') fprintf(file,"U %lu %lu\\n",a,b);\n'
    source += 'else fprintf(file,"%c %lu %lu %d\\n",op,a,b,result); fflush(file);\n}\n'
    return source


def retail(trace):
    root = Path(__file__).resolve().parents[1]
    original_run = subprocess.run
    with tempfile.TemporaryDirectory(prefix="hcu-claims-") as temp_text:
        temp = Path(temp_text)
        validator = root / "submodules/halo-ce-universal/port/linux/game/tag_validate.c"
        transformed = temp / "tag_validate_instrumented.c"
        transformed.write_text(instrument(validator.read_text(), trace))
        main_path = root / "tests/hcu_scenario_bsp_switch_main.c"
        rewritten = temp / "main.c"
        text = main_path.read_text().replace(
            '#include "../submodules/halo-ce-universal/port/linux/game/tag_validate.c"',
            '#include ' + json.dumps(str(transformed)))
        rewritten.write_text(text)
        identity = {
            "validator_sha256": hashlib.sha256(validator.read_bytes()).hexdigest(),
            "instrumented_validator_sha256": hashlib.sha256(transformed.read_bytes()).hexdigest(),
            "fixture_original_sha256": hashlib.sha256(main_path.read_bytes()).hexdigest(),
            "fixture_compiled_sha256": hashlib.sha256(rewritten.read_bytes()).hexdigest(),
            "fixture_python_sha256": hashlib.sha256((root / "tests/test_hcu_scenario_bsp_switch.py").read_bytes()).hexdigest(),
            "trace_scope": "actual CE validator, host ILP32 a30/a50 package transactions",
        }
        trace.with_suffix(trace.suffix + ".identity.json").write_text(json.dumps(identity, indent=2) + "\n")

        def run(command, *args, **kwargs):
            if isinstance(command, list) and str(main_path) in command:
                command = [str(rewritten) if item == str(main_path) else item for item in command]
            return original_run(command, *args, **kwargs)

        spec = importlib.util.spec_from_file_location("claims_retail_fixture", root / "tests/test_hcu_scenario_bsp_switch.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite = unittest.TestSuite()
        for name in dir(module):
            cls = getattr(module, name)
            if isinstance(cls, type) and issubclass(cls, unittest.TestCase):
                for method in unittest.defaultTestLoader.getTestCaseNames(cls):
                    if "retail" in method:
                        suite.addTest(cls(method))
        subprocess.run = run
        try:
            result = unittest.TextTestRunner(verbosity=2).run(suite)
        finally:
            subprocess.run = original_run
        if not result.wasSuccessful() or result.skipped:
            raise RuntimeError("retail fixture failed or skipped")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trace", type=Path, required=True)
    parser.add_argument("--retail", action="store_true")
    parser.add_argument("--capacity", type=int, default=65536)
    args = parser.parse_args()
    if args.retail:
        if args.trace.exists():
            raise SystemExit("choose a fresh trace path")
        retail(args.trace.resolve())
    print(json.dumps(replay(args.trace, args.capacity), indent=2))


if __name__ == "__main__":
    main()
