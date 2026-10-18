"""Strict classification of the bounded R5900 integer-math probe controls."""
import json
import re

EXPECTED = {"fixture": "integer_math", "abi": "ILP32", "status": "passed"}


def validate_probe(text, scenario, host):
    if "HALO_PS2_FAIL" in text:
        raise RuntimeError("Guest reported a probe failure")
    fixtures = [json.loads(line) for line in re.findall(r'\{"fixture":"integer_math"[^\n]*?\}', text)]
    if scenario == "probe-assert":
        if fixtures or "outcome=passed" in text:
            raise RuntimeError("Assertion control continued into successful execution")
        if not re.search(r"probe-diagnostics:\d+ assertion: 0", text):
            raise RuntimeError("Expected assertion diagnostic is missing")
        return {"assertion": "observed", "status": "expected-failure"}
    if "expected diagnostic fixture warning" not in text:
        raise RuntimeError("Expected warning diagnostic is missing")
    if scenario == "probe-negative":
        if fixtures or "outcome=passed" in text:
            raise RuntimeError("Boundary mutation escaped fixture rejection")
        if "check failed: !point2d_in_rectangle2d(&a, &point)" not in text:
            raise RuntimeError("Expected exclusive rectangle-edge rejection is missing")
        if "HALO_PS2_PROBE negative_control=rejected diagnostics_calls=2" not in text:
            raise RuntimeError("Negative-control wrapper completion is missing")
        return {"negative_control": "rejected", "diagnostics_calls": 2}
    if fixtures != [EXPECTED] or host != EXPECTED:
        raise RuntimeError("Host and EE canonical integer-math fixtures differ")
    if "HALO_PS2_PROBE outcome=passed diagnostics_calls=2" not in text:
        raise RuntimeError("Probe wrapper completion or expression evaluation is missing")
    return {"canonical": EXPECTED, "host_equal": True, "diagnostics_calls": 2}
