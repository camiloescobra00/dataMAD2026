"""Display provenance and structural metadata without filling gaps with estimates."""
from urllib.parse import quote

import pandas as pd
import streamlit as st

from discovery import coverage, fold


def dataset_metadata(dataset, resource=None):
    extras = {fold(row.get("key", "")): row.get("value") for row in dataset.get("extras", [])}
    geography, period = coverage(dataset)
    territory = next((value for key, value in extras.items() if "nivel territorial" in key), None)
    title = str(dataset.get("title") or "")
    if not territory and "municipios" in fold(title):
        territory = "Municipal (según el título)"
    resource = resource or {}
    fields = resource.get("schema") or {}
    fields = fields.get("fields", []) if isinstance(fields, dict) else []
    definitions = {row["name"]: row["description"] for row in fields if isinstance(row, dict)
                   and row.get("name") and row.get("description")}
    return {
        "descripción": dataset.get("notes") or "Sin descripción publicada",
        "fuente": extras.get("fuente") or resource.get("url"),
        "organismo": (dataset.get("organization") or {}).get("title"),
        "publicación": dataset.get("metadata_created"),
        "actualización": extras.get("fecha actualizacion") or dataset.get("metadata_modified"),
        "frecuencia": next((value for key, value in extras.items() if "frecuencia" in key or "periodicidad" in key), None),
        "cobertura temporal": period, "cobertura geográfica": geography, "nivel territorial": territory,
        "formato": resource.get("format") or ", ".join(sorted({str(r["format"]) for r in dataset.get("resources", [])
                                                              if r.get("format")})),
        "licencia": dataset.get("license_title"), "variables": definitions,
        "ficha": "https://datos.comunidad.madrid/dataset/" + quote(str(dataset.get("name") or dataset.get("id") or ""), safe=""),
    }


def metadata_card(metadata):
    st.text(metadata["descripción"])
    fields = [{"Metadato": key.capitalize(), "Información": str(value) if value else "Sin información publicada"}
              for key, value in metadata.items() if key not in {"descripción", "variables", "ficha"}]
    st.dataframe(pd.DataFrame(fields), hide_index=True)
    st.link_button("Ficha oficial", metadata["ficha"])
