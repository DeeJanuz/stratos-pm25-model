#!/usr/bin/env python3
"""Run a reproducible Stratos PM2.5 screening matrix and comparison tables."""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
import sys
from pathlib import Path


SITE_LAT = 41.7744825
SITE_LON = -112.6559297
FALLBACK_STATIONS = ["BV", "EN", "CV", "SM", "H3"]


PERIODS = {
    "strict_bg_2024_2025": {
        "years": ["2024", "2025"],
        "pm25_fallbacks": [],
    },
    "proxy_4yr_2022_2025": {
        "years": ["2022", "2023", "2024", "2025"],
        "pm25_fallbacks": FALLBACK_STATIONS,
    },
}


SCENARIOS = {
    "direct_only": {
        "secondary_profile": "none",
        "nox_lb_hr": "0",
        "so2_lb_hr": "0",
        "nh3_lb_hr": "0",
        "voc_lb_hr": "0",
    },
    "typical_secondary": {
        "secondary_profile": "typical_inversion",
        "nox_lb_hr": "250",
        "so2_lb_hr": "5",
        "nh3_lb_hr": "40",
        "voc_lb_hr": "30",
    },
    "worst_secondary": {
        "secondary_profile": "worst_inversion",
        "nox_lb_hr": "250",
        "so2_lb_hr": "5",
        "nh3_lb_hr": "40",
        "voc_lb_hr": "30",
    },
}


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Stratos PM2.5 scenario matrix.")
    parser.add_argument("--output-root", type=Path, default=Path("runs/screening_matrix"))
    parser.add_argument("--matrix-name", default=dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    parser.add_argument("--site-lat", type=float, default=SITE_LAT)
    parser.add_argument("--site-lon", type=float, default=SITE_LON)
    parser.add_argument("--grid-radius-km", type=float, default=50.0)
    parser.add_argument("--grid-step-km", type=float, default=2.5)
    parser.add_argument("--primary-pm25-lb-hr", type=float, default=405.0)
    parser.add_argument("--period", action="append", choices=sorted(PERIODS), help="Period to run; defaults to both strict and proxy periods.")
    parser.add_argument("--scenario-name", action="append", choices=sorted(SCENARIOS), help="Scenario to run; defaults to all built-in scenarios.")
    parser.add_argument("--top-events-only", action="store_true", help="Use --max-events instead of modeling all detected inversion events.")
    parser.add_argument("--max-events", type=int, default=15)
    return parser.parse_args(argv)


def run(cmd: list[str], cwd: Path) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=cwd, check=True)


def model_command(
    args: argparse.Namespace,
    matrix_dir: Path,
    run_name: str,
    period: dict[str, list[str]],
    scenario: dict[str, str],
) -> list[str]:
    cmd = [
        sys.executable,
        "stratos_pm25_model.py",
        "--mode",
        "historical",
        "--output-dir",
        str(matrix_dir),
        "--run-name",
        run_name,
        "--site-lat",
        str(args.site_lat),
        "--site-lon",
        str(args.site_lon),
        "--grid-radius-km",
        str(args.grid_radius_km),
        "--grid-step-km",
        str(args.grid_step_km),
        "--years",
        *period["years"],
        "--met-station",
        "BG",
        "--met-fallback-stations",
        *FALLBACK_STATIONS,
        "--pm25-station",
        "BG",
        "--primary-pm25-lb-hr",
        str(args.primary_pm25_lb_hr),
        "--nox-lb-hr",
        scenario["nox_lb_hr"],
        "--so2-lb-hr",
        scenario["so2_lb_hr"],
        "--nh3-lb-hr",
        scenario["nh3_lb_hr"],
        "--voc-lb-hr",
        scenario["voc_lb_hr"],
        "--secondary-profile",
        scenario["secondary_profile"],
    ]
    if period["pm25_fallbacks"]:
        cmd.extend(["--pm25-fallback-stations", *period["pm25_fallbacks"]])
    if args.top_events_only:
        cmd.extend(["--max-events", str(args.max_events)])
    else:
        cmd.append("--all-events")
    return cmd


def overlay_command(args: argparse.Namespace, run_dir: Path) -> list[str]:
    return [
        sys.executable,
        "population_overlay.py",
        "--run-dir",
        str(run_dir),
        "--site-lat",
        str(args.site_lat),
        "--site-lon",
        str(args.site_lon),
        "--radius-km",
        str(args.grid_radius_km),
        "--place-radius-km",
        str(args.grid_radius_km),
        "--site-sensitivity-km",
        "0",
        "5",
        "10",
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    root = Path(__file__).resolve().parent
    matrix_dir = args.output_root / args.matrix_name
    matrix_dir.mkdir(parents=True, exist_ok=True)

    periods = args.period or list(PERIODS)
    scenarios = args.scenario_name or list(SCENARIOS)
    comparison_args = [sys.executable, "compare_model_runs.py", "--output-dir", str(matrix_dir / "comparison")]

    for period_name in periods:
        for scenario_name in scenarios:
            run_name = f"{period_name}__{scenario_name}"
            run_dir = matrix_dir / run_name
            run(model_command(args, matrix_dir, run_name, PERIODS[period_name], SCENARIOS[scenario_name]), root)
            run(overlay_command(args, run_dir), root)
            comparison_args.extend(["--scenario", f"{run_name}={run_dir}"])

    run(comparison_args, root)
    print(f"Matrix complete: {matrix_dir.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
