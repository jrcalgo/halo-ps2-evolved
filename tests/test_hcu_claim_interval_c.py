import ctypes as ct
from pathlib import Path
import random
import tempfile
import unittest
import subprocess

from tools.hcu_claim_interval_c_replay import Context, Entry, ROOT, compile_library, replay


class CClaimsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="claims-c-test-")
        cls.lib = compile_library(cls.temp.name)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setup_store(self, capacity, span):
        self.entries = (Entry * capacity)()
        self.context = Context()
        self.assertEqual(self.lib.ps2_claim_intervals_init(ct.byref(self.context),
                                                         self.entries, capacity, span), 1)

    def call(self, name, first, size):
        return getattr(self.lib, "ps2_claim_intervals_" + name)(ct.byref(self.context), first, size)

    def snapshot(self):
        return [(entry.first, entry.end) for entry in self.entries[:self.context.count]]

    def test_random_bitmap_differential(self):
        self.setup_store(2048, 8192)
        bitmap = bytearray(8192)
        rng = random.Random(830)
        for iteration in range(40000):
            first = rng.randrange(len(bitmap))
            size = rng.randrange(min(150, len(bitmap) - first) + 1)
            operation = rng.randrange(3)
            if operation == 0:
                expected = 1
                position = first
                while position < first + size:
                    width = 32 if position % 32 == 0 and first + size - position >= 32 else 1
                    if any(bitmap[position:position + width]):
                        expected = 0
                        break
                    bitmap[position:position + width] = bytes([1]) * width
                    position += width
                self.assertEqual(self.call("claim", first, size), expected)
            elif operation == 1:
                bitmap[first:first + size] = bytes(size)
                self.assertEqual(self.call("unclaim", first, size), 1)
            else:
                self.assertEqual(self.call("any", first, size), int(any(bitmap[first:first + size])))
            if iteration % 1000 == 0:
                actual = bytearray(len(bitmap))
                previous_end = -1
                for a, b in self.snapshot():
                    self.assertGreater(a, previous_end)
                    self.assertLess(a, b)
                    actual[a:b] = bytes([1]) * (b - a)
                    previous_end = b
                self.assertEqual(actual, bitmap)

    def test_capacity_atomic_invalid_and_adjacency(self):
        self.setup_store(1, 100)
        self.assertEqual(self.call("claim", 10, 10), 1)
        saved = self.snapshot()
        self.assertEqual(self.call("claim", 30, 10), -1)
        self.assertEqual(self.snapshot(), saved)
        self.assertEqual(self.call("unclaim", 14, 2), -1)
        self.assertEqual(self.snapshot(), saved)
        for name in ("claim", "unclaim", "any"):
            self.assertEqual(self.call(name, 0xffffffff, 2), -1)
            self.assertEqual(self.snapshot(), saved)
        self.assertEqual(self.call("claim", 0, 15), 0)
        self.assertEqual(self.snapshot(), [(0, 20)])
        self.assertEqual(self.call("claim", 20, 10), 1)
        self.assertEqual(self.snapshot(), [(0, 30)])
        self.assertEqual(self.call("unclaim", 0, 30), 1)
        self.assertEqual(self.snapshot(), [])
        self.assertEqual(self.call("claim", 100, 0), 1)
        self.assertEqual(self.call("any", 100, 0), 0)

    def test_actual_ce_validator_trace(self):
        trace = ROOT / "build/hcu-claims-experiment-20261021/retail.trace"
        if not trace.is_file():
            self.skipTest("run real CE-validator trace capture first")
        result = replay(trace, 8192)
        self.assertEqual(result["operations"], 226395)
        self.assertEqual(result["maximum_intervals"], 4820)
        self.assertEqual(result["reserved_entry_bytes"], 65536)

    def test_ce_word_failure_prefix(self):
        for occupied, start, end, expected in ((1, 0, 64, [(1, 2)]),
                                               (31, 0, 64, [(31, 32)]),
                                               (40, 0, 64, [(0, 32), (40, 41)]),
                                               (40, 1, 64, [(1, 32), (40, 41)]),
                                               (40, 33, 64, [(33, 41)]),
                                               (40, 0, 48, [(0, 41)])):
            self.setup_store(16, 128)
            self.assertEqual(self.call("claim", occupied, 1), 1)
            self.assertEqual(self.call("claim", start, end - start), 0)
            self.assertEqual(self.snapshot(), expected)

    def test_literal_production_claim_function(self):
        source = (ROOT / "submodules/halo-ce-universal/port/linux/game/tag_validate.c").read_text()
        body = source[source.index("static boolean claim(\n"):source.index("/* unclaims the size bytes")]
        # The actual production function is compiled verbatim; only its address
        # provider/global store are replaced with a bounded test domain.
        glue = r'''
#include <stdint.h>
#include <string.h>
typedef int boolean;
#define TRUE 1
#define FALSE 0
#define CLAIM_BITS 32
static unsigned long words[256];
static unsigned long *tag_validate_claims = words;
static struct {unsigned long claims_address_space_size;} tag_validate_globals = {8192};
static boolean claims_cover(unsigned long size) {return size <= 8192;}
static boolean claim_address_offset(void const *address, unsigned long size, unsigned long *first)
{*first=(uintptr_t)address; return *first<=8192 && size<=8192-*first;}
'''
        glue += body
        glue += r'''
int ce_claim(unsigned first, unsigned size) {return claim((void *)(uintptr_t)first,size);}
void ce_reset(void) {memset(words,0,sizeof(words));}
int ce_byte(unsigned pos) {return !!(words[pos/32] & (1UL<<(pos%32)));}
void ce_clear(unsigned first,unsigned size) {unsigned i;for(i=first;i<first+size;i++)words[i/32]&=~(1UL<<(i%32));}
'''
        path = Path(self.temp.name) / "literal_claim.c"
        library = path.with_suffix(".so")
        path.write_text(glue)
        subprocess.run(["gcc", "-shared", "-fPIC", "-O2", str(path), "-o", str(library)], check=True)
        oracle = ct.CDLL(str(library))
        self.setup_store(2048, 8192)
        rng = random.Random(32840)
        for iteration in range(30000):
            first = rng.randrange(8192)
            size = rng.randrange(min(150, 8192-first) + 1)
            if iteration % 4:
                self.assertEqual(self.call("claim", first, size), oracle.ce_claim(first, size))
            else:
                self.assertEqual(self.call("unclaim", first, size), 1)
                oracle.ce_clear(first, size)
            if iteration % 300 == 0:
                self.assertEqual([self.call("any", pos, 1) for pos in range(8192)],
                                 [oracle.ce_byte(pos) for pos in range(8192)])


if __name__ == "__main__":
    unittest.main()
