"""Dataset profile, assisted cleaning and statistical study interface."""
from dataclasses import asdict

import pandas as pd
import plotly.express as px
import streamlit as st

from data_tables import csv_export
from interface import metric_cards, report_chart
from joins import normalized_name
from map_view import export_chart, linked_map
from profiling import CATEGORIES, ROLES, corrected, schema
from reports import html_report
from statistical_engine import (
    FAMILIES,
    GROUPED,
    MODELS,
    PAIRED,
    association,
    compatible,
    descriptive,
    frequencies,
    group_test,
    numeric_values,
    regression,
    temporal,
)
from territories import normalize_code, official_codes


def get_profile(item):
    if "profile" not in item:
        item["profile"] = schema(item["df"])
    return item["profile"]


def role_map(item):
    return {entry["Variable"]: item.get("roles", {}).get(entry["Variable"], entry["Rol"])
            for entry in get_profile(item)["variables"]}


def dictionary(item):
    roles = role_map(item)
    definitions = item.get("metadata", {}).get("variables", {})
    return pd.DataFrame([{**entry, "Rol": roles[entry["Variable"]],
                          "Descripción": definitions.get(entry["Variable"], "Sin descripción publicada")}
                         for entry in get_profile(item)["variables"]])


def provenance(item, **parameters):
    return {"fuentes": item["sources"], "metadatos": item.get("metadata", {}), "transformaciones": item["history"],
            "roles": role_map(item), "filtros": parameters.pop("filtros", {}), "parámetros": parameters}


def diagnostics(item, key):
    profile = get_profile(item)
    st.subheader("Diagnóstico del dataset")
    st.caption(item.get("metadata", {}).get("descripción") or item["title"])
    percent = 100 * profile["missing"] / item["df"].size if item["df"].size else 0
    metric_cards([("Filas", profile["rows"], None), ("Variables", profile["columns"], None),
                  ("Ausentes", f"{percent:.1f} %", "Proporción de celdas ausentes o vacías."),
                  ("Duplicados", profile["duplicates"], "Filas idénticas posteriores a su primera aparición.")])
    info = dictionary(item)
    st.dataframe(info, hide_index=True)
    valid = compatible(item["df"], role_map(item))
    uses = [family for family, options in FAMILIES.items()
            if any(len(study_spec(option, valid)[0]) > study_spec(option, valid)[1] for option in options)]
    if uses:
        st.caption("Usos posibles según el perfil: " + " · ".join(uses))
    with st.expander("Corregir la clasificación de una variable"):
        column = st.selectbox("Variable", list(role_map(item)), key=f"role_col_{key}")
        if column is not None:
            inferred = role_map(item)[column]
            role = st.selectbox("Rol", ROLES, index=ROLES.index(inferred), key=f"role_value_{key}_{column}")
            if st.button("Guardar clasificación", key=f"role_save_{key}"):
                item.setdefault("roles", {})[column] = role
                st.rerun()
    with st.expander("Vista de datos y procedencia"):
        st.dataframe(item["df"].head(150), hide_index=True)
        st.json(provenance(item))
        st.download_button("Descargar datos (CSV)", csv_export(item["df"]), "madrid-datos.csv", "text/csv",
                           key=f"profile_csv_{key}")


def cleaning(item, key, tables, store):
    st.subheader("Mejoras recomendadas para tus datos")
    suggested = get_profile(item)["advice"]
    dismissed = item.setdefault("dismissed", set())
    options = [i for i in range(len(suggested)) if i not in dismissed]
    if not options:
        st.info("El diagnóstico actual no tiene recomendaciones pendientes.")
        return
    pick = st.selectbox("Recomendación", options, key=f"advice_{key}",
                        format_func=lambda i: f"{suggested[i].operation} · {suggested[i].column or 'Tabla completa'}")
    if pick is None:
        return
    entry = suggested[pick]
    st.write(entry.reason)
    st.caption(f"Registros afectados o por revisar: {entry.count}.")
    df = item["df"]
    derived = None
    if entry.actionable:
        try:
            derived = corrected(df, entry)
            comparison = st.columns(2)
            column = entry.column
            if column:
                changed = df[column].astype("string").fillna("").ne(derived[column].astype("string").fillna(""))
                sample = changed[changed].index[:15]
                if sample.empty:
                    sample = df.index[:15]
                comparison[0].dataframe(df.loc[sample, [column]].astype("string"), hide_index=True)
                comparison[1].dataframe(derived.loc[sample, [column]].astype("string"), hide_index=True)
            else:
                comparison[0].dataframe(df[df.duplicated(keep=False)].head(15), hide_index=True)
                comparison[1].dataframe(derived.head(15), hide_index=True)
            comparison[0].caption("Antes")
            comparison[1].caption("Después")
        except ValueError as exc:
            st.warning(str(exc))
    elif entry.column:
        st.dataframe(df[[entry.column]].head(15), hide_index=True)
    with st.container(horizontal=True):
        if st.button("Aplicar y crear versión", disabled=derived is None, key=f"apply_{key}_{pick}", type="primary"):
            try:
                new = store(f"{item['title']} · limpia", derived, item["sources"],
                            (*item["history"], asdict(entry)), True, metadata=item.get("metadata"))
                tables[new]["original"] = item.get("original", key)
                tables[new]["parent"] = key
                tables[new]["roles"] = dict(item.get("roles", {}))
                st.session_state["studio_focus"] = new
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
        if st.button("Descartar recomendación", key=f"dismiss_{key}_{pick}"):
            dismissed.add(pick)
            st.rerun()


