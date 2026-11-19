"""Municipal choropleths and linked selection."""
import html
import math
import re
from hashlib import sha256
from itertools import pairwise

import folium
import pandas as pd
import plotly.express as px
import streamlit as st
from branca.element import Element
from streamlit_folium import st_folium

from data_tables import csv_export
from interface import report_chart
from territories import boundaries, official_codes

ATTRIBUTION = "Obra derivada de BDLJE CC-BY 4.0 ign.es"
PALETTES = {
    "Azul": ["#e5f2ff", "#b4d8f5", "#70b5de", "#2f7fb7", "#17406b"],
    "Verde": ["#ecf7ec", "#bedfc5", "#83c39b", "#3c8964", "#16513b"],
    "Violeta": ["#f2eafa", "#dfc9ef", "#ba99d8", "#8964b1", "#57367f"],
}
MISSING = "#303A46"
SELECTION = "mde_selected_codes"


def value_text(value, unit, *, decimals=2):
    if pd.isna(value):
        return "Sin datos"
    number = f"{value:,.{decimals}f}".rstrip("0").rstrip(".").translate(str.maketrans(",.", ".,"))
    return f"{number} {unit}".strip()


def natural_breaks(values, count):
    """Minimize the sum of within-class squared deviations without splitting ties."""
    ordered = sorted(map(float, values))
    count = min(count, len(set(ordered)))
    size = len(ordered)
    # Centering the observations keeps variance calculations stable for large counts.
    sums, squares = [0.0], [0.0]
    for value in ordered:
        centered = value - ordered[0]
        sums.append(sums[-1] + centered)
        squares.append(squares[-1] + centered ** 2)
    starts = [0, *(i for i in range(1, size) if ordered[i - 1] != ordered[i])]
    costs = [{0: (0.0, 0)}]
    for _ in range(count):
        layer = {}
        previous = costs[-1]
        for end in [*starts[1:], size]:
            options = []
            for start in starts:
                if start >= end:
                    break
                if start in previous:
                    total = sums[end] - sums[start]
                    variance = squares[end] - squares[start] - total ** 2 / (end - start)
                    options.append((previous[start][0] + max(0, variance), start))
            if options:
                layer[end] = min(options)
        costs.append(layer)
    breaks = []
    end = size
    for layer in reversed(costs[1:]):
        breaks.append(ordered[end - 1])
        end = layer[end][1]
    return [ordered[0], *reversed(breaks)]


def classify(values, method, count=5):
    values = pd.to_numeric(values, errors="coerce").dropna()
    values = values[values.map(math.isfinite)]
    if values.empty:
        return []
    low, high = float(values.min()), float(values.max())
    if low == high:
        return [low]
    if method == "Cortes naturales (Jenks)":
        return natural_breaks(values, count)
    if method == "Cuantiles":
        return sorted(set(map(float, values.quantile([i/count for i in range(count + 1)]))))
    return [low + (high - low) * i/count for i in range(count)] + [high]


def map_features(frame, unit, method, palette):
    if frame["INE"].dropna().duplicated().any():
        raise ValueError("Selecciona un periodo o filtra hasta dejar una fila por municipio.")
    rows = frame.dropna(subset=["INE"]).set_index("INE")["Valor"]
    bins = classify(rows, method)
    features = []
    for feature in boundaries()["features"]:
        code = feature["id"]
        value = rows.get(code)
        present = pd.notna(value) and math.isfinite(float(value))
        index = next((i for i, edge in enumerate(bins[1:]) if value <= edge), max(0, len(bins)-2)) if present else 0
        color = palette[index] if present else MISSING
        properties = {"name": official_codes()[code][1], "code": code,
                      "value": value_text(value if present else None, unit), "color": color}
        features.append({**feature, "properties": properties})
    return {"type": "FeatureCollection", "features": features}, bins


def clicked_code(event):
    tooltip = (event or {}).get("last_object_clicked_tooltip") or ""
    match = re.search(r"Código INE\s*:?\s*(28\d{3})(?!\d)", str(tooltip))
    return match[1] if match and match[1] in official_codes() else None


