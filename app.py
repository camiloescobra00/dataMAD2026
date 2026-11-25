"""Interfaz de Madrid Data Explorer."""
import json
from zipfile import BadZipFile

import pandas as pd
import requests
import streamlit as st

from analysis_workspace import get_profile, studio
from analytics import NEEDS_NUMERIC_X, NEEDS_Y, OPERATIONS, analyze
from assistant import plan_analysis
from catalog import FACETS, SORT, catalog_page, compatible_resources, download_table
from data_tables import (
    category_variants,
    csv_export,
    describe_table,
    read_table,
    transform,
)
from dataset_cards import dataset_metadata, metadata_card
from explore_view import full_map, question_screen
from interface import navigation
from joins import join_preview, key_role, normalized_name, suggest_keys
from map_view import export_chart, linked_map
from maps import municipal_map
from settings import ai_settings
from territories import normalize_code

st.set_page_config(page_title="Madrid Data Explorer", page_icon="📊", layout="wide")
st.session_state.setdefault("tables", {})
st.session_state.setdefault("undo", [])
st.session_state.setdefault("serial", 0)
tables = st.session_state.tables


@st.cache_data(ttl=600, max_entries=48, show_spinner=False)
def search(query, start, filters, sort):
    return catalog_page(query, start=start, filters=filters, sort=sort)


def store(title, df, sources, history=(), reversible=False, *, metadata=None):
    if len(tables) >= 8 or sum(item["df"].size for item in tables.values()) + df.size > 4_000_000:
        raise ValueError("Se alcanzó el límite de ocho tablas o cuatro millones de celdas. Retira una tabla.")
    st.session_state.serial += 1
    key = st.session_state.serial
    item = {"title": title, "df": df, "sources": tuple(dict.fromkeys(sources)), "history": tuple(history),
            "metadata": metadata or {}}
    get_profile(item)
    tables[key] = item
    if reversible:
        st.session_state.undo.append(key)
    return key


def table_picker(label, key, choices=None):
    return st.selectbox(label, list(tables) if choices is None else choices,
                        format_func=lambda i: f"{tables[i]['title']} · #{i}", key=key)


def preview(df):
    st.caption(f"{len(df):,} filas · {len(df.columns)} variables")
    st.dataframe(df.head(100), hide_index=True)


def downloads(df, metadata, name):
    st.download_button("Descargar CSV", csv_export(df), file_name=f"{name}.csv", mime="text/csv")
    st.download_button("Descargar metodología", json.dumps(metadata, ensure_ascii=False, indent=2, default=str),
                       file_name=f"{name}.json", mime="application/json")


