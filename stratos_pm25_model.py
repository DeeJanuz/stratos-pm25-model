#!/usr/bin/env python3
"""Screening model for Stratos-area PM2.5 impacts during Utah inversion events.

This is a research/scoping tool, not a regulatory AERMOD/CMAQ replacement.
It improves on a centerline-only plume calculator by adding:

* Utah DAQ historical met and PM2.5 data ingestion.
* Winter inversion-event detection from PM2.5 and stagnation indicators.
* A receptor grid with wind-direction rotation and crosswind dispersion.
* Multiple stacks, simple plume-rise screening, and optional inversion-lid reflection.
* Regional box accumulation for trapped-basin "plume has mixed out" behavior.
* Configurable secondary PM2.5 precursor screening from NOx, SO2, NH3, and VOC.

The model intentionally keeps dependencies to the Python standard library so it
can run on a clean workstation. Fill in permit-grade emissions, exact source
coordinates, source geometry, and validated meteorology before relying on it.
"""

from __future__ import annotations

import argparse
import csv
import dataclasses
import datetime as dt
import math
import os
import statistics
import sys
import textwrap
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Iterable


UTAH_DAQ_ARCHIVE = "https://air.utah.gov/dataarchive"
MPH_TO_MPS = 0.44704
LB_HR_TO_G_S = 453.59237 / 3600.0
SECONDS_PER_HOUR = 3600.0
UG_PER_G = 1_000_000.0


@dataclasses.dataclass(frozen=True)
class Source:
    name: str
    x_m: float = 0.0
    y_m: float = 0.0
    primary_pm25_g_s: float = 51.0
    nox_g_s: float = 0.0
    so2_g_s: float = 0.0
    nh3_g_s: float = 0.0
    voc_g_s: float = 0.0
    stack_height_m: float = 150.0
    stack_diameter_m: float = 7.0
    exit_velocity_m_s: float = 20.0
    exit_temp_k: float = 390.0


@dataclasses.dataclass(frozen=True)
class SecondaryProfile:
    name: str
    nox_to_nitrate_fraction: float
    so2_to_sulfate_fraction: float
    nh3_to_ammonium_fraction: float
    voc_to_soa_fraction: float


SECONDARY_PROFILES = {
    "none": SecondaryProfile("none", 0.0, 0.0, 0.0, 0.0),
    # Conservative screening coefficients, intended for sensitivity analysis.
    # For NOx and SO2, the molecular mass uplift approximates nitrate/sulfate salts.
    "typical_inversion": SecondaryProfile("typical_inversion", 0.08, 0.15, 0.05, 0.02),
    "worst_inversion": SecondaryProfile("worst_inversion", 0.60, 0.80, 0.50, 0.20),
}


@dataclasses.dataclass(frozen=True)
class ModelConfig:
    site_lat: float = 41.7744825
    site_lon: float = -112.6559297
    grid_radius_km: float = 50.0
    grid_step_km: float = 5.0
    mixing_height_m: float = 400.0
    basin_area_km2: float = 6_000.0
    basin_vent_length_km: float = 120.0
    deposition_velocity_m_s: float = 0.0005
    receptor_height_m: float = 0.0
    stability: str = "F"
    meander_sigma_deg: float = 12.0
    inversion_lid_reflection: bool = True


@dataclasses.dataclass(frozen=True)
class MetHour:
    timestamp: dt.datetime
    wind_speed_m_s: float
    wind_dir_deg: float
    ambient_temp_c: float | None
    pm25_ug_m3: float | None
    pm25_24h_ug_m3: float | None = None


@dataclasses.dataclass(frozen=True)
class InversionEvent:
    event_id: str
    start: dt.datetime
    end: dt.datetime
    hours: tuple[MetHour, ...]

    @property
    def duration_hours(self) -> int:
        return len(self.hours)

    @property
    def peak_background_pm25(self) -> float | None:
        values = [h.pm25_24h_ug_m3 or h.pm25_ug_m3 for h in self.hours if h.pm25_ug_m3 is not None]
        return max(values) if values else None

    @property
    def avg_background_pm25(self) -> float | None:
        values = [h.pm25_ug_m3 for h in self.hours if h.pm25_ug_m3 is not None]
        return statistics.fmean(values) if values else None

    @property
    def avg_background_24h_pm25(self) -> float | None:
        values = [h.pm25_24h_ug_m3 for h in self.hours if h.pm25_24h_ug_m3 is not None]
        return statistics.fmean(values) if values else None

    @property
    def avg_wind_speed(self) -> float:
        return statistics.fmean(h.wind_speed_m_s for h in self.hours)


