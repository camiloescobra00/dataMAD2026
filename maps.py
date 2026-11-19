"""Mapas coropléticos con geometrías facilitadas por el usuario."""
import json

import plotly.express as px


def municipal_map(df, code, metric, raw, property_name):
    if len(raw) > 5 * 1024 * 1024:
        raise ValueError("El GeoJSON supera 5 MB.")
    geo = json.loads(raw)
    if not isinstance(geo, dict) or geo.get("type") != "FeatureCollection":
        raise ValueError("Selecciona una colección GeoJSON de polígonos municipales.")
    features = geo.get("features")
    if not isinstance(features, list) or not 1 <= len(features) <= 500:
        raise ValueError("La colección debe contener entre 1 y 500 municipios.")
    cleaned = []
    identifiers = set()
    for feature in features:
        if not isinstance(feature, dict):
            raise TypeError("Hay una entidad GeoJSON inválida.")
        geometry, props = feature.get("geometry"), feature.get("properties")
        if (not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}
                or not isinstance(props, dict) or not isinstance(props.get(property_name), (str, int))):
            raise ValueError("Cada geometría debe ser un polígono y tener un código municipal.")
        key = str(props[property_name]).strip()
        if not key or key in identifiers:
            raise ValueError("Los códigos de la geometría deben estar completos y ser únicos.")
        identifiers.add(key)
        cleaned.append({"type": "Feature", "id": key, "geometry": geometry})
    points = df[[code, metric]].dropna().copy()
    points.columns = ["municipio", "valor"]
    points["municipio"] = points["municipio"].astype("string").str.strip()
    points = points[points["municipio"].ne("")]
    if points["municipio"].duplicated().any():
        raise ValueError("Filtra la tabla hasta tener un único registro por municipio.")
    matches = points[points["municipio"].isin(identifiers)]
    if matches.empty:
        raise ValueError("No hay códigos coincidentes. Comprueba el formato y los ceros iniciales.")
    fig = px.choropleth(matches, geojson={"type": "FeatureCollection", "features": cleaned},
                        locations="municipio", color="valor", title=f"{metric} por municipio",
                        labels={"valor": metric, "municipio": code})
    fig.update_geos(fitbounds="locations", visible=False)
    return fig, len(matches), len(points)
