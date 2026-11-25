"""Question-first interface and verified municipal reports."""
from urllib.parse import quote

import plotly.express as px
import streamlit as st

from analytics import analyze
from catalog import compatible_resources, download_table
from data_tables import csv_export
from dataset_cards import dataset_metadata
from discovery import coverage, fold, interpret, mentions, retrieve
from interface import correlation_sentence, metric_cards, navigate, report_chart
from map_view import SELECTION, export_chart, linked_map, remembered_choice, value_text
from territories import (
    AGE,
    EXAMPLES,
    INDICATORS,
    RENT,
    analysis_window,
    growth,
    official_codes,
    prepared_series,
    question_plan,
    regional,
    source_metadata,
    verified_relationship,
)


@st.cache_data(ttl=600, max_entries=32, show_spinner=False)
def candidates(query):
    return retrieve(query)


def municipality_mentions(question):
    names = official_codes()
    text = fold(question)
    found = []
    for code, (_, name) in names.items():
        alias = name
        if " (" in name and name.endswith(")"):
            name_part, article = name[:-1].rsplit(" (", 1)
            alias = f"{article} {name_part}"
        if name != "Madrid" and (mentions(alias, text) or mentions(name, text)):
            found.append(code)
    if mentions("madrid capital", text) or mentions("municipio de madrid", text):
        found.extend(code for code, (_, name) in names.items() if name == "Madrid")
    return found


def submit_question(question, live=True):
    if not question.strip():
        st.session_state.pop("question", None)
        st.session_state.question_input = ""
        return
    st.session_state.question_id = st.session_state.get("question_id", 0) + 1
    st.session_state.question = question.strip()
    st.session_state.question_input = question.strip()
    st.session_state.question_live = live
    st.session_state[SELECTION] = municipality_mentions(question)


def official_reference(indicator, year):
    df = regional()
    values = df.loc[(df["Fuente"] == indicator) & (df["Año"] == year), "Valor"]
    return values.iat[0] if not values.empty else None


def full_map():
    st.header("Madrid, municipio a municipio")
    st.write("Elige un indicador y pulsa un municipio para consultar su valor y compararlo.")
    source = remembered_choice(st.selectbox, "Indicador", list(INDICATORS), "map_indicator",
                               format_func=lambda value: INDICATORS[value][0])
    frame = prepared_series(source)
    years = sorted(frame["Año"].unique(), reverse=True)
    year = remembered_choice(st.selectbox, "Año", years, f"map_year_{source}")
    title, unit, notes = INDICATORS[source]
    st.caption(notes)
    linked_map(frame[frame["Año"] == year], title=f"{title} · {year}", unit=unit, key="territory",
               history=frame, reference=official_reference(source, year), source=source_metadata()[source]["url"])


def render_sources(sources):
    metadata = source_metadata()
    with st.expander("Fuentes y criterios"):
        for source in sources:
            row = metadata[source]
            st.link_button(row["title"], row["url"])
            st.caption(f"Comunidad de Madrid · {row['license'] or 'Consulta la licencia en la fuente'}")


def view_choice(options, default, key):
    saved = f"view_{key}"
    current = st.session_state.get(saved, default)
    icons = {"Mapa": "map", "Ranking": "bar_chart", "Resumen": "analytics", "Tabla": "table_chart",
             "Evolución": "show_chart", "Dispersión": "scatter_plot",
             "Mapa de envejecimiento": "map", "Mapa de renta": "map"}

    def select(view):
        st.session_state[saved] = view

    with st.container(horizontal=True, gap="small"):
        for view in options:
            st.button(view, icon=f":material/{icons[view]}:", type="primary" if view == current else "secondary",
                      key=f"{key}_{view}", on_click=select, args=(view,))
    return current


def municipality_filter(prefix):
    codes = official_codes()
    key = f"report_municipios_{prefix}"

    def remember():
        st.session_state[SELECTION] = st.session_state[key]

    selection = st.session_state.get(SELECTION, [])
    st.session_state[key] = selection[:6]
    return st.multiselect("Municipios", sorted(codes, key=lambda code: codes[code][1]),
                          format_func=lambda code: codes[code][1], max_selections=6,
                          placeholder="Buscar y comparar municipios", on_change=remember, key=key)


