# Stratos PM2.5 Screening Model

This folder contains a dependency-free Python screening model for estimating incremental PM2.5 impacts from Stratos-area power generation during Utah winter inversion events.

It is designed to replace the original centerline-only plume script with a more useful scaffold:

- receptor grid instead of one plume path
- wind-direction rotation and crosswind dispersion
- multiple stacks with source geometry inputs
- simple plume-rise and inversion-lid reflection
- trapped-lid fumigation floor for downward mixing under shallow inversions
- Utah DAQ historical met and PM2.5 archive ingestion
- inversion-event detection from winter PM2.5 and stagnation
- regional trapped-box accumulation for mixed-out basin impacts
- configurable secondary PM2.5 screening from NOx, SO2, NH3, and VOC

This is not a regulatory model. Use AERMOD/AERSCREEN for refined direct-source permitting and CAMx/CMAQ/WRF-Chem or an approved reduced-form method for secondary PM2.5 chemistry.

## Quick Start

Run worst-case and historical-event simulations using the original `405 lb/hr` primary PM2.5 assumption:

```bash
cd /Users/daenonjanis/projects/stratos-pm25-model
python3 stratos_pm25_model.py --mode all --years 2024 2025
```

The default PM2.5 background station is strict. `BG` is not present in the
Utah DAQ PM2.5 archive CSVs for 2022-2023, so a four-year proxy run must
explicitly allow fallback background stations:

```bash
python3 stratos_pm25_model.py \
  --mode all \
  --years 2022 2023 2024 2025 \
  --pm25-fallback-stations BV EN CV SM H3
```

Run a faster smoke test:

```bash
python3 stratos_pm25_model.py --mode worst --grid-radius-km 20 --grid-step-km 10
```

Outputs are written under `runs/YYYYMMDD_HHMMSS/`.

For the comparison matrix used by the current screening summary, run:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python run_screening_matrix.py \
  --matrix-name 20260507_all_events_70km_screen_v3_conservative_secondaries \
  --grid-radius-km 70 \
  --grid-step-km 2.5
```

The matrix runs strict `BG` 2024-2025 and four-year proxy 2022-2025 periods
across three assumption-labeled emissions cases:

- `direct_only`: primary PM2.5 only
- `typical_secondary`: primary PM2.5 plus the illustrative precursor rates with the `typical_inversion` conversion profile
- `worst_secondary`: primary PM2.5 plus the illustrative precursor rates with the conservative `worst_inversion` conversion profile

It writes merged comparison tables to `runs/screening_matrix/<matrix-name>/comparison/`.

## Historical Data

The model downloads and caches Utah DAQ archive CSVs from:

- `https://air.utah.gov/dataarchive/YYYY-WindSpeed.csv`
- `https://air.utah.gov/dataarchive/YYYY-WindDir.csv`
- `https://air.utah.gov/dataarchive/YYYY-Temperature.csv`
- `https://air.utah.gov/dataarchive/YYYY-PM2.5.csv`

Defaults:

- met station: `BG` for Brigham City
- PM2.5 station: `BG`
- met fallback stations: `BV EN CV SM H3` when the requested met station is missing in older archive years
- PM2.5 fallback stations: none by default; add them explicitly for proxy background runs
- years: `2022 2023 2024 2025` if requested, but strict `BG` background only works for years where `BG` is present

You can change stations:

```bash
python3 stratos_pm25_model.py --met-station BG --pm25-station BG
```

The run writes `station_usage.csv` so you can see which station was actually
used for each year. Utah DAQ did not publish every station in every historical
CSV, so this fallback is explicit rather than silent.

Use `--all-events` to model every detected inversion/stagnation event instead
of only the top `--max-events` rows. Use `--run-name` when a deterministic
output path is needed for reproducible comparison matrices.

## Emissions

The default preserves the original script's primary PM2.5 rate:

```text
primary PM2.5 = 405 lb/hr = about 51 g/s
```

Precursor emissions default to zero because they should come from permit limits, stack tests, or a clearly labeled emission-factor scenario.

To test secondary PM2.5 sensitivity:

```bash
python3 stratos_pm25_model.py \
  --mode all \
  --primary-pm25-lb-hr 405 \
  --nox-lb-hr 250 \
  --so2-lb-hr 5 \
  --nh3-lb-hr 40 \
  --voc-lb-hr 30 \
  --secondary-profile worst_inversion
```

