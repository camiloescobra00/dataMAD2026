from types import SimpleNamespace

import pandas as pd
import pytest

from analytics import NEEDS_Y, OPERATIONS, analyze
from assistant import plan_analysis
from data_tables import csv_export, read_table, transform
from settings import ai_settings


@pytest.mark.parametrize("operation", OPERATIONS)
def test_all_analytic_operations(operation):
    df = pd.DataFrame({"año": [2020, 2021, 2022, 2023, 2024], "valor": [1, 2, 3, 4, None]})
    plan = {"operation": operation, "x": "año", "y": "valor" if operation in NEEDS_Y else None}
    result, figure, notes = analyze(df, plan)
    assert notes
    assert figure is not None or operation == "summary"
    if operation == "regression":
        assert result["Pendiente"].iloc[0] == pytest.approx(1)
        assert result["Pares"].iloc[0] == 4


def test_analysis_rejects_invalid_operations_and_empty():
    df = pd.DataFrame({"x": [float("nan")]})
    with pytest.raises(ValueError, match="Operación"):
        analyze(df, {"operation": "import os", "x": "x", "y": None})
    with pytest.raises(ValueError, match="observaciones"):
        analyze(df, {"operation": "summary", "x": "x", "y": None})


def test_ai_receives_schema_only_and_validates(monkeypatch):
    df = pd.DataFrame({"dato": ["contenido privado"], "cantidad": [10]})
    seen = {}
    def create(**kwargs):
        seen.update(kwargs)
        return SimpleNamespace(output_text='{"operation":"summary","x":"v2","y":null}')
    responses = SimpleNamespace(create=create)
    client = SimpleNamespace(responses=responses)
    assert plan_analysis(client, "modelo", "resumen", df)["x"] == "cantidad"
    assert "contenido privado" not in seen["input"]
    monkeypatch.setattr(responses, "create", lambda **_: SimpleNamespace(
        output_text='{"operation":"foo","x":"v2","y":null}'))
    with pytest.raises(ValueError):
        plan_analysis(client, "modelo", "resumen", df)


def test_parse_transform_and_export():
    df = read_table("Código;Precio;Fecha;Texto\n001;1.234,50;31/12/2024;=2+2\n002;-;mal;ok\n".encode(), "csv")
    assert df["Código"].tolist() == ["001", "002"]
    clean, invalid = transform(df, "Convertir a número", "Precio", decimal_comma=True)
    assert clean["Precio"].iloc[0] == 1234.5 and invalid == 1
    clean, invalid = transform(clean, "Convertir a fecha", "Fecha", date_format="%d/%m/%Y")
    assert clean["Fecha"].iloc[0].year == 2024 and invalid == 1
    assert "'=2+2" in csv_export(clean).decode("utf-8-sig")


def test_settings(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "entorno")
    monkeypatch.delenv("MDE_AI_MODEL", raising=False)
    monkeypatch.delenv("MDE_AI_BASE_URL", raising=False)
    assert ai_settings({"OPENAI_API_KEY": "archivo", "MDE_AI_MODEL": "modelo"}) == ("entorno", "modelo", "")


def test_municipal_map_checks_codes_and_duplicates():
    from maps import municipal_map

    df = pd.DataFrame({"code": ["001", "002"], "value": [1, 2]})
    geo = b'{"type":"FeatureCollection","features":[{"properties":{"code":"001"},' \
          b'"geometry":{"type":"Polygon","coordinates":[[[-4,40],[-3,40],[-3,41],[-4,40]]]}}]}'
    _, matched, total = municipal_map(df, "code", "value", geo, "code")
    assert (matched, total) == (1, 2)
    with pytest.raises(ValueError, match="único"):
        municipal_map(pd.concat([df, df]), "code", "value", geo, "code")
