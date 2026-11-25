"""Shared map controls for catalog, uploaded and derived tables."""
import plotly.express as px
import streamlit as st

from data_tables import csv_export
from dataset_maps import (
    AGGREGATIONS,
    SYSTEMS,
    coordinate_columns,
    location_candidates,
    metric_columns,
    municipal_frame,
    point_frame,
)
from joins import key_role, normalized_name
from map_view import export_chart, linked_map


def dataset_map(df, key, sources=(), spec=None):
    if spec:
        from map_eligibility import validate_map_resource

        try:
            validate_map_resource(df, spec, minimum_locations=1)
        except ValueError as exc:
            st.warning(str(exc))
            return
        st.caption(spec["reason"])
        for column, values in spec.get("filters", {}).items():
            df = df[df[column].isin(values)]
    if df.empty or not len(df.columns):
        st.info("La selección no contiene filas para representar.")
        return
    suggestions = location_candidates(df)
    lat, lon = coordinate_columns(df)
    if not suggestions and (lat is None or lon is None):
        st.info("No se ha detectado una ubicación. Selecciona columnas de municipio o coordenadas WGS84. "
                "Las tablas sin ubicación necesitan una unión con datos geográficos; "
                "los distritos y barrios requieren sus propias geometrías.")
    mode = st.radio("Tipo de mapa", ["Municipios de Madrid", "Puntos (latitud/longitud)"],
                    index=1 if (spec and spec["kind"] == "points") or (lat is not None and lon is not None and not suggestions) else 0,
                    disabled=bool(spec),
                    key=f"dataset_map_mode_{key}", horizontal=True)
    period = next((c for c in df if key_role(c) in {"Año", "Fecha"}), None)
    if period is not None:
        periods = sorted(df[period].dropna().unique(), key=str, reverse=True)
        if periods:
            selected = st.selectbox("Periodo del mapa", periods, key=f"dataset_map_period_{key}")
            df = df[df[period] == selected]
    for dimension in (spec or {}).get("dimensions", []):
        options = df[dimension].dropna().drop_duplicates().tolist()
        if not options:
            continue
        default = next((i for i, value in enumerate(options) if normalized_name(value) in {"total", "ambos_sexos"}), 0)
        selected = st.selectbox(dimension, options, index=default, key=f"dataset_map_dimension_{key}_{dimension}")
        df = df[df[dimension] == selected]
    # An optional category filter also supports datasets with repeated subgroups.
    category = st.selectbox("Filtrar categoría", [None, *[c for c in df if c != period]],
                            format_func=lambda c: "Sin filtro" if c is None else str(c),
                            key=f"dataset_map_category_{key}")
    if category is not None:
        choices = df[category].dropna().drop_duplicates().tolist()
        selected = st.multiselect("Valores del mapa", choices, key=f"dataset_map_values_{key}_{category}")
        if selected:
            df = df[df[category].isin(selected)]
    if mode == "Municipios de Madrid":
        default_column, default_system = suggestions[0] if suggestions else (df.columns[0], SYSTEMS[0])
        if spec:
            default_column, default_system = spec["column"], spec["system"]
        column = st.selectbox("Columna del municipio", list(df), index=list(df).index(default_column),
                              key=f"dataset_map_location_{key}")
        default_system = next((system for name, system in suggestions if name == column), default_system)
        system = st.selectbox("Formato de ubicación", SYSTEMS, index=SYSTEMS.index(default_system),
                              key=f"dataset_map_system_{key}_{column}")
        metrics = [c for c in metric_columns(df) if c != column]
        options = [None, *metrics]
        if spec:
            options = [None] if spec["kind"] == "municipal_count" else [c for c in spec["metrics"] if c in metrics]
            if not options:
                st.info("La selección no contiene valores numéricos del indicador.")
                return
        default_metric = (spec or {}).get("metric")
        metric = st.selectbox("Indicador del mapa", options,
                              index=options.index(default_metric) if default_metric in options else 0,
                              format_func=lambda c: "Recuento de registros" if c is None else str(c),
                              key=f"dataset_map_metric_{key}")
        aggregation = "Sin agregar"
        if metric is not None:
            aggregation = st.selectbox("Agregación por municipio", AGGREGATIONS, key=f"dataset_map_agg_{key}")
            st.caption("Filtra primero el periodo y las categorías. Suma solo magnitudes aditivas; "
                       "la media es simple, sin ponderación.")
        try:
            frame, excluded = municipal_frame(df, column, system, metric, aggregation)
        except ValueError as exc:
            st.info(str(exc))
            return
        st.caption(f"{len(df) - excluded} de {len(df)} registros con municipio reconocido · "
                   f"{excluded} sin coincidencia, excluidos.")
        if frame.empty:
            st.info("No hay municipios coincidentes. Comprueba la columna y el formato de ubicación.")
            return
        title = "Recuento de registros" if metric is None else f"{metric} · {aggregation}"
        source = next((url for url in sources if url.startswith("https://")), None)
        unit_column = next((c for c in df if normalized_name(c) == "unidad"), None)
        units = df[unit_column].dropna().unique() if unit_column is not None else []
        unit = "registros" if metric is None else str(units[0]) if len(units) == 1 else ""
        st.subheader(title)
        linked_map(frame, title=title, unit=unit, key=f"dataset_{key}", source=source)
    else:
        st.caption("Coordenadas geográficas WGS84 en grados decimales. Convierte las coordenadas UTM antes de usarlas.")
        latitude = st.selectbox("Latitud", list(df), index=list(df).index(lat) if lat is not None else 0,
                                key=f"dataset_map_lat_{key}")
        longitude = st.selectbox("Longitud", list(df), index=list(df).index(lon) if lon is not None else min(1, len(df.columns)-1),
                                 key=f"dataset_map_lon_{key}")
        try:
            points, excluded = point_frame(df, latitude, longitude)
        except ValueError as exc:
            st.info(str(exc))
            return
        if points.empty:
            st.info("No hay coordenadas válidas en la selección.")
            return
        st.caption(f"{len(points)} de {len(df)} registros localizados · {excluded} coordenadas inválidas, excluidas.")
        # Limit browser rendering, but export all valid locations.
        shown = points.head(10000)
        if len(points) > len(shown):
            st.info("Se muestran los primeros 10.000 puntos. La descarga contiene todos los puntos válidos.")
        figure = px.scatter_map(shown, lat="Latitud", lon="Longitud", zoom=8,
                                center={"lat": float(points.Latitud.median()), "lon": float(points.Longitud.median())},
                                map_style="open-street-map", title="Ubicaciones del dataset")
        st.plotly_chart(figure)
        export_chart(figure, f"points_{key}", label="Descargar mapa interactivo (HTML)")
        st.download_button("Descargar datos del mapa", csv_export(points), file_name="madrid-puntos.csv",
                           mime="text/csv", key=f"points_csv_{key}")
