import pandas as pd
import pytest

from joins import join_preview


def test_composite_keys_dont_multiply_years():
    a = pd.DataFrame({"municipio": ["Madrid", "Madrid"], "anio": [2023, 2024], "pob": [1, 2]})
    b = pd.DataFrame({"municipio": ["madrid", "MADRID"], "anio": [2023, 2024], "centros": [8, 9]})
    result, info = join_preview(a, b, ["municipio", "anio"], ["municipio", "anio"], "inner")
    assert len(result) == 2
    assert info["filas_coincidentes"] == 2


def test_null_keys_never_match():
    a = pd.DataFrame({"municipio": [None, "A"]})
    b = pd.DataFrame({"municipio": [None, "A"]})
    result, _ = join_preview(a, b, ["municipio"], ["municipio"], "inner")
    assert len(result) == 1


def test_refuse_explosive_join():
    a = pd.DataFrame({"id": ["X"] * 100})
    b = pd.DataFrame({"id": ["X"] * 100})
    with pytest.raises(ValueError):
        join_preview(a, b, ["id"], ["id"], "inner", max_rows=1000)


@pytest.mark.parametrize("how", ["inner", "left", "right", "outer"])
def test_successive_joins_with_key_and_column_collisions(how):
    source = pd.DataFrame({"municipio": ["001", "002"], "año": [2024, 2024],
                           "valor": [1, 2], "valor_B": [3, 4], "_merge": ["x", "y"],
                           "__join_key": ["original", "original"]})
    result = source
    for _ in range(3):
        result, info = join_preview(result, source, ["municipio", "año"], ["municipio", "año"], how)
        assert info["cardinalidad"] == "uno a uno"
        assert result.columns.is_unique
        assert result.municipio.tolist() == ["001", "002"]
        assert result["__join_key"].tolist() == ["original", "original"]


def test_empty_and_missing_columns():
    left = pd.DataFrame({"id": pd.Series([], dtype="string")})
    right = pd.DataFrame({"id": ["001"]})
    joined, info = join_preview(left, right, ["id"], ["id"], "outer")
    assert joined["id"].tolist() == ["001"]
    assert info["solo_derecha"] == 1
    with pytest.raises(ValueError, match="claves"):
        join_preview(left, right, ["bad"], ["id"], "inner")


def test_many_to_many_reports_input_matches_and_result_rows():
    a = pd.DataFrame({"id": ["a", "a", "b", None]})
    b = pd.DataFrame({"id": ["A", "A", "c", None]})
    joined, info = join_preview(a, b, ["id"], ["id"], "inner")
    assert len(joined) == 4
    assert info["solo_izquierda"] == info["solo_derecha"] == 2
    assert info["coincidencia_A_pct"] == 50
    assert info["cardinalidad"] == "muchos a muchos"
    assert info["advertencias"]


def test_outer_join_retains_reusable_codes_and_years():
    a = pd.DataFrame({"code": ["001"], "año": [2023], "a": [1]})
    b = pd.DataFrame({"code": ["002"], "año": [2024], "b": [2]})
    c = pd.DataFrame({"code": ["001", "002", "2"], "año": [2023, 2024, 2024], "c": [3, 4, 5]})
    keys = ["code", "año"]
    outer, _ = join_preview(a, b, keys, keys, "outer")
    result, info = join_preview(outer, c, keys, keys, "inner")
    assert set(result["code"]) == {"001", "002"}
    assert info["coincidencia_A_pct"] == 100
