# Stratos PM2.5 Screening Comparison

This document summarizes an assumption-labeled PM2.5 screening matrix for the approximate Stratos project-center source point in Box Elder County, Utah. It is structured to show methodology, input assumptions, event-window monitor background concentrations, modeled incremental concentrations, and arithmetic background-plus-increment comparisons. It does not estimate mortality, dose, indoor exposure, toxicology, or regulatory compliance.

The main comparison run used a 70 km receptor grid so Brigham City and other larger nearby population centers are inside the modeled domain rather than assigned to an edge receptor. A 50 km immediate-area matrix was also generated and remains available in the run artifacts.

## How These Numbers Are Derived

The project-increment numbers are not directly measured project pollution. They are modeled screening estimates made by replaying historical inversion/stagnation weather as if the project source existed during those events.

Plain-language workflow:

1. Historical Utah monitor data is loaded for PM2.5, wind speed, wind direction, and temperature.
2. Winter inversion/stagnation events are detected from cold-season timing, low wind, elevated hourly PM2.5, and elevated rolling 24-hour PM2.5.
3. Each detected event is rerun through the dispersion model using the observed hourly wind direction, wind speed, and temperature.
4. The model estimates how much PM2.5 the assumed project emissions would add at each receptor point on the 70 km grid.
5. Each town/place centroid is assigned to the nearest modeled receptor.
6. For each place, the "max project-increment" event is the historical event where the simulation produced that place's largest modeled project-added PM2.5.
7. For each place, the "max total" event is the historical event where the arithmetic screening total was largest: BG/BV monitor background for that event plus the modeled project increment for that event.

The model uses meteorology and a simplified dispersion simulation to determine which event would produce the greatest project increment in a given area. It is not using a sensor measurement of project PM2.5, because the project emissions are hypothetical in this historical replay.

Reliability interpretation:

- Best used for first-pass screening, relative comparisons, and identifying whether modeled increments appear small, moderate, or large enough to warrant refined modeling.
- More reliable for comparing scenarios and broad spatial patterns than for claiming an exact PM2.5 value at a specific town.
- Less reliable where exact source coordinates, stack parameters, building downwash, local terrain winds, inversion depth, secondary chemistry, or place-specific background PM2.5 are important.
- The BG/BV background values are monitor context, not measured town-specific background unless the town is represented by that monitor.
- A permitting-grade or health-impact estimate would need refined source parameters, local meteorology, and accepted regulatory or chemical-transport modeling.

## What Was Run

Primary matrix:

- Run folder: `runs/screening_matrix/20260507_all_events_70km_screen_v3_conservative_secondaries`
- Comparison tables: `runs/screening_matrix/20260507_all_events_70km_screen_v3_conservative_secondaries/comparison`
- Source point: `41.7744825, -112.6559297`
- Receptor grid: 70 km radius, 2.5 km spacing
- Population overlay: 2020 Census block population within 70 km, Box Elder County only
- Event handling: every detected winter inversion/stagnation event was modeled, not only the top ranked events

Historical periods:

| Period | Years | Met station use | PM2.5 background use |
|---|---:|---|---|
| Strict BG | 2024-2025 | BG both years | BG both years |
| Four-year proxy | 2022-2025 | BV for 2022-2023, BG for 2024-2025 | BV for 2022-2023, BG for 2024-2025 |

Plain-language label key:

- `Strict BG` means the shorter 2024-2025 run where the Brigham City `BG` monitor/station is used for both meteorology and PM2.5 background. It is "strict" because it avoids substituting another background station for missing earlier BG years.
- `Four-year proxy` means the longer 2022-2025 run. It includes more historical inversion events, but uses `BV` as the proxy/fallback station for 2022-2023 and `BG` for 2024-2025. It is "proxy" because the full period is not all measured at the same BG station.

Emission scenarios:

| Scenario | Primary PM2.5 | NOx | SO2 | NH3 | VOC | Secondary PM treatment |
|---|---:|---:|---:|---:|---:|---|
| Direct only | 405 lb/hr | 0 | 0 | 0 | 0 | none |
| Typical secondary | 405 lb/hr | 250 lb/hr | 5 lb/hr | 40 lb/hr | 30 lb/hr | `typical_inversion` screening coefficients |
| Conservative worst secondary | 405 lb/hr | 250 lb/hr | 5 lb/hr | 40 lb/hr | 30 lb/hr | higher `worst_inversion` screening coefficients |

