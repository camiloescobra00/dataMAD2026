"""Indicadores contrastados, códigos municipales y planes de análisis."""
import json
import re
from functools import lru_cache

import pandas as pd

from data_tables import read_table
from demos import AGE, DATA, DEMO_NAMES, demo_table
from discovery import fold

RENT = "irpf_indicador_renta"
JOBS = "302038"
POP = "padron_por_sexo"
HEALTH = "centros_sanitarios_por_tipo"
INDICATORS = {
    RENT: ("Renta por habitante", "EUR", "Indicador de renta disponible bruta municipal per cápita."),
    AGE: ("Población de 65 años y más", "%", "Porcentaje de población municipal a 1 de enero."),
    JOBS: ("Paro registrado", "personas", "Recuento de personas. Para comparar tasas hacen falta denominadores."),
    POP: ("Población empadronada", "personas", "Población total a 1 de enero."),
    HEALTH: ("Centros de atención primaria", "centros por 10.000 hab.",
             "Consultorios locales y centros de salud. El indicador no mide accesibilidad."),
}
EXAMPLES = (
    "¿Qué municipios tienen mayor renta por habitante?",
    "¿Dónde está más envejecida la población?",
    "¿Cómo ha evolucionado el desempleo?",
    "¿Qué municipios han crecido más en población?",
    "¿Existe relación entre renta y envejecimiento?",
)


@lru_cache(maxsize=1)
def boundaries():
    return json.loads((DATA / "municipios.geojson").read_text(encoding="utf-8"))


@lru_cache(maxsize=8)
def series(indicator):
    frame = read_table((DATA / f"{indicator}.csv").read_bytes(), "csv")
    return frame.set_axis(["Código", "Año", "Municipio", "Valor"], axis=1)


@lru_cache(maxsize=1)
def official_codes():
    source = series(POP)[["Código", "Municipio"]].drop_duplicates("Código")
    return {f"28{code[:3]}": (code, name) for code, name in source.itertuples(index=False, name=None)}


def normalize_code(value, system="INE"):
    if pd.isna(value):
        return None
    raw = str(value).strip()
    if re.fullmatch(r"\d+\.0", raw):
        raw = raw[:-2]
    codes = official_codes()
    if system == "Almudena":
        raw = raw.zfill(4)
        ine = "28" + raw[:3]
        return ine if ine in codes and codes[ine][0] == raw else None
    return raw if raw in codes else None


def prepared_series(indicator):
    frame = series(indicator)
    return frame.assign(INE=frame["Código"].map(lambda code: normalize_code(code, "Almudena")))


@lru_cache(maxsize=1)
def source_metadata():
    return json.loads((DATA / "sources.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def regional():
    return pd.read_csv(DATA / "regional.csv", dtype={"Fuente": "string"})


def question_plan(query, municipalities=()):
    if query.geography in {"Distritos", "Barrios"}:
        return None
    topics = set(query.topics)
    text = fold(query.text)
    if re.search(r"\b(tasa de (paro|desempleo)|salarios?|densidad|menores?)\b", text):
        return None
    if topics == {"renta", "envejecimiento"} and query.intent in {"relación", "comparación"}:
        if any(year != 2024 for year in query.years) or query.recent:
            return None
        return "relación", (AGE, RENT)
    indicator = {"renta": RENT, "envejecimiento": AGE, "paro": JOBS,
                 "población": POP, "salud": HEALTH}.get(next(iter(topics))) if len(topics) == 1 else None
    if not indicator:
        return None
    if query.intent == "crecimiento":
        if indicator != POP or len(query.years) == 1:
            return None
        return "crecimiento", (indicator,)
    if query.intent == "relación":
        return None
    if query.intent == "evolución" and series(indicator)["Año"].nunique() < 2:
        return None
    if query.geography and query.geography not in {"Comunidad de Madrid", "Municipios"} and not municipalities:
        return None
    return query.intent, (indicator,)


def analysis_window(frame, query):
    available = sorted(frame["Año"].unique())
    if query.years:
        if any(year not in available for year in query.years):
            return frame.iloc[:0]
        start, end = min(query.years), max(query.years)
    elif query.recent:
        end = available[-1]
        start = end - query.recent
    else:
        start, end = available[0], available[-1]
    return frame[frame["Año"].between(start, end)]


def growth(frame, years):
    start, end = years
    values = frame[frame["Año"].isin(years)].pivot(index="INE", columns="Año", values="Valor")
    if start == end or start not in values or end not in values:
        raise ValueError("Se requieren dos años con datos.")
    values = values.dropna(subset=list(years))
    values = values[values[start] > 0]
    result = (100 * (values[end] / values[start] - 1)).rename("Valor").reset_index()
    return result.assign(Municipio=result["INE"].map(lambda code: official_codes()[code][1]))


def verified_relationship():
    frame, info = demo_table(DEMO_NAMES[0])
    return frame.dropna(subset=list(frame.columns[3:])), info
