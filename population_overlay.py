#!/usr/bin/env python3
"""Overlay modeled PM2.5 increments with Census block population.

This script makes the population-exposure step reproducible. It reads the event
grid CSVs produced by ``stratos_pm25_model.py``, downloads Census 2020 block
population/geography when needed, assigns populated block centroids to the
nearest modeled receptor, and writes exposure summaries.

The overlay is intentionally conservative about uncertainty: it can also rerun
the same exposure assignment under source-location shifts so approximate siting
does not get hidden inside a single point estimate.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Iterable


STATE = "49"
BOX_ELDER_COUNTY = "003"
TIGER_BLOCK_URL = "https://www2.census.gov/geo/tiger/TIGER2020PL/STATE/49_UTAH/49/tl_2020_49_tabblock20.zip"
GAZ_PLACE_URL = "https://www2.census.gov/geo/docs/maps-data/data/gazetteer/2020_Gazetteer/2020_Gaz_place_national.zip"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Overlay Stratos PM2.5 model output with Census population.")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--site-lat", type=float, required=True)
    parser.add_argument("--site-lon", type=float, required=True)
    parser.add_argument("--radius-km", type=float, default=50.0)
    parser.add_argument("--state", default=STATE)
    parser.add_argument("--county", default=BOX_ELDER_COUNTY)
    parser.add_argument("--census-cache", type=Path, default=Path("data/census"))
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--thresholds", nargs="*", type=float, default=[0.5, 1.0, 2.0, 3.0, 5.0, 7.5, 10.0, 12.5, 15.0, 20.0])
    parser.add_argument("--place-radius-km", type=float, help="Place-centroid screen radius. Defaults to --radius-km and is capped to the model grid unless --include-outside-grid-places is set.")
    parser.add_argument("--include-outside-grid-places", action="store_true", help="Allow place centroids outside the receptor grid; rows are marked outside_model_domain_km.")
    parser.add_argument("--site-sensitivity-km", nargs="*", type=float, default=[0.0, 5.0, 10.0])
    parser.add_argument("--include-diagonal-shifts", action="store_true")
    return parser.parse_args(argv)


def download(url: str, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 0:
        return path
    request = urllib.request.Request(url, headers={"User-Agent": "stratos-pm25-population-overlay/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        path.write_bytes(response.read())
    return path


def ensure_block_shapefile(cache: Path) -> Path:
    shp = cache / "tabblock20" / "tl_2020_49_tabblock20.shp"
    if shp.exists():
        return shp
    zip_path = download(TIGER_BLOCK_URL, cache / "tl_2020_49_tabblock20.zip")
    (cache / "tabblock20").mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(cache / "tabblock20")
    return shp


def ensure_place_gazetteer(cache: Path) -> Path:
    txt = cache / "gaz" / "2020_Gaz_place_national.txt"
    if txt.exists():
        return txt
    zip_path = download(GAZ_PLACE_URL, cache / "gaz" / "2020_Gaz_place_national.zip")
    (cache / "gaz").mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(cache / "gaz")
    return txt


def load_pyshp():
    try:
        import shapefile  # type: ignore

        return shapefile
    except ImportError as exc:
        raise RuntimeError("population_overlay.py requires pyshp. Install with: python3 -m pip install pyshp") from exc


def census_block_population(state: str, county: str) -> dict[str, int]:
    url = (
        "https://api.census.gov/data/2020/dec/pl"
        f"?get=P1_001N&for=block:*&in=state:{state}%20county:{county}%20tract:*"
    )
    with urllib.request.urlopen(url, timeout=120) as response:
        data = json.load(response)
    header = data[0]
    populations: dict[str, int] = {}
    for row in data[1:]:
        record = dict(zip(header, row))
        geoid = record["state"] + record["county"] + record["tract"] + record["block"]
        populations[geoid] = int(record["P1_001N"])
    return populations


def census_place_population(state: str) -> dict[str, int]:
    url = f"https://api.census.gov/data/2020/dec/pl?get=NAME,P1_001N&for=place:*&in=state:{state}"
    with urllib.request.urlopen(url, timeout=120) as response:
        data = json.load(response)
    header = data[0]
    populations: dict[str, int] = {}
    for row in data[1:]:
        record = dict(zip(header, row))
        populations[state + record["place"]] = int(record["P1_001N"])
    return populations


def xy_from_lat_lon(lat: float, lon: float, site_lat: float, site_lon: float) -> tuple[float, float]:
    y_m = (lat - site_lat) * 111_320.0
    x_m = (lon - site_lon) * 111_320.0 * math.cos(math.radians(site_lat))
    return x_m, y_m


def offset_site(site_lat: float, site_lon: float, shift_x_km: float, shift_y_km: float) -> tuple[float, float]:
    lat = site_lat + shift_y_km * 1000.0 / 111_320.0
    lon = site_lon + shift_x_km * 1000.0 / (111_320.0 * math.cos(math.radians(site_lat)))
    return lat, lon


def load_blocks(cache: Path, state: str, county: str, site_lat: float, site_lon: float, radius_km: float) -> list[dict[str, object]]:
    shapefile = load_pyshp()
    shp = ensure_block_shapefile(cache)
    populations = census_block_population(state, county)
    reader = shapefile.Reader(str(shp))
    blocks: list[dict[str, object]] = []
    for shape_record in reader.iterShapeRecords():
        record = shape_record.record.as_dict()
        if record["STATEFP20"] != state or record["COUNTYFP20"] != county:
            continue
        population = populations.get(record["GEOID20"], 0)
        if population <= 0:
            continue
        lat = float(record["INTPTLAT20"])
        lon = float(record["INTPTLON20"])
        x_m, y_m = xy_from_lat_lon(lat, lon, site_lat, site_lon)
        distance_km = math.hypot(x_m, y_m) / 1000.0
        if distance_km <= radius_km:
            blocks.append(
                {
                    "geoid": record["GEOID20"],
                    "population": population,
                    "lat": lat,
                    "lon": lon,
                    "distance_km": distance_km,
                    "bearing_deg": (math.degrees(math.atan2(x_m, y_m)) + 360.0) % 360.0,
                    "x_m": x_m,
                    "y_m": y_m,
                }
            )
    return blocks


def load_event_grids(run_dir: Path) -> dict[str, list[dict[str, float | str]]]:
    events_dir = run_dir / "events"
    if not events_dir.exists():
        raise RuntimeError(f"No events directory found in {run_dir}")
    event_grids: dict[str, list[dict[str, float | str]]] = {}
    for path in sorted(events_dir.glob("*_grid.csv")):
        rows: list[dict[str, float | str]] = []
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                rows.append(
                    {
                        "receptor_id": row["receptor_id"],
                        "x_m": float(row["x_m"]),
                        "y_m": float(row["y_m"]),
                        "avg_increment_ug_m3": float(row["avg_increment_ug_m3"]),
                        "max_hourly_increment_ug_m3": float(row["max_hourly_increment_ug_m3"]),
                        "avg_increment_percent_of_event_avg_bg": float(row["avg_increment_percent_of_event_avg_bg"] or 0.0),
                    }
                )
        event_grids[path.stem.replace("_grid", "")] = rows
    return event_grids


def event_grid_domain_radius_km(event_grids: dict[str, list[dict[str, float | str]]]) -> float:
    radii = [
        max((math.hypot(float(row["x_m"]), float(row["y_m"])) / 1000.0 for row in grid), default=0.0)
        for grid in event_grids.values()
    ]
    return min(radii, default=0.0)


def nearest_receptor(grid: list[dict[str, float | str]], x_m: float, y_m: float) -> dict[str, float | str]:
    return min(grid, key=lambda row: (float(row["x_m"]) - x_m) ** 2 + (float(row["y_m"]) - y_m) ** 2)


def assign_block_exposure(
    blocks: list[dict[str, object]],
    event_grids: dict[str, list[dict[str, float | str]]],
    site_lat: float,
    site_lon: float,
) -> list[dict[str, object]]:
    results: list[dict[str, object]] = []
    if not event_grids:
        return results
    reference_grid = next(iter(event_grids.values()))
    event_grid_indexes = [
        (event_id, {str(row["receptor_id"]): row for row in grid}, grid)
        for event_id, grid in event_grids.items()
    ]
    for block in blocks:
        x_m, y_m = xy_from_lat_lon(float(block["lat"]), float(block["lon"]), site_lat, site_lon)
        nearest_reference = nearest_receptor(reference_grid, x_m, y_m)
        nearest_receptor_id = str(nearest_reference["receptor_id"])
        nearest_error_km = math.hypot(float(nearest_reference["x_m"]) - x_m, float(nearest_reference["y_m"]) - y_m) / 1000.0
        best: dict[str, object] | None = None
        for event_id, grid_index, grid in event_grid_indexes:
            receptor = grid_index.get(nearest_receptor_id)
            if receptor is None:
                receptor = nearest_receptor(grid, x_m, y_m)
            avg_increment = float(receptor["avg_increment_ug_m3"])
            if best is None or avg_increment > float(best["max_avg_increment_ug_m3"]):
                best = {
                    **block,
                    "x_m": x_m,
                    "y_m": y_m,
                    "distance_km": math.hypot(x_m, y_m) / 1000.0,
                    "bearing_deg": (math.degrees(math.atan2(x_m, y_m)) + 360.0) % 360.0,
                    "max_avg_increment_ug_m3": avg_increment,
                    "max_hourly_increment_ug_m3": float(receptor["max_hourly_increment_ug_m3"]),
                    "percent_of_event_avg_background": float(receptor["avg_increment_percent_of_event_avg_bg"]),
                    "event_id": event_id,
                    "receptor_id": receptor["receptor_id"],
                    "nearest_receptor_error_km": nearest_error_km,
                }
        if best is not None:
            results.append(best)
    return results


def threshold_summary(rows: list[dict[str, object]], thresholds: Iterable[float]) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for threshold in thresholds:
        matching = [row for row in rows if float(row["max_avg_increment_ug_m3"]) >= threshold]
        out.append(
            {
                "threshold_ug_m3": threshold,
                "population": sum(int(row["population"]) for row in matching),
                "blocks": len(matching),
            }
        )
    return out


def threshold_column(threshold: float) -> str:
    clean = f"{threshold:g}".replace(".", "p")
    return f"population_ge_{clean}ug_m3"


def weighted_percentile_pairs(pairs: list[tuple[float, int]], percentile: float) -> float:
    pairs = sorted(pairs)
    total = sum(weight for _, weight in pairs)
    if total <= 0:
        return 0.0
    target = total * percentile / 100.0
    running = 0
    for value, weight in pairs:
        running += weight
        if running >= target:
            return value
    return pairs[-1][0] if pairs else 0.0


def event_population_summary(
    blocks: list[dict[str, object]],
    event_grids: dict[str, list[dict[str, float | str]]],
    site_lat: float,
    site_lon: float,
    thresholds: Iterable[float],
) -> list[dict[str, object]]:
    if not event_grids:
        return []
    threshold_values = list(thresholds)
    reference_grid = next(iter(event_grids.values()))
    assignments: list[tuple[int, str]] = []
    for block in blocks:
        x_m, y_m = xy_from_lat_lon(float(block["lat"]), float(block["lon"]), site_lat, site_lon)
        nearest_reference = nearest_receptor(reference_grid, x_m, y_m)
        assignments.append((int(block["population"]), str(nearest_reference["receptor_id"])))

    rows: list[dict[str, object]] = []
    for event_id, grid in event_grids.items():
        grid_index = {str(row["receptor_id"]): row for row in grid}
        pairs: list[tuple[float, int]] = []
        for population, receptor_id in assignments:
            receptor = grid_index.get(receptor_id)
            if receptor is None:
                continue
            pairs.append((float(receptor["avg_increment_ug_m3"]), population))
        row: dict[str, object] = {
            "event_id": event_id,
            "population_total": sum(weight for _, weight in pairs),
            "p50_increment_ug_m3": f"{weighted_percentile_pairs(pairs, 50):.6f}",
            "p95_increment_ug_m3": f"{weighted_percentile_pairs(pairs, 95):.6f}",
            "p99_increment_ug_m3": f"{weighted_percentile_pairs(pairs, 99):.6f}",
            "max_populated_block_increment_ug_m3": f"{max((value for value, _ in pairs), default=0.0):.6f}",
        }
        for threshold in threshold_values:
            row[threshold_column(threshold)] = sum(
                population for value, population in pairs if value >= threshold
            )
        rows.append(row)
    return rows


def within_radius(rows: list[dict[str, object]], radius_km: float) -> list[dict[str, object]]:
    return [row for row in rows if float(row["distance_km"]) <= radius_km]


def weighted_percentile(rows: list[dict[str, object]], percentile: float) -> float:
    return weighted_percentile_pairs(
        [(float(row["max_avg_increment_ug_m3"]), int(row["population"])) for row in rows],
        percentile,
    )


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def load_places(cache: Path, state: str, site_lat: float, site_lon: float, radius_km: float) -> list[dict[str, object]]:
    gazetteer = ensure_place_gazetteer(cache)
    populations = census_place_population(state)
    places: list[dict[str, object]] = []
    with gazetteer.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        lon_field = next(field for field in reader.fieldnames or [] if field.strip() == "INTPTLONG")
        for row in reader:
            if row["USPS"] != "UT":
                continue
            lat = float(row["INTPTLAT"])
            lon = float(row[lon_field])
            x_m, y_m = xy_from_lat_lon(lat, lon, site_lat, site_lon)
            distance_km = math.hypot(x_m, y_m) / 1000.0
            if distance_km <= radius_km:
                places.append(
                    {
                        "geoid": row["GEOID"],
                        "name": row["NAME"],
                        "population": populations.get(row["GEOID"], 0),
                        "lat": lat,
                        "lon": lon,
                    }
                )
    return places


def assign_place_exposure(
    places: list[dict[str, object]],
    event_grids: dict[str, list[dict[str, float | str]]],
    site_lat: float,
    site_lon: float,
    model_radius_km: float | None = None,
) -> list[dict[str, object]]:
    block_like = [
        {
            "geoid": place["geoid"],
            "population": place["population"],
            "lat": place["lat"],
            "lon": place["lon"],
            "name": place["name"],
        }
        for place in places
    ]
    assigned = assign_block_exposure(block_like, event_grids, site_lat, site_lon)
    if model_radius_km is not None:
        for row in assigned:
            outside_km = max(0.0, float(row["distance_km"]) - model_radius_km)
            row["inside_model_domain"] = outside_km == 0.0
            row["outside_model_domain_km"] = outside_km
    return sorted(assigned, key=lambda row: float(row["max_avg_increment_ug_m3"]), reverse=True)


def sensitivity_shifts(distances_km: Iterable[float], include_diagonal: bool) -> list[tuple[str, float, float]]:
    shifts = [("base", 0.0, 0.0)]
    directions = [("east", 1, 0), ("west", -1, 0), ("north", 0, 1), ("south", 0, -1)]
    if include_diagonal:
        directions.extend([("northeast", 1, 1), ("northwest", -1, 1), ("southeast", 1, -1), ("southwest", -1, -1)])
    for distance in distances_km:
        if distance == 0:
            continue
        for name, sx, sy in directions:
            scale = distance / math.hypot(sx, sy)
            shifts.append((f"{distance:g}km_{name}", sx * scale, sy * scale))
    return shifts


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    output_dir = args.output_dir or args.run_dir / "population_overlay"
    event_grids = load_event_grids(args.run_dir)
    model_radius_km = event_grid_domain_radius_km(event_grids)
    base_blocks = load_blocks(args.census_cache, args.state, args.county, args.site_lat, args.site_lon, args.radius_km + max(args.site_sensitivity_km or [0]))
    base_blocks_in_radius = within_radius(base_blocks, args.radius_km)

    base_rows = within_radius(assign_block_exposure(base_blocks, event_grids, args.site_lat, args.site_lon), args.radius_km)
    write_csv(
        output_dir / "population_overlay_blocks.csv",
        base_rows,
        [
            "geoid",
            "population",
            "lat",
            "lon",
            "distance_km",
            "bearing_deg",
            "max_avg_increment_ug_m3",
            "max_hourly_increment_ug_m3",
            "percent_of_event_avg_background",
            "event_id",
            "receptor_id",
            "nearest_receptor_error_km",
        ],
    )
    write_csv(output_dir / "population_threshold_summary.csv", threshold_summary(base_rows, args.thresholds), ["threshold_ug_m3", "population", "blocks"])
    event_population_fields = [
        "event_id",
        "population_total",
        "p50_increment_ug_m3",
        "p95_increment_ug_m3",
        "p99_increment_ug_m3",
        "max_populated_block_increment_ug_m3",
        *(threshold_column(threshold) for threshold in args.thresholds),
    ]
    write_csv(
        output_dir / "population_event_threshold_summary.csv",
        event_population_summary(base_blocks_in_radius, event_grids, args.site_lat, args.site_lon, args.thresholds),
        event_population_fields,
    )

    weighted_rows = [
        {"percentile": percentile, "max_avg_increment_ug_m3": f"{weighted_percentile(base_rows, percentile):.6f}"}
        for percentile in [50, 75, 90, 95, 99]
    ]
    write_csv(output_dir / "population_weighted_percentiles.csv", weighted_rows, ["percentile", "max_avg_increment_ug_m3"])

    requested_place_radius_km = args.place_radius_km if args.place_radius_km is not None else args.radius_km
    place_radius_km = requested_place_radius_km if args.include_outside_grid_places else min(requested_place_radius_km, model_radius_km)
    places = load_places(args.census_cache, args.state, args.site_lat, args.site_lon, place_radius_km)
    place_rows = assign_place_exposure(places, event_grids, args.site_lat, args.site_lon, model_radius_km=model_radius_km)
    write_csv(
        output_dir / "place_exposure_summary.csv",
        place_rows,
        [
            "geoid",
            "name",
            "population",
            "lat",
            "lon",
            "distance_km",
            "bearing_deg",
            "max_avg_increment_ug_m3",
            "max_hourly_increment_ug_m3",
            "percent_of_event_avg_background",
            "event_id",
            "receptor_id",
            "nearest_receptor_error_km",
            "inside_model_domain",
            "outside_model_domain_km",
        ],
    )

    sensitivity_rows: list[dict[str, object]] = []
    for label, shift_x_km, shift_y_km in sensitivity_shifts(args.site_sensitivity_km, args.include_diagonal_shifts):
        shifted_lat, shifted_lon = offset_site(args.site_lat, args.site_lon, shift_x_km, shift_y_km)
        shifted_rows = within_radius(assign_block_exposure(base_blocks, event_grids, shifted_lat, shifted_lon), args.radius_km)
        summary = {row["threshold_ug_m3"]: row for row in threshold_summary(shifted_rows, args.thresholds)}
        sensitivity_rows.append(
            {
                "shift": label,
                "shift_x_km": shift_x_km,
                "shift_y_km": shift_y_km,
                "site_lat": shifted_lat,
                "site_lon": shifted_lon,
                "population_total": sum(int(row["population"]) for row in shifted_rows),
                "p95_weighted_increment_ug_m3": f"{weighted_percentile(shifted_rows, 95):.6f}",
                "population_ge_2ug_m3": summary.get(2.0, {}).get("population", ""),
                "population_ge_5ug_m3": summary.get(5.0, {}).get("population", ""),
                "population_ge_10ug_m3": summary.get(10.0, {}).get("population", ""),
                "max_populated_block_increment_ug_m3": f"{max((float(row['max_avg_increment_ug_m3']) for row in shifted_rows), default=0.0):.6f}",
            }
        )
    write_csv(
        output_dir / "site_location_sensitivity.csv",
        sensitivity_rows,
        [
            "shift",
            "shift_x_km",
            "shift_y_km",
            "site_lat",
            "site_lon",
            "population_total",
            "p95_weighted_increment_ug_m3",
            "population_ge_2ug_m3",
            "population_ge_5ug_m3",
            "population_ge_10ug_m3",
            "max_populated_block_increment_ug_m3",
        ],
    )

    print(f"Wrote population overlay outputs to {output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
