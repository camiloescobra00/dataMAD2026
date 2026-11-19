"""Importación, diagnóstico y transformaciones tabulares."""
import csv
import io
import json
import zipfile

import pandas as pd

from joins import key_role, normalized_name

MAX_ROWS = 150_000
MAX_CELLS = 1_500_000


def read_table(raw, fmt):
    fmt = fmt.strip().upper()
    if len(raw) > 15 * 1024 * 1024:
        raise ValueError("El fichero supera 15 MB.")
    if fmt in {"CSV", "TSV"}:
        for encoding in ("utf-8-sig", "cp1252", "latin-1"):
            try:
                content = raw.decode(encoding)
                break
            except UnicodeError:
                continue
        header = io.StringIO(content).readline()
        if fmt == "TSV":
            delimiter = "\t"
        else:
            try:
                delimiter = csv.Sniffer().sniff(header, delimiters=",;\t|").delimiter
            except csv.Error:
                delimiter = ","
        reader = csv.reader(io.StringIO(content), delimiter=delimiter, strict=True)
        expected = None
        try:
            for row in reader:
                if not row:
                    continue
                if expected is None:
                    expected = len(row)
                    if expected > 300 or len(set(row)) != len(row):
                        raise ValueError("El encabezado tiene demasiadas columnas o nombres repetidos.")
                elif len(row) != expected:
                    raise ValueError(f"Línea {reader.line_num}: número de campos inesperado.")
        except csv.Error as exc:
            raise ValueError(f"CSV inválido cerca de la línea {reader.line_num}.") from exc
        frame = pd.read_csv(io.StringIO(content), sep=delimiter, dtype="string",
                            keep_default_na=False, na_values=[""], nrows=MAX_ROWS + 1)
    elif fmt in {"XLS", "XLSX"}:
        if fmt == "XLSX":
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                if sum(entry.file_size for entry in archive.infolist()) > 50 * 1024 * 1024:
                    raise ValueError("El libro Excel supera el tamaño descomprimido permitido.")
        frame = pd.read_excel(io.BytesIO(raw), dtype="string", nrows=MAX_ROWS + 1,
                              keep_default_na=False, na_values=[""])
    elif fmt == "JSON":
        payload = json.loads(raw)
        if isinstance(payload, dict):
            payload = next((payload[k] for k in ("data", "results", "result", "records")
                            if isinstance(payload.get(k), list)), None)
        if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
            raise ValueError("El JSON debe contener una lista de registros.")
        if len(payload) > MAX_ROWS or sum(map(len, payload)) > MAX_CELLS:
            raise ValueError("La tabla supera el límite de filas o celdas.")
        frame = pd.json_normalize(payload)
        for column in frame.select_dtypes(include="object"):
            frame[column] = frame[column].map(
                lambda value: json.dumps(value, ensure_ascii=False) if isinstance(value, (list, dict)) else value)
    else:
        raise ValueError("Formato no soportado.")
    if len(frame) > MAX_ROWS or frame.size > MAX_CELLS or len(frame.columns) > 300:
        raise ValueError("La tabla supera el límite de filas, columnas o celdas.")
    frame.columns = frame.columns.map(str)
    for column in frame:
        values = frame[column]
        name = normalized_name(column)
        if (key_role(column) in {"Código municipal", "Nombre municipal", "Fecha"}
                or any(p in name.split("_") for p in ("id", "codigo", "cod", "ine"))
                or values.astype("string").str.match(r"^0\d+$", na=False).any()):
            continue
        if pd.api.types.is_string_dtype(values) or values.dtype == object:
            numeric = pd.to_numeric(values, errors="coerce")
            if numeric.notna().any() and numeric.notna().sum() == values.notna().sum():
                frame[column] = numeric
    return frame


def describe_table(df):
    return {
        "filas": len(df), "columnas": len(df.columns), "duplicados": int(df.duplicated().sum()),
        "variables": [{"nombre": str(c), "tipo": str(df[c].dtype),
                       "faltantes": int(df[c].isna().sum()), "distintos": int(df[c].nunique())} for c in df],
    }


def category_variants(values):
    values = values.dropna().astype("string").drop_duplicates().to_frame("valor")
    values["normalizado"] = values["valor"].str.strip().str.casefold()
    return values[values["normalizado"].duplicated(keep=False)].sort_values("normalizado")


def transform(df, operation, column=None, *, decimal_comma=False, date_format="%Y-%m-%d"):
    if operation == "Quitar duplicados":
        return df.drop_duplicates(), int(df.duplicated().sum())
    if operation == "Normalizar nombres de columnas":
        names = [normalized_name(c) for c in df]
        if not all(names) or len(set(names)) != len(names):
            raise ValueError("La normalización generaría nombres vacíos o repetidos.")
        return df.set_axis(names, axis=1), sum(c != name for c, name in zip(df, names))
    values = df[column].astype("string").str.strip()
    if operation == "Convertir a número":
        if decimal_comma:
            values = values.str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
        updated = pd.to_numeric(values, errors="coerce")
    elif operation == "Convertir a fecha":
        updated = pd.to_datetime(values, format=date_format, errors="coerce")
    elif operation == "Normalizar categorías":
        updated = values.str.casefold()
    else:
        raise ValueError("Transformación desconocida.")
    invalid = int((values.notna() & updated.isna()).sum())
    return df.assign(**{column: updated}), invalid


def csv_export(df):
    safe = df.copy()
    def cell(value):
        if isinstance(value, str) and (value.startswith(("\t", "\r", "\n"))
                                       or value.lstrip().startswith(("=", "+", "-", "@"))):
            return "'" + value
        return value
    safe.columns = [cell(c) for c in safe]
    for column in safe.select_dtypes(exclude=["number", "datetime"]):
        safe[column] = safe[column].map(cell)
    return safe.to_csv(index=False).encode("utf-8-sig")
