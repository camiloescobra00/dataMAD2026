"""Publish a compact, audited map-only catalog from cached official sample responses."""
import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from audit_map_catalog import candidate

from catalog import MAX_BYTES, compatible_resources
from data_tables import MAX_CELLS, MAX_ROWS
from map_eligibility import assess_map_table


def build(snapshot, cache):
    accepted, audit = [], []
    for dataset in snapshot["conjuntos_de_datos"]:
        reason = "Cobertura regional o geografía no compatible según los metadatos"
        resources = []
        if candidate(dataset):
            reason = "Sin recurso tabular verificable dentro de los límites de la aplicación"
            for resource in compatible_resources(dataset):
                path = cache / (resource["id"] + ".json")
                if not path.exists() or (resource.get("size") or 0) > MAX_BYTES:
                    continue
                result = json.loads(path.read_text())
                if result.get("error"):
                    reason = "No se pudo verificar el recurso oficial"
                    continue
                fields = [f["id"] for f in result.get("fields", []) if f["id"] != "_id"]
                total = result.get("total", 0)
                if total > MAX_ROWS or total * len(fields) > MAX_CELLS or len(fields) > 300:
                    reason = "Recurso superior a los límites de filas o celdas de la aplicación"
                    continue
                frame = pd.DataFrame(result.get("records", [])).drop(columns="_id", errors="ignore")
                spec, why = assess_map_table(dataset, frame)
                if spec:
                    resources.append({**resource, "map_spec": {**spec, "sample_rows": len(frame)}})
                else:
                    reason = why
        if resources:
            fields = ["id", "name", "title", "notes", "organization", "groups", "tags", "extras",
                      "metadata_modified", "metadata_created", "license_title"]
            entry = {k: dataset.get(k) for k in fields}
            entry["resources"] = resources
            accepted.append(entry)
        audit.append({"name": dataset["name"], "title": dataset["title"],
                      "included": bool(resources), "reason": resources[0]["map_spec"]["reason"] if resources else reason})
    return {"schema_version": 1, "source": snapshot["fuente"], "snapshot_at": snapshot["extraido_en_utc"],
            "audited_at": datetime.now(timezone.utc).isoformat(), "reviewed": len(audit),
            "count": len(accepted), "datasets": accepted}, audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    catalog, audit = build(json.loads(args.snapshot.read_text()), args.cache)
    output = Path(__file__).resolve().parents[1] / "catalog_data"
    output.mkdir(exist_ok=True)
    (output / "map_catalog.json").write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")
    (output / "map_catalog_audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    print(f"Included {catalog['count']}/{catalog['reviewed']} datasets")
    print(Counter(r['map_spec']['kind'] for d in catalog['datasets'] for r in d['resources']))
    print(Counter(row['reason'] for row in audit if not row['included']))


if __name__ == "__main__":
    main()
