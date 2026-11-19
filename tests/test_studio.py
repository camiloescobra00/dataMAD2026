import numpy as np
import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from map_view import synced_view
from profiling import corrected, schema
from reports import html_report
from statistical_engine import (
    association,
    compatible,
    descriptive,
    group_test,
    regression,
    temporal,
)


def test_profile_classifies_year_date_ids_and_percentages_without_modifying_input():
    frame = pd.DataFrame({"Año": ["2020", "2021", "2021"], "día": ["01/02/2021", "01/03/2021", None],
                          "ID": ["001", "002", "003"], "participación": ["8,5 %", "125 %", None],
                          "valor": ["12,5", "0,0", None], "Municipio": ["Getafe", "getafe", None]})
    profile = schema(frame)
    roles = {row["Variable"]: row["Rol"] for row in profile["variables"]}
    assert roles == {"Año": "Año", "día": "Fecha", "ID": "Identificador", "participación": "Porcentaje",
                     "valor": "Numérica", "Municipio": "Municipio"}
    advice = {rec.operation: rec for rec in profile["advice"]}
    assert advice["Revisar rango porcentual"].count == 1
    assert profile["missing"] == 4
    assert corrected(frame, advice["Convertir a año entero"])["Año"].tolist() == [2020, 2021, 2021]
    assert corrected(frame, advice["Fecha día/mes/año"])["día"].iloc[0] == pd.Timestamp("2021-02-01")
    assert corrected(frame, advice["Porcentaje explícito"])["participación"].iloc[0] == 8.5
    assert corrected(frame, advice["Número con coma decimal"])["valor"].iloc[1] == 0
    assert frame["ID"].tolist() == ["001", "002", "003"]
    assert "Año" not in compatible(frame, roles)["numeric"]


def test_duplicates_do_not_change_original():
    df = pd.DataFrame({"Código territorio": ["0650", "0650", "0000"], "Valor": [4, 4, 2]})
    entries = {rec.operation: rec for rec in schema(df)["advice"]}
    assert len(corrected(df, entries["Eliminar duplicados exactos"])) == 2
    assert corrected(df, entries["Unificar códigos con INE"])["Código territorio"].tolist() == ["28065", "28065", "0000"]
    assert len(df) == 3


def test_known_descriptive_association_and_contingency():
    result = descriptive(pd.Series([1, 2, 3, None]))
    values = result.table.set_index("Estadístico")["Valor"]
    assert values["Mediana"] == 2 and values["Varianza"] == 1 and values["Ausentes (%)"] == 25
    df = pd.DataFrame({"x": [1, 2, 3, 4], "y": [2, 4, 6, 8]})
    assert association(df, "Pearson", "x", "y").table["Coeficiente"].iat[0] == pytest.approx(1)
    assert association(df, "Spearman", "x", "y").table["Coeficiente"].iat[0] == pytest.approx(1)
    cats = pd.DataFrame({"x": ["a", "a", "b", "b"], "y": ["c", "d", "c", "d"]})
    contingency = association(cats, "Contingencia y chi-cuadrado", "x", "y")
    assert "0.000" in contingency.summary
    assert any("menor de 5" in n for n in contingency.notes)


@pytest.mark.parametrize("method", ["t independiente (Welch)", "Mann–Whitney", "ANOVA", "Kruskal–Wallis"])
def test_group_statistics_check_design_and_show_known_equal_groups(method):
    df = pd.DataFrame({"value": [1, 2, 3, 1, 2, 3], "group": ["A"] * 3 + ["B"] * 3})
    with pytest.raises(ValueError, match="diseño"):
        group_test(df, method, "value", "group")
    result = group_test(df, method, "value", "group", design_confirmed=True)
    assert result.table["p"].iat[0] == pytest.approx(1)


@pytest.mark.parametrize("method", ["t pareada", "Wilcoxon"])
def test_paired_tests(method):
    df = pd.DataFrame({"x": [1, 3, 9, 7], "y": [2, 1, 10, 8]})
    result = group_test(df, method, "x", "y", design_confirmed=True)
    assert 0 < result.table["p"].iat[0] <= 1
    assert result.table["Observaciones"].iat[0] == 4


def test_regression_coefficients_and_outcomes():
    x = np.arange(1, 31)
    z = x % 3
    df = pd.DataFrame({"x": x, "z": z, "y": 5 + 2*x + 3*z, "simple": 5 + 2*x})
    simple = regression(df, "Lineal simple", "simple", ["x"]).table.set_index("Variable")
    assert simple.loc["x", "Coeficiente"] == pytest.approx(2)
    result = regression(df, "Lineal múltiple", "y", ["x", "z"]).table.set_index("Variable")
    assert result.loc["z", "Coeficiente"] == pytest.approx(3)
    df["event"] = np.tile([0, 1], 15)
    log = regression(df, "Logística binaria", "event", ["x"], positive=1)
    assert "Odds ratio" in log.table
    df["counts"] = 1 + x % 4
    df["exposure"] = x + 5
    pois = regression(df, "Poisson", "counts", ["x"], "exposure")
    assert "Razón de tasas" in pois.table and any("offset" in note for note in pois.notes)
    with pytest.raises(ValueError, match="recuentos"):
        regression(df.assign(counts=df["counts"] + .5), "Poisson", "counts", ["x"])