These are screening assumptions. They are not confirmed permit limits or stack-test values.

Scenario label key:

- `Direct only` means only directly emitted primary PM2.5 is counted.
- `Typical secondary` means primary PM2.5 plus a simple screening estimate for secondary PM2.5 formed from NOx, SO2, NH3, and VOC precursors under the model's `typical_inversion` coefficients.
- `Conservative worst secondary` means the same precursor emissions are included with the higher `worst_inversion` screening coefficients. The updated conservative profile converts NOx, SO2, NH3, and VOC at 0.60, 0.80, 0.50, and 0.20 respectively before the simple mass-uplift factors for nitrate/sulfate. It is the highest secondary-PM assumption in this matrix, not a claim about the worst physically possible event.
- A combined label such as `Four-year proxy conservative worst` means: use the four-year proxy historical period and the conservative-worst secondary emissions/chemistry assumption.

## Method

1. Utah DAQ archive CSVs were loaded for PM2.5, wind speed, wind direction, and temperature.
2. Winter inversion/stagnation events were identified using cold-season timing, low wind, elevated hourly PM2.5, and elevated rolling 24-hour PM2.5.
3. Each event was modeled on a receptor grid using hourly wind-direction rotation, Pasquill-Gifford-style stable dispersion, simple plume rise, inversion-lid reflection, and a trapped-lid fumigation floor. Deposition is included only in the separate broad mixed-box accumulation estimate, not in the receptor-grid Gaussian plume increments.
4. Secondary PM2.5 was represented by simple precursor-to-PM2.5 screening coefficients. No CAMx, CMAQ, WRF-Chem, or equivalent chemistry model was used.
5. Census block centroids were assigned to the nearest receptor. The assignment is now computed once per block/place per source location and reused across event grids with the same geometry.
6. Place-centroid outputs are capped to the receptor-grid domain by default. Off-grid place estimates are not included unless explicitly requested for diagnostics.
7. For SLC comparison, Salt Lake City Hawthorne `HW` PM2.5 was calculated over the same event windows as each modeled event.

## Population Exposure, 70 km Screen

Values are modeled event-average PM2.5 increments in ug/m3. Population counts are 2020 Census block population within the 70 km Box Elder County screen.

This table is max-over-history: each Census block is assigned its own largest modeled event-average increment across all modeled events. It answers "how many people have at least one modeled event above the threshold?" It is not a simultaneous single-event exposure count.

| Scenario | p50 added | p95 added | p99 added | Population >=2 | Population >=5 | Population >=10 |
|---|---:|---:|---:|---:|---:|---:|
| Strict BG direct only | 0.57 | 1.62 | 2.39 | 732 | 278 | 18 |
| Strict BG typical secondary | 0.61 | 1.75 | 2.58 | 738 | 345 | 18 |
| Strict BG conservative worst secondary | 0.90 | 2.57 | 3.79 | 8,368 | 514 | 50 |
| Four-year proxy direct only | 0.78 | 1.64 | 2.85 | 1,060 | 288 | 24 |
| Four-year proxy typical secondary | 0.84 | 1.76 | 3.07 | 1,092 | 360 | 24 |
| Four-year proxy conservative worst secondary | 1.24 | 2.59 | 4.52 | 9,232 | 522 | 72 |

The underlying CSV includes additional thresholds at 0.5, 1.0, 3.0, 7.5, 12.5, 15.0, and 20.0 ug/m3.

## Event-Specific Population Exposure

This table is event-specific: it selects individual events that maximize the number of people above selected thresholds. It is the better table for asking "how many people are above X during the same modeled inversion event?"

| Period | Event selected by | Event window | Population >=2 | Population >=5 | Population >=10 | p95 added | Max populated block |
|---|---|---|---:|---:|---:|---:|---:|
| Strict BG conservative worst | max pop >=2 | 2025-11-29 16 to 2025-11-30 17 | 4,960 | 195 | 0 | 2.46 | 7.7 |
| Strict BG conservative worst | max pop >=5 | 2025-11-26 19 to 2025-11-27 08 | 320 | 261 | 24 | 0.00 | 12.2 |
| Strict BG conservative worst | max pop >=10 | 2025-03-03 20 to 2025-03-04 08 | 256 | 238 | 40 | 0.00 | 17.8 |
| Four-year proxy conservative worst | max pop >=2 | 2025-11-29 16 to 2025-11-30 17 | 4,960 | 195 | 0 | 2.46 | 7.7 |
| Four-year proxy conservative worst | max pop >=5 | 2025-11-26 19 to 2025-11-27 08 | 320 | 261 | 24 | 0.00 | 12.2 |
| Four-year proxy conservative worst | max pop >=10 | 2025-03-03 20 to 2025-03-04 08 | 256 | 238 | 40 | 0.00 | 17.8 |

