"""Search the audited map catalog before pagination, with consistent counts and facets."""
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path

from joins import normalized_name

CATALOG_PATH = Path(__file__).resolve().parent / "catalog_data" / "map_catalog.json"
FACET_FIELDS = {"Tema": "groups", "Organismo": "organization", "Formato": "res_format", "Etiqueta": "tags"}


@lru_cache(maxsize=1)
def catalog_index():
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def facets_for(dataset, field):
    if field == "res_format":
        return {str(r["format"]).upper(): str(r["format"]).upper() for r in dataset["resources"]}
    values = [dataset.get("organization") or {}] if field == "organization" else dataset.get(field, [])
    return {row["name"]: row.get("display_name") or row.get("title") or row["name"]
            for row in values if row.get("name")}


def search_maps(query, rows=20, start=0, filters=None, sort="Relevancia", *, index=None):
    data = index if index is not None else catalog_index()
    terms = set(normalized_name(query).split("_")) - {"", "de", "del", "la", "el", "los", "las", "por", "en", "y"}
    ranked = []
    for dataset in data["datasets"]:
        title = normalized_name(dataset["title"])
        searchable = title + "_" + normalized_name(dataset.get("notes") or "")
        searchable += "_" + "_".join(normalized_name(v) for field in ("groups", "tags")
                                     for v in facets_for(dataset, field).values())
        if not all(term in searchable for term in terms):
            continue
        if any(value and value not in facets_for(dataset, FACET_FIELDS[label])
               for label, value in (filters or {}).items() if label in FACET_FIELDS):
            continue
        ranked.append((sum(term in title for term in terms), dataset))
    if sort == "Título":
        ranked.sort(key=lambda row: (normalized_name(row[1]["title"]), row[1]["id"]))
    elif sort == "Actualización":
        ranked.sort(key=lambda row: (row[1].get("metadata_modified") or "", row[1]["id"]), reverse=True)
    else:
        ranked.sort(key=lambda row: (-row[0], normalized_name(row[1]["title"]), row[1]["id"]))
    facets = {}
    for field in FACET_FIELDS.values():
        counts, labels = Counter(), {}
        for _, dataset in ranked:
            values = facets_for(dataset, field)
            counts.update(values.keys())
            labels.update(values)
        facets[field] = {"items": [{"name": name, "display_name": labels[name], "count": count}
                                   for name, count in sorted(counts.items())]}
    start, rows = max(0, start), min(max(1, rows), 100)
    return {"count": len(ranked), "results": [d for _, d in ranked[start:start + rows]], "search_facets": facets}
