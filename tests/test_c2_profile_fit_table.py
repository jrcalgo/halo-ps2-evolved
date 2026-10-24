import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.c2_profile_fit_table import extract, matched_owner, owner_qualifies_fit


class ProfileFitMatchingTests(unittest.TestCase):
    def test_two_profiles_only_exact_package_identity_matches(self):
        row_a = {"name": "map_a_session", "map":"map_a", "hcp_package_sha256": "a" * 64,
                 "hcp_package_sha256_matches_manifest":True,"profile_id":7}
        row_b = {"name": "map_b_session", "map":"map_b", "hcp_package_sha256": "b" * 64,
                 "hcp_package_sha256_matches_manifest":True}
        sample = {"bound": 1, "capacity": 100, "current": 25, "peak": 50,
                  "failures": 0, "resets": 1}
        evidence = {"complete": True, "identity": ["map_a_session","mounted-map:map_a"],
                    "owners": {"streaming": [sample]},
                    "provenance": {"profile_package_sha256": "a" * 64,"profile_name":"map_a_session",
                                   "partition_profile":"map_a_session","scenario_mode":"capacity",
                                   "runtime_profile":{"row":"map_a_session","map":"map_a","profile_id":7}}}
        self.assertEqual(matched_owner(row_a, evidence, "streaming", "capacity")[0], sample)
        self.assertIsNone(matched_owner(row_b, evidence, "streaming", "capacity"))

    def test_unbound_owner_is_not_a_guarded_measurement(self):
        profile = {"name": "map_a_session", "map":"map_a", "hcp_package_sha256": "a" * 64,
                   "hcp_package_sha256_matches_manifest":True,"profile_id":7}
        evidence = {"complete": True, "identity": ["map_a_session","mounted-map:map_a"],
                    "owners": {"streaming": [{"bound": 0, "capacity": 0}]},
                    "provenance": {"profile_package_sha256": "a" * 64,"profile_name":"map_a_session",
                                   "partition_profile":"map_a_session","scenario_mode":"capacity",
                                   "runtime_profile":{"row":"map_a_session","map":"map_a","profile_id":7}}}
        self.assertIsNone(matched_owner(profile, evidence, "streaming", "capacity"))

    def test_nonzero_failure_counter_disqualifies_fit_but_preserves_observation(self):
        row = {"name":"map_a_session","map":"map_a","hcp_package_sha256":"a"*64,
               "hcp_package_sha256_matches_manifest":True,"profile_id":7}
        sample = {"bound":1,"capacity":100,"current":90,"peak":100,"failures":2,"resets":1}
        evidence = {"complete":True,"identity":["map_a_session","mounted-map:map_a"],
                    "owners":{"streaming":[sample]},"provenance":{"profile_package_sha256":"a"*64,
                      "profile_name":"map_a_session","partition_profile":"map_a_session","scenario_mode":"capacity",
                      "runtime_profile":{"row":"map_a_session","map":"map_a","profile_id":7}}}
        observed, _ = matched_owner(row,evidence,"streaming","capacity")
        self.assertEqual(observed["failures"],2)
        self.assertFalse(owner_qualifies_fit(observed))

    def test_counter_order_overflow_and_static_capacity_mismatch_disqualify_fit(self):
        self.assertFalse(owner_qualifies_fit({"bound":1,"capacity":100,"current":60,"peak":50,"failures":0}))
        self.assertFalse(owner_qualifies_fit({"bound":1,"capacity":100,"current":20,"peak":101,"failures":0}))
        self.assertFalse(owner_qualifies_fit({"bound":1,"capacity":100,"current":20,"peak":50,"failures":0},90))

    def test_package_hash_not_matching_manifest_never_qualifies(self):
        row = {"name":"map_a_session","map":"map_a","hcp_package_sha256":"a"*64,
               "hcp_package_sha256_matches_manifest":False,"profile_id":7}
        evidence = {"complete":True,"identity":["map_a_session","mounted-map:map_a"],
                    "owners":{"streaming":[{"bound":1,"capacity":100}]},
                    "provenance":{"profile_package_sha256":"a"*64,"profile_name":"map_a_session",
                      "partition_profile":"map_a_session","scenario_mode":"capacity",
                      "runtime_profile":{"row":"map_a_session","map":"map_a","profile_id":7}}}
        self.assertIsNone(matched_owner(row,evidence,"streaming","capacity"))

    def test_wrong_profile_id_map_or_scenario_does_not_join(self):
        profile={"name":"map_a_session","map":"map_a","profile_id":7,
                 "hcp_package_sha256":"a"*64,"hcp_package_sha256_matches_manifest":True}
        evidence={"complete":True,"identity":["map_a_session","mounted-map:map_a"],
            "owners":{"streaming":[{"bound":1,"capacity":100,"current":10,"peak":20,"failures":0}]},
            "provenance":{"profile_package_sha256":"a"*64,"profile_name":"map_a_session",
                "partition_profile":"map_a_session","scenario_mode":"capacity",
                "runtime_profile":{"row":"map_a_session","map":"map_a","profile_id":8}}}
        self.assertIsNone(matched_owner(profile,evidence,"streaming","capacity"))
        evidence["provenance"]["runtime_profile"]["profile_id"]=7
        evidence["provenance"]["runtime_profile"]["map"]="beavercreek"
        self.assertIsNone(matched_owner(profile,evidence,"streaming","capacity"))
        evidence["provenance"]["runtime_profile"]["map"]="map_a"
        evidence["provenance"]["scenario_mode"]="workload4p"
        self.assertIsNone(matched_owner(profile,evidence,"streaming","capacity"))

    def test_selected_production_guest_uses_explicit_headless_mode(self):
        profile={"name":"map_a_session","map":"map_a","profile_id":7,
                 "hcp_package_sha256":"a"*64,"hcp_package_sha256_matches_manifest":True}
        evidence={"complete":True,"identity":["map_a_session","mounted-map:map_a"],
            "owners":{"streaming":[{"bound":1,"capacity":100,"current":10,"peak":20,"failures":0}]},
            "provenance":{"profile_package_sha256":"a"*64,"profile_name":"map_a_session",
                "partition_profile":"map_a_session","scenario_mode":"production-ce-map-load-headless",
                "runtime_profile":{"row":"map_a_session","map":"map_a","profile_id":7}}}
        self.assertIsNotNone(matched_owner(profile,evidence,"streaming","partition-selected"))

    def test_failed_or_unpinned_guest_never_completes(self):
        markers = [
            "Address Error, addr=0x1ff [store]",
            "HALO_PS2_LOCAL machine entry",
            "HALO_PS2_LOCAL partition-selected name=map_a_session qualified=1",
            "HALO_PS2_LOCAL profile-runtime row=map_a_session map=map_a profile=7",
            "HALO_PS2_LOCAL owner-telemetry phase=map name=streaming kind=backing parent=- bound=1 cap=100 used=25 high=50 failures=0 resets=1",
            "HALO_PS2_LOCAL cache-owner phase=map name=tags current=10 peak=20 failures=0 resets=0",
            "HALO_PS2_LOCAL arena name=streaming_map_owner cap=100 used=25 high=50 alloc_failures=0 resets=1",
            "HALO_PS2_LOCAL render-storage-bound snapshot-cap=1 renderer-workspace-cap=1 renderer-dma-cap=1 geometry-chain-qw=1 upload-chain-qw=1 frame-parent-used=1 frame-parent-high=1 streaming-map-cap=100 section-scratch-base=0x1 section-scratch-cap=1",
            "HALO_PS2_LOCAL map-mount result=1 active=1 map=map_a source=profile-runtime",
        ]
        for exit_status, extra, mutate_hash, completed, expected in (("completion-marker; host-stopped-sigint-0", [], False, True, True),
                ("bounded timeout after 600s (SIGINT)", [], False, False, False),
                ("completion-marker; host-stopped-sigint-0", ["[err] test failure"], False, True, False),
                ("host-exited-1", [], False, False, False),
                ("completion-marker; host-stopped-sigint-0", [], True, True, False)):
            with self.subTest(exit=exit_status, extra=extra, bad_hash=mutate_hash), tempfile.TemporaryDirectory() as td:
                root = Path(td)
                elf = root / "guest.elf"
                elf.write_bytes(b"pinned ELF")
                log = root / "emu.txt"
                log.write_text("\n".join(markers + extra) + "\n")
                digest = hashlib.sha256(elf.read_bytes()).hexdigest()
                run = {"elf": str(elf), "elf_sha256": "0" * 64 if mutate_hash else digest,
                       "profile_package_sha256":"a" * 64,"profile_name":"map_a_session",
                       "partition_profile":"map_a_session","scenario_mode":"capacity","run":"capacity",
                       "guest_terminal":"completion-marker","guest_completed":completed,
                       "log": str(log), "exit": exit_status, "elapsed_seconds": 1}
                result = extract(run, root / "manifest.json")
                self.assertEqual(result["complete"], expected)
                if expected:
                    self.assertEqual(len(result["provenance"]["boot_diagnostics"]), 1)
                    self.assertEqual(result["provenance"]["errors"], [])
                found = matched_owner({"name":"map_a_session", "map":"map_a", "hcp_package_sha256":"a"*64,
                                       "hcp_package_sha256_matches_manifest":True,"profile_id":7},
                                      result, "streaming", "capacity")
                self.assertEqual(found is not None, expected)


if __name__ == "__main__":
    unittest.main()