@dataclasses.dataclass(frozen=True)
class Receptor:
    receptor_id: str
    x_m: float
    y_m: float
    distance_km: float
    bearing_deg: float
    lat: float
    lon: float


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Simulate screening PM2.5 impacts for Stratos-area power generation.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent(
            """
            Examples:
              python3 stratos_pm25_model.py --mode all --years 2024 2025
              python3 stratos_pm25_model.py --mode historical --met-station BG --pm25-station BG --max-events 10
              python3 stratos_pm25_model.py --mode worst --nox-lb-hr 250 --nh3-lb-hr 40 --secondary-profile worst_inversion

            Utah DAQ station codes are used directly. BG is Brigham City and is the
            closest default station in the Utah DAQ archive for this screening run.
            """
        ),
    )
    parser.add_argument("--mode", choices=["all", "historical", "worst"], default="all")
    parser.add_argument("--years", nargs="+", type=int, default=[2022, 2023, 2024, 2025])
    parser.add_argument("--met-station", default="BG")
    parser.add_argument("--pm25-station", default="BG")
    parser.add_argument("--met-fallback-stations", nargs="*", default=["BV", "EN", "CV", "SM", "H3"])
    parser.add_argument("--pm25-fallback-stations", nargs="*", default=[])
    parser.add_argument("--cache-dir", type=Path, default=Path("data/cache"))
    parser.add_argument("--output-dir", type=Path, default=Path("runs"))
    parser.add_argument("--run-name", help="Optional deterministic run directory name under --output-dir")
    parser.add_argument("--grid-radius-km", type=float, default=50.0)
    parser.add_argument("--grid-step-km", type=float, default=5.0)
    parser.add_argument("--site-lat", type=float, default=41.7744825)
    parser.add_argument("--site-lon", type=float, default=-112.6559297)
    parser.add_argument("--mixing-height-m", type=float, default=400.0)
    parser.add_argument("--stability", choices=["A", "B", "C", "D", "E", "F"], default="F")
    parser.add_argument("--meander-sigma-deg", type=float, default=12.0)
    parser.add_argument("--no-lid-reflection", action="store_true")
    parser.add_argument("--stack-count", type=int, default=1)
    parser.add_argument("--stack-spacing-m", type=float, default=250.0)
    parser.add_argument("--stack-height-m", type=float, default=150.0)
    parser.add_argument("--stack-diameter-m", type=float, default=7.0)
    parser.add_argument("--exit-velocity-m-s", type=float, default=20.0)
    parser.add_argument("--exit-temp-k", type=float, default=390.0)
    parser.add_argument("--primary-pm25-lb-hr", type=float, default=405.0)
    parser.add_argument("--nox-lb-hr", type=float, default=0.0)
    parser.add_argument("--so2-lb-hr", type=float, default=0.0)
    parser.add_argument("--nh3-lb-hr", type=float, default=0.0)
    parser.add_argument("--voc-lb-hr", type=float, default=0.0)
    parser.add_argument("--secondary-profile", choices=sorted(SECONDARY_PROFILES), default="typical_inversion")
    parser.add_argument("--nox-to-nitrate-fraction", type=float)
    parser.add_argument("--so2-to-sulfate-fraction", type=float)
    parser.add_argument("--nh3-to-ammonium-fraction", type=float)
    parser.add_argument("--voc-to-soa-fraction", type=float)
    parser.add_argument("--event-pm25-24h-threshold", type=float, default=25.0)
    parser.add_argument("--event-hourly-pm25-threshold", type=float, default=30.0)
    parser.add_argument("--event-wind-threshold-m-s", type=float, default=2.0)
    parser.add_argument("--event-min-hours", type=int, default=12)
    parser.add_argument("--event-gap-hours", type=int, default=6)
    parser.add_argument("--max-events", type=int, default=15)
    parser.add_argument("--all-events", action="store_true", help="Model every detected inversion event instead of the top --max-events events")
    parser.add_argument("--worst-duration-hours", type=int, default=72)
    parser.add_argument("--worst-wind-speed-m-s", type=float, default=1.5)
    parser.add_argument("--worst-wind-dir-deg", type=float, default=180.0)
    parser.add_argument("--worst-temp-c", type=float, default=-4.0)
    parser.add_argument("--basin-area-km2", type=float, default=6_000.0)
    parser.add_argument("--basin-vent-length-km", type=float, default=120.0)
    parser.add_argument("--deposition-velocity-m-s", type=float, default=0.0005)
    return parser.parse_args(argv)


def lb_hr_to_g_s(value: float) -> float:
    return value * LB_HR_TO_G_S


def safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or stripped.upper() in {"NA", "N/A", "NULL", "-999", "-9999"}:
        return None
    try:
        return float(stripped)
    except ValueError:
        return None


def parse_utah_datetime(value: str) -> dt.datetime:
    value = value.strip()
    formats = (
        "%d-%b-%Y %H:%M",
        "%d-%b-%y %H:%M",
        "%m/%d/%Y %H:%M",
        "%m/%d/%y %H:%M",
        "%m/%d/%Y %H:%M:%S",
    )
    for fmt in formats:
        try:
            return dt.datetime.strptime(value, fmt)
        except ValueError:
            pass
    raise ValueError(f"Unrecognized Utah DAQ timestamp: {value!r}")