def explorer():
    st.header("Catálogo oficial")
    st.write("Busca en el catálogo oficial de la Comunidad de Madrid o incorpora una tabla propia.")
    with st.form("buscar"):
        existing = st.session_state.get("search_params", ("", 0, {}, "Relevancia"))
        query = st.text_input("Tema o palabra clave", key="explorer_query", placeholder="Población, empleo, calidad del aire")
        sort = st.selectbox("Orden", list(SORT), key="catalog_sort")
        facets = st.session_state.get("facets", {})
        filters = {}
        with st.expander("Filtros del catálogo"):
            for label, field in FACETS.items():
                values = {i["name"]: i.get("display_name", i["name"])
                          for i in facets.get(field, {}).get("items", [])}
                previous = existing[2].get(label)
                if previous:
                    values.setdefault(previous, previous)
                filters[label] = st.selectbox(label, [None, *values], key=f"facet_{field}",
                                              format_func=lambda v, labels=values: labels[v] if v else "Todos")
        if st.form_submit_button("Buscar datasets", type="primary"):
            st.session_state.search_params = (query, 0, filters, sort)
    if "search_params" in st.session_state:
        query, offset, filters, sort = st.session_state.search_params
        try:
            with st.spinner("Consultando catálogo oficial…"):
                result = search(query, offset, filters, sort)
        except (requests.RequestException, ValueError, KeyError):
            st.error("El catálogo no respondió correctamente. Vuelve a buscar en unos instantes.")
        else:
            st.session_state.facets = result.get("search_facets", {})
            st.caption(f"{result['count']:,} resultados · página {offset // 20 + 1}")
            a, b = st.columns(2)
            if a.button("Anterior", disabled=offset == 0):
                st.session_state.search_params = (query, offset - 20, filters, sort)
                st.rerun()
            if b.button("Siguiente", disabled=offset + 20 >= result["count"]):
                st.session_state.search_params = (query, offset + 20, filters, sort)
                st.rerun()
            if not result["results"]:
                st.info("Prueba otros términos o amplía los filtros.")
            selected = []
            for ds in result["results"]:
                title = ds.get("title", "Sin título")
                dataset_id = ds["id"]
                resources = compatible_resources(ds)
                with st.expander(title):
                    metadata_card(dataset_metadata(ds))
                    if not resources:
                        st.info("No se encontraron formatos tabulares compatibles en los dominios admitidos.")
                    chosen = st.multiselect("Recursos", range(len(resources)), key=f"sel_{dataset_id}",
                                            format_func=lambda i, rr=resources: f"{rr[i].get('name')} · {rr[i]['format']}")
                    if chosen:
                        ri = st.selectbox("Recurso para previsualizar", chosen, key=f"preview_pick_{dataset_id}",
                                          format_func=lambda i, rr=resources: rr[i].get("name") or rr[i]["format"])
                        actions = st.container(horizontal=True)
                        destination = None
                        for label, target in (("Explorar este dataset", "Estudio estadístico"),
                                              ("Analizar", "Estudio estadístico"),
                                              ("Combinar con otro dataset", "Preparar y combinar tablas")):
                            if actions.button(label, key=f"catalog_{label}_{dataset_id}"):
                                destination = target
                        detail = st.button("Previsualizar recurso", key=f"preview_{dataset_id}")
                        resource = resources[ri]
                        if detail or destination:
                            try:
                                with st.spinner("Leyendo y diagnosticando el recurso…"):
                                    existing_key = next((key for key, item in tables.items()
                                                         if item["sources"] == (resource["url"],) and not item["history"]),
                                                        None)
                                    if existing_key is None:
                                        df = download_table(resource)
                                        if df.empty:
                                            raise ValueError("El recurso no contiene filas.")
                                        existing_key = store(title, df, [resource["url"]],
                                                             metadata=dataset_metadata(ds, resource))
                                    item = tables[existing_key]
                                if destination:
                                    st.session_state.page = "Analizar"
                                    st.session_state.analysis_tool = destination
                                    st.session_state.studio_focus = existing_key
                                    st.session_state.workspace_table = existing_key
                                    st.session_state.join_left = existing_key
                                    st.session_state.studio_view = ("Análisis disponibles" if st.session_state.get(
                                        f"catalog_Analizar_{dataset_id}") else "Diagnóstico e informe")
                                    st.rerun()
                                preview(item["df"])
                                profile = get_profile(item)
                                st.caption(f"{profile['duplicates']} filas duplicadas · {profile['missing']} celdas ausentes")
                                st.dataframe(pd.DataFrame(profile["variables"]), hide_index=True)
                            except requests.RequestException:
                                st.error("El recurso no está disponible temporalmente.")
                            except (ValueError, TypeError, KeyError, OSError, BadZipFile) as exc:
                                st.error(f"No se pudo leer el recurso: {exc}")
                    selected.extend((ds, resources[i]) for i in chosen)
            if selected and st.button(f"Cargar selección ({len(selected)})", type="primary"):
                for ds, resource in selected:
                    title = ds.get("title", "Dataset")
                    if any(item["sources"] == (resource["url"],) and not item["history"] for item in tables.values()):
                        continue
                    try:
                        with st.spinner(f"Leyendo {title}…"):
                            df = download_table(resource)
                            if df.empty:
                                raise ValueError("El recurso no contiene filas.")
                            store(f"{title} · {resource.get('name') or resource['format']}", df, [resource["url"]],
                                  metadata=dataset_metadata(ds, resource))
                        st.success(f"{title} · {len(df):,} filas. Vista previa en Espacio de trabajo.")
                    except requests.RequestException:
                        st.error(f"{title}: recurso no disponible temporalmente o enlace inválido.")
                    except (ValueError, TypeError, KeyError, OSError, BadZipFile) as exc:
                        st.error(f"{title}: {exc}")
    with st.expander("Importar un fichero"):
        file = st.file_uploader("Datos de tu sesión", type=["csv", "tsv", "xlsx", "xls", "json"])
        if file and st.button("Importar tabla"):
            try:
                with st.spinner("Leyendo fichero…"):
                    df = read_table(file.getvalue(), file.name.rsplit(".", 1)[-1])
                    store(file.name, df, [f"Archivo de sesión: {file.name}"], metadata={"formato": file.name.rsplit(".", 1)[-1]})
                st.success("Tabla importada. Puedes revisarla en Espacio de trabajo.")
            except (ValueError, TypeError, KeyError, OSError, BadZipFile) as exc:
                st.error(f"No se pudo interpretar el fichero: {exc}")


