"""Explicit maintenance operation: resolve audited upstream refs, never run by builds."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def declarations():
    result = []
    for target in ("ee", "iop", "dvp"):
        config = f"submodules/ps2toolchain-{target}/config/ps2toolchain-{target}-config.sh"
        values = dict(re.findall(r'^([A-Z0-9_]+)="([^"\n]*)"$', (ROOT / config).read_text(), re.M))
        for key, url in values.items():
            if key.endswith("_REPO_URL"):
                prefix = key.removesuffix("_REPO_URL")
                result.append({"id": prefix.lower(), "url": url,
                               "ref": values[prefix + "_DEFAULT_REPO_REF"], "declared_by": config})
    config = "submodules/ps2sdk/download_dependencies.sh"
    values = dict(re.findall(r'^([A-Z0-9_]+)="([^"\n]*)"$', (ROOT / config).read_text(), re.M))
    for prefix in ("LWIP", "FATFS"):
        result.append({"id": "ps2sdk_" + prefix.lower(), "url": values[prefix + "_REPO_URL"],
                       "ref": values[prefix + "_BRANCH_NAME"], "declared_by": config})
    return result


def resolve(item):
    ref = item["ref"]
    refs = ["refs/heads/" + ref, "refs/tags/" + ref, "refs/tags/" + ref + "^{}"]
    output = subprocess.check_output(["git", "ls-remote", item["url"], *refs], text=True, timeout=90)
    found = {name: sha for sha, name in (line.split() for line in output.splitlines())}
    branch = found.get(refs[0])
    tag = found.get(refs[2], found.get(refs[1]))
    if branch and tag and branch != tag:
        raise RuntimeError(f"Ambiguous upstream ref: {item['id']} {ref}")
    commit = tag or branch
    if not commit or not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError(f"No unique commit for {item['id']} {ref}")
    return {**item, "commit": commit}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resolve", action="store_true", help="Contact upstreams and write a new lock candidate")
    args = parser.parse_args()
    if not args.resolve:
        print(json.dumps(declarations(), indent=2))
        return
    # Resolve all refs before writing; failures cannot leave a partial lock.
    with ThreadPoolExecutor(max_workers=4) as pool:
        sources = list(pool.map(resolve, declarations()))
    lock = {"schema_version": 1, "sources": sources,
            "scope": "Audited compiler and SDK source refs; acquisition, archive checksums, host packages and container base remain pending."}
    path = ROOT / "config/toolchain-sources.json"
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(lock, indent=2) + "\n")
    temporary.replace(path)
    print(f"Resolved {len(sources)} source identities to {path}")


if __name__ == "__main__":
    main()