def exploratory(item, key):
    roles = role_map(item)
    df = item["df"]
    valid = compatible(df, roles)
    profile = get_profile(item)
    summary = f"{profile['rows']} filas, {profile['columns']} variables, {profile['duplicates']} duplicados exactos."
    st.subheader("Informe exploratorio")
    st.write(summary)
    selected = valid["numeric"][:3]
    figures, sections = [], []
    for variable in selected:
        result = descriptive(df[variable])
        sections.append((variable, result.table))
        st.write(f"**{variable}.** {result.summary}")
        fig = report_chart(result.figure.update_layout(title=f"Distribución de {variable}"))
        st.plotly_chart(fig)
        figures.append(fig)
    if not selected and valid["category"]:
        result = frequencies(df[valid["category"][0]])
        sections.append((valid["category"][0], result.table))
        st.write(result.summary)
        figures.append(report_chart(result.figure))
        st.plotly_chart(figures[-1])
    st.download_button("Descargar informe exploratorio (HTML)", html_report(item["title"], summary, dictionary(item),
                       provenance(item, exploradas=[label for label, _ in sections]), figures, sections=sections),
                       "madrid-informe.html", "text/html", key=f"initial_report_{key}")


def study_spec(name, valid):
    nums, varied, cats = valid["numeric"], valid["varied"], valid["category"]
    if name == "Frecuencias":
        return cats, 0, "Se requieren variables categóricas de entre 2 y 20 valores."
    if name in {"Contingencia y chi-cuadrado", "Pearson", "Spearman"}:
        options = cats if name.startswith("Contingencia") else varied
        return options, 1, "Se requieren dos variables compatibles con variación."
    if name in PAIRED:
        return nums, 1, "Se requieren dos mediciones numéricas y pares verificables."
    if name in GROUPED:
        groups = valid["two_groups"] if name in {"t independiente (Welch)", "Mann–Whitney"} else cats
        return nums if groups else [], 0, "Se requiere una medida numérica y una variable con los grupos necesarios."
    if name == "Evolución y cambios":
        return nums if valid["time"] else [], 0, "Se requieren un periodo y un indicador numérico."
    if name == "Comparación municipal":
        return nums if valid["geo"] else [], 0, "Se requieren un código municipal y un indicador numérico."
    if name in MODELS:
        predictors = 2 if name == "Lineal múltiple" else 1
        responses = valid["binary"] if name == "Logística binaria" else valid["counts"] if name == "Poisson" else nums
        responses = [column for column in responses if len(set(varied) - {column}) >= predictors]
        return responses, 0, "Se requieren una respuesta válida y predictores numéricos con variación."
    return nums, 0, "Se requiere una variable numérica válida."