Secondary profiles:

- `none`
- `typical_inversion`
- `worst_inversion`

These are screening coefficients, not atmospheric chemistry. The current
`worst_inversion` profile is deliberately conservative for high-end sensitivity:
NOx 0.60, SO2 0.80, NH3 0.50, and VOC 0.20 before the model's simple
nitrate/sulfate mass-uplift factors.

You can override the secondary conversion factors directly:

```bash
python3 stratos_pm25_model.py \
  --mode historical \
  --years 2024 2025 \
  --nox-lb-hr 250 \
  --nh3-lb-hr 40 \
  --secondary-profile worst_inversion \
  --nox-to-nitrate-fraction 0.75 \
  --nh3-to-ammonium-fraction 0.60
```

The receptor-grid model also applies a conservative trapped-lid floor when plume
rise places emissions near the inversion lid. That is meant to avoid the false
comfort of a high plume sitting mathematically above all ground receptors while
the regional box model shows accumulation.

## Worst Case

The worst-case mode creates a synthetic locked inversion:

- duration: `72` hours
- wind speed: `1.5 m/s`
- wind direction from: `180 degrees`
- mixing height: `400 m`
- stability: `F`

Example:

```bash
python3 stratos_pm25_model.py \
  --mode worst \
  --worst-duration-hours 120 \
  --worst-wind-speed-m-s 1.0 \
  --mixing-height-m 250 \
  --secondary-profile worst_inversion
```

## Output Files

Typical files:

- `README.md`: run metadata and caveats
- `worst_case_grid.csv`: receptor-grid worst-case increments
- `worst_case_box_timeseries.csv`: regional box accumulation
- `detected_inversion_events.csv`: all detected historical events
- `station_usage.csv`: selected archive station per year after fallback
- `historical_event_summary.csv`: summarized modeled events
- `events/*_grid.csv`: receptor-grid output for each selected historical event

Important columns:

- `avg_increment_ug_m3`: event-average modeled increment at receptor
- `max_hourly_increment_ug_m3`: highest modeled hourly increment at receptor
- `avg_increment_percent_of_event_avg_bg`: event-average increment as a percent of recorded event-average PM2.5
- `max_hourly_percent_of_event_peak_bg`: highest hourly increment as a percent of recorded event peak PM2.5
- `avg_secondary_increment_ug_m3`: secondary share from configured precursor profile
- `max_box_increment_ug_m3`: basin-scale mixed accumulation estimate

## Population Overlay

Install the overlay dependency:

```bash
python3 -m pip install -r requirements.txt
```

Then run the reproducible Census population overlay against a completed run:

```bash
python3 population_overlay.py \
  --run-dir runs/hansel_population_overlay_2p5km/20260506_184451 \
  --site-lat 41.7744825 \
  --site-lon -112.6559297 \
  --radius-km 50 \
  --place-radius-km 50 \
  --site-sensitivity-km 0 5 10
```

Outputs are written to `population_overlay/` under the run directory:

- `population_overlay_blocks.csv`
- `population_threshold_summary.csv`
- `population_event_threshold_summary.csv`
- `population_weighted_percentiles.csv`
- `place_exposure_summary.csv`
- `site_location_sensitivity.csv`

By default, place-centroid tables are capped to the modeled receptor-grid
domain so a place outside the grid is not reported as if it were explicitly
modeled. Use `--include-outside-grid-places` only for diagnostics; those rows
are marked with `inside_model_domain` and `outside_model_domain_km`.

Event-specific exposure tables answer "how many people exceeded a threshold
during the same modeled inversion event?" The threshold summary answers the
different max-over-history question: "how many people had at least one modeled
event above a threshold?"

## Comparison Tables

Completed runs can be merged into event-window monitor background, modeled
increment, and arithmetic background-plus-increment tables with:

```bash
python3 compare_model_runs.py \
  --output-dir runs/comparison_example \
  --scenario label_one=runs/path/to/run_one \
  --scenario label_two=runs/path/to/run_two
```

The outputs are:

- `scenario_assumptions.csv`
- `scenario_population_comparison.csv`
- `scenario_place_comparison.csv`
- `scenario_event_comparison.csv`
- `scenario_bad_case_benchmark.csv`
- `scenario_max_increment_benchmark.csv`

## Tests

```bash
python3 -m unittest -v
```
