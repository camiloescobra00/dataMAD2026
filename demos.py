"""Demostraciones reproducibles basadas en extractos de fuentes oficiales."""
import json
from pathlib import Path

import plotly.express as px
import streamlit as st

from analytics import analyze
from data_tables import read_table
from joins import join_preview

DATA = Path(__file__).resolve().parent / "demo_data"
KEYS = ["Código territorio", "Año"]
AGE = "grado_envejecimiento_por_edad"
DEMO_NAMES = ["Economía y demografía", "Mercado laboral", "Salud y territorio"]
SOURCES = {
    DEMO_NAMES[0]: (AGE, "irpf_indicador_renta"),
    DEMO_NAMES[1]: ("302038",),
    DEMO_NAMES[2]: (AGE, "centros_sanitarios_por_tipo"),
}


def demo_table(name):
    sources = SOURCES[name]
    frames = [read_table((DATA / f"{source}.csv").read_bytes(), "csv") for source in sources]
    if len(frames) == 1:
        return frames[0], {}
    result, info = join_preview(frames[0], frames[1].drop(columns="Territorio"), KEYS, KEYS, "inner")
    if info["cardinalidad"] != "uno a uno":
        raise ValueError("La demostración requiere una observación por municipio y año.")
    return result, info


def show_demos(store):
    name = st.selectbox("Ejemplo", DEMO_NAMES)
    if not st.checkbox("Abrir demostración"):
        return
    df, info = demo_table(name)
    metrics = list(df.columns[3:])
    if name == DEMO_NAMES[1]:
        options = sorted(df["Territorio"].unique())
        selected = st.multiselect("Municipios", options, default=["Alcalá de Henares", "Alcorcón", "Móstoles"])
        view = df[df["Territorio"].isin(selected)].sort_values("Año")
        st.plotly_chart(px.line(view, x="Año", y=metrics[0], color="Territorio", markers=True,
                                title="Evolución anual del paro registrado · 2018–2025"))
        endpoints = view.pivot(index="Territorio", columns="Año", values=metrics[0])
        if {2018, 2025} <= set(endpoints):
            endpoints["Variación en personas"] = endpoints[2025] - endpoints[2018]
            st.dataframe(endpoints[[2018, 2025, "Variación en personas"]].rename(columns=str))
        st.caption("Son recuentos de paro registrado. El tamaño poblacional y la proporción de personas activas "
                   "varían entre municipios. La serie compara recuentos y evolución.")
    else:
        x, y = metrics
        complete = df.dropna(subset=[x, y])
        result, _, _ = analyze(complete, {"operation": "correlation", "x": x, "y": y})
        st.plotly_chart(px.scatter(complete, x=x, y=y, hover_name="Territorio", title=f"{y} y envejecimiento · 2024"))
        r = result["Pearson r"].iat[0]
        direction = "negativa" if r < 0 else "positiva" if r > 0 else "nula"
        st.write(f"Asociación lineal {direction} de Pearson, **r = {r:.3f}** en **{len(complete)} municipios**. "
                 f"Se excluyeron {len(df) - len(complete)} municipios con valores faltantes.")
        st.caption("Cada municipio tiene el mismo peso. La correlación describe una asociación territorial "
                   "y no permite inferir causalidad.")
        if name == DEMO_NAMES[0]:
            st.caption("La renta es el indicador municipal de renta disponible bruta per cápita. "
                       "Los valores protegidos por secreto estadístico se conservan como faltantes.")
        else:
            st.caption("El indicador cuenta consultorios locales y centros de salud por 10.000 habitantes. "
                       "En municipios pequeños, un solo centro puede elevar mucho la tasa. "
                       "La cifra no mide capacidad asistencial ni accesibilidad.")
    sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))
    urls = []
    with st.expander("Fuentes y método"):
        for key in SOURCES[name]:
            source = sources[key]
            urls.append(source["url"])
            st.link_button(source["title"], source["url"])
            st.caption(f"Comunidad de Madrid · {source['license'] or 'Licencia por consultar'}")
        if info:
            st.json(info)
    if st.button("Añadir demostración al espacio de trabajo"):
        try:
            steps = [{"operación": "selección documentada en demo_data/build.py", "demostración": name,
                      **info}]
            store(name, df, urls, steps)
            st.success("Demostración añadida. Puedes analizarla o exportarla desde el espacio de trabajo.")
        except ValueError as exc:
            st.error(str(exc))