def relationship_report(prefix):
    frame, diagnostics = verified_relationship()
    x, y = list(frame.columns[3:])
    result, _, notes = analyze(frame, {"operation": "correlation", "x": x, "y": y})
    coefficient = result["Pearson r"].iat[0]
    st.header("Renta y envejecimiento municipal")
    st.write(correlation_sentence(coefficient))
    metric_cards([
        ("Correlación de Pearson", value_text(coefficient, "", decimals=3),
         "Mide la asociación lineal entre dos variables y toma valores entre −1 y 1."),
        ("Municipios comparados", len(frame), "Municipios con datos en ambas fuentes. Cada municipio pesa lo mismo."),
        ("Año de referencia", "2024", "Año común de los indicadores."),
    ])
    view = view_choice(["Dispersión", "Mapa de envejecimiento", "Mapa de renta", "Tabla"],
                       "Dispersión", f"relationship_{prefix}")
    visual = st.container()
    plot = None
    if view == "Dispersión":
        with st.popover("Filtrar municipios"):
            selected = municipality_filter(f"pair_{prefix}")
        plot = px.scatter(frame, x=x, y=y, hover_name="Territorio", title="Renta por habitante frente a población de 65 años y más",
                          color_discrete_sequence=["#49D5B3"])
        highlighted = frame[frame["Código territorio"].isin([official_codes()[code][0] for code in selected])]
        if not highlighted.empty:
            plot.add_scatter(x=highlighted[x], y=highlighted[y], text=highlighted["Territorio"],
                             mode="markers+text", textposition="top center", name="Municipios seleccionados",
                             marker={"size": 11, "color": "#ab4522"})
    elif view == "Tabla":
        visual.dataframe(frame, hide_index=True)
    else:
        indicator = AGE if view == "Mapa de envejecimiento" else RENT
        title, unit, _ = INDICATORS[indicator]
        with visual:
            linked_map(prepared_series(indicator), title=title, unit=unit, key=f"relation_{prefix}",
                       reference=official_reference(indicator, 2024), source=source_metadata()[indicator]["url"])
    if plot is not None:
        visual.plotly_chart(report_chart(plot))
    with st.expander("Metodología y descargas"):
        st.caption("Cruce por código municipal y año. Se usaron únicamente pares completos.")
        for note in notes:
            st.caption(note)
        st.json(diagnostics)
        st.download_button("Descargar tabla (CSV)", csv_export(frame), file_name="madrid-resultados.csv",
                           mime="text/csv", key=f"report_csv_{prefix}")
        if plot is not None:
            export_chart(plot, f"relationship_{prefix}")


def trend_summary(frame, start, end, unit):
    endpoints = frame.pivot(index="Municipio", columns="Año", values="Valor")
    if start not in endpoints or end not in endpoints:
        return [], "La serie muestra los años con datos disponibles."
    complete = endpoints[[start, end]].dropna()
    if complete.empty:
        return [], "Los extremos del periodo carecen de observaciones comparables."
    cards = []
    changes = []
    for name, first, last in complete.itertuples():
        delta = last - first
        direction = "aumentó" if delta > 0 else "descendió" if delta < 0 else "se mantuvo"
        changes.append(f"{name} {direction}" + (f" en {value_text(abs(delta), unit)}" if delta else ""))
        if len(complete) == 1:
            cards.extend([
                (str(start), value_text(first, unit), "Valor al inicio del periodo."),
                (str(end), value_text(last, unit), "Valor al final del periodo."),
            ])
            if first > 0:
                cards.append(("Variación", value_text(100 * delta / first, "%"), "Cambio respecto al primer año."))
    return cards, f"Entre {start} y {end}, " + ", ".join(changes) + "."


