"""Check the HCU fixed-UTC mktime/localtime replacement in src/stream/hcu_c3_tz.c.

The object is compiled for the host and driven by a small C program. The expected
values come from Python's calendar.timegm, so the test checks the calendar maths
and the field normalisation, not a copy of the C code. It proves nothing about
the EE link; tools/c2_profile_boot_matrix.py --c3 links the ELF.
"""
import calendar
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/stream/hcu_c3_tz.c"

DRIVER = r"""
#include <stdio.h>
#include <time.h>
int main(void) {
    struct tm tm = {0};
    time_t t;
    struct tm *g;
    /* Field normalisation: month 13 and day 0 carry into the next year. */
    tm.tm_year = 124; tm.tm_mon = 12; tm.tm_mday = 0; tm.tm_hour = 25; tm.tm_min = 61; tm.tm_sec = 3;
    t = mktime(&tm);
    printf("%lld %d %d %d %d %d\n", (long long)t, tm.tm_year, tm.tm_mon, tm.tm_mday, tm.tm_hour, tm.tm_min);
    tm.tm_year = 70; tm.tm_mon = 0; tm.tm_mday = 1; tm.tm_hour = 0; tm.tm_min = 0; tm.tm_sec = 0;
    printf("%lld\n", (long long)mktime(&tm));
    tm.tm_year = 69; tm.tm_mon = 11; tm.tm_mday = 31; tm.tm_hour = 23; tm.tm_min = 59; tm.tm_sec = 59;
    printf("%lld\n", (long long)mktime(&tm));
    t = 951782400; /* 2000-02-29 00:00:00 UTC */
    g = localtime(&t);
    printf("%d %d %d %d\n", g->tm_year, g->tm_mon, g->tm_mday, g->tm_yday);
    return 0;
}
"""


def expected_timegm(year, mon, day, hour, minute, sec):
    """Python normalises like mktime: month carries into years, then day/hour/min/sec are added."""
    year += (mon) // 12
    mon %= 12
    base = calendar.timegm((year, mon + 1, 1, 0, 0, 0))
    return base + (day - 1) * 86400 + hour * 3600 + minute * 60 + sec


class HcuC3TzTest(unittest.TestCase):
    def test_utc_conversion_matches_timegm(self):
        cc = shutil.which("gcc") or shutil.which("cc")
        if cc is None:
            self.skipTest("no host C compiler")
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            driver = tmp_path / "driver.c"
            driver.write_text(DRIVER)
            exe = tmp_path / "tz_test"
            build = subprocess.run(
                [cc, "-std=gnu11", "-Wall", "-Werror", "-I", str(ROOT / "submodules/halo-ce-universal/source/cseries"),
                 str(driver), str(SOURCE), "-o", str(exe)],
                capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(exe)], capture_output=True, text=True, check=True, env={"TZ": "UTC0"})
        lines = run.stdout.split("\n")
        # 2024-12-00 25:61:03 normalises to 2025-01-01 02:01:03 (day 0 is 31 Dec, then 25h, 61m).
        want = expected_timegm(2024, 12, 0, 25, 61, 3)
        got_t, got_year, got_mon, got_day, got_hour, got_min = lines[0].split()
        self.assertEqual(int(got_t), want)
        self.assertEqual((int(got_year), int(got_mon), int(got_day), int(got_hour), int(got_min)),
                         (125, 0, 1, 2, 1))
        self.assertEqual(int(lines[1]), 0)
        self.assertEqual(int(lines[2]), -1)
        self.assertEqual(lines[3].split(), ["100", "1", "29", "59"])


if __name__ == "__main__":
    unittest.main()