def test_time_and_report_export():
    df = pd.DataFrame({"año": [2018, 2020, 2021], "ventas": [0, 5, 15]})
    result = temporal(df, "año", "ventas", "Año", window=2)
    assert result.table["Cambio absoluto"].tolist()[1:] == [5, 10]
    assert pd.isna(result.table["Cambio (%)"].iat[1])
    assert result.table["Media móvil"].iat[2] == 10
    assert result.table["año"].tolist() == [2018, 2020, 2021]
    rendered = html_report("<b>test</b>", "Datos", result.table, {"año": 2021}, notes=result.notes)
    assert "&lt;b&gt;test&lt;/b&gt;" in rendered and "2021" in rendered


def test_studio_profiles_applies_and_undoes_with_real_widgets():
    app = AppTest.from_file("app.py", default_timeout=40).run()
    frame = pd.DataFrame({"Año": ["2020", "2021"], "Valor": [1, 3]})
    app.session_state.tables[1] = {"df": frame, "title": "Datos", "sources": ("Prueba",), "history": ()}
    app.session_state.serial = 1
    app.button(key="nav_Analizar").click().run()
    assert not app.exception
    assert app.session_state.tables[1]["profile"]["rows"] == 2
    app.radio(key="studio_view").set_value("Limpieza recomendada").run()
    app.button(key="apply_1_0").click().run()
    assert not app.exception
    assert app.session_state.tables[2]["df"]["Año"].tolist() == [2020, 2021]
    assert app.session_state.tables[1]["df"]["Año"].tolist() == ["2020", "2021"]
    next(button for button in app.button if button.label == "Deshacer esta versión").click().run()
    assert set(app.session_state.tables) == {1}
    app.radio(key="studio_view").set_value("Análisis disponibles").run()
    app.button(key="execute_1_Distribución").click().run()
    assert not app.exception
    assert any("mediana" in node.value for node in app.markdown)


def test_map_sync_payload():
    assert synced_view({"center": {"lat": 40.4, "lng": -3.7}, "zoom": 10}) == ((40.4, -3.7), 10)
    assert synced_view({"center": {"lat": None, "lng": -3.7}, "zoom": 10}) is None


def test_catalog_metadata_preserves_unknown_and_uses_dictionary():
    from dataset_cards import dataset_metadata

    dataset = {"title": "Padrón. Municipios", "name": "padron", "extras": [{"key": "Frecuencia", "value": "Anual"}]}
    resource = {"format": "CSV", "schema": {"fields": [{"name": "Año", "description": "Año de referencia"}]}}
    meta = dataset_metadata(dataset, resource)
    assert meta["cobertura temporal"] is None
    assert meta["nivel territorial"] == "Municipal (según el título)"
    assert meta["frecuencia"] == "Anual"
    assert meta["variables"]["Año"] == "Año de referencia"


def test_studio_ranks_geographic_data_and_mounts_two_linked_maps(monkeypatch):
    maps = []
    def fake_map(*args, **kwargs):
        maps.append(kwargs)
        return {}
    monkeypatch.setattr("map_view.st_folium", fake_map)
    app = AppTest.from_file("app.py", default_timeout=45).run()
    frame = pd.DataFrame({"Código territorio": ["0650", "0796"], "medida A": [4, 6], "medida B": [12, 14]})
    app.session_state.tables[1] = {"df": frame, "title": "Datos", "sources": ("Prueba",), "history": ()}
    app.button(key="nav_Analizar").click().run()
    app.radio(key="studio_view").set_value("Análisis disponibles").run()
    app.button(key="family_1_Análisis geográfico").click().run()
    app.multiselect(key="geo_metrics_1").set_value(["medida A", "medida B"]).run()
    assert not app.exception
    assert len(maps) == 2 and all("zoom" in m["returned_objects"] for m in maps)
    assert app.dataframe[-1].value["medida B"].tolist() == [14, 12]


def test_catalog_resource_opens_profile_with_detected_schema(monkeypatch):
    dataset = {"name": "datos-prueba", "id": "test-3", "title": "Indicador de prueba", "notes": "Descripción",
               "resources": [{"name": "Tabla", "format": "CSV", "url": "https://datos.comunidad.madrid/prueba.csv"}]}
    monkeypatch.setattr("catalog.catalog_page", lambda *args, **kwargs: {"count": 1, "results": [dataset]})
    monkeypatch.setattr("catalog.download_table", lambda _: pd.DataFrame({"Año": [2023, 2024], "Valor": [3, 5]}))
    app = AppTest.from_file("app.py", default_timeout=45).run()
    app.button(key="nav_Catálogo").click().run()
    app.text_input(key="explorer_query").set_value("prueba v3")
    next(w for w in app.button if w.label == "Buscar datasets").click().run()
    app.multiselect(key="sel_test-3").set_value([0]).run()
    app.button(key="catalog_Explorar este dataset_test-3").click().run()
    assert not app.exception
    assert app.session_state.page == "Analizar"
    assert app.session_state.tables[1]["profile"]["variables"][0]["Rol"] == "Año"
    assert app.session_state.tables[1]["metadata"]["formato"] == "CSV"