def workspace():
    st.header("Espacio de trabajo")
    notice = st.session_state.pop("join_notice", None)
    if notice:
        level, message = notice
        if level == "success":
            st.success(message)
        else:
            st.error(message)
    if not tables:
        st.info("Carga una tabla desde Explorar para inspeccionar sus variables.")
        return
    key = table_picker("Tabla para inspeccionar", "workspace_table")
    item = tables[key]
    df = item["df"]
    preview(df)
    overview = describe_table(df)
    st.caption(f"{overview['duplicados']:,} filas duplicadas · {int(df.isna().sum().sum()):,} celdas vacías")
    with st.expander("Variables, fuentes e historial"):
        st.dataframe(pd.DataFrame(overview["variables"]), hide_index=True)
        st.json({k: item[k] for k in ("sources", "history")})
        downloads(df, {k: item[k] for k in ("sources", "history")}, "madrid-tabla")
    with st.expander("Limpiar y transformar"):
        if len(df.columns):
            operation = st.selectbox("Transformación", [
                "Convertir a número", "Convertir a fecha", "Normalizar categorías",
                "Normalizar nombres de columnas", "Quitar duplicados"])
            column = st.selectbox("Variable", df.columns, key=f"clean_{key}") if operation in {
                "Convertir a número", "Convertir a fecha", "Normalizar categorías"} else None
            comma = operation == "Convertir a número" and st.checkbox("Coma decimal y punto de miles")
            date_fmt = st.text_input("Formato de fecha", "%Y-%m-%d") if operation == "Convertir a fecha" else "%Y-%m-%d"
            if operation == "Normalizar categorías":
                st.dataframe(category_variants(df[column]).head(25), hide_index=True)
            if st.button("Previsualizar transformación"):
                try:
                    changed, affected = transform(df, operation, column, decimal_comma=comma, date_format=date_fmt)
                    preview(changed)
                    st.info(f"{affected:,} cambios de nombres, duplicados retirados o nuevos valores faltantes, según la operación.")
                except (ValueError, TypeError, KeyError) as exc:
                    st.error(str(exc))
            if st.checkbox("Confirmo la transformación", key=f"clean_confirm_{key}_{operation}_{column}") and st.button(
                "Guardar tabla transformada"
            ):
                try:
                    changed, affected = transform(df, operation, column, decimal_comma=comma, date_format=date_fmt)
                    step = {"operación": operation, "variable": column, "afectados": affected,
                            "coma_decimal": comma, "formato_fecha": date_fmt}
                    store(f"{item['title']} · limpia", changed, item["sources"], (*item["history"], step), True)
                    st.rerun()
                except (ValueError, TypeError, KeyError) as exc:
                    st.error(str(exc))
    with st.expander("Gestionar tablas"):
        if st.button("Retirar tabla seleccionada"):
            del tables[key]
            st.session_state.undo = [i for i in st.session_state.undo if i != key]
            st.rerun()
        if st.session_state.undo and st.button("Deshacer última transformación o unión"):
            del tables[st.session_state.undo.pop()]
            st.rerun()

    if len(tables) < 2:
        return
    st.subheader("Combinar tablas")
    a = table_picker("Tabla A", "join_left")
    b = table_picker("Tabla B", f"join_right_{a}", [i for i in tables if i != a])
    left, right = tables[a], tables[b]
    suggestions = suggest_keys(left["df"], right["df"])
    if suggestions:
        st.caption("Candidatas según el nombre de la variable. Verifica entidad, cobertura y periodo.")
        st.dataframe(pd.DataFrame(suggestions, columns=["Clave A", "Clave B", "Función"]), hide_index=True)
    x, y = st.columns(2)
    keys_a = x.multiselect("Claves A en orden", left["df"].columns, key=f"keys_a_{a}")
    keys_b = y.multiselect("Claves B en el mismo orden", right["df"].columns, key=f"keys_b_{b}")
    methods = {"inner": "Coincidencias", "left": "Conservar A", "right": "Conservar B", "outer": "Conservar ambas"}
    method = st.selectbox("Tipo de unión", list(methods), format_func=methods.get, key="join_method")
    signature = (a, b, keys_a, keys_b, method)
    if st.button("Previsualizar unión", type="primary"):
        st.session_state.join_checked = None
        try:
            merged, info = join_preview(left["df"], right["df"], keys_a, keys_b, method)
            st.session_state.join_checked = signature
        except ValueError as exc:
            st.error(str(exc))
    if st.session_state.get("join_checked") == signature:
        # Recompute on confirmation so the preview need not occupy persistent session memory.
        merged, info = join_preview(left["df"], right["df"], keys_a, keys_b, method)
        preview(merged)
        for warning in info["advertencias"]:
            st.warning(warning)
        st.json(info)
        approved = st.checkbox("He comprobado el territorio, periodo y cardinalidad", key=f"approval_{signature}")
        def confirm_join():
            try:
                result, diagnostics = join_preview(left["df"], right["df"], keys_a, keys_b, method)
                step = {"operación": "unión", "tipo": method, "A": a, "B": b, **diagnostics}
                store(f"Unión #{a} + #{b}", result, (*left["sources"], *right["sources"]),
                      (*left["history"], *right["history"], step), True)
                st.session_state.join_checked = None
                st.session_state.join_notice = ("success", "Unión guardada. Puedes usarla en el siguiente cruce.")
            except ValueError as exc:
                st.session_state.join_notice = ("error", str(exc))

        st.button("Guardar unión", disabled=not approved, on_click=confirm_join)


