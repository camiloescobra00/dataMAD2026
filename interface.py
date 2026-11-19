"""Shared presentation for navigation and analytical reports."""
import math

import plotly.io as pio
import streamlit as st

pio.templates.default = "plotly_dark"

PAGES = {"Explorar": ":material/search:", "Mapa": ":material/map:",
         "Analizar": ":material/analytics:", "Catálogo": ":material/folder_open:"}
PERSISTENT_FILTERS = (
    "facet_", "filter_", "values_", "keys_a_", "keys_b_", "join_right_",
    "analysis_year_", "x_", "y_", "sel_", "studio_filter_", "studio_values_", "method_",
)
PERSISTENT_KEYS = {
    "explorer_query", "catalog_sort", "analysis_tool", "analysis_table", "workspace_table",
    "analysis_mode", "analysis_operation", "join_left", "join_method", "studio_dataset", "studio_view",
}


def navigate(page):
    st.session_state.page = page


def navigation():
    # Reattach these widget values to the session before Streamlit cleans up the inactive page.
    for key in list(st.session_state):
        if key in PERSISTENT_KEYS or key.startswith(PERSISTENT_FILTERS):
            st.session_state[key] = st.session_state[key]
    page = st.session_state.setdefault("page", "Explorar")
    with st.container(horizontal=True, horizontal_alignment="distribute", vertical_alignment="center",
                      border=True, gap="small", key="mde_navigation"):
        st.html("""
        <div class="mde-brand">
          <span class="mde-brand-mark" aria-hidden="true">M</span>
          <span>Madrid <span class="mde-brand-detail">Data Explorer</span></span>
        </div>
        <style>
          .mde-brand {display:flex; align-items:center; gap:.65rem; white-space:nowrap;
              font-size:1.06rem; font-weight:750; color:#F0F3F6; letter-spacing:-.025em}
          .mde-brand-mark {display:grid; place-items:center; width:2rem; height:2rem;
              border-radius:.55rem; background:#16A085; color:#fff; font-size:1rem}
          .mde-brand-detail {font-weight:560}
          .mde-hero {background:#161B22; color:#F0F3F6; padding:clamp(1.25rem,4vw,3.25rem);
              border:1px solid #303A46; border-radius:1rem; text-align:center}
          .mde-hero h1 {font-size:clamp(1.85rem,4vw,3.35rem); letter-spacing:-.045em;
              line-height:1.08; margin:0 auto .65rem; padding:0; color:inherit; max-width:24ch}
          .st-key-mde_topics button {min-height:3.45rem; border-radius:.75rem; text-align:left;
              background:#1C2530; border-color:#303A46}
          .st-key-mde_topics button:hover {border-color:#16A085; background:#161B22}
          .mde-hero p {margin:0 auto; color:#AAB6C3; max-width:48ch; font-size:1.025rem}
        </style>
        """)
        with st.container(horizontal=True, gap="small"):
            for name, icon in PAGES.items():
                st.button(name, icon=icon, type="primary" if page == name else "tertiary",
                          key=f"nav_{name}", on_click=navigate, args=(name,))
    return page


def metric_cards(cards):
    with st.container(horizontal=True, gap="small"):
        for label, value, help_text in cards:
            st.metric(label, value, help=help_text, border=True, width=190)


def correlation_sentence(value):
    if not math.isfinite(value):
        return "No se pudo estimar una correlación lineal para los datos disponibles."
    magnitude = abs(value)
    if magnitude < .01:
        return "La correlación lineal es prácticamente nula. El análisis no permite establecer causalidad."
    level = next((label for cutoff, label in ((.2, "muy débil"), (.4, "débil"), (.6, "moderada"),
                                               (.8, "fuerte")) if magnitude < cutoff), "muy fuerte")
    direction = "positiva" if value > 0 else "negativa"
    return f"Se observa una relación lineal {direction} {level} entre las dos variables. Esto no implica causalidad."


def report_chart(figure):
    return figure.update_layout(template="plotly_dark", paper_bgcolor="#0D1117", plot_bgcolor="#161B22", height=430, margin={"l": 14, "r": 16, "t": 54, "b": 24},
                                legend={"orientation": "h", "y": -0.20},
                                colorway=["#49D5B3", "#F7A879", "#89AEF7", "#C5A4ED"])
