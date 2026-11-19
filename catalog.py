"""Cliente del catálogo CKAN y descarga restringida de recursos oficiales."""
from time import monotonic
from urllib.parse import urljoin, urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from data_tables import describe_table, read_table

__all__ = ["catalog_page", "compatible_resources", "describe_table", "download_table", "search_catalog"]

API_ROOT = "https://datos.comunidad.madrid/api/3/action"
MAX_BYTES = 15 * 1024 * 1024
FORMATS = {"CSV", "TSV", "JSON", "XLSX", "XLS"}
SORT = {"Relevancia": "score desc, metadata_modified desc",
        "Actualización": "metadata_modified desc", "Título": "title_string asc"}
FACETS = {"Tema": "groups", "Organismo": "organization", "Formato": "res_format", "Etiqueta": "tags"}


def _session():
    session = requests.Session()
    session.headers["User-Agent"] = "MadridDataExplorer/1.0"
    session.mount("https://", HTTPAdapter(max_retries=Retry(
        total=1, status_forcelist=[429, 500, 502, 503, 504], backoff_factor=0.2,
        respect_retry_after_header=False,
    )))
    return session


def catalog_page(query, rows=20, start=0, filters=None, sort="Relevancia"):
    clauses = []
    for label, value in (filters or {}).items():
        if value and label in FACETS:
            escaped = str(value).replace(chr(92), chr(92)*2).replace('"', chr(92)+'"')
            clauses.append(f'{FACETS[label]}:"{escaped}"')
    with _session() as session:
        response = session.get(f"{API_ROOT}/package_search", params={
            "q": query.strip(), "rows": min(max(rows, 1), 100), "start": max(start, 0),
            "fq": " ".join(clauses), "sort": SORT[sort], "facet.field": '["groups","organization","res_format","tags"]',
            "facet.limit": 40,
        }, timeout=(4, 12))
        response.raise_for_status()
        payload = response.json()
    if not payload.get("success"):
        raise ValueError("La API del catálogo devolvió un error.")
    return payload["result"]


def search_catalog(query, rows=25):
    result = catalog_page(query, rows)
    return result["count"], result["results"]


def official_url(url):
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        return (parsed.scheme == "https" and parsed.port in {None, 443}
                and parsed.username is None and parsed.password is None
                and any(host == domain or host.endswith("." + domain)
                        for domain in ("comunidad.madrid", "madrid.org")))
    except ValueError:
        return False


def compatible_resources(dataset):
    return [r for r in dataset.get("resources", [])
            if str(r.get("format", "")).strip().upper() in FORMATS
            and official_url(str(r.get("url", "")))]


def download_table(resource):
    url = str(resource.get("url", ""))
    deadline = monotonic() + 45
    with _session() as session:
        for _ in range(4):
            if monotonic() > deadline:
                raise ValueError("La descarga tardó demasiado.")
            if not official_url(url):
                raise ValueError("El recurso requiere HTTPS en un dominio oficial permitido.")
            with session.get(url, timeout=(4, 12), stream=True, allow_redirects=False) as response:
                if response.is_redirect:
                    url = urljoin(url, response.headers["Location"])
                    continue
                response.raise_for_status()
                if response.status_code != 200:
                    raise ValueError("El recurso no devolvió un fichero completo.")
                data = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    if monotonic() > deadline:
                        raise ValueError("La descarga tardó demasiado.")
                    data.extend(chunk)
                    if len(data) > MAX_BYTES:
                        raise ValueError("El fichero supera 15 MB.")
                return read_table(bytes(data), str(resource.get("format", "")))
    raise ValueError("Demasiadas redirecciones al cargar el recurso.")