def map_panel(df, key):
    with st.expander("Mapa municipal con geometrías propias"):
        st.caption("Usa límites municipales de una fuente oficial en GeoJSON WGS84. "
                   "Los códigos deben coincidir exactamente con la tabla.")
        source = st.file_uploader("Geometrías municipales", type=["geojson", "json"], key=f"map_{key}")
        if source is None:
            return
        numeric = df.select_dtypes(include="number").columns.tolist()
        code = st.selectbox("Código municipal de la tabla", list(df), key=f"map_code_{key}")
        metric = st.selectbox("Indicador del mapa", [c for c in numeric if c != code], key=f"map_metric_{key}")
        prop = st.text_input("Propiedad del código en el GeoJSON", key=f"map_prop_{key}")
        attribution = st.text_input("Fuente de la cartografía", key=f"map_source_{key}")
        if metric is not None and prop and attribution and st.button("Mostrar mapa"):
            try:
                figure, matched, total = municipal_map(df, code, metric, source.getvalue(), prop)
                st.plotly_chart(figure)
                st.caption(f"{matched} de {total} códigos con geometría · Cartografía: {attribution}")
            except (TypeError, ValueError) as exc:
                st.error(str(exc))


def suggest_municipal_map(df, key, sources):
    for code in df.columns:
        if key_role(code) != "Código municipal":
            continue
        system = "Almudena" if normalized_name(code) == "codigo_territorio" else "INE"
        identifiers = df[code].map(lambda value, system=system: normalize_code(value, system) or normalize_code(value))
        if not identifiers.notna().any():
            continue
        numeric = [name for name in df.select_dtypes(include="number")
                   if name != code and key_role(name) not in {"Año", "Fecha", "Código municipal"}]
        if not numeric:
            return
        with st.expander("Ver el indicador en el mapa de Madrid"):
            if not st.checkbox("Mostrar mapa de la tabla", key=f"enable_territory_{key}"):
                return
            years = next((name for name in df if key_role(name) == "Año"), None)
            view = df
            if years:
                available = sorted(df[years].dropna().unique(), reverse=True)
                year = st.selectbox("Año", available, key=f"analysis_year_{key}")
                view = df[df[years] == year]
            metric = st.selectbox("Indicador", numeric, key=f"auto_metric_{key}")
            frame = pd.DataFrame({"INE": identifiers.loc[view.index], "Valor": view[metric]})
            if years:
                history = pd.DataFrame({"INE": identifiers, "Año": df[years], "Valor": df[metric]})
                if history.dropna(subset=["INE"]).duplicated(["INE", "Año"]).any():
                    history = None
                else:
                    from territories import official_codes
                    history["Municipio"] = history["INE"].map(lambda value: official_codes().get(value, ("", ""))[1])
            else:
                history = None
            source = next((link for link in sources if link.startswith("https://")), None)
            linked_map(frame, title=metric, unit="", key=f"advanced_{key}", history=history, source=source)
        return


