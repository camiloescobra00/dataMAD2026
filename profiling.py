"""Semantic schema and auditable quality recommendations."""
from dataclasses import dataclass

import pandas as pd

from joins import key_role, normalized_name
from territories import normalize_code

ROLES = ("Numérica", "Porcentaje", "Tasa", "Categoría", "Identificador", "Código municipal", "Municipio", "Año", "Fecha")
NUMERIC = {"Numérica", "Porcentaje", "Tasa"}
CATEGORIES = {"Categoría", "Municipio"}
TIME = {"Año", "Fecha"}


@dataclass(frozen=True)
class Advice:
    operation: str
    column: str | None
    count: int
    reason: str
    actionable: bool = True


def text_values(series):
    return series.astype("string").str.strip().replace("", pd.NA)


def number_values(text, operation):
    if operation == "Número con coma decimal":
        text = text.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
    if operation == "Porcentaje explícito":
        text = text.str.removesuffix("%").str.strip().str.replace(",", ".", regex=False)
    return pd.to_numeric(text, errors="coerce")


def schema(df):
    columns = []
    advice = []
    duplicates = int(df.duplicated().sum())
    if duplicates:
        advice.append(Advice("Eliminar duplicados exactos", None, duplicates, "Las filas repetidas pueden inflar recuentos."))
    for column in df:
        values = df[column]
        text = text_values(values)
        live = text.dropna()
        name = normalized_name(column)
        tokens = set(name.split("_"))
        known = key_role(column)
        parsed = pd.to_numeric(live, errors="coerce")
        year = not live.empty and live.str.fullmatch(r"(?:18|19|20|21)\d{2}").all()
        percentage = not live.empty and live.str.fullmatch(r"[+-]?\d+(?:[.,]\d+)?\s*%").all()
        iso_date = not live.empty and live.str.match(r"^\d{4}-\d{2}-\d{2}(?:[ T]|$)").all()
        local_date = not live.empty and live.str.fullmatch(r"\d{1,2}/\d{1,2}/\d{4}").all()
        is_number = pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values)
        if known == "Código municipal":
            role = "Código municipal"
            target = live.map(lambda val, name=name: normalize_code(val, "Almudena" if name == "codigo_territorio" else "INE"))
            count = int((target.notna() & target.ne(live)).sum())
            if count:
                advice.append(Advice("Unificar códigos con INE", column, count, "Facilita la unión con la cartografía oficial."))
        elif known == "Nombre municipal":
            role = "Municipio"
        elif known == "Año" or (year and tokens & {"periodo", "ejercicio"}):
            role = "Año"
            if year and not is_number:
                advice.append(Advice("Convertir a año entero", column, len(live), "Permite ordenar por año y mantiene su granularidad."))
        elif tokens & {"id", "identificador", "codigo", "cod", "ine"} or live.str.match(r"^0\d+$").any():
            role = "Identificador"
        elif known == "Fecha" or iso_date or local_date or pd.api.types.is_datetime64_any_dtype(values):
            role = "Fecha"
            if (iso_date or local_date) and not pd.api.types.is_datetime64_any_dtype(values):
                operation = "Fecha día/mes/año" if local_date else "Fecha ISO"
                advice.append(Advice(operation, column, len(live), "Permite ordenar y agrupar fechas válidas."))
        elif percentage or "%" in column or tokens & {"porcentaje", "pct", "proporcion"}:
            role = "Porcentaje"
            if percentage:
                advice.append(Advice("Porcentaje explícito", column, len(live), "Convierte el texto con % a puntos porcentuales."))
            if percentage or "%" in column or "porcentaje" in tokens:
                points = number_values(live, "Porcentaje explícito") if percentage else parsed
                outside = int((points.notna() & ~points.between(0, 100)).sum())
                if outside:
                    advice.append(Advice("Revisar rango porcentual", column, outside,
                                         "Revisa si el indicador admite valores fuera de 0 a 100.", False))
        elif tokens & {"tasa", "ratio", "razon"}:
            role = "Tasa"
        elif is_number:
            role = "Numérica"
        else:
            role = "Categoría"
        comma = not live.empty and live.str.fullmatch(r"[+-]?(?:\d+|\d{1,3}(?:\.\d{3})+)(?:,\d+)?").all()
        if role in NUMERIC | {"Categoría"} and not is_number and not live.empty:
            operation = "Número con coma decimal" if comma and live.str.contains(",", regex=False).any() else "Número"
            if (operation != "Número" or parsed.notna().all()) and not percentage:
                if role == "Categoría":
                    role = "Numérica"
                advice.append(Advice(operation, column, len(live), "Permite usar el indicador en los análisis numéricos."))
        missing = int(text.isna().sum())
        if missing:
            advice.append(Advice("Examinar ausencias", column, missing, "Los análisis explican cuántos casos excluyen.", False))
        category = role in CATEGORIES
        if category:
            normalized = live.str.normalize("NFC").str.strip().str.casefold()
            inconsistent = int(normalized.isin(normalized[live.ne(normalized)]).sum()) if live.nunique() > normalized.nunique() else 0
            count = max(inconsistent, int((values.dropna().astype("string") != live).sum())) if len(live) == values.notna().sum() else inconsistent
            if count:
                advice.append(Advice("Normalizar municipios" if role == "Municipio" else "Normalizar categorías", column,
                                     count, "Evita separar categorías por mayúsculas o espacios."))
        totals = int(live.str.casefold().isin({"total", "totales", "total general", "todos"}).sum())
        if totals:
            advice.append(Advice("Examinar posibles totales", column, totals, "Mezclar totales y desgloses duplica recuentos.", False))
        if tokens & {"unidad", "unidades"} and live.nunique() > 1:
            advice.append(Advice("Revisar unidades", column, len(live), "Filtra por unidad antes de combinar valores.", False))
        encoding = int(live.str.contains(r"�|Ã[\u0080-\u00bf]|Â[\u0080-\u00bf]", regex=True).sum())
        if encoding:
            advice.append(Advice("Examinar codificación", column, encoding, "Revisa la codificación del fichero original.", False))
        if role in NUMERIC and is_number and parsed.notna().sum() >= 8:
            q1, q3 = parsed.quantile([.25, .75])
            span = q3 - q1
            outliers = int((~parsed.between(q1 - 1.5 * span, q3 + 1.5 * span) & parsed.notna()).sum())
            if outliers:
                advice.append(Advice("Examinar posibles atípicos", column, outliers,
                                     "Superan las cercas de 1,5 rangos intercuartílicos. Pueden ser datos válidos.", False))
        markers = int(live.str.casefold().isin({"n/d", "n/a", "s/d", "-", "..", "null", "nan"}).sum())
        if markers:
            advice.append(Advice("Examinar marcadores de lectura", column, markers,
                                 "Confirma con el diccionario si representan ausencias, supresión o datos válidos.", False))
        columns.append({"Variable": column, "Rol": role, "Tipo": str(values.dtype),
                        "Ausentes": missing, "% ausente": round(100 * missing / len(df), 2) if len(df) else 0,
                        "Distintos": values.nunique(), "Ejemplos": ", ".join(str(v)[:55] for v in live.unique()[:3])})
    return {"rows": len(df), "columns": len(df.columns), "duplicates": duplicates,
            "missing": sum(row["Ausentes"] for row in columns), "variables": columns, "advice": advice}


def corrected(df, recommendation):
    op, column = recommendation.operation, recommendation.column
    if not recommendation.actionable:
        raise ValueError("Esta recomendación requiere revisión manual.")
    if op == "Eliminar duplicados exactos":
        return df.drop_duplicates().copy()
    text = text_values(df[column])
    if op == "Convertir a año entero":
        value = pd.to_numeric(text, errors="coerce").astype("Int64")
    elif op.startswith("Fecha"):
        value = pd.to_datetime(text, format="%d/%m/%Y" if "día/" in op else "ISO8601", errors="coerce")
    elif op.startswith("Normalizar"):
        value = text.str.normalize("NFC").str.casefold()
    elif op == "Unificar códigos con INE":
        value = text.map(lambda val: normalize_code(val, "Almudena") or normalize_code(val) or val).astype("string")
    else:
        value = number_values(text, op)
    if (text.notna() & value.isna()).any():
        raise ValueError("Hay valores que la transformación no puede interpretar. Revisa el formato de origen.")
    return df.assign(**{column: value})
