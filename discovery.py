"""Interpretación de consultas y recuperación temática explicable."""
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

import requests

from catalog import catalog_page

TOPICS = {
    "renta": (("renta", "ingreso", "ingresos", "riqueza", "salario"), "renta municipal"),
    "envejecimiento": (("envejecimiento", "envejecida", "envejecido", "personas mayores", "65 años"), "envejecimiento"),
    "paro": (("paro", "desempleo", "desempleada", "desempleados", "desocupación"), "paro registrado"),
    "población joven": (("joven", "jóvenes", "juventud", "infantil"), "juventud población"),
    "población": (("población", "habitantes", "demográfico", "demográfica", "padrón"), "población empadronada"),
    "educación": (("educación", "educativo", "estudios", "escolar"), "nivel educativo"),
    "salud": (("salud", "sanitario", "hospital", "sanitaria", "atención primaria"), "centros sanitarios"),
    "vivienda": (("vivienda", "alquiler", "residencial"), "vivienda alquiler"),
    "transporte": (("transporte", "autobús", "autobuses", "movilidad", "metro"), "transporte público"),
}
STOP = {"que", "cuales", "quiero", "ver", "cual", "hay", "mas", "donde", "tiene", "tienen", "datos", "madrid", "como", "ha", "han", "en", "de", "del", "la", "las", "los", "el", "y", "por", "un", "una", "se", "es", "con", "sobre", "entre", "para", "me", "muestrame", "ultimos", "anos", "ano", "vive", "esta"}


def fold(value):
    return "".join(c for c in unicodedata.normalize("NFKD", str(value).casefold())
                   if not unicodedata.combining(c))


def words(value):
    return set(re.findall(r"[a-z0-9]+", fold(value)))


def mentions(phrase, text):
    return bool(re.search(r"(?<!\w)" + re.escape(fold(phrase)) + r"(?!\w)", text))


@dataclass(frozen=True)
class Query:
    text: str
    topics: tuple
    geography: str | None
    years: tuple
    recent: int | None
    intent: str
    terms: tuple


def interpret(question, municipalities=()):
    text = fold(question)
    topics = tuple(topic for topic, (aliases, _) in TOPICS.items() if any(mentions(a, text) for a in aliases))
    if "población" in topics and {"envejecimiento", "población joven"}.intersection(topics):
        topics = tuple(t for t in topics if t != "población")
    specific = tuple(name for name in municipalities if name != "Madrid" and mentions(name, text))
    geo = ", ".join(specific) if specific else next(
        (name for name, pattern in (("Distritos", r"\bdistritos?\b"), ("Barrios", r"\bbarrios?\b"),
                                     ("Municipios", r"\bmunicip\w+\b|\bdonde\b|\bzonas?\b"),
                                     ("Comunidad de Madrid", r"\bmadrid\b")) if re.search(pattern, text)), None)
    years = tuple(dict.fromkeys(map(int, re.findall(r"\b(?:19|20)\d{2}\b", text))))
    recent = re.search(r"ultim[oa]s?\s+(\d{1,2}|cinco|diez|veinte)\s+anos", text)
    recent = ({"cinco": 5, "diez": 10, "veinte": 20}.get(recent[1], recent[1])) if recent else None
    if re.search(r"relacion|correlacion|asocia", text):
        intent = "relación"
    elif re.search(r"crecid|crecimiento|variacion demogra", text) and "población" in topics:
        intent = "crecimiento"
    elif re.search(r"evolu|cambiad|histori|serie|desde", text) or recent or len(years) > 1:
        intent = "evolución"
    elif re.search(r"compar", text):
        intent = "comparación"
    elif geo:
        intent = "territorio"
    else:
        intent = "resumen"
    terms = tuple(dict.fromkeys(w for w in re.findall(r"[a-z]+", text) if w not in STOP))
    return Query(question, topics, geo, years, int(recent) if recent else None, intent, terms)


def queries(query):
    topical = [TOPICS[topic][1] for topic in query.topics]
    literal = " ".join(query.terms[:8])
    return tuple(dict.fromkeys(q for q in [*topical, literal, query.text[:250]] if q))[:6]


def coverage(dataset):
    extras = {fold(e.get("key", "")): str(e.get("value", "")) for e in dataset.get("extras", [])}
    geo = next((value for key, value in extras.items() if "espacial" in key or "geograf" in key or key == "ambito"), None)
    temporal = next((value for key, value in extras.items() if "temporal" in key), None)
    if re.search(r"\bmunicipios\b", fold(dataset.get("title", ""))) and (not geo or "municip" not in fold(geo)):
        geo = f"Municipios (según el título) · {geo}" if geo else "Municipios (según el título)"
    return geo, temporal


def relevance(query, dataset):
    title = fold(dataset.get("title", ""))
    tags = " ".join(str(t.get("display_name") or t.get("name", "")) for t in dataset.get("tags", []))
    groups = " ".join(str(t.get("title") or t.get("name", "")) for t in dataset.get("groups", []))
    metadata = fold(" ".join([str(dataset.get("notes") or ""), tags, groups]))
    title_hits = {w for w in query.terms if mentions(w, title)}
    metadata_hits = {w for w in query.terms if mentions(w, metadata)} - title_hits
    score = 4 * len(title_hits) + len(metadata_hits)
    reasons = []
    for topic in query.topics:
        aliases = TOPICS[topic][0]
        if any(mentions(word, title) for word in aliases):
            score += 10
            reasons.append(f"Indicador en el título: {topic}")
        elif any(mentions(word, metadata) for word in aliases):
            score += 3
            reasons.append(f"Tema en los metadatos: {topic}")
    geo, temporal = coverage(dataset)
    if query.geography and geo and "municip" in fold(geo) and query.geography not in {"Distritos", "Barrios"}:
        score += 4
        reasons.append("Cobertura municipal indicada")
    if temporal and any(str(year) in temporal for year in query.years):
        score += 2
        reasons.append("Año mencionado en la cobertura")
    if not reasons and title_hits:
        reasons.append("Coincide con " + ", ".join(sorted(title_hits)))
    return score, reasons


def retrieve(query, fetch=catalog_page):
    def request(term):
        try:
            return fetch(term, rows=15)["results"], False
        except (requests.RequestException, ValueError, KeyError):
            return [], True

    terms = queries(query)
    if not terms:
        return [], False
    with ThreadPoolExecutor(max_workers=min(len(terms), 4)) as pool:
        responses = list(pool.map(request, terms))
    candidates = {}
    for group, _ in responses:
        for rank, dataset in enumerate(group):
            key = dataset.get("id") or dataset.get("name")
            if not key:
                continue
            score, reasons = relevance(query, dataset)
            row = score + 1 / (rank + 1), dataset, reasons
            if key not in candidates or row[0] > candidates[key][0]:
                candidates[key] = row
    ranked = sorted(candidates.values(), key=lambda row: -row[0])
    # Comparisons need at least one visible source per indicator when candidates exist.
    featured = []
    if len(query.topics) > 1:
        for topic in query.topics:
            matched = next((row for row in ranked if any(reason.endswith(f": {topic}") for reason in row[2])), None)
            if matched and matched not in featured:
                featured.append(matched)
    ordered = featured + [row for row in ranked if row not in featured]
    return ordered[:15], any(failed for _, failed in responses)