The full artifact is `scenario_event_population_comparison.csv`.

## Bad-Case Max-to-Max Benchmark

This table is the cleaner comparison for the question: "What do bad PM2.5 scenarios look like in the modeled rural places versus bad measured SLC outcomes?" It scans every modeled inversion/stagnation event and reports each place's maximum arithmetic event-average total: BG/BV monitor background for that event plus the modeled place increment for that same event. It then compares that maximum rural screening total to SLC Hawthorne's maximum measured event-window average and maximum measured winter rolling 24-hour value over the same years.

Interpretation limit: the rural total is still not a measured local city value. It is the model's place increment added to the BG/BV monitor background. `SLC max model-window avg` is the largest SLC Hawthorne event-window average among the BG/BV-detected model windows, not an independently detected SLC event. The winter maximum 24-hour SLC value is the independent bad-air benchmark over the same years.

| Period | Place | Max-total event window | Max total | BG/BV avg | Project inc | SLC max model-window avg | SLC winter max 24h |
|---|---|---|---:|---:|---:|---:|---:|
| Strict BG conservative worst | Snowville | 2025-03-28 12 to 2025-03-30 08 | 21.01 | 19.37 | 1.64 | 22.75 | 35.48 |
| Strict BG conservative worst | Howell | 2025-03-28 12 to 2025-03-30 08 | 19.37 | 19.37 | 0.00 | 22.75 | 35.48 |
| Strict BG conservative worst | Portage | 2025-03-28 12 to 2025-03-30 08 | 19.65 | 19.37 | 0.28 | 22.75 | 35.48 |
| Strict BG conservative worst | Tremonton | 2025-03-28 12 to 2025-03-30 08 | 19.37 | 19.37 | 0.00 | 22.75 | 35.48 |
| Strict BG conservative worst | Garland | 2025-03-28 12 to 2025-03-30 08 | 19.37 | 19.37 | 0.00 | 22.75 | 35.48 |
| Strict BG conservative worst | Brigham City | 2025-03-28 12 to 2025-03-30 08 | 19.37 | 19.37 | 0.00 | 22.75 | 35.48 |
| Four-year proxy conservative worst | Snowville | 2023-01-30 18 to 2023-02-07 08 | 30.65 | 27.58 | 3.08 | 28.82 | 51.71 |
| Four-year proxy conservative worst | Howell | 2023-01-30 18 to 2023-02-07 08 | 29.65 | 27.58 | 2.07 | 28.82 | 51.71 |
| Four-year proxy conservative worst | Portage | 2023-01-30 18 to 2023-02-07 08 | 28.13 | 27.58 | 0.55 | 28.82 | 51.71 |
| Four-year proxy conservative worst | Tremonton | 2023-01-30 18 to 2023-02-07 08 | 28.46 | 27.58 | 0.89 | 28.82 | 51.71 |
| Four-year proxy conservative worst | Garland | 2023-01-30 18 to 2023-02-07 08 | 28.46 | 27.58 | 0.89 | 28.82 | 51.71 |
| Four-year proxy conservative worst | Brigham City | 2023-01-30 18 to 2023-02-07 08 | 28.08 | 27.58 | 0.50 | 28.82 | 51.71 |

The full artifact is `scenario_bad_case_benchmark.csv`. It also includes the event windows for each maximum, modeled hourly screening totals, SLC winter maximum hourly values, and percentage comparisons to SLC's rolling 24-hour maximum.

## Max Project-Increment Benchmark

This table answers a different question: "During the inversion/stagnation event where the project would add the most PM2.5 at a place, what was the measured background during that same event?" This is useful because the maximum project increment and the maximum total PM2.5 do not necessarily occur during the same event.

Interpretation limit: the BG/BV value is still the background monitor used by the run, not a measured city-specific value. The "BG/BV + increment" column is arithmetic context for that event.

