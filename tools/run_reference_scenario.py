"""Repeat a source-derived host reference scenario and require identical results."""
import json
import os
from pathlib import Path
import subprocess
import sys

from memory_budget import canonical_json, scenario_result

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "config/reference-scenarios"


def load_scenario(name):
    path = SCENARIOS / f"{name}.json"
    scenario = json.loads(path.read_text())
    if scenario["id"] != name:
        raise RuntimeError(f"Scenario id {scenario['id']} does not match {name}")
    return scenario


def run_once(binary):
    completed = subprocess.run([str(binary)], check=True, capture_output=True, text=True, timeout=15)
    lines = [line for line in completed.stdout.splitlines() if line.startswith("{")]
    if len(lines) != 1:
        raise RuntimeError(f"Fixture did not emit one JSON result: {completed.stdout!r}")
    return json.loads(lines[0])


def observe(scenario, fixture):
    if fixture.get("status") != scenario["expected_outcome"]:
        raise RuntimeError(f"Fixture outcome {fixture.get('status')!r} differs from {scenario['expected_outcome']!r}")
    return scenario_result(
        {"id": scenario["id"], "map": scenario["map"], "variant": scenario["difficulty_or_variant"],
         "camera": scenario["camera"], "observation_method": scenario["observation_method"]},
        scenario["seed"], scenario["tick_count"], fixture["status"],
        {"fixture": fixture["fixture"], "abi": fixture["abi"], "player_actions": scenario["player_actions"]})


def repeat(name, binary):
    scenario = load_scenario(name)
    first = observe(scenario, run_once(binary))
    second = observe(scenario, run_once(binary))
    if canonical_json(first) != canonical_json(second):
        raise RuntimeError("Repeated scenario results differ")
    return first


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "integer-math-host"
    selected = os.environ.get("BUILD_ENV", "native")
    if selected != "native":
        raise RuntimeError("The host reference scenario runs only in the native environment")
    subprocess.run([sys.executable, str(ROOT / "tools/test_gameplay_host32.py")], cwd=ROOT, check=True)
    binary = Path(os.environ.get("HALO_BUILD_ROOT", ROOT / "build")).resolve() / "gameplay-host32/integer-math"
    result = repeat(name, binary)
    print(canonical_json(result))


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError, json.JSONDecodeError) as error:
        sys.exit(f"Reference scenario failed: {error}")
