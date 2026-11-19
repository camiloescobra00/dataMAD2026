import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from demos import DEMO_NAMES, demo_table


@pytest.mark.parametrize("demo,rows", list(zip(DEMO_NAMES, [179, 1432, 179])))
def test_official_demo(demo, rows):
    df, _ = demo_table(demo)
    assert len(df) == rows
    assert df["Código territorio"].str.startswith("00").any()
    assert not df.duplicated(["Código territorio", "Año"]).any()


def test_ui_combine_three_and_analyze():
    app = AppTest.from_file("app.py", default_timeout=20).run()
    assert not app.exception
    for idx in range(1, 4):
        app.session_state.tables[idx] = {
            "title": f"Tabla {idx}", "df": pd.DataFrame({"municipio": ["001", "002"], "valor": [idx, idx + 1]}),
            "sources": (f"Fuente {idx}",), "history": (),
        }
    app.session_state.serial = 3
    app.button(key="nav_Analizar").click().run()
    app.radio(key="analysis_tool").set_value("Preparar y combinar tablas").run()

    def click(label):
        next(widget for widget in app.button if widget.label == label).click().run()
        assert not app.exception

    for left, right in [(1, 2), (4, 3)]:
        app.selectbox(key="join_left").set_value(left).run()
        app.selectbox(key=f"join_right_{left}").set_value(right).run()
        app.multiselect(key=f"keys_a_{left}").set_value(["municipio"])
        app.multiselect(key=f"keys_b_{right}").set_value(["municipio"]).run()
        click("Previsualizar unión")
        assert next(w for w in app.button if w.label == "Guardar unión").disabled
        next(w for w in app.checkbox if w.label.startswith("He comprobado")).set_value(True).run()
        click("Guardar unión")
    result = app.session_state.tables[5]
    assert len(result["history"]) == 2
    assert len(result["sources"]) == 3
    assert result["df"].columns.tolist() == ["municipio", "valor", "valor_B", "valor_B_2"]
    app.button(key="nav_Analizar").click().run()
    app.radio(key="analysis_tool").set_value("Resultados y gráficos").run()
    app.selectbox(key="analysis_table").set_value(5).run()
    assert not app.exception
    assert app.dataframe[0].value.shape[0] > 2
    assert len(app.get("download_button")) == 2
    app.button(key="nav_Analizar").click().run()
    app.radio(key="analysis_tool").set_value("Preparar y combinar tablas").run()
    click("Deshacer última transformación o unión")
    assert 5 not in app.session_state.tables


@pytest.mark.parametrize("demo", DEMO_NAMES)
def test_ui_demo(demo):
    app = AppTest.from_file("app.py", default_timeout=20).run()
    app.selectbox[0].set_value(demo).run()
    app.checkbox[0].set_value(True).run()
    assert not app.exception
    assert app.get("plotly_chart")


def test_ui_catalog_selection(monkeypatch):
    import catalog

    resources = [{"id": str(i), "url": f"https://datos.comunidad.madrid/{i}.csv",
                  "format": "CSV", "name": f"Recurso {i}"} for i in range(2)]
    datasets = [{"id": f"fixture-{i}", "name": f"tabla-{i}", "title": f"Tabla {i}",
                 "resources": [resource]} for i, resource in enumerate(resources)]
    monkeypatch.setattr(catalog, "catalog_page",
                        lambda *args, **kwargs: {"count": 2, "results": datasets})
    monkeypatch.setattr(catalog, "download_table", lambda _: pd.DataFrame({"x": [1]}))
    app = AppTest.from_file("app.py", default_timeout=20).run()
    app.button(key="nav_Catálogo").click().run()
    app.text_input(key="explorer_query").set_value("datos de prueba")
    next(w for w in app.button if w.label == "Buscar datasets").click().run()
    assert app.session_state.page == "Catálogo"
    app.multiselect(key="sel_fixture-0").set_value([0])
    app.multiselect(key="sel_fixture-1").set_value([0]).run()
    next(w for w in app.button if w.label == "Cargar selección (2)").click().run()
    assert not app.exception
    assert len(app.session_state.tables) == 2


def test_ui_ai_plan_runs_local_analysis(monkeypatch):
    from types import SimpleNamespace

    import openai

    monkeypatch.setenv("OPENAI_API_KEY", "test")
    reply = SimpleNamespace(output_text='{"operation":"ranking","x":"v1","y":"v2"}')
    monkeypatch.setattr(openai, "OpenAI", lambda **_: SimpleNamespace(
        responses=SimpleNamespace(create=lambda **_: reply)))
    app = AppTest.from_file("app.py", default_timeout=20).run()
    app.session_state.tables[1] = {
        "title": "Indicador", "df": pd.DataFrame({"municipio": ["A", "B"], "renta": [1, 3]}),
        "sources": ("Fuente de prueba",), "history": (),
    }
    app.button(key="nav_Analizar").click().run()
    app.radio(key="analysis_tool").set_value("Resultados y gráficos").run()
    next(w for w in app.radio if w.label == "Modo").set_value("Pregunta en lenguaje natural").run()
    app.text_input(key="question_1").set_value("¿Qué municipio tiene mayor renta?").run()
    next(w for w in app.button if w.label == "Interpretar pregunta").click().run()
    assert not app.exception
    result = app.dataframe[0].value
    assert result["Grupo"].tolist() == ["B", "A"]
    assert result["Media"].tolist() == [3, 1]


def test_advanced_filters_survive_navigation():
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.session_state.tables[1] = {
        "title": "Datos", "df": pd.DataFrame({"grupo": ["A", "B"], "valor": [1, 3]}),
        "sources": ("Fuente",), "history": (),
    }
    app.button(key="nav_Analizar").click().run()
    app.radio(key="analysis_tool").set_value("Resultados y gráficos").run()
    app.selectbox(key="filter_1").set_value("grupo").run()
    app.multiselect(key="values_1_grupo").set_value(["B"]).run()
    app.button(key="nav_Explorar").click().run()
    app.button(key="nav_Analizar").click().run()
    assert not app.exception
    assert app.selectbox(key="filter_1").value == "grupo"
    assert app.multiselect(key="values_1_grupo").value == ["B"]
