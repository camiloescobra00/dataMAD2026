"""Conservative, evidence-based admission to the app's map catalog."""
import re

from dataset_maps import (
    coordinate_columns,
    location_candidates,
    metric_columns,
    point_frame,
    resolve_location,
)
from joins import key_role, normalized_name

MIN_COVERAGE = .8
DIRECTORIES = re.compile(r"\b(centros|establecimientos|farmacia|farmacias|alojamientos|desfibriladores|parcelas|instalaciones|bibliotecas|aparcamientos)\b")


def assess_map_table(dataset, frame):
    """Return a map specification or an exclusion reason, never infer from coverage alone."""
    if frame.empty:
        return None, "Sin registros verificables"
    latitude, longitude = coordinate_columns(frame)
    if latitude is not None and longitude is not None:
        points, _ = point_frame(frame, latitude, longitude)
        if len(points) / len(frame) >= MIN_COVERAGE and len(points.drop_duplicates()) >= 2:
            return {"kind": "points", "latitude": latitude, "longitude": longitude,
                    "reason": "Ubicaciones con latitud y longitud válidas; mapa de puntos.",
                    "coverage": round(len(points) / len(frame), 3)}, None
    names = {normalized_name(c): c for c in frame}
    if any(re.search(r"(?:^|_)(distrito|barrio|seccion|zona_basica)(?:_|$)", c) for c in names):
        return None, "Detalle submunicipal: requiere otras geometrías o una agregación específica"
    text = normalized_name(dataset.get("title", "")).replace("_", " ")
    # Survey respondents and legal/procedural records do not become geographic indicators just by having a town.
    if re.search(r"\b(encuesta|percepcion|microdatos|solicitudes|expedientes|puestos de trabajo)\b", text):
        return None, "Registros que requieren una metodología adicional antes de compararlos territorialmente"
    directory = bool(DIRECTORIES.search(text))
    is_statistic = (dataset.get("organization") or {}).get("name") == "estadistica"
    geographic_title = bool(re.search(r"\bmunicip(?:io|ios|al|ales)\b", text))
    if not (is_statistic or geographic_title or directory):
        return None, "No se ha confirmado un indicador municipal ni un directorio de ubicaciones"
    scope = names.get("tipo_territorio")
    scoped = frame
    filters = {}
    if scope:
        values = frame[scope].map(normalized_name)
        municipal = values.isin(["municipio", "municipios", "municipal"])
        scoped = frame[municipal]
        filters[scope] = sorted(frame.loc[municipal, scope].dropna().unique().tolist())
    if scoped.empty:
        return None, "Sin observaciones municipales en la muestra"
    choices = []
    for column, system in location_candidates(scoped):
        codes = scoped[column].map(lambda v, system=system: resolve_location(v, system))
        ratio = codes.notna().mean()
        if ratio >= MIN_COVERAGE and codes.nunique() >= 2:
            choices.append((ratio, column, system))
    if not choices:
        return None, "Sin dos municipios reconocibles y al menos un 80 % de ubicaciones válidas en la muestra"
    ratio, column, system = max(choices, key=lambda choice: choice[0])
    metrics = [c for c in metric_columns(scoped) if not re.search(
        r"(?:^|_)(id|codigo|cod|code|postal|telefono|registro|ano|anio|year)(?:_|$)", normalized_name(c))]
    value_column = next((c for c in metrics if normalized_name(c) == "valor"), None)
    if value_column:
        metrics = [value_column]
    metric = metrics[0] if metrics else None
    if not directory and metric is None:
        return None, "Sin indicador numérico municipal verificable"
    # Statistical tables must filter every dimension before coloring; record count is not the indicator.
    dimensions = [c for c in frame if c not in metrics and key_role(c) is None
                  and normalized_name(c) not in {"id", "tipo_territorio", "estado_dato"}
                  and not re.search(r"(?:^|_)(codigo|cod|id)(?:_|$)", normalized_name(c))] if is_statistic else []
    return {"kind": "municipal_count" if directory and not is_statistic else "municipal_indicator",
            "column": column, "system": system, "metric": None if directory and not is_statistic else metric,
            "metrics": metrics, "filters": filters, "dimensions": dimensions,
            "coverage": round(float(ratio), 3),
            "reason": ("Directorio con municipios reconocidos; permite comparar el número de registros por municipio."
                       if directory and not is_statistic else
                       "Indicador con municipios reconocidos; compara valores tras seleccionar periodo y categorías.")}, None


def validate_map_resource(frame, spec, *, minimum_locations=2):
    """Fail closed if a downloaded resource no longer supports its audited map."""
    try:
        scoped = frame
        for column, values in spec.get("filters", {}).items():
            scoped = scoped[scoped[column].isin(values)]
        if scoped.empty:
            raise ValueError("No hay registros en el ámbito geográfico verificado.")
        if spec["kind"] == "points":
            points, _ = point_frame(scoped, spec["latitude"], spec["longitude"])
            valid = len(points) / len(scoped) >= MIN_COVERAGE and len(points.drop_duplicates()) >= minimum_locations
        else:
            codes = scoped[spec["column"]].map(lambda value: resolve_location(value, spec["system"]))
            valid = codes.notna().mean() >= MIN_COVERAGE and codes.nunique() >= minimum_locations
            if spec.get("metric"):
                valid = valid and spec["metric"] in metric_columns(scoped)
            valid = valid and all(c in scoped for c in spec.get("dimensions", []))
        if not valid:
            raise ValueError("La descarga ya no cumple los criterios geográficos verificados.")
    except KeyError as exc:
        raise ValueError("La estructura del recurso ha cambiado; necesita una nueva revisión cartográfica.") from exc