def apply_click(selection, code):
    if not code or code in selection:
        return list(selection)
    return [*selection[-5:], code]


def build_map(features, bins, palette, unit):
    map_ = folium.Map(tiles=None, zoom_control=True, scroll_wheel_zoom=True, prefer_canvas=True)
    pairs = [(lat, lon) for feature in features["features"]
             for polygon in (feature["geometry"]["coordinates"] if feature["geometry"]["type"] == "MultiPolygon"
                             else [feature["geometry"]["coordinates"]])
             for ring in polygon for lon, lat in ring]
    if pairs:
        latitudes, longitudes = zip(*pairs)
        map_.fit_bounds([[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]],
                        padding=(26, 26))
    map_.get_root().header.add_child(Element(
        "<style>.leaflet-container{background:#0D1117}.leaflet-tooltip,.leaflet-bar a"
        "{background:#161B22!important;color:#F0F3F6!important;border-color:#303A46!important}</style>"))

    folium.GeoJson(
        features,
        style_function=lambda f: {"weight": 0.7, "color": "#8c9eae", "fillColor": f["properties"]["color"],
                                  "fillOpacity": .92},
        highlight_function=lambda _: {"weight": 2.4, "color": "#F0F3F6", "fillOpacity": 1},
        tooltip=folium.GeoJsonTooltip(fields=["name", "value", "code"], aliases=["Municipio", "Indicador", "Código INE"],
                                      sticky=False),
    ).add_to(map_)
    levels = list(pairwise(bins)) if len(bins) > 1 else [(v, v) for v in bins]
    tags = [(palette[i], value_text(a, unit) if a == b else f"{value_text(a, '')} – {value_text(b, unit)}")
            for i, (a, b) in enumerate(levels)]
    tags.append((MISSING, "Sin datos"))
    entries = "".join(f'<div><span style="display:inline-block;width:11px;height:11px;margin-right:6px;'
                      f'background:{color}"></span>{html.escape(label)}</div>' for color, label in tags)
    legend = ('<div style="position:fixed;bottom:18px;right:12px;z-index:1000;background:#161B22;color:#F0F3F6;'
              'padding:9px 12px;border:1px solid #303A46;border-radius:8px;font:12px system-ui">'
              + entries + "</div>")
    map_.get_root().html.add_child(Element(legend))
    return map_


def export_chart(figure, key, *, label="Descargar gráfico (HTML)"):
    st.download_button(label, figure.to_html(include_plotlyjs=True),
                       file_name="madrid-grafico.html", mime="text/html", key=f"chart_{key}")


def remembered_choice(widget, label, options, key, *, index=0, **kwargs):
    """Keep a choice even when its widget is absent on another page."""
    state_key = f"saved_{key}"
    current = st.session_state.get(state_key)
    if key not in st.session_state and current in options:
        st.session_state[key] = current

    def remember():
        st.session_state[state_key] = st.session_state[key]

    return widget(label, options, key=key, index=index, on_change=remember, **kwargs)


def synced_view(event):
    center, zoom = event.get("center"), event.get("zoom")
    if not isinstance(center, dict) or not isinstance(zoom, int):
        return None
    lat, lon = center.get("lat"), center.get("lng")
    if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in (lat, lon)):
        return None
    return (round(lat, 6), round(lon, 6)), zoom