| Period | Place | Max-increment event window | BG/BV avg in event | Project increment | BG/BV + increment | SLC avg same window | SLC max model-window avg | SLC winter max 24h |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Strict BG conservative worst | Snowville | 2025-03-03 20 to 2025-03-04 08 | 4.99 | 9.97 | 14.96 | 5.44 | 22.75 | 35.48 |
| Strict BG conservative worst | Howell | 2025-11-29 16 to 2025-11-30 17 | 3.37 | 5.76 | 9.13 | 6.89 | 22.75 | 35.48 |
| Strict BG conservative worst | Portage | 2025-12-03 20 to 2025-12-04 10 | 5.71 | 2.47 | 8.18 | 6.49 | 22.75 | 35.48 |
| Strict BG conservative worst | Tremonton | 2025-11-29 16 to 2025-11-30 17 | 3.37 | 1.69 | 5.05 | 6.89 | 22.75 | 35.48 |
| Strict BG conservative worst | Garland | 2025-11-29 16 to 2025-11-30 17 | 3.37 | 1.69 | 5.05 | 6.89 | 22.75 | 35.48 |
| Strict BG conservative worst | Brigham City | 2025-03-13 18 to 2025-03-14 10 | 1.11 | 0.81 | 1.93 | 1.24 | 22.75 | 35.48 |
| Four-year proxy conservative worst | Snowville | 2025-03-03 20 to 2025-03-04 08 | 4.99 | 9.97 | 14.96 | 5.44 | 28.82 | 51.71 |
| Four-year proxy conservative worst | Howell | 2025-11-29 16 to 2025-11-30 17 | 3.37 | 5.76 | 9.13 | 6.89 | 28.82 | 51.71 |
| Four-year proxy conservative worst | Portage | 2022-02-15 19 to 2022-02-16 11 | 2.99 | 3.75 | 6.73 | 5.15 | 28.82 | 51.71 |
| Four-year proxy conservative worst | Tremonton | 2022-12-22 05 to 2022-12-27 06 | 23.76 | 1.77 | 25.53 | 25.55 | 28.82 | 51.71 |
| Four-year proxy conservative worst | Garland | 2022-12-22 05 to 2022-12-27 06 | 23.76 | 1.77 | 25.53 | 25.55 | 28.82 | 51.71 |
| Four-year proxy conservative worst | Brigham City | 2025-03-13 18 to 2025-03-14 10 | 1.11 | 0.81 | 1.93 | 1.24 | 28.82 | 51.71 |

The full artifact is `scenario_max_increment_benchmark.csv`. It also includes rolling 24-hour monitor context and percent-of-SLC comparison columns.

## Place-Center Comparison

Rows show the event that produced each place's maximum modeled event-average increment in the 70 km matrix. Because the maximum can occur during a different event for each place, the SLC Hawthorne comparison value is not expected to be constant across rows.

Important interpretation limit: the BG/BV column is not a measured place-specific rural baseline. It is the event-window PM2.5 average from the available background monitor used in the run. The arithmetic total is therefore monitor background plus modeled increment, not an estimate that Snowville, Howell, Portage, Tremonton, Garland, or Brigham City would have exactly that without-project PM2.5 concentration. A defensible place-specific baseline would require a local monitor, monitor interpolation, or another documented background-field method.

| Period | Place | Event window | BG/BV monitor avg | Added direct | Added typical | Added conservative worst | BG/BV avg + added conservative worst | SLC HW avg same window |
|---|---|---|---:|---:|---:|---:|---:|---:|
| Strict BG 2024-2025 | Snowville | 2025-03-03 20 to 2025-03-04 08 | 4.99 | 6.30 | 6.78 | 9.97 | 14.96 | 5.44 |
| Strict BG 2024-2025 | Howell | 2025-11-29 16 to 2025-11-30 17 | 3.37 | 3.64 | 3.92 | 5.76 | 9.13 | 6.89 |
| Strict BG 2024-2025 | Portage | 2025-12-03 20 to 2025-12-04 10 | 5.71 | 1.56 | 1.68 | 2.47 | 8.18 | 6.49 |
| Strict BG 2024-2025 | Tremonton | 2025-11-29 16 to 2025-11-30 17 | 3.37 | 1.06 | 1.15 | 1.69 | 5.05 | 6.89 |
| Strict BG 2024-2025 | Garland | 2025-11-29 16 to 2025-11-30 17 | 3.37 | 1.06 | 1.15 | 1.69 | 5.05 | 6.89 |
| Strict BG 2024-2025 | Brigham City | 2025-03-13 18 to 2025-03-14 10 | 1.11 | 0.51 | 0.55 | 0.81 | 1.93 | 1.24 |
| Four-year proxy | Snowville | 2025-03-03 20 to 2025-03-04 08 | 4.99 | 6.30 | 6.78 | 9.97 | 14.96 | 5.44 |
| Four-year proxy | Howell | 2025-11-29 16 to 2025-11-30 17 | 3.37 | 3.64 | 3.92 | 5.76 | 9.13 | 6.89 |
| Four-year proxy | Portage | 2022-02-15 19 to 2022-02-16 11 | 2.99 | 2.37 | 2.55 | 3.75 | 6.73 | 5.15 |
| Four-year proxy | Tremonton | 2022-12-22 05 to 2022-12-27 06 | 23.76 | 1.12 | 1.21 | 1.77 | 25.53 | 25.55 |
| Four-year proxy | Garland | 2022-12-22 05 to 2022-12-27 06 | 23.76 | 1.12 | 1.21 | 1.77 | 25.53 | 25.55 |
| Four-year proxy | Brigham City | 2025-03-13 18 to 2025-03-14 10 | 1.11 | 0.51 | 0.55 | 0.81 | 1.93 | 1.24 |

