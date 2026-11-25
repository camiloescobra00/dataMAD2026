"""Geographic matching and map preparation for arbitrary loaded tables."""
import re
from functools import lru_cache

import pandas as pd

from joins import key_role, normalized_name
from territories import normalize_code, official_codes

SYSTEMS = ("INE", "Almudena", "Código municipal de 3 dígitos", "Nombre municipal")
AGGREGATIONS = ("Sin agregar", "Media", "Suma", "Mediana", "Mínimo", "Máximo")


@lru_cache(maxsize=1)
def municipality_names():
    aliases = {}
    for code, (_, name) in official_codes().items():
        names = [name]
        if " (" in name and name.endswith(")"):
            stem, article = name[:-1].rsplit(" (", 1)
            names.append(f"{article} {stem}")
        for alias in names:
            aliases[normalized_name(alias)] = code
    return aliases


def resolve_location(value, system):
    if pd.isna(value):
        return None
    if system == "Nombre municipal":
        return municipality_names().get(normalized_name(value))
    if system == "Código municipal de 3 dígitos":
        raw = re.sub(r"\.0$", "", str(value).strip())
        if re.fullmatch(r"\d{1,3}", raw):
            return normalize_code("28" + raw.zfill(3))
        return None
    return normalize_code(value, system)


def location_candidates(df):
    """Suggest only declared geographic columns; never infer locations from measures."""
    candidates = []
    for column in df:
        role = key_role(column)
        if role not in {"Código municipal", "Nombre municipal"}:
            continue
        systems = ("Nombre municipal",) if role == "Nombre municipal" else SYSTEMS[:3]
        for system in systems:
            if df[column].map(lambda v, system=system: resolve_location(v, system)).notna().any():
                candidates.append((column, system))
    return candidates


def number_values(values):
    if pd.api.types.is_numeric_dtype(values):
        numeric = pd.to_numeric(values, errors="coerce")
    else:
        text = values.astype("string").str.strip()
        # Decimal commas are accepted, without guessing ambiguous thousands separators.
        numeric = pd.to_numeric(text.str.replace(",", ".", regex=False), errors="coerce")
    return numeric.where(numeric.abs().lt(float("inf")))


def metric_columns(df):
    return [c for c in df if key_role(c) not in {"Año", "Fecha", "Código municipal", "Nombre municipal"}
            and number_values(df[c]).notna().any()]


def coordinate_columns(df):
    lat = next((c for c in df if normalized_name(c) in {"lat", "latitude", "latitud", "direccion_latitud", "estacion_coord_latitud"}), None)
    lon = next((c for c in df if normalized_name(c) in {"lon", "lng", "long", "longitude", "longitud", "direccion_longitud", "estacion_coord_longitud"}), None)
    return lat, lon


def point_frame(df, latitude, longitude, metric=None):
    if latitude == longitude:
        raise ValueError("Selecciona columnas distintas para latitud y longitud.")
    frame = pd.DataFrame({"Latitud": number_values(df[latitude]), "Longitud": number_values(df[longitude])})
    valid = (frame["Latitud"].between(-90, 90) & frame["Longitud"].between(-180, 180)).fillna(False)
    if metric is not None:
        frame["Valor"] = number_values(df[metric])
    return frame.loc[valid].copy(), int((~valid).sum())


def municipal_frame(df, column, system, metric=None, aggregation="Sin agregar"):
    frame = pd.DataFrame({"INE": df[column].map(lambda v, system=system: resolve_location(v, system))})
    excluded = int(frame["INE"].isna().sum())
    frame["Valor"] = 1 if metric is None else number_values(df[metric])
    frame = frame.dropna(subset=["INE"])
    grouped = frame.groupby("INE")["Valor"]
    if metric is None:
        frame = grouped.size().rename("Valor").reset_index()
    elif aggregation == "Sin agregar":
        if frame["INE"].duplicated().any():
            raise ValueError("Hay varias filas por municipio. Filtra el periodo y las categorías o elige una agregación.")
    elif aggregation == "Suma":
        frame = grouped.sum(min_count=1).reset_index()
    elif aggregation in AGGREGATIONS:
        method = {"Media": "mean", "Mediana": "median", "Mínimo": "min", "Máximo": "max"}[aggregation]
        frame = getattr(grouped, method)().reset_index()
    else:
        raise ValueError("Agregación desconocida.")
    return frame, excluded