def geo_study(df, valid, names, key):
    column = st.selectbox("Código municipal", valid["geo"])
    period = st.selectbox("Variable temporal", [None, *valid["time"]], format_func=lambda x: x or "Sin periodo")
    years = sorted(df[period].dropna().unique(), reverse=True) if period else []
    a = st.selectbox("Periodo principal", years, key=f"geo_first_{key}") if years else None
    b = st.selectbox("Periodo de comparación", [None, *years], key=f"geo_second_{key}",
                     format_func=lambda x: "Mismo periodo" if x is None else str(x)) if years else None
    metrics = st.multiselect("Indicadores", names, max_selections=2, key=f"geo_metrics_{key}")
    if not metrics:
        return
    system = st.selectbox("Formato de código", ["INE", "Almudena"], index=int(normalized_name(column) == "codigo_territorio"))
    codes = df[column].map(lambda value: normalize_code(value, system) or normalize_code(value))
    frames = []
    for index, metric in enumerate(metrics if len(metrics) == 2 or b is None else metrics * 2):
        period_value = (b or a) if index else a
        subset = df[period].eq(period_value) if period and period_value is not None else pd.Series(True, index=df.index)
        frame = pd.DataFrame({"INE": codes[subset], "Valor": numeric_values(df.loc[subset, metric])}).dropna(subset=["INE"])
        label = f"{metric} · {period_value}" if period_value is not None else metric
        frames.append((label, frame))
    st.caption("Las vistas comparten selección municipal, zoom y centro. Los rankings y diferencias se calculan por código INE.")
    areas = st.columns(len(frames))
    for index, (label, frame) in enumerate(frames):
        with areas[index]:
            st.write(f"**{label}**")
            linked_map(frame, title=label, unit="", key=f"studio_{key}_{index}",
                       sync=f"studio_viewport_{key}" if len(frames) == 2 else None)
    if any(frame["INE"].duplicated().any() for _, frame in frames):
        st.warning("Filtra la tabla hasta obtener una fila por municipio y periodo.")
        return
    ranking = frames[0][1].dropna().sort_values("Valor", ascending=False)
    ranking = ranking.rename(columns={"Valor": frames[0][0]})
    if len(frames) == 2 and frames[0][0] != frames[1][0]:
        first, second = (entry[0] for entry in frames)
        ranking = ranking.merge(frames[1][1].rename(columns={"Valor": second}), on="INE", how="outer")
        if len(metrics) == 1:
            ranking["Cambio absoluto (principal − comparación)"] = ranking[first] - ranking[second]
    ranking["Municipio"] = ranking["INE"].map(lambda code: official_codes()[code][1])
    ranking = ranking.sort_values(frames[0][0], ascending=False)
    st.dataframe(ranking.head(179), hide_index=True)
    with st.expander("Distribución territorial"):
        chart = report_chart(px.histogram(ranking, x=frames[0][0], title="Distribución entre municipios"))
        st.plotly_chart(chart)
        export_chart(chart, f"geo_distribution_{key}")
    st.download_button("Descargar comparación territorial", csv_export(ranking), "madrid-territorio.csv", "text/csv",
                       key=f"geo_csv_{key}")