def linked_map(frame, *, title, unit, key, history=None, reference=None, source=None, sync=None):
    visual = st.container()
    opts = official_codes()
    selected = [code for code in st.session_state.get(SELECTION, []) if code in opts]
    epoch_key = f"extent_{sync or key}"

    def sync_picker():
        st.session_state[SELECTION] = st.session_state[f"municipios_{key}"]

    with st.container(horizontal=True, vertical_alignment="bottom"):
        st.session_state[f"municipios_{key}"] = selected
        st.multiselect("Municipios", sorted(opts, key=lambda c: opts[c][1]),
                       format_func=lambda code: opts[code][1], key=f"municipios_{key}",
                       on_change=sync_picker, max_selections=6, placeholder="Buscar y comparar municipios")
        with st.popover("Estilo del mapa", icon=":material/tune:"):
            method = remembered_choice(st.selectbox, "Distribución",
                                       ["Cuantiles", "Intervalos iguales", "Cortes naturales (Jenks)"], f"bins_{key}")
            palette = PALETTES[remembered_choice(st.selectbox, "Colores", list(PALETTES), f"palette_{key}")]
        if st.button("Restablecer vista", key=f"reset_{key}", icon=":material/zoom_out_map:", type="tertiary"):
            st.session_state[epoch_key] = st.session_state.get(epoch_key, 0) + 1
            if sync:
                st.session_state.pop(sync, None)
                st.rerun()
    try:
        features, bins = map_features(frame, unit, method, palette)
    except ValueError as exc:
        st.info(str(exc))
        return
    fingerprint = sha256(pd.util.hash_pandas_object(frame[["INE", "Valor"]]).values.tobytes()).hexdigest()[:12]
    map_key = f"map_{key}_{fingerprint}_{method}_{palette[0]}_{st.session_state.get(epoch_key, 0)}"
    map_ = build_map(features, bins, palette, unit)
    center, zoom = st.session_state.get(sync, (None, None)) if sync else (None, None)
    returned = ["last_object_clicked", "last_object_clicked_tooltip"]

    def sync_viewport():
        view = synced_view(st.session_state.get(map_key, {}))
        if view is not None:
            st.session_state[sync] = view

    if sync:
        returned.extend(["center", "zoom"])
    with visual:
        event = st_folium(map_, use_container_width=True, height=450, key=map_key,
                          returned_objects=returned, center=center, zoom=zoom,
                          on_change=sync_viewport if sync else None)
    code = clicked_code(event)
    token = (map_key, event.get("last_object_clicked"), code) if code else None
    if token and token != st.session_state.get(f"last_{key}"):
        st.session_state[f"last_{key}"] = token
        if code not in selected:
            st.session_state[SELECTION] = apply_click(selected, code)
            st.rerun()
    available = sum(f["properties"]["value"] != "Sin datos" for f in features["features"])
    st.caption(f"{available} de 179 municipios con datos · {ATTRIBUTION} · Límites actuales.")
    with st.expander("Fuente, referencia y descargas del mapa"):
        if source:
            st.link_button("Fuente del indicador", source)
        if reference is not None:
            st.caption(f"Comunidad de Madrid (dato oficial): {value_text(reference, unit)}.")
        st.download_button("Descargar datos del mapa", csv_export(frame), file_name="madrid-mapa.csv",
                           mime="text/csv", key=f"map_csv_{key}")
        st.download_button("Descargar mapa interactivo (HTML)", map_.get_root().render(),
                           file_name="madrid-mapa.html", mime="text/html", key=f"map_html_{key}")
    if not selected:
        return
    data = frame.assign(Posición=pd.to_numeric(frame["Valor"], errors="coerce").rank(ascending=False, method="min"))
    detail = pd.DataFrame({"INE": selected, "Municipio": [opts[c][1] for c in selected]}).merge(
        data[["INE", "Valor", "Posición"]], how="left", on="INE")
    st.dataframe(detail[["Municipio", "Valor", "Posición"]], hide_index=True)
    if history is not None and history["Año"].nunique() > 1:
        points = history[history["INE"].isin(selected)].sort_values("Año")
        figure = px.line(points, x="Año", y="Valor", color="Municipio", markers=True,
                         labels={"Valor": title}, title="Evolución de los municipios seleccionados")
    else:
        figure = px.bar(detail, x="Municipio", y="Valor", labels={"Valor": title}, title="Comparación municipal")
    st.plotly_chart(report_chart(figure))
    export_chart(figure, f"map_detail_{key}")
