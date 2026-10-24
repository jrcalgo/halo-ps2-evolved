import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "closure_generator", ROOT / "tools/generate_hcu_step7_step8_closure.py")
closure = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(closure)


class SchemaBuildIdentityTests(unittest.TestCase):
    def test_exact_unit_sources_and_objects_are_bound(self):
        with tempfile.TemporaryDirectory() as temp:
            source_root = Path(temp)
            source_root.mkdir(exist_ok=True)
            one = source_root / "one.c"
            one.write_bytes(b"current source")
            built_hash = hashlib.sha256(b"current source").hexdigest()
            units = {
                "one.c": {"source_sha256": built_hash, "object_sha256": "obj-one"},
                "two.c": {"source_sha256": "old-source", "object_sha256": "obj-two"},
            }
            result = closure.schema_source_identity(units, source_root)

        self.assertEqual(result["status"], "stale-or-incomplete")
        self.assertEqual(result["counts"], {"match": 1, "changed": 0, "missing": 1})
        self.assertEqual(result["units"][0]["object_sha256"], "obj-one")
        self.assertEqual(result["units"][1]["status"], "missing")

    def test_changed_source_is_not_reported_as_current(self):
        with tempfile.TemporaryDirectory() as temp:
            source_root = Path(temp)
            (source_root / "unit.c").write_bytes(b"new")
            result = closure.schema_source_identity(
                {"unit.c": {"source_sha256": "old", "object_sha256": "obj"}},
                source_root)
        self.assertEqual(result["status"], "stale-or-incomplete")
        self.assertEqual(result["counts"], {"match": 0, "changed": 1, "missing": 0})


if __name__ == "__main__":
    unittest.main()
