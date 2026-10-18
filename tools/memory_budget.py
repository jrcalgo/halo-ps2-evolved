"""Machine-checked 32 MiB budget and observable host resource accounting."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUDGET_PATH = ROOT / "config/memory-budget.json"
POOL_ROLES = ("permanent", "map", "frame_scratch", "streaming", "dynamic")


class BudgetError(RuntimeError):
    pass


def load_budget(path=BUDGET_PATH):
    budget = json.loads(Path(path).read_text())
    validate_budget(budget)
    return budget


def validate_budget(budget):
    regions = budget["regions"]
    names = [region["name"] for region in regions]
    if len(names) != len(set(names)):
        raise BudgetError("region names are repeated")
    total = 0
    for region in regions:
        if region["bytes"] <= 0:
            raise BudgetError(f"region {region['name']} is not positive")
        total += region["bytes"]
        if len(region["accounts"]) != len(set(region["accounts"])):
            raise BudgetError(f"accounts repeat inside {region['name']}")
    if total != budget["total_bytes"] or total != 32 * 1024 * 1024:
        raise BudgetError(f"budget totals {total}, not 32 MiB")
    reserve = next(region for region in regions if region["role"] == "reserve")
    if reserve["bytes"] != budget["reserve_bytes"] or reserve["bytes"] != int(5.5 * 1024 * 1024):
        raise BudgetError("5.5 MiB reserve was not preserved")
    committed = total - reserve["bytes"]
    if committed != budget["committed_bytes"] or committed != int(26.5 * 1024 * 1024):
        raise BudgetError("committed memory is not 26.5 MiB")
    roles = {region["role"] for region in regions}
    missing = [role for role in POOL_ROLES if role not in roles]
    if missing:
        raise BudgetError("missing pool roles: " + ", ".join(missing))
    return layout(budget)


def layout(budget):
    cursor = 0
    spans = []
    for region in budget["regions"]:
        spans.append({"name": region["name"], "role": region["role"], "start": cursor,
                      "end": cursor + region["bytes"], "accounts": list(region["accounts"])})
        cursor += region["bytes"]
    return spans


def claim(spans, name, start, length):
    if length < 0 or start < 0:
        raise BudgetError(f"{name} has a negative range")
    end = start + length
    owner = None
    for span in spans:
        if start >= span["start"] and end <= span["end"]:
            owner = span
            break
        if start < span["end"] and span["start"] < end:
            raise BudgetError(f"{name} crosses {span['name']}")
    if owner is None:
        raise BudgetError(f"{name} is outside the 32 MiB map")
    for existing in owner.setdefault("claims", []):
        if start < existing["end"] and existing["start"] < end:
            raise BudgetError(f"{name} double-counts {existing['name']} in {owner['name']}")
    owner["claims"].append({"name": name, "start": start, "end": end})
    return owner["name"]


class Pool:
    def __init__(self, name, cap):
        self.name = name
        self.cap = cap
        self.used = 0
        self.high = 0

    def allocate(self, nbytes):
        if nbytes < 0 or self.used > self.cap or nbytes > self.cap - self.used:
            return {"ok": False, "reason": "exhausted", "pool": self.name,
                    "requested": nbytes, "used": self.used, "cap": self.cap}
        self.used += nbytes
        self.high = max(self.high, self.used)
        return {"ok": True, "pool": self.name, "used": self.used, "high": self.high}


class Ledger:
    def __init__(self, budget):
        self.spans = validate_budget(budget)
        self.pools = {span["role"]: Pool(span["name"], span["end"] - span["start"])
                      for span in self.spans if span["role"] in POOL_ROLES}
        self.steady = False
        self.steady_allocations = []

    def allocate(self, role, nbytes):
        result = self.pools[role].allocate(nbytes)
        if self.steady:
            self.steady_allocations.append({"role": role, "requested": nbytes, "ok": result["ok"]})
        return result


def scenario_result(configuration, seed, tick_count, outcome, diagnostics):
    result = {"configuration": configuration, "seed": seed, "tick_count": tick_count,
              "outcome": outcome, "diagnostics": diagnostics}
    required = ("configuration", "seed", "tick_count", "outcome", "diagnostics")
    if tuple(result) != required:
        raise BudgetError("scenario fields are not in canonical order")
    return result


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))
