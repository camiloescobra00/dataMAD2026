"""Rebuild the map catalog from a CKAN snapshot and bounded official record samples.

Run from the app directory: .venv/bin/python scripts/audit_map_catalog.py SNAPSHOT --cache /tmp/mde-map-audit
Only resources whose sample supports a map are published. Unverified resources stay out.
"""
import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from catalog import API_ROOT, MAX_BYTES, _session, compatible_resources
from joins import normalized_name


def candidate(dataset):
    if (dataset.get("organization") or {}).get("name") != "estadistica":
        return True
    text = normalized_name(dataset.get("title", ""))
    extras = {normalized_name(row["key"]): normalized_name(row.get("value", "")) for row in dataset.get("extras", [])}
    return (bool(re.search(r"(?:^|_)municip(?:io|ios|al|ales)(?:_|$)", text))
            or extras.get("origen") == "almudena" or "municip" in extras.get("ambito", ""))


def sample(dataset, cache):
    resources = [r for r in compatible_resources(dataset) if r.get("datastore_active")
                 and (not r.get("size") or r["size"] <= MAX_BYTES)]
    results = []
    for resource in resources:
        path = cache / (resource["id"] + ".json")
        if path.exists():
            result = json.loads(path.read_text())
        else:
            try:
                with _session() as session:
                    response = session.get(API_ROOT + "/datastore_search",
                                           params={"resource_id": resource["id"], "limit": 100}, timeout=(4, 12))
                    response.raise_for_status()
                    payload = response.json()
                    if not payload.get("success"):
                        raise ValueError("Datastore no disponible")
                    result = payload["result"]
            except (ValueError, OSError) as exc:
                result = {"error": type(exc).__name__}
            path.write_text(json.dumps(result, ensure_ascii=False))
        results.append((resource, result))
    return dataset, results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    snapshot = json.loads(args.snapshot.read_text())
    candidates = [d for d in snapshot["conjuntos_de_datos"] if candidate(d)]
    print(f"Reviewing {len(candidates)} candidates out of {snapshot['numero_conjuntos']} datasets", flush=True)
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(sample, d, args.cache) for d in candidates]
        for count, future in enumerate(as_completed(futures), 1):
            future.result()
            if count % 50 == 0 or count == len(candidates):
                print(f"Reviewed {count}/{len(candidates)}", flush=True)
    print("Samples cached; use build_map_catalog.py to classify and publish the local index.", flush=True)


if __name__ == "__main__":
    main()
