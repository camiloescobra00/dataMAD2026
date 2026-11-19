import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from discovery import interpret, retrieve
from explore_view import municipality_mentions
from map_view import (
    MISSING,
    PALETTES,
    SELECTION,
    apply_click,
    build_map,
    classify,
    clicked_code,
    map_features,
)
from territories import (
    EXAMPLES,
    POP,
    analysis_window,
    boundaries,
    growth,
    normalize_code,
    official_codes,
    prepared_series,
    question_plan,
)


def test_interpret_geography_synonyms_and_time():
    query = interpret("¿Cómo ha cambiado el desempleo en Getafe entre 2018 y 2025?", ["Getafe"])
    assert (query.topics, query.geography, query.years, query.intent) == (("paro",), "Getafe", (2018, 2025), "evolución")
    assert municipality_mentions("Getafe, Madrid capital y El Álamo") == ["28004", "28065", "28079"]
    assert interpret("Población en los últimos diez años").recent == 10
    assert question_plan(interpret("Tasa de desempleo de Madrid")) is None
    assert question_plan(interpret("Renta de los barrios de Madrid")) is None


def test_candidate_ranking_explains_and_deduplicates():
    high = {"name": "age", "title": "Grado de envejecimiento. Municipios", "notes": ""}
    low = {"name": "other", "title": "Censo electoral", "notes": "envejecimiento"}
    def fetch(term, rows):
        assert rows == 15
        return {"results": [low, high]}
    query = interpret("¿Dónde vive la población más envejecida?")
    results, failed = retrieve(query, fetch)
    assert not failed
    assert [row[1]["name"] for row in results] == ["age", "other"]
    assert "Cobertura municipal indicada" in results[0][2]


def test_cartography_correspondence_and_missing():
    assert len(official_codes()) == 179
    assert {row["id"] for row in boundaries()["features"]} == set(official_codes())
    assert normalize_code("0650", "Almudena") == "28065"
    assert normalize_code("0658", "Almudena") is None
    assert normalize_code("28065") == "28065"
    frame = pd.DataFrame({"INE": ["28065", "28079"], "Valor": [10, float("nan")]})
    features, bins = map_features(frame, "%", "Cuantiles", PALETTES["Azul"])
    props = {f["id"]: f["properties"] for f in features["features"]}
    assert props["28065"]["value"] == "10 %"
    assert props["28079"]["color"] == MISSING and props["28001"]["color"] == MISSING
    document = build_map(features, bins, PALETTES["Azul"], "%").get_root().render()
    assert r"C\u00f3digo INE" in document and "Sin datos" in document
    with pytest.raises(ValueError, match="una fila"):
        map_features(pd.concat([frame, frame]), "%", "Cuantiles", PALETTES["Azul"])


def test_click_and_selected_municipalities():
    code = clicked_code({"last_object_clicked_tooltip": "Municipio Getafe\nCódigo INE28065"})
    assert code == "28065"
    assert apply_click(["28079"], code) == ["28079", "28065"]
    assert apply_click(["28065"], code) == ["28065"]
    assert clicked_code({"last_object_clicked_tooltip": "No municipal 28999"}) is None


def test_population_window_and_growth():
    query = interpret("¿Qué municipios han crecido más en población entre 2015 y 2025?")
    assert question_plan(query) == ("crecimiento", (POP,))
    frame = prepared_series(POP)
    series = analysis_window(frame, query)
    assert (series["Año"].min(), series["Año"].max()) == (2015, 2025)
    growth_table = growth(series, (2015, 2025))
    assert len(growth_table) == 179
    getafe = frame[frame["INE"] == "28065"].set_index("Año")["Valor"]
    value = growth_table.loc[growth_table["INE"] == "28065", "Valor"].iat[0]
    assert value == pytest.approx(100 * (getafe[2025] / getafe[2015] - 1))


@pytest.mark.parametrize("index", range(len(EXAMPLES)))
def test_example_route_and_exports(index, monkeypatch):
    monkeypatch.setattr("map_view.st_folium", lambda *args, **kwargs: {})
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.button(key=f"example_{index}").click().run()
    assert not app.exception
    assert app.session_state.question == EXAMPLES[index]
    assert app.get("download_button")
    assert app.get("plotly_chart") or index in {0, 1, 3}


