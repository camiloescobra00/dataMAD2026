import json

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from catalog import catalog_page, compatible_resources
from map_catalog import CATALOG_PATH, catalog_index, search_maps
from map_eligibility import assess_map_table, validate_map_resource


def statistics():
    return {"title": "Indicador. Municipios", "organization": {"name": "estadistica"}}


def municipal_data():
    return pd.DataFrame({"Año": [2024] * 5, "Tipo territorio": ["Comunidad de Madrid"] + ["Municipios"] * 4,
                         "Código territorio": [None, "0650", "0796", "0650", "0796"],
                         "Territorio": ["Comunidad de Madrid", "Getafe", "Madrid", "Getafe", "Madrid"],
                         "Sexo": ["Total", "Total", "Total", "Mujeres", "Mujeres"],
                         "Valor": [100, 20, 30, 10, 15], "Unidad": ["Personas"] * 5})


def test_statistics_require_real_municipal_values_and_filter_dimensions():
    frame = municipal_data()
    spec, reason = assess_map_table(statistics(), frame)
    assert reason is None
    assert spec["kind"] == "municipal_indicator"
    assert spec["metric"] == "Valor" and spec["metrics"] == ["Valor"]
    assert spec["filters"] == {"Tipo territorio": ["Municipios"]}
    assert spec["dimensions"] == ["Sexo", "Unidad"]
    validate_map_resource(frame, spec)
    with pytest.raises(ValueError, match="estructura"):
        validate_map_resource(frame.drop(columns=spec["column"]), spec)
    with pytest.raises(ValueError, match="criterios"):
        validate_map_resource(frame.assign(**{spec["column"]: "unknown"}), spec)


def test_reject_regional_totals_place_mentions_surveys_and_unsupported_geometry():
    for frame, ds in [
        (pd.DataFrame({"Año": [2024, 2025], "Territorio": ["Madrid", "Madrid"], "Valor": [2, 3]}), statistics()),
        (pd.DataFrame({"titulo": ["Mapa de Madrid"], "valor": [4]}), statistics()),
        (pd.DataFrame({"Municipio": ["Madrid", "Getafe"], "distrito_codigo": [1, 2], "Valor": [1, 3]}), statistics()),
        (pd.DataFrame({"Municipio": ["Madrid", "Getafe"], "Respuesta": [1, 2]}), {"title": "Encuesta de percepción"}),
        (pd.DataFrame({"latitud": [440000, 450000], "longitud": [4500000, 4500010]}), {"title": "Ubicaciones"}),
        (pd.DataFrame({"Municipio": ["Madrid", "Getafe"], "documento": ["A", "B"]}), statistics()),
    ]:
        spec, reason = assess_map_table(ds, frame)
        assert spec is None and reason


def test_admit_points_and_facility_counts_but_not_numeric_ids_as_indicators():
    spec, _ = assess_map_table({"title": "Desfibriladores"}, pd.DataFrame({
        "direccion_latitud": [40.1, 40.2], "direccion_longitud": [-3.5, -3.6]}))
    assert spec["kind"] == "points"
    spec, _ = assess_map_table({"title": "Oficinas de farmacia"}, pd.DataFrame({
        "Municipio": ["Madrid", "Getafe"], "codigo_registro": [1, 2]}))
    assert spec["kind"] == "municipal_count" and spec["metric"] is None
    spec, _ = assess_map_table(statistics(), pd.DataFrame({"Municipio": ["Madrid", "Getafe"], "id": [1, 2]}))
    assert spec is None


def test_catalog_snapshot_and_pagination_only_publish_audited_resources():
    index = catalog_index()
    assert index["reviewed"] == 2275
    assert index["count"] == len(index["datasets"]) == 372
    audit = json.loads(CATALOG_PATH.with_name("map_catalog_audit.json").read_text())
    assert len(audit) == index["reviewed"]
    included = {row["name"] for row in audit if row["included"]}
    assert included == {d["name"] for d in index["datasets"]}
    assert "padron_por_sexo" in included and "calidad_aire_estaciones" in included
    assert "relacion_puestos_trabajo" not in included and "calidad_aire_datos_mes" not in included
    pages = [catalog_page("", start=start) for start in range(0, index["count"], 20)]
    names = [d["name"] for page in pages for d in page["results"]]
    assert len(names) == len(set(names)) == index["count"]
    assert set(names) == included
    for dataset in index["datasets"]:
        assert compatible_resources(dataset) == dataset["resources"]
        assert all(r.get("map_spec") for r in dataset["resources"])


def test_search_counts_facets_and_filters_share_the_same_subset():
    result = search_maps("población", rows=100)
    assert result["count"] > 0
    assert all("map_spec" in r for d in result["results"] for r in d["resources"])
    filtered = search_maps("", filters={"Formato": "PDF"})
    assert filtered["count"] == 0 and not filtered["results"]
    all_rows = search_maps("", rows=100, sort="Título")
    assert all_rows["search_facets"]["res_format"]["items"] == [
        {"name": "CSV", "display_name": "CSV", "count": 372}]


def test_curated_map_defaults_to_indicator_and_filters_strata(monkeypatch):
    spec, _ = assess_map_table(statistics(), municipal_data())
    captured = []
    monkeypatch.setattr("dataset_map_view.linked_map", lambda frame, **kwargs: captured.append(frame))
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.session_state.tables[1] = {"title": "Indicador verificado", "df": municipal_data(), "sources": (),
                                   "metadata": {"map_spec": spec}, "history": ()}
    app.button(key="nav_Mapa").click().run()
    app.selectbox(key="map_dataset").set_value(1).run()
    assert not app.exception
    assert app.selectbox(key="dataset_map_metric_page_1").value == "Valor"
    assert "Recuento de registros" not in app.selectbox(key="dataset_map_metric_page_1").options
    assert app.selectbox(key="dataset_map_dimension_page_1_Sexo").value == "Total"
    assert captured[-1].Valor.tolist() == [20, 30]
    app.selectbox(key="dataset_map_dimension_page_1_Sexo").set_value("Mujeres").run()
    assert not app.exception and captured[-1].Valor.tolist() == [10, 15]


def test_catalog_starts_with_only_supported_datasets():
    import streamlit as st

    # Other UI tests replace the catalog provider; discard their cached empty-query fixtures.
    st.cache_data.clear()
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.button(key="nav_Catálogo").click().run()
    assert not app.exception
    assert any("372 datasets seleccionados" in c.value for c in app.caption)
    assert any("372 resultados" in c.value for c in app.caption)
    assert any("municipios reconocidos" in i.value or "Ubicaciones" in i.value for i in app.info)


@pytest.mark.integration
@pytest.mark.parametrize("name", ["padron_por_sexo", "oficinas_farmacia", "calidad_aire_estaciones"])
def test_official_curated_resource_still_maps(name):
    import os

    from catalog import download_table

    if os.getenv("MDE_RUN_INTEGRATION") != "1":
        pytest.skip("Activa MDE_RUN_INTEGRATION=1 para comprobar recursos oficiales")
    dataset = next(d for d in catalog_index()["datasets"] if d["name"] == name)
    resource = dataset["resources"][0]
    frame = download_table(resource)
    validate_map_resource(frame, resource["map_spec"])