def run_study(item, key):
    full = item["df"]
    df = full
    filters = {}
    with st.expander("Filtrar observaciones"):
        col = st.selectbox("Variable para filtrar", [None, *full.columns], key=f"studio_filter_{key}",
                           format_func=lambda x: x or "Sin filtro")
        if col is not None:
            selected = st.multiselect("Valores", full[col].dropna().unique()[:500], key=f"studio_values_{key}_{col}")
            if selected:
                filters[col] = selected
                df = full[full[col].isin(selected)]
    roles = role_map(item)
    valid = compatible(df, roles)
    st.subheader("Análisis disponibles")
    with st.container(horizontal=True):
        for family in FAMILIES:
            options = FAMILIES[family]
            enabled = any(len(study_spec(option, valid)[0]) > study_spec(option, valid)[1] for option in options)
            st.button(family, disabled=not enabled, key=f"family_{key}_{family}",
                      help=None if enabled else study_spec(options[0], valid)[2],
                      on_click=lambda family=family: st.session_state.update({f"family_{key}": family}))
    family = st.session_state.get(f"family_{key}", "Descriptivos")
    method = st.selectbox("Análisis", FAMILIES[family], key=f"method_{key}_{family}")
    options, minimum, why = study_spec(method, valid)
    if len(options) <= minimum:
        st.info(why)
        return
    if method == "Comparación municipal":
        geo_study(df, valid, options, key)
        return
    x = st.selectbox("Variable principal", options, key=f"primary_{key}_{method}")
    y = None
    params = {"análisis": method, "variable": x, "filtros": filters}
    if minimum:
        y = st.selectbox("Segunda variable", [c for c in options if c != x], key=f"second_{key}_{method}")
    elif method in GROUPED:
        categories = valid["two_groups"] if method in {"t independiente (Welch)", "Mann–Whitney"} else valid["category"]
        y = st.selectbox("Variable de grupo", [c for c in categories if c != x], key=f"group_{key}_{method}")
        if y is None:
            st.info("Selecciona una variable de grupo distinta del indicador.")
            return
    if y:
        params["segunda variable"] = y
    confirmed = method not in PAIRED | GROUPED or st.checkbox(
        "Cada fila contiene dos mediciones de la misma unidad" if method in PAIRED
        else "Las observaciones son independientes entre grupos y dentro de cada grupo",
        key=f"design_{key}_{method}")
    if method in MODELS:
        available = [c for c in valid["varied"] if c != x]
        predictors = st.multiselect("Predictores", available, max_selections=1 if method == "Lineal simple" else 10)
        exposure = st.selectbox("Exposición (opcional)", [None, *[c for c in available if c not in predictors]],
                                format_func=lambda c: c or "Sin exposición") if method == "Poisson" else None
        positive = st.selectbox("Clase positiva", df[x].dropna().unique()) if method == "Logística binaria" else None
        params.update(predictores=predictors, exposición=exposure, clase_positiva=positive)
    if method == "Evolución y cambios":
        period = st.selectbox("Periodo", valid["time"])
        by = st.selectbox("Separar series por", [None, *[c for c in roles if roles[c] in CATEGORIES | {"Código municipal"}]],
                          format_func=lambda c: c or "Una sola serie")
        window = st.number_input("Ventana de media móvil", min_value=2, max_value=30, value=3)
        params.update(periodo=period, grupo=by, ventana=window)
    state = f"study_result_{key}"
    if st.button("Ejecutar análisis", type="primary", disabled=not confirmed, key=f"execute_{key}_{method}"):
        st.session_state.pop(state, None)
        try:
            if method == "Distribución":
                answer = descriptive(df[x])
            elif method == "Frecuencias":
                answer = frequencies(df[x])
            elif method in PAIRED | GROUPED:
                answer = group_test(df, method, x, y, design_confirmed=confirmed)
            elif method in MODELS:
                answer = regression(df, method, x, predictors, exposure, positive=positive)
            elif method == "Evolución y cambios":
                answer = temporal(df, period, x, roles[period], by, window)
            else:
                answer = association(df, method, x, y)
            st.session_state[state] = (params, answer)
        except (ValueError, TypeError) as exc:
            st.warning(str(exc))
    stored = st.session_state.get(state)
    if stored is None or stored[0] != params:
        return
    answer = stored[1]
    st.write(answer.summary)
    st.dataframe(answer.table.astype({"Valor": "string"}) if method == "Distribución" else answer.table, hide_index=True)
    figures = [report_chart(figure) for figure in [answer.figure, *answer.charts] if figure is not None]
    for figure in figures:
        st.plotly_chart(figure)
    for note in answer.notes:
        st.caption(note)
    meta = provenance(item, **params)
    with st.expander("Descargas y metodología"):
        st.json(meta)
        st.download_button("Descargar resultados (CSV)", csv_export(answer.table), "madrid-resultados.csv", "text/csv")
        for index, figure in enumerate(figures):
            export_chart(figure, f"studio_{key}_{index}", label=f"Descargar gráfico {index + 1} (HTML)")
        st.download_button("Descargar informe estadístico (HTML)",
                           html_report(method, answer.summary, answer.table, meta, figures, answer.notes),
                           "madrid-estudio.html", "text/html")


def studio(tables, store):
    if not tables:
        st.info("Carga un dataset desde Catálogo para generar el diagnóstico y empezar un estudio.")
        return
    focus = st.session_state.pop("studio_focus", None)
    if focus in tables:
        st.session_state["studio_dataset"] = focus
    key = st.selectbox("Dataset", list(tables), format_func=lambda n: f"{tables[n]['title']} · #{n}", key="studio_dataset")
    item = tables[key]
    view = st.radio("Herramienta", ["Diagnóstico e informe", "Limpieza recomendada", "Análisis disponibles"],
                    horizontal=True, key="studio_view")
    if view == "Diagnóstico e informe":
        diagnostics(item, key)
        exploratory(item, key)
    elif view == "Limpieza recomendada":
        cleaning(item, key, tables, store)
        original = item.get("original")
        if original in tables:
            with st.expander("Comparar con el original"):
                left, right = st.columns(2)
                left.caption("Original")
                left.dataframe(tables[original]["df"].head(20), hide_index=True)
                right.caption("Versión actual")
                right.dataframe(item["df"].head(20), hide_index=True)
        parent = item.get("parent")
        if key in st.session_state.undo and parent in tables and st.button("Deshacer esta versión"):
            del tables[key]
            st.session_state.undo.remove(key)
            st.session_state["studio_focus"] = parent
            st.rerun()
    else:
        run_study(item, key)