## Worst Physical Receptor Comparison

The worst physical receptor is not necessarily populated. This table shows the largest event-average receptor increment anywhere on the grid for each scenario. "BG/BV monitor avg" is the same event-window monitor context described above, not a receptor-specific measured background. "Mixed-box added" is the broad accumulation estimate for the same event and scenario.

| Scenario | Event with largest physical receptor | BG/BV monitor avg | Max physical added | BG/BV avg + max physical | Mixed-box added | SLC HW avg |
|---|---|---:|---:|---:|---:|---:|
| Strict BG direct only | 2024-01-15 to 2024-01-17 | 9.15 | 50.84 | 59.99 | 1.55 | 10.06 |
| Strict BG typical secondary | 2024-01-15 to 2024-01-17 | 9.15 | 54.72 | 63.87 | 1.67 | 10.06 |
| Strict BG conservative worst secondary | 2024-01-15 to 2024-01-17 | 9.15 | 80.46 | 89.61 | 2.46 | 10.06 |
| Four-year proxy direct only | 2022-02-07 to 2022-02-08 | 6.87 | 55.38 | 62.25 | 0.97 | 13.60 |
| Four-year proxy typical secondary | 2022-02-07 to 2022-02-08 | 6.87 | 59.61 | 66.47 | 1.05 | 13.60 |
| Four-year proxy conservative worst secondary | 2022-02-07 to 2022-02-08 | 6.87 | 87.65 | 94.52 | 1.54 | 13.60 |

## Source-Location Sensitivity

The table below uses the 70 km conservative-worst secondary runs and shifts the assumed source point while keeping the same modeled plume fields. Counts are 2020 Census block population within the shifted 70 km screen.

| Period | Shift | Population >=2 | Population >=5 | Population >=10 | p95 added | Max populated block |
|---|---|---:|---:|---:|---:|---:|
| Strict BG | base | 8,368 | 514 | 50 | 2.57 | 22.1 |
| Strict BG | 10 km east | 19,472 | 664 | 238 | 3.78 | 40.3 |
| Strict BG | 10 km west | 3,244 | 300 | 45 | 2.09 | 28.3 |
| Strict BG | 10 km north | 12,496 | 324 | 266 | 2.66 | 59.3 |
| Strict BG | 10 km south | 21,254 | 470 | 11 | 3.10 | 22.1 |
| Four-year proxy | base | 9,232 | 522 | 72 | 2.59 | 22.1 |
| Four-year proxy | 10 km east | 32,392 | 725 | 244 | 3.78 | 40.3 |
| Four-year proxy | 10 km west | 3,587 | 430 | 57 | 2.18 | 28.3 |
| Four-year proxy | 10 km north | 12,654 | 341 | 275 | 2.66 | 67.5 |
| Four-year proxy | 10 km south | 21,875 | 636 | 11 | 3.12 | 22.1 |

## Code Audit Changes

The code was updated to make these comparisons more reproducible and less prone to overstatement:

