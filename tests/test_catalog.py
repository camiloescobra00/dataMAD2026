import pandas as pd
import pytest

from catalog import compatible_resources, describe_table, download_table


def test_resource_filter():
    dataset = {"resources": [
        {"format": "CSV", "url": "https://datos.comunidad.madrid/file.csv"},
        {"format": "PDF", "url": "https://datos.comunidad.madrid/file.pdf"},
    ]}
    assert len(compatible_resources(dataset)) == 1


def test_reject_external_host():
    with pytest.raises(ValueError):
        download_table({"format": "CSV", "url": "https://example.org/data.csv"})


def test_describe():
    result = describe_table(pd.DataFrame({"a": [1, None], "b": ["x", "y"]}))
    assert result["filas"] == 2
    assert result["variables"][0]["faltantes"] == 1


def test_search_and_http_failure(monkeypatch):
    from unittest.mock import MagicMock

    from requests import HTTPError

    import catalog

    session = MagicMock()
    monkeypatch.setattr(catalog, "_session", lambda: session)
    response = session.__enter__.return_value.get.return_value
    response.json.return_value = {"success": True, "result": {"count": 1, "results": [{}]}}
    assert catalog.search_catalog(" paro ") == (1, [{}])
    params = session.__enter__.return_value.get.call_args.kwargs["params"]
    assert params["q"] == "paro"
    response.raise_for_status.side_effect = HTTPError()
    with pytest.raises(HTTPError):
        catalog.search_catalog("paro")


def test_download_limits_and_redirect(monkeypatch):
    from unittest.mock import MagicMock

    import catalog

    session = MagicMock()
    monkeypatch.setattr(catalog, "_session", lambda: session)
    request = session.__enter__.return_value.get
    response = request.return_value.__enter__.return_value
    response.is_redirect = False
    response.status_code = 200
    response.iter_content.return_value = [b"id;valor\n001;23\n"]
    resource = {"format": "CSV", "url": "https://datos.comunidad.madrid/file.csv"}
    assert catalog.download_table(resource).iloc[0].tolist() == ["001", 23]
    monkeypatch.setattr(catalog, "MAX_BYTES", 3)
    with pytest.raises(ValueError, match="15 MB"):
        catalog.download_table(resource)
    response.is_redirect = True
    response.headers = {"Location": "https://example.org/documento"}
    request.reset_mock()
    with pytest.raises(ValueError, match="dominio oficial"):
        catalog.download_table(resource)
    assert request.call_count == 1


@pytest.mark.integration
def test_official_ckan_and_resource():
    import os

    from catalog import catalog_page

    if os.getenv("MDE_RUN_INTEGRATION") != "1":
        pytest.skip("Activa MDE_RUN_INTEGRATION=1 para consultar CKAN.")
    result = catalog_page("paro", rows=5, filters={"Formato": "CSV"})
    assert result["count"] > 0
    assert result["search_facets"]["res_format"]["items"]
    resources = [r for ds in result["results"] for r in compatible_resources(ds)]
    csv_resource = next(r for r in resources if r["format"].upper() == "CSV")
    assert not download_table(csv_resource).empty


def test_single_column_and_malformed_csv():
    from data_tables import read_table

    assert read_table(b'municipio\nMadrid\n', "CSV").columns.tolist() == ["municipio"]
    with pytest.raises(ValueError, match="campos"):
        read_table(b'a;b\n1;2;3\n', "CSV")


def test_json_and_excel_keep_string_identifiers():
    from io import BytesIO

    from data_tables import read_table

    data = {"id": ["001"], "valor": [23]}
    workbook = BytesIO()
    pd.DataFrame(data).to_excel(workbook, index=False)
    assert read_table(workbook.getvalue(), "XLSX").iloc[0].tolist() == ["001", 23]
    assert read_table(b'{"records":[{"id":"001","valor":23}]}', "JSON").iloc[0].tolist() == ["001", 23]