def indicator_report(query, intent, indicator, prefix):
    title, unit, note = INDICATORS[indicator]
    full = prepared_series(indicator)
    window = analysis_window(full, query)
    if window.empty or (intent in {"evolución", "crecimiento"} and window["Año"].nunique() < 2):
        st.warning(f"El extracto verificado cubre {full['Año'].min()}–{full['Año'].max()}. "
                   "Consulta el catálogo para buscar el periodo solicitado.")
        return
    years = sorted(window["Año"].unique(), reverse=True)
    start, end = years[-1], years[0]
    is_growth = intent == "crecimiento"
    if is_growth:
        title, unit = "Crecimiento de población", "%"
        note = "Variación porcentual entre los extremos del periodo. El ranking requiere datos de ambos años."
    st.header(title)
    main = st.container()
    filters = st.container(horizontal=True, gap="small")
    with filters:
        if len(years) > 1 and intent not in {"crecimiento", "evolución"}:
            year = remembered_choice(st.selectbox, "Año de referencia", years, f"result_year_{prefix}")
        else:
            year = end
    reference = official_reference(indicator, year)
    if is_growth:
        frame = growth(window, (start, end))
        initial = official_reference(indicator, start)
        reference = 100 * (reference / initial - 1) if initial and reference is not None else None
        history = None
    else:
        frame = window[window["Año"] == year].copy()
        history = window
    mode_list = ["Mapa", "Ranking", "Resumen", "Tabla"]
    if history is not None and len(years) > 1:
        mode_list.append("Evolución")
    default = {"evolución": "Evolución", "comparación": "Ranking", "resumen": "Resumen"}.get(intent, "Mapa")
    with main:
        headline = st.container()
        view = view_choice(mode_list, default, f"result_view_{prefix}")
        visual = st.container()
    if view != "Mapa":
        with filters, st.popover("Filtrar municipios"):
            selected = municipality_filter(prefix)
    else:
        selected = st.session_state.get(SELECTION, [])
    plot = None
    if view == "Evolución":
        region = regional()
        region = region[(region["Fuente"] == indicator) & region["Año"].isin(years)]
        region = region.assign(Municipio="Comunidad de Madrid")
        frame = (history[history["INE"].isin(selected)].sort_values("Año") if selected
                 else region[["Año", "Municipio", "Valor"]])
        cards, answer = trend_summary(frame, start, end, unit)
        plot = px.line(frame, x="Año", y="Valor", color="Municipio", markers=True,
                       labels={"Valor": f"{title} ({unit})"}, title=f"{title} · {start}–{end}")
    else:
        selected_frame = frame[frame["INE"].isin(selected)] if selected else frame
        ranked = selected_frame.dropna(subset=["Valor"]).nlargest(15, "Valor")
        values = selected_frame["Valor"].dropna()
        period = f"{start}–{end}" if is_growth else str(year)
        cards = [
            ("Municipios con datos", len(values), "Municipios con valor del indicador en la selección."),
            ("Periodo", period, "Fecha o intervalo de referencia del indicador."),
        ]
        if not values.empty:
            cards.insert(0, ("Mediana municipal", value_text(values.median(), unit),
                             "Valor que divide los municipios con datos en dos mitades de igual tamaño."))
        if ranked.empty:
            answer = f"La selección no contiene valores disponibles para {period}."
        else:
            best = ranked.iloc[0]
            scope = "de la selección" if selected else "entre los municipios con datos"
            answer = f"En {period}, {best['Municipio']} registra el valor más alto {scope}, con {value_text(best['Valor'], unit)}."
        if view == "Mapa":
            with visual:
                linked_map(frame, title=f"{title} · {period}", unit=unit, key=f"result_{prefix}", history=history,
                           reference=reference, source=source_metadata()[indicator]["url"])
        else:
            frame = selected_frame
            if view == "Ranking":
                plot = px.bar(ranked.sort_values("Valor"), x="Valor", y="Municipio", orientation="h",
                              labels={"Valor": f"{title} ({unit})"}, title="Hasta 15 municipios con los valores más altos",
                              color_discrete_sequence=["#49D5B3"])
            elif view == "Resumen":
                plot = px.histogram(frame, x="Valor", labels={"Valor": f"{title} ({unit})"},
                                    title="Distribución municipal", color_discrete_sequence=["#49D5B3"])
            else:
                visual.dataframe(frame, hide_index=True)
    with headline:
        st.write(answer)
        if cards:
            metric_cards(cards)
    if plot is not None:
        visual.plotly_chart(report_chart(plot))
    with st.expander("Metodología y descargas"):
        st.caption(f"{note} Periodo disponible para la consulta: {start}–{end}.")
        if reference is not None:
            st.caption(f"Comunidad de Madrid (dato oficial): {value_text(reference, unit)}.")
        if view != "Mapa":
            st.download_button("Descargar tabla (CSV)", csv_export(frame), file_name="madrid-resultados.csv",
                               mime="text/csv", key=f"report_csv_{prefix}")
        if plot is not None:
            export_chart(plot, f"indicator_{prefix}")


def render_report(query, plan, prefix):
    intent, sources = plan
    if intent == "relación":
        relationship_report(prefix)
    else:
        indicator_report(query, intent, sources[0], prefix)
    render_sources(sources)


