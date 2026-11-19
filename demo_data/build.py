"""Regenera extractos reproducibles a partir de CSV oficiales."""
import argparse
import csv
import json
from io import StringIO
from pathlib import Path
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parent
RULES = {
    "irpf_indicador_renta": ("Renta per cápita (EUR)", {"Medida": "Per cápita"}),
    "grado_envejecimiento_por_edad": ("Población de 65 años y más (%)", {"Edad": "65 años y más"}),
    "centros_sanitarios_por_tipo": ("Centros por 10.000 habitantes", {
        "Tipo": "Consultorios locales y centros de salud", "Medida": "Por 10.000 habitantes"}),
    "padron_por_sexo": ("Población (personas)", {"Sexo": "Total"}),
    "302038": ("Paro registrado (personas)", {}),
}
KEYS = ["Código territorio", "Año", "Territorio"]


def build(local=None):
    sources = json.loads((ROOT / "sources.json").read_text())
    regional = []
    for name, (metric, conditions) in RULES.items():
        years = range(2018, 2026) if name == "302038" else range(2015, 2026) if name == "padron_por_sexo" else [2024]
        if local:
            filename = "paro" if name == "302038" else name
            contents = (local / f"mde-{filename}.csv").read_text(encoding="utf-8-sig")
        else:
            with urlopen(sources[name]["url"], timeout=20) as response:
                contents = response.read().decode("utf-8-sig")
        reader = csv.DictReader(StringIO(contents), delimiter=";")
        extracted = []
        seen = set()
        for row in reader:
            if int(row["Año"]) not in years or any(row[col] != value for col, value in conditions.items()):
                continue
            if row["Tipo territorio"] == "Comunidad de Madrid":
                regional.append([name, row["Año"], row["Valor"]])
            if row["Tipo territorio"] != "Municipios":
                continue
            key = [row[c] for c in KEYS]
            if not key[0] or tuple(key[:2]) in seen:
                raise ValueError(f"Clave municipal anual no única en {name}: {key}")
            seen.add(tuple(key[:2]))
            value = row["Valor"]
            extracted.append([*key, "" if value == "-" else value])
        if not extracted:
            raise ValueError(f"No hay datos para {name}.")
        with (ROOT / f"{name}.csv").open("w", encoding="utf-8", newline="") as target:
            writer = csv.writer(target, lineterminator="\n")
            writer.writerow([*KEYS, metric])
            writer.writerows(sorted(extracted))
    with (ROOT / "regional.csv").open("w", encoding="utf-8", newline="") as target:
        writer = csv.writer(target, lineterminator="\n")
        writer.writerow(["Fuente", "Año", "Valor"])
        writer.writerows(sorted(regional))


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("--local", type=Path)
    build(cli.parse_args().local)