def download_with_cache(url: str, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and target.stat().st_size > 0:
        return target
    request = urllib.request.Request(url, headers={"User-Agent": "stratos-pm25-screening/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        body = response.read()
    if len(body) < 100:
        raise RuntimeError(f"Downloaded file is unexpectedly small: {url}")
    target.write_bytes(body)
    return target


def utah_archive_filename(year: int, measurement: str) -> str:
    return f"{year}-{measurement}.csv"


def load_utah_station_series(
    year: int,
    measurement: str,
    station: str,
    cache_dir: Path,
) -> dict[dt.datetime, float]:
    filename = utah_archive_filename(year, measurement)
    url = f"{UTAH_DAQ_ARCHIVE}/{filename}"
    path = download_with_cache(url, cache_dir / filename)
    station = station.upper()

    with path.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.reader(handle))
    if len(rows) < 4:
        raise RuntimeError(f"{path} does not look like a Utah DAQ archive CSV")

    station_row = rows[0]
    old_single_header = station_row and station_row[0].strip().lower() == "date"
    if old_single_header:
        matching_indexes = [
            i for i, heading in enumerate(station_row) if utah_header_station_code(heading) == station
        ]
        data_start = 1
    else:
        matching_indexes = [i for i, code in enumerate(station_row) if code.strip().upper() == station]
        data_start = 3
    if not matching_indexes:
        available = ", ".join(
            sorted({utah_header_station_code(code) or code.strip().upper() for code in station_row[1:] if code.strip()})
        )
        raise RuntimeError(f"Station {station} not found in {filename}. Available: {available}")

    index = matching_indexes[0]
    series: dict[dt.datetime, float] = {}
    for row in rows[data_start:]:
        if not row or not row[0].strip() or index >= len(row):
            continue
        value = safe_float(row[index])
        if value is None:
            continue
        try:
            timestamp = parse_utah_datetime(row[0])
        except ValueError:
            continue
        series[timestamp] = value
    return series


def utah_header_station_code(value: str) -> str:
    token = value.strip().upper()
    if not token or token == "DATE":
        return ""
    token = token.split()[0]
    token = token.split("-")[0]
    return token


def unique_station_candidates(primary: str, fallbacks: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for station in [primary, *fallbacks]:
        code = station.strip().upper()
        if code and code not in seen:
            seen.add(code)
            candidates.append(code)
    return candidates


def load_met_bundle_for_year(
    year: int,
    station_candidates: list[str],
    cache_dir: Path,
) -> tuple[dict[dt.datetime, float], dict[dt.datetime, float], dict[dt.datetime, float], str]:
    errors: list[str] = []
    for station in station_candidates:
        try:
            wind_mph = load_utah_station_series(year, "WindSpeed", station, cache_dir)
            wind_dir = load_utah_station_series(year, "WindDir", station, cache_dir)
            temp_c = load_utah_station_series(year, "Temperature", station, cache_dir)
        except RuntimeError as exc:
            errors.append(str(exc))
            continue
        return wind_mph, wind_dir, temp_c, station
    joined = "\n".join(errors[-5:])
    raise RuntimeError(f"No complete met bundle found for {year}. Last errors:\n{joined}")


def load_series_with_fallback(
    year: int,
    measurement: str,
    station_candidates: list[str],
    cache_dir: Path,
) -> tuple[dict[dt.datetime, float], str]:
    errors: list[str] = []
    for station in station_candidates:
        try:
            return load_utah_station_series(year, measurement, station, cache_dir), station
        except RuntimeError as exc:
            errors.append(str(exc))
    joined = "\n".join(errors[-5:])
    raise RuntimeError(f"No station series found for {year} {measurement}. Last errors:\n{joined}")


def rolling_average(values: list[float | None], window: int) -> list[float | None]:
    result: list[float | None] = []
    running: list[float] = []
    for value in values:
        if value is not None:
            running.append(value)
        else:
            running.append(math.nan)
        if len(running) > window:
            running.pop(0)
        valid = [v for v in running if not math.isnan(v)]
        if len(valid) >= max(6, window // 2):
            result.append(statistics.fmean(valid))
        else:
            result.append(None)
    return result


def load_historical_hours(
    years: Iterable[int],
    met_station: str,
    pm25_station: str,
    met_fallback_stations: Iterable[str],
    pm25_fallback_stations: Iterable[str],
    cache_dir: Path,
) -> tuple[list[MetHour], list[dict[str, object]]]:
    hours: list[MetHour] = []
    usage: list[dict[str, object]] = []
    met_candidates = unique_station_candidates(met_station, met_fallback_stations)
    pm25_candidates = unique_station_candidates(pm25_station, pm25_fallback_stations)
    for year in years:
        wind_mph, wind_dir, temp_c, met_used = load_met_bundle_for_year(year, met_candidates, cache_dir)
        pm25, pm25_used = load_series_with_fallback(year, "PM2.5", pm25_candidates, cache_dir)
        usage.append({"year": year, "met_station": met_used, "pm25_station": pm25_used})
        timestamps = sorted(set(wind_mph) & set(wind_dir))
        raw: list[MetHour] = []
        for timestamp in timestamps:
            speed = wind_mph.get(timestamp)
            direction = wind_dir.get(timestamp)
            if speed is None or direction is None:
                continue
            raw.append(
                MetHour(
                    timestamp=timestamp,
                    wind_speed_m_s=max(0.25, speed * MPH_TO_MPS),
                    wind_dir_deg=direction % 360.0,
                    ambient_temp_c=temp_c.get(timestamp),
                    pm25_ug_m3=pm25.get(timestamp),
                )
            )
        rolling = rolling_average([h.pm25_ug_m3 for h in raw], 24)
        hours.extend(dataclasses.replace(h, pm25_24h_ug_m3=avg) for h, avg in zip(raw, rolling))
    return sorted(hours, key=lambda h: h.timestamp), usage


def is_winter_hour(timestamp: dt.datetime) -> bool:
    return timestamp.month in {11, 12, 1, 2, 3}


def is_inversion_candidate_hour(
    hour: MetHour,
    pm25_24h_threshold: float,
    hourly_pm25_threshold: float,
    wind_threshold_m_s: float,
) -> bool:
    if not is_winter_hour(hour.timestamp):
        return False
    polluted = (
        (hour.pm25_24h_ug_m3 is not None and hour.pm25_24h_ug_m3 >= pm25_24h_threshold)
        or (hour.pm25_ug_m3 is not None and hour.pm25_ug_m3 >= hourly_pm25_threshold)
    )
    stagnant_cold = hour.wind_speed_m_s <= wind_threshold_m_s and (
        hour.ambient_temp_c is None or hour.ambient_temp_c <= 5.0
    )
    return polluted or stagnant_cold


def detect_inversion_events(
    hours: list[MetHour],
    pm25_24h_threshold: float = 25.0,
    hourly_pm25_threshold: float = 30.0,
    wind_threshold_m_s: float = 2.0,
    min_hours: int = 12,
    gap_hours: int = 6,
) -> list[InversionEvent]:
    sorted_hours = sorted(hours, key=lambda hour: hour.timestamp)
    candidates = [
        hour
        for hour in sorted_hours
        if is_inversion_candidate_hour(hour, pm25_24h_threshold, hourly_pm25_threshold, wind_threshold_m_s)
    ]
    if not candidates:
        return []

    grouped: list[list[MetHour]] = [[candidates[0]]]
    for hour in candidates[1:]:
        previous = grouped[-1][-1]
        gap = (hour.timestamp - previous.timestamp).total_seconds() / SECONDS_PER_HOUR
        if gap <= gap_hours:
            grouped[-1].append(hour)
        else:
            grouped.append([hour])

    events: list[InversionEvent] = []
    for index, group in enumerate(grouped, start=1):
        if len(group) < min_hours:
            continue
        start = group[0].timestamp
        end = group[-1].timestamp
        window_hours = tuple(hour for hour in sorted_hours if start <= hour.timestamp <= end)
        event_id = f"{start:%Y%m%d}_{index:02d}"
        events.append(InversionEvent(event_id, start, end, window_hours))
    events.sort(
        key=lambda event: (
            event.peak_background_pm25 if event.peak_background_pm25 is not None else -1.0,
            event.duration_hours,
        ),
        reverse=True,
    )
    return events


def build_receptor_grid(config: ModelConfig) -> list[Receptor]:
    radius_m = config.grid_radius_km * 1000.0
    step_m = config.grid_step_km * 1000.0
    count = int(math.floor(radius_m / step_m))
    receptors: list[Receptor] = []
    for ix in range(-count, count + 1):
        for iy in range(-count, count + 1):
            x_m = ix * step_m
            y_m = iy * step_m
            distance_m = math.hypot(x_m, y_m)
            if distance_m > radius_m or distance_m == 0:
                continue
            bearing = (math.degrees(math.atan2(x_m, y_m)) + 360.0) % 360.0
            lat, lon = offset_lat_lon(config.site_lat, config.site_lon, x_m, y_m)
            receptors.append(
                Receptor(
                    receptor_id=f"r_{ix:+03d}_{iy:+03d}",
                    x_m=x_m,
                    y_m=y_m,
                    distance_km=distance_m / 1000.0,
                    bearing_deg=bearing,
                    lat=lat,
                    lon=lon,
                )
            )
    receptors.sort(key=lambda r: (r.distance_km, r.bearing_deg))
    return receptors


def offset_lat_lon(lat: float, lon: float, x_m: float, y_m: float) -> tuple[float, float]:
    d_lat = y_m / 111_320.0
    d_lon = x_m / (111_320.0 * math.cos(math.radians(lat)))
    return lat + d_lat, lon + d_lon


def build_sources(args: argparse.Namespace) -> list[Source]:
    stack_count = max(1, args.stack_count)
    total_primary = lb_hr_to_g_s(args.primary_pm25_lb_hr)
    total_nox = lb_hr_to_g_s(args.nox_lb_hr)
    total_so2 = lb_hr_to_g_s(args.so2_lb_hr)
    total_nh3 = lb_hr_to_g_s(args.nh3_lb_hr)
    total_voc = lb_hr_to_g_s(args.voc_lb_hr)

    start_offset = -0.5 * (stack_count - 1) * args.stack_spacing_m
    sources: list[Source] = []
    for index in range(stack_count):
        sources.append(
            Source(
                name=f"stack_{index + 1:02d}",
                x_m=start_offset + index * args.stack_spacing_m,
                y_m=0.0,
                primary_pm25_g_s=total_primary / stack_count,
                nox_g_s=total_nox / stack_count,
                so2_g_s=total_so2 / stack_count,
                nh3_g_s=total_nh3 / stack_count,
                voc_g_s=total_voc / stack_count,
                stack_height_m=args.stack_height_m,
                stack_diameter_m=args.stack_diameter_m,
                exit_velocity_m_s=args.exit_velocity_m_s,
                exit_temp_k=args.exit_temp_k,
            )
        )
    return sources


def selected_secondary_profile(args: argparse.Namespace) -> SecondaryProfile:
    base = SECONDARY_PROFILES[args.secondary_profile]
    overrides = {
        "nox_to_nitrate_fraction": args.nox_to_nitrate_fraction,
        "so2_to_sulfate_fraction": args.so2_to_sulfate_fraction,
        "nh3_to_ammonium_fraction": args.nh3_to_ammonium_fraction,
        "voc_to_soa_fraction": args.voc_to_soa_fraction,
    }
    if all(value is None for value in overrides.values()):
        return base
    values = dataclasses.asdict(base)
    for key, value in overrides.items():
        if value is not None:
            if value < 0:
                raise ValueError(f"{key} must be non-negative")
            values[key] = value
    values["name"] = f"{base.name}_custom"
    return SecondaryProfile(**values)


def source_pm25_equivalent_g_s(source: Source, secondary_profile: SecondaryProfile) -> tuple[float, float]:
    nitrate_equiv = source.nox_g_s * secondary_profile.nox_to_nitrate_fraction * 1.36
    sulfate_equiv = source.so2_g_s * secondary_profile.so2_to_sulfate_fraction * 1.50
    ammonium_equiv = source.nh3_g_s * secondary_profile.nh3_to_ammonium_fraction
    soa_equiv = source.voc_g_s * secondary_profile.voc_to_soa_fraction
    secondary = nitrate_equiv + sulfate_equiv + ammonium_equiv + soa_equiv
    return source.primary_pm25_g_s + secondary, secondary


def pg_sigma_y(x_m: float, stability: str) -> float:
    x = max(1.0, x_m)
    stability = stability.upper()
    if stability == "A":
        return 0.22 * x * (1 + 0.0001 * x) ** -0.5
    if stability == "B":
        return 0.16 * x * (1 + 0.0001 * x) ** -0.5
    if stability == "C":
        return 0.11 * x * (1 + 0.0001 * x) ** -0.5
    if stability == "D":
        return 0.08 * x * (1 + 0.0001 * x) ** -0.5
    if stability == "E":
        return 0.06 * x * (1 + 0.0001 * x) ** -0.5
    return 0.04 * x * (1 + 0.0001 * x) ** -0.5


def pg_sigma_z(x_m: float, stability: str) -> float:
    x = max(1.0, x_m)
    stability = stability.upper()
    if stability == "A":
        return 0.20 * x
    if stability == "B":
        return 0.12 * x
    if stability == "C":
        return 0.08 * x * (1 + 0.0002 * x) ** -0.5
    if stability == "D":
        return 0.06 * x * (1 + 0.0015 * x) ** -0.5
    if stability == "E":
        return 0.03 * x * (1 + 0.0003 * x) ** -1.0
    return 0.016 * x * (1 + 0.0003 * x) ** -1.0


def rotate_to_downwind(dx_m: float, dy_m: float, wind_from_deg: float) -> tuple[float, float]:
    wind_to_rad = math.radians((wind_from_deg + 180.0) % 360.0)
    ux = math.sin(wind_to_rad)
    uy = math.cos(wind_to_rad)
    downwind = dx_m * ux + dy_m * uy
    crosswind = dx_m * uy - dy_m * ux
    return downwind, crosswind


def effective_stack_height(
    source: Source,
    wind_speed_m_s: float,
    ambient_temp_c: float | None,
    mixing_height_m: float,
    trap_at_lid: bool,
) -> float:
    u = max(0.5, wind_speed_m_s)
    ambient_k = (ambient_temp_c + 273.15) if ambient_temp_c is not None else 285.0
    temp_delta = max(0.0, source.exit_temp_k - ambient_k)
    momentum_rise = 1.5 * source.stack_diameter_m * source.exit_velocity_m_s / u
    buoyancy_flux = 9.81 * source.exit_velocity_m_s * source.stack_diameter_m**2 * temp_delta / (
        4.0 * max(source.exit_temp_k, 1.0)
    )
    buoyancy_rise = 35.0 * (max(0.0, buoyancy_flux) ** (1.0 / 3.0)) / u
    plume_rise = min(350.0, max(momentum_rise, buoyancy_rise))
    h_eff = source.stack_height_m + plume_rise
    if trap_at_lid and mixing_height_m > 0:
        h_eff = min(h_eff, 0.85 * mixing_height_m)
    return max(1.0, h_eff)


def gaussian_receptor_concentration_ug_m3(
    source: Source,
    receptor: Receptor,
    hour: MetHour,
    config: ModelConfig,
    secondary_profile: SecondaryProfile,
) -> tuple[float, float]:
    q_total_g_s, q_secondary_g_s = source_pm25_equivalent_g_s(source, secondary_profile)
    dx = receptor.x_m - source.x_m
    dy = receptor.y_m - source.y_m
    downwind_m, crosswind_m = rotate_to_downwind(dx, dy, hour.wind_dir_deg)
    if downwind_m <= 1.0:
        return 0.0, 0.0

    u = max(0.25, hour.wind_speed_m_s)
    sy = pg_sigma_y(downwind_m, config.stability)
    sz = pg_sigma_z(downwind_m, config.stability)
    meander_sigma_m = downwind_m * math.tan(math.radians(max(0.0, config.meander_sigma_deg)))
    sy_eff = math.sqrt(sy * sy + meander_sigma_m * meander_sigma_m)
    h_eff = effective_stack_height(
        source,
        u,
        hour.ambient_temp_c,
        config.mixing_height_m,
        config.inversion_lid_reflection,
    )

    lateral = math.exp(-(crosswind_m**2) / (2.0 * sy_eff**2))
    vertical = vertical_reflection_term(
        config.receptor_height_m,
        h_eff,
        sz,
        config.mixing_height_m if config.inversion_lid_reflection else None,
    )
    concentration_g_m3 = q_total_g_s / (2.0 * math.pi * u * sy_eff * sz) * lateral * vertical
    if config.inversion_lid_reflection and config.mixing_height_m > 0:
        concentration_g_m3 = max(
            concentration_g_m3,
            trapped_lid_fumigation_floor_g_m3(q_total_g_s, u, sy_eff, lateral, h_eff, sz, config.mixing_height_m),
        )
    total_ug_m3 = concentration_g_m3 * UG_PER_G
    secondary_share = (q_secondary_g_s / q_total_g_s) if q_total_g_s > 0 else 0.0
    return total_ug_m3, total_ug_m3 * secondary_share


def trapped_lid_fumigation_floor_g_m3(
    q_g_s: float,
    wind_speed_m_s: float,
    sy_eff_m: float,
    lateral_term: float,
    h_eff_m: float,
    sz_m: float,
    mixing_height_m: float,
) -> float:
    """Return a conservative line-plume floor when a stable lid traps the plume.

    The image-plume term can predict near-zero ground concentration when plume
    rise places emissions close to the inversion lid. In real cold-air pools,
    shear, terrain flows, plume impaction, and fumigation can mix that material
    downward. This floor treats the vertical column under the lid as mixed once
    the plume approaches the lid or vertical spread reaches a meaningful share
    of the mixing depth.
    """
    if h_eff_m < 0.70 * mixing_height_m and sz_m < 0.25 * mixing_height_m:
        return 0.0
    return q_g_s / (wind_speed_m_s * math.sqrt(2.0 * math.pi) * sy_eff_m * mixing_height_m) * lateral_term


def vertical_reflection_term(z_m: float, h_eff_m: float, sz_m: float, mixing_height_m: float | None) -> float:
    if sz_m <= 0:
        return 0.0
    if mixing_height_m is None or mixing_height_m <= 0:
        return math.exp(-((z_m - h_eff_m) ** 2) / (2.0 * sz_m**2)) + math.exp(
            -((z_m + h_eff_m) ** 2) / (2.0 * sz_m**2)
        )

    total = 0.0
    lid = mixing_height_m
    for n in range(-4, 5):
        image_shift = 2.0 * n * lid
        total += math.exp(-((z_m - h_eff_m + image_shift) ** 2) / (2.0 * sz_m**2))
        total += math.exp(-((z_m + h_eff_m + image_shift) ** 2) / (2.0 * sz_m**2))
    return total


def run_grid_for_hours(
    hours: Iterable[MetHour],
    sources: list[Source],
    receptors: list[Receptor],
    config: ModelConfig,
    secondary_profile: SecondaryProfile,
) -> dict[str, dict[str, float]]:
    stats: dict[str, dict[str, float]] = {
        receptor.receptor_id: {
            "sum": 0.0,
            "sum_secondary": 0.0,
            "max": 0.0,
            "max_secondary": 0.0,
            "hours": 0.0,
        }
        for receptor in receptors
    }
    for hour in hours:
        for receptor in receptors:
            total = 0.0
            secondary = 0.0
            for source in sources:
                c_total, c_secondary = gaussian_receptor_concentration_ug_m3(
                    source, receptor, hour, config, secondary_profile
                )
                total += c_total
                secondary += c_secondary
            row = stats[receptor.receptor_id]
            row["sum"] += total
            row["sum_secondary"] += secondary
            row["max"] = max(row["max"], total)
            row["max_secondary"] = max(row["max_secondary"], secondary)
            row["hours"] += 1.0
    return stats


def regional_box_timeseries_ug_m3(
    hours: Iterable[MetHour],
    sources: list[Source],
    config: ModelConfig,
    secondary_profile: SecondaryProfile,
) -> list[tuple[dt.datetime, float]]:
    q_g_s = sum(source_pm25_equivalent_g_s(source, secondary_profile)[0] for source in sources)
    emissions_ug_s = q_g_s * UG_PER_G
    volume_m3 = config.basin_area_km2 * 1_000_000.0 * config.mixing_height_m
    vent_length_m = max(1_000.0, config.basin_vent_length_km * 1000.0)
    concentration = 0.0
    series: list[tuple[dt.datetime, float]] = []
    for hour in hours:
        ventilation = max(0.0, hour.wind_speed_m_s) / vent_length_m
        deposition = max(0.0, config.deposition_velocity_m_s) / max(1.0, config.mixing_height_m)
        decay = ventilation + deposition
        if decay > 0:
            retained = math.exp(-decay * SECONDS_PER_HOUR)
            steady = emissions_ug_s / (volume_m3 * decay)
            concentration = concentration * retained + steady * (1.0 - retained)
        else:
            concentration += emissions_ug_s * SECONDS_PER_HOUR / volume_m3
        series.append((hour.timestamp, concentration))
    return series


def build_worst_case_hours(args: argparse.Namespace) -> list[MetHour]:
    start = dt.datetime(2025, 1, 1, 0, 0)
    rolling_background = args.event_pm25_24h_threshold
    return [
        MetHour(
            timestamp=start + dt.timedelta(hours=i),
            wind_speed_m_s=args.worst_wind_speed_m_s,
            wind_dir_deg=args.worst_wind_dir_deg % 360.0,
            ambient_temp_c=args.worst_temp_c,
            pm25_ug_m3=rolling_background,
            pm25_24h_ug_m3=rolling_background,
        )
        for i in range(args.worst_duration_hours)
    ]


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    sorted_values = sorted(values)
    if len(sorted_values) == 1:
        return sorted_values[0]
    rank = (pct / 100.0) * (len(sorted_values) - 1)
    lower = int(math.floor(rank))
    upper = int(math.ceil(rank))
    if lower == upper:
        return sorted_values[lower]
    weight = rank - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


def percent_of(value: float, baseline: float | None) -> float | None:
    if baseline is None or baseline <= 0:
        return None
    return 100.0 * value / baseline


def fmt_optional(value: float | None, digits: int = 6) -> str:
    if value is None:
        return ""
    return f"{value:.{digits}f}"


def write_grid_csv(
    path: Path,
    receptors: list[Receptor],
    stats: dict[str, dict[str, float]],
    avg_background_pm25_ug_m3: float | None = None,
    peak_background_pm25_ug_m3: float | None = None,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "receptor_id",
                "lat",
                "lon",
                "x_m",
                "y_m",
                "distance_km",
                "bearing_deg",
                "avg_increment_ug_m3",
                "max_hourly_increment_ug_m3",
                "avg_increment_percent_of_event_avg_bg",
                "max_hourly_percent_of_event_peak_bg",
                "avg_secondary_increment_ug_m3",
                "max_secondary_increment_ug_m3",
            ]
        )
        for receptor in receptors:
            row = stats[receptor.receptor_id]
            hours = max(1.0, row["hours"])
            avg_increment = row["sum"] / hours
            max_increment = row["max"]
            writer.writerow(
                [
                    receptor.receptor_id,
                    f"{receptor.lat:.6f}",
                    f"{receptor.lon:.6f}",
                    f"{receptor.x_m:.1f}",
                    f"{receptor.y_m:.1f}",
                    f"{receptor.distance_km:.3f}",
                    f"{receptor.bearing_deg:.1f}",
                    f"{avg_increment:.6f}",
                    f"{max_increment:.6f}",
                    fmt_optional(percent_of(avg_increment, avg_background_pm25_ug_m3), 3),
                    fmt_optional(percent_of(max_increment, peak_background_pm25_ug_m3), 3),
                    f"{row['sum_secondary'] / hours:.6f}",
                    f"{row['max_secondary']:.6f}",
                ]
            )


def write_event_summary_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "event_id",
        "start",
        "end",
        "duration_hours",
        "avg_wind_m_s",
        "avg_background_pm25_ug_m3",
        "avg_background_24h_pm25_ug_m3",
        "peak_background_pm25_ug_m3",
        "max_grid_avg_increment_ug_m3",
        "max_grid_avg_percent_of_event_avg_bg",
        "max_grid_avg_percent_of_event_avg_24h_bg",
        "max_grid_hourly_increment_ug_m3",
        "max_grid_hourly_percent_of_peak_bg",
        "p95_grid_avg_increment_ug_m3",
        "p95_grid_avg_percent_of_event_avg_bg",
        "max_box_increment_ug_m3",
        "max_box_percent_of_event_avg_bg",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def summarize_grid(stats: dict[str, dict[str, float]]) -> dict[str, float]:
    avg_values = []
    max_values = []
    for row in stats.values():
        hours = max(1.0, row["hours"])
        avg_values.append(row["sum"] / hours)
        max_values.append(row["max"])
    return {
        "max_avg": max(avg_values) if avg_values else 0.0,
        "p95_avg": percentile(avg_values, 95.0),
        "max_hourly": max(max_values) if max_values else 0.0,
    }


def top_receptors(receptors: list[Receptor], stats: dict[str, dict[str, float]], limit: int = 10) -> list[tuple[Receptor, float]]:
    ranked: list[tuple[Receptor, float]] = []
    receptor_by_id = {r.receptor_id: r for r in receptors}
    for receptor_id, row in stats.items():
        ranked.append((receptor_by_id[receptor_id], row["max"]))
    return sorted(ranked, key=lambda item: item[1], reverse=True)[:limit]


def run_worst_case(
    args: argparse.Namespace,
    sources: list[Source],
    receptors: list[Receptor],
    config: ModelConfig,
    secondary_profile: SecondaryProfile,
    run_dir: Path,
) -> dict[str, float]:
    worst_hours = build_worst_case_hours(args)
    stats = run_grid_for_hours(worst_hours, sources, receptors, config, secondary_profile)
    box = regional_box_timeseries_ug_m3(worst_hours, sources, config, secondary_profile)
    write_grid_csv(
        run_dir / "worst_case_grid.csv",
        receptors,
        stats,
        avg_background_pm25_ug_m3=args.event_pm25_24h_threshold,
        peak_background_pm25_ug_m3=args.event_pm25_24h_threshold,
    )
    summary = summarize_grid(stats)
    summary["max_box"] = max((value for _, value in box), default=0.0)
    with (run_dir / "worst_case_box_timeseries.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["timestamp", "regional_box_increment_ug_m3"])
        for timestamp, value in box:
            writer.writerow([timestamp.isoformat(sep=" "), f"{value:.6f}"])
    return summary


def run_historical_events(
    args: argparse.Namespace,
    sources: list[Source],
    receptors: list[Receptor],
    config: ModelConfig,
    secondary_profile: SecondaryProfile,
    run_dir: Path,
) -> list[dict[str, object]]:
    hours, station_usage = load_historical_hours(
        args.years,
        args.met_station,
        args.pm25_station,
        args.met_fallback_stations,
        args.pm25_fallback_stations,
        args.cache_dir,
    )
    write_station_usage_csv(run_dir / "station_usage.csv", station_usage)
    events = detect_inversion_events(
        hours,
        pm25_24h_threshold=args.event_pm25_24h_threshold,
        hourly_pm25_threshold=args.event_hourly_pm25_threshold,
        wind_threshold_m_s=args.event_wind_threshold_m_s,
        min_hours=args.event_min_hours,
        gap_hours=args.event_gap_hours,
    )
    selected_events = events if args.all_events else events[: max(0, args.max_events)]
    event_rows: list[dict[str, object]] = []
    for event in selected_events:
        stats = run_grid_for_hours(event.hours, sources, receptors, config, secondary_profile)
        grid_summary = summarize_grid(stats)
        box = regional_box_timeseries_ug_m3(event.hours, sources, config, secondary_profile)
        avg_bg = event.avg_background_pm25
        avg_24h_bg = event.avg_background_24h_pm25
        peak_bg = event.peak_background_pm25
        max_box = max((value for _, value in box), default=0.0)
        write_grid_csv(
            run_dir / "events" / f"{event.event_id}_grid.csv",
            receptors,
            stats,
            avg_background_pm25_ug_m3=avg_bg,
            peak_background_pm25_ug_m3=peak_bg,
        )
        event_rows.append(
            {
                "event_id": event.event_id,
                "start": event.start.isoformat(sep=" "),
                "end": event.end.isoformat(sep=" "),
                "duration_hours": event.duration_hours,
                "avg_wind_m_s": f"{event.avg_wind_speed:.3f}",
                "avg_background_pm25_ug_m3": fmt_optional(avg_bg, 3),
                "avg_background_24h_pm25_ug_m3": fmt_optional(avg_24h_bg, 3),
                "peak_background_pm25_ug_m3": fmt_optional(peak_bg, 3),
                "max_grid_avg_increment_ug_m3": f"{grid_summary['max_avg']:.6f}",
                "max_grid_avg_percent_of_event_avg_bg": fmt_optional(percent_of(grid_summary["max_avg"], avg_bg), 3),
                "max_grid_avg_percent_of_event_avg_24h_bg": fmt_optional(
                    percent_of(grid_summary["max_avg"], avg_24h_bg), 3
                ),
                "max_grid_hourly_increment_ug_m3": f"{grid_summary['max_hourly']:.6f}",
                "max_grid_hourly_percent_of_peak_bg": fmt_optional(percent_of(grid_summary["max_hourly"], peak_bg), 3),
                "p95_grid_avg_increment_ug_m3": f"{grid_summary['p95_avg']:.6f}",
                "p95_grid_avg_percent_of_event_avg_bg": fmt_optional(percent_of(grid_summary["p95_avg"], avg_bg), 3),
                "max_box_increment_ug_m3": f"{max_box:.6f}",
                "max_box_percent_of_event_avg_bg": fmt_optional(percent_of(max_box, avg_bg), 3),
            }
        )
    write_event_summary_csv(run_dir / "historical_event_summary.csv", event_rows)
    write_detected_events_csv(run_dir / "detected_inversion_events.csv", events)
    return event_rows


def write_station_usage_csv(path: Path, usage: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["year", "met_station", "pm25_station"])
        writer.writeheader()
        for row in usage:
            writer.writerow(row)


def write_detected_events_csv(path: Path, events: list[InversionEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "event_id",
                "start",
                "end",
                "duration_hours",
                "avg_wind_m_s",
                "avg_background_pm25_ug_m3",
                "avg_background_24h_pm25_ug_m3",
                "peak_background_pm25_ug_m3",
            ]
        )
        for event in events:
            writer.writerow(
                [
                    event.event_id,
                    event.start.isoformat(sep=" "),
                    event.end.isoformat(sep=" "),
                    event.duration_hours,
                    f"{event.avg_wind_speed:.3f}",
                    fmt_optional(event.avg_background_pm25, 3),
                    fmt_optional(event.avg_background_24h_pm25, 3),
                    fmt_optional(event.peak_background_pm25, 3),
                ]
            )


def write_run_metadata(path: Path, args: argparse.Namespace, sources: list[Source], config: ModelConfig) -> None:
    total_primary = sum(source.primary_pm25_g_s for source in sources)
    total_nox = sum(source.nox_g_s for source in sources)
    total_so2 = sum(source.so2_g_s for source in sources)
    total_nh3 = sum(source.nh3_g_s for source in sources)
    total_voc = sum(source.voc_g_s for source in sources)
    body = [
        "# Stratos PM2.5 Screening Run",
        "",
        "This run is a screening simulation. It is not a permit model and does not replace AERMOD, AERSCREEN, CAMx, CMAQ, or WRF-Chem.",
        "",
        "## Inputs",
        "",
        f"- Years: {', '.join(str(year) for year in args.years)}",
        f"- Met station: {args.met_station}",
        f"- Met fallback stations: {', '.join(args.met_fallback_stations)}",
        f"- PM2.5 station: {args.pm25_station}",
        f"- PM2.5 fallback stations: {', '.join(args.pm25_fallback_stations)}",
        f"- Site: {config.site_lat:.5f}, {config.site_lon:.5f}",
        f"- Grid radius/step: {config.grid_radius_km:g} km / {config.grid_step_km:g} km",
        f"- Mixing height: {config.mixing_height_m:g} m",
        f"- Stability: {config.stability}",
        f"- Meander sigma: {config.meander_sigma_deg:g} degrees",
        f"- Stack count: {len(sources)}",
        f"- Total primary PM2.5: {total_primary:.3f} g/s ({total_primary / LB_HR_TO_G_S:.1f} lb/hr)",
        f"- Total NOx: {total_nox:.3f} g/s ({total_nox / LB_HR_TO_G_S:.1f} lb/hr)",
        f"- Total SO2: {total_so2:.3f} g/s ({total_so2 / LB_HR_TO_G_S:.1f} lb/hr)",
        f"- Total NH3: {total_nh3:.3f} g/s ({total_nh3 / LB_HR_TO_G_S:.1f} lb/hr)",
        f"- Total VOC: {total_voc:.3f} g/s ({total_voc / LB_HR_TO_G_S:.1f} lb/hr)",
        f"- Secondary profile: {args.secondary_profile}",
        f"- Secondary factors: NOx={args.nox_to_nitrate_fraction if args.nox_to_nitrate_fraction is not None else 'profile'}, SO2={args.so2_to_sulfate_fraction if args.so2_to_sulfate_fraction is not None else 'profile'}, NH3={args.nh3_to_ammonium_fraction if args.nh3_to_ammonium_fraction is not None else 'profile'}, VOC={args.voc_to_soa_fraction if args.voc_to_soa_fraction is not None else 'profile'}",
        "",
        "## Key Caveats",
        "",
        "- Utah DAQ station data is used as a screening surrogate for site meteorology.",
        "- Secondary PM2.5 is represented by simple sensitivity coefficients, not atmospheric chemistry.",
        "- Plume rise is a conservative screening approximation and must be replaced with source-specific stack parameters.",
        "- Complex terrain, building downwash, cold-air-pool structure, and chemical transport are not resolved.",
    ]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")


def print_worst_summary(summary: dict[str, float]) -> None:
    print("\nWorst-case screening summary")
    print(f"  Max receptor event-average increment: {summary['max_avg']:.3f} ug/m3")
    print(f"  P95 receptor event-average increment: {summary['p95_avg']:.3f} ug/m3")
    print(f"  Max receptor hourly increment:        {summary['max_hourly']:.3f} ug/m3")
    print(f"  Max regional box increment:           {summary['max_box']:.3f} ug/m3")


def print_historical_summary(rows: list[dict[str, object]]) -> None:
    print("\nHistorical inversion-event screening summary")
    if not rows:
        print("  No inversion events matched the current filters.")
        return
    for row in rows[:5]:
        print(
            "  {event_id}: {start} to {end}, "
            "max grid avg {max_grid_avg_increment_ug_m3} ug/m3, "
            "max hourly {max_grid_hourly_increment_ug_m3} ug/m3, "
            "box {max_box_increment_ug_m3} ug/m3".format(**row)
        )
    if len(rows) > 5:
        print(f"  ... {len(rows) - 5} more events written to CSV")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    run_dir = args.output_dir / (args.run_name or dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    run_dir.mkdir(parents=True, exist_ok=True)
    config = ModelConfig(
        site_lat=args.site_lat,
        site_lon=args.site_lon,
        grid_radius_km=args.grid_radius_km,
        grid_step_km=args.grid_step_km,
        mixing_height_m=args.mixing_height_m,
        basin_area_km2=args.basin_area_km2,
        basin_vent_length_km=args.basin_vent_length_km,
        deposition_velocity_m_s=args.deposition_velocity_m_s,
        stability=args.stability,
        meander_sigma_deg=args.meander_sigma_deg,
        inversion_lid_reflection=not args.no_lid_reflection,
    )
    sources = build_sources(args)
    secondary_profile = selected_secondary_profile(args)
    receptors = build_receptor_grid(config)
    write_run_metadata(run_dir / "README.md", args, sources, config)

    print(f"Writing run outputs to {run_dir.resolve()}")
    print(f"Receptors: {len(receptors)} | Sources: {len(sources)}")

    if args.mode in {"all", "worst"}:
        worst_summary = run_worst_case(args, sources, receptors, config, secondary_profile, run_dir)
        print_worst_summary(worst_summary)

    if args.mode in {"all", "historical"}:
        rows = run_historical_events(args, sources, receptors, config, secondary_profile, run_dir)
        print_historical_summary(rows)

    print("\nOutput files:")
    for path in sorted(run_dir.rglob("*")):
        if path.is_file():
            print(f"  {path.relative_to(run_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
