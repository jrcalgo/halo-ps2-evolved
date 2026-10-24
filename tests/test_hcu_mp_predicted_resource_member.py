"""Exercise CE's exact predicted-resource validator against synthetic entries."""
from pathlib import Path
import hashlib
import os
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "submodules/halo-ce-universal/source/cache/predicted_resources.c"
SOURCE_SHA256 = "c2f81e7cab0307a5cb33f2094837556b3638594711a2e88dc187a1ec1c093eb4"
TEMPLATE = ROOT / "tests/hcu_predicted_resource_member_main.c"


def extract_definition(source: str, marker: str) -> str:
    start = source.index(marker)
    opening = source.index("{", start)
    prototype_end = source.find(";", start, opening)
    if prototype_end >= 0:
        start = source.index(marker, prototype_end + 1)
        opening = source.index("{", start)
    depth = 0
    for position in range(opening, len(source)):
        if source[position] == "{":
            depth += 1
        elif source[position] == "}":
            depth -= 1
            if depth == 0:
                return source[start:position + 1]
    raise AssertionError(f"unterminated CE function {marker}")


class PredictedResourceMemberTest(unittest.TestCase):
    def test_ce_reads_resource_index_and_checks_bitmap_extent(self):
        source_bytes = SOURCE.read_bytes()
        self.assertEqual(hashlib.sha256(source_bytes).hexdigest(), SOURCE_SHA256)
        function = extract_definition(
            source_bytes.decode(), "static boolean predicted_resource_valid(")
        runner = TEMPLATE.read_text().replace(
            "/* CE_PREDICTED_RESOURCE_VALID */", function)
        with tempfile.TemporaryDirectory(prefix="hcu-predicted-resource-") as temp:
            temp = Path(temp)
            source = temp / "main.c"
            executable = temp / "predicted-resource"
            source.write_text(runner)
            compiled = subprocess.run(
                [os.environ.get("CC", "cc"), "-std=c99", "-Wall", "-Wextra",
                 "-Werror", "-Wno-unused-function", str(source), "-o", str(executable)],
                capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
            result = subprocess.run([str(executable)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("resource-index validation passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
