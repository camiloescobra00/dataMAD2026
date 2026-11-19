"""Create a lightweight Madrid layer from the IGN WFS GeoJSON response."""
import argparse
import json
from pathlib import Path

from shapely import force_2d, make_valid
from shapely.geometry import mapping, shape

ROOT = Path(__file__).resolve().parent


def matched_features(sources):
    for source in sources:
        collection = json.loads(source.read_text())
        yield from collection.get("features", [])


def build(sources):
    features = {}
    for feature in matched_features(sources):
        properties = feature["properties"]
        national = properties.get("nationalCode", "")
        if not national[-5:].startswith("28") or not properties.get("nationalLevel", {}).get("href", "").endswith(
            "/4thOrder"
        ):
            continue
        code = national[-5:]
        if code in features:
            continue
        geometry = force_2d(shape(feature["geometry"]))
        if not geometry.is_valid:
            geometry = make_valid(geometry)
        geometry = geometry.simplify(0.00025, preserve_topology=True)
        if geometry.geom_type not in {"Polygon", "MultiPolygon"} or geometry.is_empty or not geometry.is_valid:
            raise ValueError(f"Invalid municipal geometry: {code}")
        west, south, east, north = geometry.bounds
        if not (-4.8 < west < east < -2.9 and 39.8 < south < north < 41.3):
            raise ValueError(f"Unexpected geometry extent: {code}")
        features[code] = {"type": "Feature", "id": code, "properties": {"code": code}, "geometry": mapping(geometry)}
    if len(features) != 179:
        raise ValueError(f"Expected 179 unique Madrid municipalities, received {len(features)}.")
    serialized = json.dumps({"type": "FeatureCollection", "features": [features[code] for code in sorted(features)]},
                            separators=(",", ":"))
    (ROOT / "municipios.geojson").write_text(serialized + "\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser()
    cli.add_argument("source", type=Path, nargs="+")
    build(cli.parse_args().source)