def test_map_click_and_question_survive_navigation(monkeypatch):
    event = {"last_object_clicked_tooltip": "Municipio Getafe / Código INE 28065",
             "last_object_clicked": {"lat": 40.3, "lng": -3.7}}
    monkeypatch.setattr("map_view.st_folium", lambda *args, **kwargs: event)
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.button(key="example_2").click().run()
    app.button(key="nav_Mapa").click().run()
    assert not app.exception
    assert app.session_state[SELECTION] == ["28065"]
    assert "Getafe" in app.dataframe[0].value["Municipio"].tolist()
    app.button(key="nav_Explorar").click().run()
    assert app.session_state.question == EXAMPLES[2]
    assert not app.exception
    assert app.get("plotly_chart")


def test_live_question_fallback_uses_ranked_cards(monkeypatch):
    fixture = {"name": "educacion", "title": "Nivel educativo municipal", "notes": "Estudios por municipio."}
    monkeypatch.setattr("explore_view.candidates", lambda _: ([(12, fixture, ["Tema: educación"])], False))
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.text_input(key="question_input").set_value("Quiero comparar desempleo y nivel educativo")
    next(w for w in app.button if w.label == "Buscar respuesta").click().run()
    assert not app.exception
    assert any("Nivel educativo municipal" in node.value for node in app.markdown)
    assert any("fuentes candidatas" in node.value for node in app.info)


def test_map_indicator_year_survive_navigation(monkeypatch):
    monkeypatch.setattr("map_view.st_folium", lambda *args, **kwargs: {})
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.button(key="nav_Mapa").click().run()
    app.selectbox(key="map_indicator").set_value(POP).run()
    app.selectbox(key=f"map_year_{POP}").set_value(2019).run()
    app.button(key="nav_Explorar").click().run()
    app.button(key="nav_Mapa").click().run()
    assert not app.exception
    assert app.selectbox(key="map_indicator").value == POP
    assert app.selectbox(key=f"map_year_{POP}").value == 2019


def test_comparison_search_surfaces_both_indicators():
    jobs = {"name": "paro", "title": "Paro registrado. Municipios"}
    school = {"name": "estudios", "title": "Población por nivel educativo. Municipios"}
    unrelated = {"name": "certificados", "title": "Nivel educativo y titulaciones"}
    query = interpret("Comparar desempleo y nivel educativo")
    results, _ = retrieve(query, lambda term, rows: {"results": [school, unrelated, jobs]})
    assert [r[1]["name"] for r in results[:2]] == ["paro", "estudios"]


def test_real_map_component_mounts():
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.button(key="nav_Mapa").click().run()
    assert not app.exception
    assert app.get("component_instance")
    assert any("179 de 179" in message.value for message in app.caption)


def test_jenks_separates_natural_clusters_and_keeps_ties():
    values = pd.Series([1, 1, 2, 80, 80, 81, 1000, 1001])
    assert classify(values, "Cortes naturales (Jenks)", count=3) == [1, 2, 81, 1001]


def test_topic_card_starts_search_and_navigation_keeps_question(monkeypatch):
    monkeypatch.setattr("explore_view.candidates", lambda _: ([], False))
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.button(key="topic_Vivienda").click().run()
    assert not app.exception
    assert "alquiler" in app.session_state.question
    app.button(key="nav_Catálogo").click().run()
    assert app.button(key="nav_Catálogo").proto.type == "primary"
    app.button(key="nav_Explorar").click().run()
    assert app.text_input(key="question_input").value == app.session_state.question


def test_relationship_interpretation_and_metric_cards():
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.button(key="example_4").click().run()
    assert not app.exception
    assert any("negativa muy débil" in node.value for node in app.markdown)
    metrics = {node.label: node.value for node in app.metric}
    assert metrics == {"Correlación de Pearson": "-0,109", "Municipios comparados": "179", "Año de referencia": "2024"}
    assert app.button(key="relationship_1_Dispersión").proto.type == "primary"
    app.button(key="relationship_1_Tabla").click().run()
    assert not app.exception
    assert app.button(key="relationship_1_Tabla").proto.type == "primary"
    assert len(app.dataframe[0].value) == 179
