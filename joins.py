"""Uniones con estimación previa y claves de salida reutilizables."""
import re
import unicodedata

import pandas as pd


def normalized_name(value):
    ascii_value = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_value.lower()).strip("_")


def key_role(column):
    name = normalized_name(column)
    if name in {"cod_ine", "codigo_ine", "ine", "codigo_municipio", "cod_municipio", "cmun", "municipio_codigo", "codigo_territorio"}:
        return "Código municipal"
    if name in {"municipio", "nombre_municipio", "municipio_nombre", "nom_mun", "territorio"}:
        return "Nombre municipal"
    if name in {"anio", "ano", "year", "ejercicio"}:
        return "Año"
    if name in {"fecha", "date"}:
        return "Fecha"
    return None


def suggest_keys(left, right):
    return [(a, b, key_role(a)) for a in left for b in right
            if key_role(a) and key_role(a) == key_role(b)]


def _key_part(values):
    if pd.api.types.is_float_dtype(values) or values.dtype == object:
        values = values.map(lambda v: str(int(v)) if isinstance(v, float) and v.is_integer() else v)
    return values.astype("string").str.normalize("NFC").str.strip().str.casefold()


def _keys(frame, columns, side):
    parts = [_key_part(frame[c]) for c in columns]
    keys = zip(*(part.fillna("") for part in parts))
    return pd.Series([(side, i) if "" in key else ("valid", *key)
                      for i, key in enumerate(keys)], dtype=object)


def join_preview(left, right, left_key, right_key, how, max_rows=250_000):
    if (not left.columns.is_unique or not right.columns.is_unique
            or not left_key or len(left_key) != len(right_key)
            or len(set(left_key)) != len(left_key) or len(set(right_key)) != len(right_key)
            or any(c not in left for c in left_key) or any(c not in right for c in right_key)):
        raise ValueError("Selecciona claves existentes, distintas y en el mismo orden.")
    if how not in {"inner", "left", "right", "outer"}:
        raise ValueError("Tipo de unión no permitido.")
    a, b = _keys(left, left_key, "A"), _keys(right, right_key, "B")
    ac, bc = a.value_counts(), b.value_counts()
    shared = ac.index.intersection(bc.index)
    matched = sum(int(ac[k]) * int(bc[k]) for k in shared)
    only_a, only_b = int((~a.isin(shared)).sum()), int((~b.isin(shared)).sum())
    estimate = matched + (only_a if how in {"left", "outer"} else 0) + (
        only_b if how in {"right", "outer"} else 0)
    if estimate > max_rows or estimate * (len(left.columns) + len(right.columns)) > 3_000_000:
        raise ValueError(f"La unión produciría {estimate:,} filas y supera el límite de filas o celdas.")

    dup_a, dup_b = int(a.duplicated().sum()), int(b.duplicated().sum())
    warnings = []
    if not matched:
        warnings.append("Las claves seleccionadas carecen de coincidencias.")
    if (ac.reindex(shared) > 1).any() and (bc.reindex(shared) > 1).any():
        warnings.append("Hay duplicados a ambos lados. Revisa el nivel de detalle y la multiplicación de filas.")
    paired_roles = [(key_role(x), key_role(y)) for x, y in zip(left_key, right_key)]
    if any(x != y and x and y for x, y in paired_roles):
        warnings.append("Algunas claves tienen funciones geográficas o temporales distintas.")
    if (any(key_role(c) in {"Año", "Fecha"} for c in [*left, *right])
            and not any(x == y and x in {"Año", "Fecha"} for x, y in paired_roles)):
        warnings.append("Hay columnas temporales fuera de la unión. Comprueba que los periodos sean comparables.")

    occupied = set(left) | set(right)
    def unique(base):
        name, index = base, 2
        while name in occupied:
            name = f"{base}_{index}"
            index += 1
        occupied.add(name)
        return name

    shared_keys = {b_col for a_col, b_col in zip(left_key, right_key) if a_col == b_col}
    rename = {c: unique(f"{c}_B") for c in right if c in left}
    internal = unique("__join_key")
    merged = left.reset_index(drop=True).assign(**{internal: a}).merge(
        right.rename(columns=rename).reset_index(drop=True).assign(**{internal: b}), on=internal, how=how
    ).drop(columns=internal)
    for column in shared_keys:
        # A synthetic match key treats blank values as missing, but retains original data.
        first, second = merged[column], merged[rename[column]]
        if first.dtype != second.dtype:
            first, second = first.astype(object), second.astype(object)
        merged[column] = first.combine_first(second)
        merged = merged.drop(columns=rename[column])
    return merged, {
        "claves": list(zip(left_key, right_key)), "filas_A": len(left), "filas_B": len(right),
        "filas": len(merged), "filas_coincidentes": matched, "solo_izquierda": only_a,
        "solo_derecha": only_b, "coincidencia_A_pct": round(100 * (len(left)-only_a) / max(len(left), 1), 2),
        "coincidencia_B_pct": round(100 * (len(right)-only_b) / max(len(right), 1), 2),
        "duplicados_clave_A": dup_a, "duplicados_clave_B": dup_b,
        "claves_nulas_A": sum(key[0] == "A" for key in a),
        "claves_nulas_B": sum(key[0] == "B" for key in b),
        "cardinalidad": f"{'muchos' if dup_a else 'uno'} a {'muchos' if dup_b else 'uno'}",
        "advertencias": warnings,
    }