def render_candidates(query, store):
    with st.spinner("Buscando coincidencias en el catálogo oficial…"):
        rows, failed = candidates(query)
    st.subheader("Fuentes del catálogo relacionadas")
    if failed:
        st.info("Alguna consulta al catálogo tardó demasiado. Se muestran las coincidencias recuperadas.")
    if not rows:
        st.caption("Prueba con un indicador concreto, como «paro registrado» o «centros de salud».")
    for _, ds, reasons in rows:
        identifier = ds.get("id") or ds["name"]
        with st.container(border=True):
            st.markdown("**" + str(ds.get("title") or "Conjunto de datos") + "**")
            notes = str(ds.get("notes") or "").split()
            if notes:
                st.text(" ".join(notes[:42]) + ("…" if len(notes) > 42 else ""))
            geo, time = coverage(ds)
            organization = (ds.get("organization") or {}).get("title") or "Organismo sin indicar"
            date = str(ds.get("metadata_modified") or "")[:10] or "sin indicar"
            st.caption(f"{organization} · Metadatos: {date} · Cobertura: {geo or 'sin indicar'} · "
                       f"Periodo: {time or 'sin indicar'}")
            if reasons:
                st.caption(" · ".join(reasons))
            st.link_button("Consultar ficha oficial", "https://datos.comunidad.madrid/dataset/" + quote(
                str(ds.get("name") or identifier), safe=""))
            resources = compatible_resources(ds)
            if resources:
                with st.expander("Usar en un análisis"):
                    index = st.selectbox("Recurso", range(len(resources)), key=f"intelligent_{identifier}",
                                         format_func=lambda i, r=resources: f"{r[i].get('name')} · {r[i]['format']}")
                    if st.button("Añadir a Analizar", key=f"add_{identifier}"):
                        from requests import RequestException

                        try:
                            with st.spinner("Cargando el recurso oficial…"):
                                resource = resources[index]
                                df = download_table(resource)
                                if df.empty:
                                    raise ValueError("El recurso está vacío.")
                                store(ds["title"], df, [resource["url"]], metadata=dataset_metadata(ds, resource))
                            st.success("Tabla guardada. Ábrela en Analizar.")
                        except (ValueError, OSError, TypeError, KeyError, RequestException):
                            st.error("El recurso no se pudo cargar. Consulta la ficha o elige otro formato.")


TOPIC_CARDS = (
    ("Población", "groups", "¿Cómo ha evolucionado la población empadronada en Madrid?"),
    ("Economía", "payments", "¿Qué municipios tienen mayor renta por habitante?"),
    ("Empleo", "work", "¿Cómo ha evolucionado el desempleo?"),
    ("Salud", "health_and_safety", "¿Dónde hay más centros de atención primaria por habitante?"),
    ("Educación", "school", "Nivel educativo y estudios por municipio"),
    ("Vivienda", "home", "Vivienda, alquiler y precio por municipio"),
    ("Transporte", "directions_bus", "Transporte público, autobuses y movilidad en Madrid"),
)


def example_buttons():
    st.subheader("Preguntas para explorar")
    with st.container(horizontal=True, gap="small"):
        for index, prompt in enumerate(EXAMPLES):
            st.button(prompt, icon=":material/arrow_outward:", key=f"example_{index}", on_click=submit_question,
                      args=(prompt, False), type="tertiary")


def question_screen(store):
    question = st.session_state.get("question", "")
    if not question:
        st.html("""
        <section class="mde-hero">
          <h1>¿Qué quieres saber sobre Madrid?</h1>
          <p>Explora los datos oficiales de Madrid con mapas, gráficos y respuestas que puedes comprobar.</p>
        </section>
        """)
    st.session_state.question_input = question
    with (
        st.container(horizontal=True, horizontal_alignment="center"),
        st.form("question_form", border=True, width=820),
        st.container(horizontal=True, vertical_alignment="bottom", gap="small"),
    ):
        st.text_input("Tu pregunta" if question else "Pregunta sobre Madrid",
                      placeholder="¿Qué municipios han crecido más en población?",
                      key="question_input", label_visibility="visible" if question else "collapsed",
                      max_chars=350)

        def on_submit():
            submit_question(st.session_state.question_input)

        st.form_submit_button("Actualizar" if question else "Buscar respuesta", type="primary",
                              icon=":material/search:", on_click=on_submit)

    if not question:
        st.subheader("Explora por tema")
        with st.container(horizontal=True, gap="small", key="mde_topics"):
            for label, icon, prompt in TOPIC_CARDS:
                st.button(label, icon=f":material/{icon}:", width=171, key=f"topic_{label}",
                          on_click=submit_question, args=(prompt,))
        example_buttons()
        with st.container(horizontal=True, gap="small"):
            st.button("Explorar el mapa", icon=":material/map:", on_click=navigate, args=("Mapa",))
            st.button("Abrir catálogo oficial", icon=":material/folder_open:", on_click=navigate, args=("Catálogo",))
        with st.expander("Más demostraciones"):
            from demos import show_demos

            show_demos(store)
        return

    names = [name for _, name in official_codes().values()]
    query = interpret(question, names)
    prefix = str(st.session_state.get("question_id", 0))
    plan = question_plan(query, municipality_mentions(question))
    if plan:
        render_report(query, plan, prefix)
    else:
        st.header("Fuentes para responder tu pregunta")
        st.info("Consulta las fuentes candidatas. Para cruzarlas en Analizar, comprueba primero sus claves y periodos.")
    if st.session_state.get("question_live"):
        render_candidates(query, store)
    elif st.button("Buscar fuentes adicionales en el catálogo"):
        st.session_state.question_live = True
        st.rerun()
    with st.expander("Explorar otra pregunta"):
        example_buttons()
        st.button("Volver al inicio de Explorar", on_click=submit_question, args=("",), type="tertiary")