- `stratos_pm25_model.py` now supports `--all-events` so the matrix can model every detected event, not only the top `--max-events` rows.
- `stratos_pm25_model.py` now supports `--run-name` for deterministic output directories.
- `stratos_pm25_model.py` now models continuous event windows between the first and last candidate hour, rather than averaging only the candidate hours inside a labelled event range.
- `stratos_pm25_model.py` now uses a more conservative `worst_inversion` secondary screening profile for the high-end sensitivity case: NOx 0.60, SO2 0.80, NH3 0.50, and VOC 0.20.
- `population_overlay.py` now caps place summaries to the receptor-grid domain by default and marks outside-domain diagnostic rows when explicitly requested.
- `population_overlay.py` now reuses the nearest receptor for grids with common geometry, reducing the all-events overlay runtime substantially.
- `population_overlay.py` now writes event-specific population exposure summaries, so simultaneous single-event counts can be compared against max-over-history counts.
- `compare_model_runs.py` was added to create merged assumption, population, place, and event comparison CSVs.
- `compare_model_runs.py` now writes `scenario_event_population_comparison.csv` and labels SLC event-window maxima as model-window maxima.
- `run_screening_matrix.py` was added to reproduce the strict/proxy and direct/typical/conservative-worst scenario matrix.
- Documentation now clarifies that deposition is included in the broad mixed-box estimate, not in the Gaussian receptor-grid increments.
- Unit tests now include wind-direction handling, upwind zeroing, emission linearity, wind-speed response, rolling averages, continuous event-window detection, secondary profile overrides, conservative secondary profile coverage, population-overlay domain marking, and event-specific population counting.

Verification command:

```bash
.venv/bin/python -m unittest -v
```

## Reliability Boundaries

These outputs are screening estimates. They should not be read as final health, mortality, regulatory, or permit conclusions.

Known unresolved inputs:

- exact source coordinates and stack count
- stack height, exhaust temperature, exit velocity, stack diameter, and building downwash
- actual permitted hourly PM2.5, NOx, SO2, NH3, and VOC limits
- actual dispatch/load profile by hour and season
- site-specific meteorology at the project site
- valley-specific inversion depth, cold-air-pool structure, terrain effects, and drainage winds
- validated secondary PM2.5 chemistry
- exposure-response functions, baseline mortality, age/health vulnerability, indoor infiltration, and time-activity patterns

For permitting-grade or health-impact work, this screening model would need to be replaced or checked against the appropriate regulatory and chemistry tools, such as AERMOD/AERSCREEN for direct-source dispersion and CAMx/CMAQ/WRF-Chem or an accepted reduced-form method for secondary PM2.5.

## Reproducibility Pointers

Primary run artifacts used here:

- 70 km matrix: `runs/screening_matrix/20260507_all_events_70km_screen_v3_conservative_secondaries`
- 50 km supplemental matrix: `runs/screening_matrix/20260507_all_events_screen`
- Matrix runner: `run_screening_matrix.py`
- Comparison generator: `compare_model_runs.py`
- Population overlay: `population_overlay.py`
- Screening model: `stratos_pm25_model.py`

Generated comparison tables:

- `scenario_assumptions.csv`
- `scenario_population_comparison.csv`
- `scenario_event_population_comparison.csv`
- `scenario_place_comparison.csv`
- `scenario_event_comparison.csv`
- `scenario_bad_case_benchmark.csv`
- `scenario_max_increment_benchmark.csv`

## Citations

1. Utah Division of Air Quality, Utah Data Archive: https://air.utah.gov/dataarchive/index.htm
2. Utah Division of Air Quality, Air Monitoring Network Station Information: https://air.utah.gov/network/Counties.htm
3. Box Elder County, Stratos Project Map: https://www.boxeldercountyut.gov/644/Stratos-Project-Map
4. Box Elder County, Stratos Project Fact Sheet: https://www.boxeldercountyut.gov/DocumentCenter/View/2116/Stratos-Project-Fact-Sheet
5. U.S. Census Bureau, 2020 Decennial Census Redistricting Data PL 94-171 API: https://api.census.gov/data/2020/dec/pl.html
6. U.S. Census Bureau, TIGER/Line Shapefiles: https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html
7. U.S. EPA, Air Quality Dispersion Modeling / SCRAM: https://www.epa.gov/scram/air-quality-dispersion-modeling
8. U.S. EPA, Preferred and Recommended Models, including AERMOD context: https://www.epa.gov/scram/air-quality-dispersion-modeling-preferred-and-recommended-models
9. U.S. EPA, 2024 revised annual PM2.5 NAAQS page: https://www.epa.gov/particle-pollution-designations/particle-pollution-designations-2024-revised-annual-pm-naaqs-where