def analysis_screen():
    st.header("Análisis")
    if not tables:
        st.info("Carga una tabla o combina varias fuentes para empezar.")
        return
    key = table_picker("Tabla para analizar", "analysis_table")
    item = tables[key]
    df = item["df"]
    if not len(df.columns):
        st.info("Esta tabla carece de variables.")
        return
    filter_column = st.selectbox("Variable de filtro", [None, *df.columns],
                                 format_func=lambda c: "Sin filtro" if c is None else c, key=f"filter_{key}")
    filters = {}
    if filter_column is not None:
        distinct = df[filter_column].dropna().drop_duplicates().head(500).tolist()
        values = st.multiselect("Valores a conservar · hasta 500 opciones", distinct,
                                key=f"values_{key}_{filter_column}")
        if values:
            filters[filter_column] = values
            df = df[df[filter_column].isin(values)]
    suggest_municipal_map(df, key, item["sources"])
    map_panel(df, key)
    api_key, model, base_url = ai_settings(st.secrets)
    mode = st.radio("Modo", ["Manual", "Pregunta en lenguaje natural"], horizontal=True, key="analysis_mode")
    plan = None
    if mode == "Manual":
        operation = st.selectbox("Operación", list(OPERATIONS), format_func=OPERATIONS.get, key="analysis_operation")
        numeric = df.select_dtypes(include="number").columns.tolist()
        xs = numeric if operation in NEEDS_NUMERIC_X else list(df)
        x = st.selectbox("Primera variable", xs, key=f"x_{key}_{operation}")
        y = st.selectbox("Variable numérica", [n for n in numeric if n != x],
                         key=f"y_{key}_{operation}") if operation in NEEDS_Y else None
        if x is not None and (y is not None or operation not in NEEDS_Y):
            plan = {"operation": operation, "x": x, "y": y}
        else:
            st.info("Esta operación necesita más variables numéricas. Puedes convertirlas en Espacio de trabajo.")
    elif not api_key:
        st.info("El asistente requiere una clave configurada en el servidor. El modo manual incluye las mismas operaciones.")
    else:
        st.caption("El proveedor recibe la pregunta y hasta 100 nombres de variables. Los cálculos se ejecutan en la aplicación.")
        question = st.text_input("Pregunta", max_chars=1500, key=f"question_{key}")
        if st.button("Interpretar pregunta", type="primary", disabled=not question.strip()):
            from openai import OpenAI, OpenAIError

            st.session_state.pop("ai_plan", None)
            try:
                with st.spinner("Preparando análisis…"):
                    planner = OpenAI(api_key=api_key, base_url=base_url or None, timeout=20, max_retries=1)
                    st.session_state.ai_plan = (key, question, plan_analysis(planner, model, question, df))
            except ValueError as exc:
                st.error(str(exc) if exc.args else "El proveedor devolvió un plan inválido.")
            except OpenAIError:
                st.error("No se pudo consultar al proveedor de IA. Comprueba la configuración del servidor.")
        stored = st.session_state.get("ai_plan")
        if stored and stored[:2] == (key, question):
            plan = stored[2]

    if plan:
        try:
            result, figure, notes = analyze(df, plan)
        except ValueError as exc:
            st.info(str(exc))
            return
        st.subheader(OPERATIONS[plan["operation"]])
        if figure is not None:
            st.plotly_chart(figure)
            export_chart(figure, f"advanced_{key}")
        st.dataframe(result.head(500), hide_index=True)
        for note in notes:
            st.caption(note)
        metadata = {"sources": item["sources"], "transformaciones": item["history"],
                    "filtros": filters, "plan": plan, "metodología": notes}
        with st.expander("Fuentes y metodología"):
            st.json(metadata)
        downloads(result, metadata, "madrid-analisis")


page = navigation()
if page == "Explorar":
    question_screen(store)
elif page == "Mapa":
    full_map()
elif page == "Catálogo":
    explorer()
else:
    tool = st.radio("Herramientas de análisis", ["Estudio estadístico", "Resultados y gráficos", "Preparar y combinar tablas"],
                    horizontal=True, key="analysis_tool")
    if tool == "Preparar y combinar tablas":
        workspace()
    elif tool == "Resultados y gráficos":
        analysis_screen()
    else:
        studio(tables, store)
