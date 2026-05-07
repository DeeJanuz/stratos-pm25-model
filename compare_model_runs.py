#!/usr/bin/env python3
"""Build assumption-labeled PM2.5 comparison tables from completed model runs.

The comparison output is intentionally descriptive: it keeps the event-window
monitor background, modeled incremental addition, and arithmetic
background-plus-increment total in separate columns so the tables do not have
to argue a conclusion. The monitor background is not a place-specific rural
baseline unless a place is actually represented by that monitor.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import math
import sys
from pathlib import Path

import stratos_pm25_model as model


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare completed Stratos PM2.5 screening runs.")
    parser.add_argument("--scenario", action="append", required=True, metavar="LABEL=RUN_DIR")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--slc-station", default="HW")
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache"))
    return parser.parse_args(argv)


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_scenario(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise ValueError(f"Scenario must be LABEL=RUN_DIR, got {value!r}")
    label, path = value.split("=", 1)
    if not label.strip() or not path.strip():
        raise ValueError(f"Scenario must be LABEL=RUN_DIR, got {value!r}")
    return label.strip(), Path(path).expanduser()


def safe_float(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def fmt(value: float | None, digits: int = 3) -> str:
    if value is None or math.isnan(value):
        return ""
    return f"{value:.{digits}f}"


def plus(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left + right


def percent_of(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None or baseline <= 0:
        return None
    return 100.0 * value / baseline


def years_from_station_usage(run_dir: Path) -> list[int]:
    years = []
    for row in read_csv(run_dir / "station_usage.csv"):
        value = row.get("year")
        if value:
            years.append(int(value))
    return years


def station_usage_text(run_dir: Path) -> str:
    rows = read_csv(run_dir / "station_usage.csv")
    return "; ".join(f"{row['year']}: met {row['met_station']}, PM2.5 {row['pm25_station']}" for row in rows)


def metadata_line(run_dir: Path, prefix: str) -> str:
    readme = run_dir / "README.md"
    if not readme.exists():
        return ""
    for line in readme.read_text(encoding="utf-8").splitlines():
        if line.startswith(prefix):
            return line.removeprefix(prefix).strip()
    return ""


def load_monitor_stats(
    station: str,
    years: list[int],
    cache_dir: Path,
) -> tuple[dict[dt.datetime, float], dict[dt.datetime, float]]:
    values: dict[dt.datetime, float] = {}
    rolling: dict[dt.datetime, float] = {}
    for year in sorted(set(years)):
        series = model.load_utah_station_series(year, "PM2.5", station, cache_dir)
        times = sorted(series)
        rolled = model.rolling_average([series[timestamp] for timestamp in times], 24)
        for timestamp, value, rolling_value in zip(times, (series[t] for t in times), rolled):
            values[timestamp] = value
            if rolling_value is not None:
                rolling[timestamp] = rolling_value
    return values, rolling


def monitor_window_stats(
    values: dict[dt.datetime, float],
    rolling: dict[dt.datetime, float],
    start: str,
    end: str,
) -> tuple[float | None, float | None]:
    start_dt = dt.datetime.fromisoformat(start)
    end_dt = dt.datetime.fromisoformat(end)
    window_values = [value for timestamp, value in values.items() if start_dt <= timestamp <= end_dt]
    window_rolling = [value for timestamp, value in rolling.items() if start_dt <= timestamp <= end_dt]
    avg = sum(window_values) / len(window_values) if window_values else None
    peak_24h = max(window_rolling) if window_rolling else None
    return avg, peak_24h


def fmt_timestamp(timestamp: dt.datetime | None) -> str:
    if timestamp is None:
        return ""
    return timestamp.isoformat(sep=" ")


def max_monitor_value(rows: list[tuple[dt.datetime, float]]) -> tuple[dt.datetime | None, float | None]:
    if not rows:
        return None, None
    return max(rows, key=lambda row: row[1])


def monitor_period_extremes(
    values: dict[dt.datetime, float],
    rolling: dict[dt.datetime, float],
    years: list[int],
) -> dict[str, object]:
    year_set = set(years)
    winter_values = [
        (timestamp, value)
        for timestamp, value in values.items()
        if timestamp.year in year_set and model.is_winter_hour(timestamp)
    ]
    winter_rolling = [
        (timestamp, value)
        for timestamp, value in rolling.items()
        if timestamp.year in year_set and model.is_winter_hour(timestamp)
    ]
    hourly_timestamp, hourly_value = max_monitor_value(winter_values)
    rolling_timestamp, rolling_value = max_monitor_value(winter_rolling)
    return {
        "winter_max_hourly_timestamp": hourly_timestamp,
        "winter_max_hourly_ug_m3": hourly_value,
        "winter_max_24h_timestamp": rolling_timestamp,
        "winter_max_24h_ug_m3": rolling_value,
    }


def monitor_event_window_extremes(
    event_rows: list[dict[str, str]],
    values: dict[dt.datetime, float],
    rolling: dict[dt.datetime, float],
) -> dict[str, object]:
    max_avg_event: dict[str, str] | None = None
    max_avg: float | None = None
    max_peak_event: dict[str, str] | None = None
    max_peak: float | None = None
    for event in event_rows:
        avg, peak = monitor_window_stats(values, rolling, event["start"], event["end"])
        if avg is not None and (max_avg is None or avg > max_avg):
            max_avg = avg
            max_avg_event = event
        if peak is not None and (max_peak is None or peak > max_peak):
            max_peak = peak
            max_peak_event = event
    return {
        "max_event_avg_ug_m3": max_avg,
        "max_event_avg_window": event_window(max_avg_event),
        "max_event_peak_24h_ug_m3": max_peak,
        "max_event_peak_24h_window": event_window(max_peak_event),
    }


def event_window(event: dict[str, str] | None) -> str:
    if event is None:
        return ""
    return f"{event['start']} to {event['end']}"


def event_grid_increments(
    run_dir: Path,
    receptor_ids: set[str],
) -> dict[str, dict[str, tuple[float | None, float | None]]]:
    increments_by_event: dict[str, dict[str, tuple[float | None, float | None]]] = {}
    for path in sorted((run_dir / "events").glob("*_grid.csv")):
        event_id = path.name.removesuffix("_grid.csv")
        event_values: dict[str, tuple[float | None, float | None]] = {}
        for row in read_csv(path):
            receptor_id = row.get("receptor_id", "")
            if receptor_id in receptor_ids:
                event_values[receptor_id] = (
                    safe_float(row.get("avg_increment_ug_m3")),
                    safe_float(row.get("max_hourly_increment_ug_m3")),
                )
        increments_by_event[event_id] = event_values
    return increments_by_event


def threshold_column(threshold: str) -> str:
    clean = threshold.replace(".", "p")
    return f"population_ge_{clean}ug_m3"


def build_population_row(label: str, run_dir: Path) -> dict[str, object]:
    row: dict[str, object] = {"scenario": label, "run_dir": str(run_dir)}
    thresholds = read_csv(run_dir / "population_overlay" / "population_threshold_summary.csv")
    for threshold_row in thresholds:
        row[threshold_column(threshold_row["threshold_ug_m3"])] = threshold_row["population"]
    percentiles = read_csv(run_dir / "population_overlay" / "population_weighted_percentiles.csv")
    for percentile_row in percentiles:
        row[f"p{percentile_row['percentile']}_increment_ug_m3"] = percentile_row["max_avg_increment_ug_m3"]
    blocks = read_csv(run_dir / "population_overlay" / "population_overlay_blocks.csv")
    row["population_total"] = sum(int(block["population"]) for block in blocks)
    row["blocks_total"] = len(blocks)
    return row


def build_assumption_row(label: str, run_dir: Path) -> dict[str, object]:
    return {
        "scenario": label,
        "run_dir": str(run_dir),
        "years": ", ".join(str(year) for year in years_from_station_usage(run_dir)),
        "station_usage": station_usage_text(run_dir),
        "site": metadata_line(run_dir, "- Site:"),
        "grid": metadata_line(run_dir, "- Grid radius/step:"),
        "mixing_height": metadata_line(run_dir, "- Mixing height:"),
        "stability": metadata_line(run_dir, "- Stability:"),
        "primary_pm25": metadata_line(run_dir, "- Total primary PM2.5:"),
        "nox": metadata_line(run_dir, "- Total NOx:"),
        "so2": metadata_line(run_dir, "- Total SO2:"),
        "nh3": metadata_line(run_dir, "- Total NH3:"),
        "voc": metadata_line(run_dir, "- Total VOC:"),
        "secondary_profile": metadata_line(run_dir, "- Secondary profile:"),
    }


def build_event_population_rows(label: str, run_dir: Path) -> list[dict[str, object]]:
    event_rows_by_id = {row["event_id"]: row for row in read_csv(run_dir / "historical_event_summary.csv")}
    rows: list[dict[str, object]] = []
    for pop_row in read_csv(run_dir / "population_overlay" / "population_event_threshold_summary.csv"):
        event = event_rows_by_id.get(pop_row["event_id"], {})
        rows.append(
            {
                "scenario": label,
                "event_id": pop_row["event_id"],
                "start": event.get("start", ""),
                "end": event.get("end", ""),
                "duration_hours": event.get("duration_hours", ""),
                "avg_background_pm25_ug_m3": event.get("avg_background_pm25_ug_m3", ""),
                **{key: value for key, value in pop_row.items() if key != "event_id"},
            }
        )
    return rows


def comparison_rows(label: str, run_dir: Path, slc_values: dict[dt.datetime, float], slc_rolling: dict[dt.datetime, float]) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    event_rows_by_id = {row["event_id"]: row for row in read_csv(run_dir / "historical_event_summary.csv")}
    event_comparison: list[dict[str, object]] = []
    for event in event_rows_by_id.values():
        slc_avg, slc_peak = monitor_window_stats(slc_values, slc_rolling, event["start"], event["end"])
        local_bg = safe_float(event.get("avg_background_pm25_ug_m3"))
        local_peak = safe_float(event.get("peak_background_pm25_ug_m3"))
        max_increment = safe_float(event.get("max_grid_avg_increment_ug_m3"))
        p95_increment = safe_float(event.get("p95_grid_avg_increment_ug_m3"))
        box_increment = safe_float(event.get("max_box_increment_ug_m3"))
        event_comparison.append(
            {
                "scenario": label,
                "event_id": event["event_id"],
                "start": event["start"],
                "end": event["end"],
                "duration_hours": event["duration_hours"],
                "background_monitor_avg_ug_m3": fmt(local_bg),
                "background_monitor_peak_24h_ug_m3": fmt(local_peak),
                "background_monitor_is_place_specific": "false",
                "max_physical_increment_ug_m3": fmt(max_increment),
                "background_monitor_plus_max_physical_increment_ug_m3": fmt(plus(local_bg, max_increment)),
                "p95_grid_increment_ug_m3": fmt(p95_increment),
                "mixed_box_increment_ug_m3": fmt(box_increment),
                "background_monitor_plus_mixed_box_increment_ug_m3": fmt(plus(local_bg, box_increment)),
                "slc_hawthorne_avg_ug_m3": fmt(slc_avg),
                "slc_hawthorne_peak_24h_ug_m3": fmt(slc_peak),
            }
        )

    place_comparison: list[dict[str, object]] = []
    for place in read_csv(run_dir / "population_overlay" / "place_exposure_summary.csv"):
        event = event_rows_by_id.get(place["event_id"])
        if event is None:
            continue
        slc_avg, slc_peak = monitor_window_stats(slc_values, slc_rolling, event["start"], event["end"])
        increment = safe_float(place.get("max_avg_increment_ug_m3"))
        local_bg = safe_float(event.get("avg_background_pm25_ug_m3"))
        local_peak = safe_float(event.get("peak_background_pm25_ug_m3"))
        place_comparison.append(
            {
                "scenario": label,
                "place": place["name"],
                "population": place["population"],
                "distance_km": fmt(safe_float(place.get("distance_km")), 1),
                "event_id": place["event_id"],
                "event_window": f"{event['start']} to {event['end']}",
                "background_monitor_avg_ug_m3": fmt(local_bg),
                "background_monitor_is_place_specific": "false",
                "modeled_increment_ug_m3": fmt(increment),
                "background_monitor_plus_modeled_increment_ug_m3": fmt(plus(local_bg, increment)),
                "increment_percent_of_background_monitor": fmt(percent_of(increment, local_bg), 1),
                "background_monitor_peak_24h_ug_m3": fmt(local_peak),
                "slc_hawthorne_avg_ug_m3": fmt(slc_avg),
                "increment_percent_of_slc_avg": fmt(percent_of(increment, slc_avg), 1),
                "slc_hawthorne_peak_24h_ug_m3": fmt(slc_peak),
                "nearest_receptor_error_km": fmt(safe_float(place.get("nearest_receptor_error_km")), 2),
                "inside_model_domain": place.get("inside_model_domain", ""),
            }
        )
    return event_comparison, place_comparison


def build_bad_case_rows(
    label: str,
    run_dir: Path,
    slc_values: dict[dt.datetime, float],
    slc_rolling: dict[dt.datetime, float],
) -> list[dict[str, object]]:
    event_rows = read_csv(run_dir / "historical_event_summary.csv")
    event_rows_by_id = {row["event_id"]: row for row in event_rows}
    places = read_csv(run_dir / "population_overlay" / "place_exposure_summary.csv")
    receptor_ids = {place["receptor_id"] for place in places if place.get("receptor_id")}
    increments_by_event = event_grid_increments(run_dir, receptor_ids)
    slc_model_window_extremes = monitor_event_window_extremes(event_rows, slc_values, slc_rolling)
    slc_period_extremes = monitor_period_extremes(slc_values, slc_rolling, years_from_station_usage(run_dir))

    rows: list[dict[str, object]] = []
    for place in places:
        receptor_id = place.get("receptor_id", "")
        max_total: float | None = None
        max_total_increment: float | None = None
        max_total_background: float | None = None
        max_total_event: dict[str, str] | None = None
        max_hourly_total: float | None = None
        max_hourly_increment: float | None = None
        max_hourly_background: float | None = None
        max_hourly_event: dict[str, str] | None = None

        for event in event_rows:
            increments = increments_by_event.get(event["event_id"], {}).get(receptor_id)
            if increments is None:
                continue
            avg_increment, hourly_increment = increments
            background_avg = safe_float(event.get("avg_background_pm25_ug_m3"))
            background_peak = safe_float(event.get("peak_background_pm25_ug_m3"))
            total = plus(background_avg, avg_increment)
            hourly_total = plus(background_peak, hourly_increment)
            if total is not None and (max_total is None or total > max_total):
                max_total = total
                max_total_increment = avg_increment
                max_total_background = background_avg
                max_total_event = event
            if hourly_total is not None and (max_hourly_total is None or hourly_total > max_hourly_total):
                max_hourly_total = hourly_total
                max_hourly_increment = hourly_increment
                max_hourly_background = background_peak
                max_hourly_event = event

        max_increment_event = event_rows_by_id.get(place.get("event_id", ""))
        rows.append(
            {
                "scenario": label,
                "place": place["name"],
                "population": place["population"],
                "distance_km": fmt(safe_float(place.get("distance_km")), 1),
                "receptor_id": receptor_id,
                "background_monitor_is_place_specific": "false",
                "max_modeled_event_avg_total_ug_m3": fmt(max_total),
                "max_modeled_event_avg_window": event_window(max_total_event),
                "background_monitor_avg_at_modeled_max_ug_m3": fmt(max_total_background),
                "modeled_increment_at_modeled_max_ug_m3": fmt(max_total_increment),
                "max_increment_ug_m3": fmt(safe_float(place.get("max_avg_increment_ug_m3"))),
                "max_increment_window": event_window(max_increment_event),
                "max_modeled_hourly_total_ug_m3": fmt(max_hourly_total),
                "max_modeled_hourly_window": event_window(max_hourly_event),
                "background_monitor_peak_at_hourly_max_ug_m3": fmt(max_hourly_background),
                "modeled_hourly_increment_at_hourly_max_ug_m3": fmt(max_hourly_increment),
                "slc_hawthorne_max_model_window_avg_ug_m3": fmt(slc_model_window_extremes["max_event_avg_ug_m3"]),
                "slc_hawthorne_max_model_window": slc_model_window_extremes["max_event_avg_window"],
                "modeled_total_percent_of_slc_max_model_window_avg": fmt(
                    percent_of(max_total, slc_model_window_extremes["max_event_avg_ug_m3"]), 1
                ),
                "slc_hawthorne_max_model_window_24h_ug_m3": fmt(slc_model_window_extremes["max_event_peak_24h_ug_m3"]),
                "slc_hawthorne_max_model_window_24h_window": slc_model_window_extremes["max_event_peak_24h_window"],
                "slc_hawthorne_winter_max_24h_ug_m3": fmt(slc_period_extremes["winter_max_24h_ug_m3"]),
                "slc_hawthorne_winter_max_24h_timestamp": fmt_timestamp(
                    slc_period_extremes["winter_max_24h_timestamp"]
                ),
                "modeled_total_percent_of_slc_winter_max_24h": fmt(
                    percent_of(max_total, slc_period_extremes["winter_max_24h_ug_m3"]), 1
                ),
                "slc_hawthorne_winter_max_hourly_ug_m3": fmt(slc_period_extremes["winter_max_hourly_ug_m3"]),
                "slc_hawthorne_winter_max_hourly_timestamp": fmt_timestamp(
                    slc_period_extremes["winter_max_hourly_timestamp"]
                ),
                "modeled_hourly_total_percent_of_slc_winter_max_hourly": fmt(
                    percent_of(max_hourly_total, slc_period_extremes["winter_max_hourly_ug_m3"]), 1
                ),
            }
        )
    return rows


def build_max_increment_rows(
    label: str,
    run_dir: Path,
    slc_values: dict[dt.datetime, float],
    slc_rolling: dict[dt.datetime, float],
) -> list[dict[str, object]]:
    event_rows = read_csv(run_dir / "historical_event_summary.csv")
    event_rows_by_id = {row["event_id"]: row for row in event_rows}
    slc_model_window_extremes = monitor_event_window_extremes(event_rows, slc_values, slc_rolling)
    slc_period_extremes = monitor_period_extremes(slc_values, slc_rolling, years_from_station_usage(run_dir))
    rows: list[dict[str, object]] = []
    for place in read_csv(run_dir / "population_overlay" / "place_exposure_summary.csv"):
        event = event_rows_by_id.get(place["event_id"])
        if event is None:
            continue
        slc_same_window_avg, slc_same_window_peak = monitor_window_stats(
            slc_values, slc_rolling, event["start"], event["end"]
        )
        background_avg = safe_float(event.get("avg_background_pm25_ug_m3"))
        background_peak = safe_float(event.get("peak_background_pm25_ug_m3"))
        increment = safe_float(place.get("max_avg_increment_ug_m3"))
        hourly_increment = safe_float(place.get("max_hourly_increment_ug_m3"))
        total = plus(background_avg, increment)
        hourly_total = plus(background_peak, hourly_increment)
        rows.append(
            {
                "scenario": label,
                "place": place["name"],
                "population": place["population"],
                "distance_km": fmt(safe_float(place.get("distance_km")), 1),
                "receptor_id": place.get("receptor_id", ""),
                "background_monitor_is_place_specific": "false",
                "max_increment_window": event_window(event),
                "background_monitor_avg_at_max_increment_ug_m3": fmt(background_avg),
                "modeled_increment_at_max_increment_ug_m3": fmt(increment),
                "background_monitor_plus_max_increment_ug_m3": fmt(total),
                "background_monitor_peak_24h_at_max_increment_ug_m3": fmt(background_peak),
                "modeled_hourly_increment_during_max_increment_event_ug_m3": fmt(hourly_increment),
                "background_monitor_peak_plus_hourly_increment_ug_m3": fmt(hourly_total),
                "slc_hawthorne_avg_same_window_ug_m3": fmt(slc_same_window_avg),
                "slc_hawthorne_peak_24h_same_window_ug_m3": fmt(slc_same_window_peak),
                "max_increment_total_percent_of_slc_same_window_avg": fmt(percent_of(total, slc_same_window_avg), 1),
                "slc_hawthorne_max_model_window_avg_ug_m3": fmt(slc_model_window_extremes["max_event_avg_ug_m3"]),
                "slc_hawthorne_max_model_window": slc_model_window_extremes["max_event_avg_window"],
                "max_increment_total_percent_of_slc_max_model_window_avg": fmt(
                    percent_of(total, slc_model_window_extremes["max_event_avg_ug_m3"]), 1
                ),
                "slc_hawthorne_winter_max_24h_ug_m3": fmt(slc_period_extremes["winter_max_24h_ug_m3"]),
                "slc_hawthorne_winter_max_24h_timestamp": fmt_timestamp(
                    slc_period_extremes["winter_max_24h_timestamp"]
                ),
                "max_increment_total_percent_of_slc_winter_max_24h": fmt(
                    percent_of(total, slc_period_extremes["winter_max_24h_ug_m3"]), 1
                ),
            }
        )
    return rows


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    scenarios = [parse_scenario(value) for value in args.scenario]
    all_years: list[int] = []
    for _, run_dir in scenarios:
        all_years.extend(years_from_station_usage(run_dir))
    slc_values, slc_rolling = load_monitor_stats(args.slc_station, all_years, args.cache_dir)

    population_rows = []
    assumption_rows = []
    event_rows = []
    place_rows = []
    bad_case_rows = []
    max_increment_rows = []
    event_population_rows = []
    for label, run_dir in scenarios:
        population_rows.append(build_population_row(label, run_dir))
        assumption_rows.append(build_assumption_row(label, run_dir))
        event_population_rows.extend(build_event_population_rows(label, run_dir))
        scenario_event_rows, scenario_place_rows = comparison_rows(label, run_dir, slc_values, slc_rolling)
        event_rows.extend(scenario_event_rows)
        place_rows.extend(scenario_place_rows)
        bad_case_rows.extend(build_bad_case_rows(label, run_dir, slc_values, slc_rolling))
        max_increment_rows.extend(build_max_increment_rows(label, run_dir, slc_values, slc_rolling))

    threshold_fields = sorted({key for row in population_rows for key in row if key.startswith("population_ge_")})
    percentile_fields = [f"p{percentile}_increment_ug_m3" for percentile in [50, 75, 90, 95, 99]]
    write_csv(
        args.output_dir / "scenario_population_comparison.csv",
        population_rows,
        ["scenario", "run_dir", "population_total", "blocks_total", *percentile_fields, *threshold_fields],
    )
    event_population_threshold_fields = sorted(
        {key for row in event_population_rows for key in row if key.startswith("population_ge_")}
    )
    write_csv(
        args.output_dir / "scenario_event_population_comparison.csv",
        event_population_rows,
        [
            "scenario",
            "event_id",
            "start",
            "end",
            "duration_hours",
            "avg_background_pm25_ug_m3",
            "population_total",
            "p50_increment_ug_m3",
            "p95_increment_ug_m3",
            "p99_increment_ug_m3",
            "max_populated_block_increment_ug_m3",
            *event_population_threshold_fields,
        ],
    )
    write_csv(
        args.output_dir / "scenario_assumptions.csv",
        assumption_rows,
        [
            "scenario",
            "run_dir",
            "years",
            "station_usage",
            "site",
            "grid",
            "mixing_height",
            "stability",
            "primary_pm25",
            "nox",
            "so2",
            "nh3",
            "voc",
            "secondary_profile",
        ],
    )
    write_csv(
        args.output_dir / "scenario_event_comparison.csv",
        event_rows,
        [
            "scenario",
            "event_id",
            "start",
            "end",
            "duration_hours",
            "background_monitor_avg_ug_m3",
            "background_monitor_peak_24h_ug_m3",
            "background_monitor_is_place_specific",
            "max_physical_increment_ug_m3",
            "background_monitor_plus_max_physical_increment_ug_m3",
            "p95_grid_increment_ug_m3",
            "mixed_box_increment_ug_m3",
            "background_monitor_plus_mixed_box_increment_ug_m3",
            "slc_hawthorne_avg_ug_m3",
            "slc_hawthorne_peak_24h_ug_m3",
        ],
    )
    write_csv(
        args.output_dir / "scenario_place_comparison.csv",
        place_rows,
        [
            "scenario",
            "place",
            "population",
            "distance_km",
            "event_id",
            "event_window",
            "background_monitor_avg_ug_m3",
            "background_monitor_is_place_specific",
            "modeled_increment_ug_m3",
            "background_monitor_plus_modeled_increment_ug_m3",
            "increment_percent_of_background_monitor",
            "background_monitor_peak_24h_ug_m3",
            "slc_hawthorne_avg_ug_m3",
            "increment_percent_of_slc_avg",
            "slc_hawthorne_peak_24h_ug_m3",
            "nearest_receptor_error_km",
            "inside_model_domain",
        ],
    )
    write_csv(
        args.output_dir / "scenario_bad_case_benchmark.csv",
        bad_case_rows,
        [
            "scenario",
            "place",
            "population",
            "distance_km",
            "receptor_id",
            "background_monitor_is_place_specific",
            "max_modeled_event_avg_total_ug_m3",
            "max_modeled_event_avg_window",
            "background_monitor_avg_at_modeled_max_ug_m3",
            "modeled_increment_at_modeled_max_ug_m3",
            "max_increment_ug_m3",
            "max_increment_window",
            "max_modeled_hourly_total_ug_m3",
            "max_modeled_hourly_window",
            "background_monitor_peak_at_hourly_max_ug_m3",
            "modeled_hourly_increment_at_hourly_max_ug_m3",
            "slc_hawthorne_max_model_window_avg_ug_m3",
            "slc_hawthorne_max_model_window",
            "modeled_total_percent_of_slc_max_model_window_avg",
            "slc_hawthorne_max_model_window_24h_ug_m3",
            "slc_hawthorne_max_model_window_24h_window",
            "slc_hawthorne_winter_max_24h_ug_m3",
            "slc_hawthorne_winter_max_24h_timestamp",
            "modeled_total_percent_of_slc_winter_max_24h",
            "slc_hawthorne_winter_max_hourly_ug_m3",
            "slc_hawthorne_winter_max_hourly_timestamp",
            "modeled_hourly_total_percent_of_slc_winter_max_hourly",
        ],
    )
    write_csv(
        args.output_dir / "scenario_max_increment_benchmark.csv",
        max_increment_rows,
        [
            "scenario",
            "place",
            "population",
            "distance_km",
            "receptor_id",
            "background_monitor_is_place_specific",
            "max_increment_window",
            "background_monitor_avg_at_max_increment_ug_m3",
            "modeled_increment_at_max_increment_ug_m3",
            "background_monitor_plus_max_increment_ug_m3",
            "background_monitor_peak_24h_at_max_increment_ug_m3",
            "modeled_hourly_increment_during_max_increment_event_ug_m3",
            "background_monitor_peak_plus_hourly_increment_ug_m3",
            "slc_hawthorne_avg_same_window_ug_m3",
            "slc_hawthorne_peak_24h_same_window_ug_m3",
            "max_increment_total_percent_of_slc_same_window_avg",
            "slc_hawthorne_max_model_window_avg_ug_m3",
            "slc_hawthorne_max_model_window",
            "max_increment_total_percent_of_slc_max_model_window_avg",
            "slc_hawthorne_winter_max_24h_ug_m3",
            "slc_hawthorne_winter_max_24h_timestamp",
            "max_increment_total_percent_of_slc_winter_max_24h",
        ],
    )
    print(f"Wrote comparison tables to {args.output_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
