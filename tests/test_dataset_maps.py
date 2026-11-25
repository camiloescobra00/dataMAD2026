import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from dataset_maps import (
    location_candidates,
    municipal_frame,
    point_frame,
    resolve_location,
)


def test_location_formats_and_names():
    for value, system in [(28065.0, "INE"), ("0650", "Almudena"), (65, "Código municipal de 3 dígitos"),
                          ("  GETAFE ", "Nombre municipal")]:
        assert resolve_location(value, system) == "28065"
    assert resolve_location("El Álamo", "Nombre municipal") == "28004"
    assert resolve_location("Álamo (El)", "Nombre municipal") == "28004"
    assert resolve_location("Comunidad de Madrid", "Nombre municipal") is None
    assert resolve_location("28999", "INE") is None
    assert resolve_location("0658", "Almudena") is None
    assert resolve_location("28065", "Código municipal de 3 dígitos") is None
    assert location_candidates(pd.DataFrame({"income": [28065]})) == []
    assert location_candidates(pd.DataFrame({"Municipio": ["Getafe"]})) == [("Municipio", "Nombre municipal")]


def test_counts_aggregation_and_missing_values():
    df = pd.DataFrame({"town": ["Getafe", "Getafe", "Madrid", "Unknown"], "value": ["1,5", "2,5", None, "10"]})
    frame, excluded = municipal_frame(df, "town", "Nombre municipal")
    assert excluded == 1
    assert frame.set_index("INE").Valor.to_dict() == {"28065": 2, "28079": 1}
    with pytest.raises(ValueError, match="varias filas"):
        municipal_frame(df, "town", "Nombre municipal", "value")
    frame, _ = municipal_frame(df, "town", "Nombre municipal", "value", "Suma")
    assert frame.set_index("INE").Valor["28065"] == 4
    assert pd.isna(frame.set_index("INE").Valor["28079"])
    frame, _ = municipal_frame(df, "town", "Nombre municipal", "value", "Media")
    assert frame.set_index("INE").Valor["28065"] == 2


def test_points_validate_bounds_and_decimal_commas():
    df = pd.DataFrame({"lat": ["40,3", "91", None, "inf", "440000"],
                       "lon": ["-3,7", "0", "-3", "-3", "4500000"]})
    points, excluded = point_frame(df, "lat", "lon")
    assert excluded == 4
    assert points.iloc[0].to_dict() == {"Latitud": 40.3, "Longitud": -3.7}
    with pytest.raises(ValueError, match="distintas"):
        point_frame(df, "lat", "lat")


def loaded_app(frame):
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.session_state['tables'] = {1: {"title": "Dataset de prueba", "df": frame, "sources": ()}}
    return app.button(key="nav_Mapa").click().run()


def test_loaded_municipal_dataset_on_map_page(monkeypatch):
    monkeypatch.setattr("map_view.st_folium", lambda *args, **kwargs: {})
    app = loaded_app(pd.DataFrame({"Municipio": ["Getafe", "Getafe", "Madrid"],
                                   "Año": [2024, 2025, 2025], "Valor": [2, 4, 8]}))
    app.selectbox(key="map_dataset").set_value(1).run()
    assert not app.exception
    assert any("2 de 2 registros" in c.value for c in app.caption)
    assert app.get("download_button")
    app.selectbox(key="dataset_map_metric_page_1").set_value("Valor").run()
    assert not app.exception


def test_loaded_points_and_unmapped_dataset():
    app = loaded_app(pd.DataFrame({"latitud": [40.3], "longitud": [-3.7]}))
    app.selectbox(key="map_dataset").set_value(1).run()
    assert not app.exception
    assert app.get("plotly_chart")
    app = loaded_app(pd.DataFrame({"categoría": ["A", "B"]}))
    app.selectbox(key="map_dataset").set_value(1).run()
    assert not app.exception
    assert any("No se ha detectado" in info.value for info in app.info)


def test_empty_map_page_routes_to_catalog():
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.button(key="nav_Mapa").click().run()
    assert app.selectbox(key="map_dataset").disabled
    assert any("Aún no hay datasets cargados" in info.value for info in app.info)
    app.button(key="map_open_catalog").click().run()
    assert not app.exception
    assert app.session_state.page == "Catálogo"


def test_catalog_opens_selected_dataset_map_and_remembers_it(monkeypatch):
    resource = {"id": "map-resource", "url": "https://datos.comunidad.madrid/map.csv",
                "format": "CSV", "name": "Ubicaciones"}
    dataset = {"id": "map-fixture", "name": "map-fixture", "title": "Centros de prueba",
               "resources": [resource]}
    downloads = []

    def download(resource):
        downloads.append(resource["url"])
        return pd.DataFrame({"Municipio": ["Getafe", "Madrid"], "Plazas": [10, 20]})

    monkeypatch.setattr("catalog.catalog_page", lambda *args, **kwargs: {"count": 1, "results": [dataset]})
    monkeypatch.setattr("catalog.download_table", download)
    monkeypatch.setattr("map_view.st_folium", lambda *args, **kwargs: {})
    app = AppTest.from_file("app.py", default_timeout=30).run()
    app.button(key="nav_Catálogo").click().run()
    app.text_input(key="explorer_query").set_value("centros para mapa")
    next(w for w in app.button if w.label == "Buscar datasets").click().run()
    app.multiselect(key="sel_map-fixture").set_value([0]).run()
    app.button(key="catalog_Ver en mapa_map-fixture").click().run()
    assert not app.exception
    assert app.session_state.page == "Mapa"
    assert app.selectbox(key="map_dataset").value == 1
    assert any("2 de 2 registros" in caption.value for caption in app.caption)
    app.selectbox(key="dataset_map_metric_page_1").set_value("Plazas").run()
    app.button(key="nav_Explorar").click().run()
    app.button(key="nav_Mapa").click().run()
    assert not app.exception
    assert app.selectbox(key="map_dataset").value == 1
    assert app.selectbox(key="dataset_map_metric_page_1").value == "Plazas"
    app.button(key="nav_Catálogo").click().run()
    app.button(key="catalog_Ver en mapa_map-fixture").click().run()
    assert not app.exception
    assert len(downloads) == 1
    assert len(app.session_state.tables) == 1
