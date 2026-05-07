# Stratos PM2.5 Screening Findings

This narrative summary is a companion to `stratos_pm25_population_comparison_summary.md`, which remains the evidence-first table document. Both documents now refer to the same current screening matrix:

- Primary run: `runs/screening_matrix/20260507_all_events_70km_screen_v3_conservative_secondaries`
- Source point: `41.7744825, -112.6559297`, an approximate Hansel Valley project-area point, not an exact stack coordinate
- Receptor grid: 70 km radius, 2.5 km spacing
- Population overlay: 2020 Census block population within the 70 km Box Elder County screen
- Historical periods: strict `BG` 2024-2025 and four-year proxy 2022-2025

This is a screening model. It does not estimate mortality, indoor exposure, toxicology, permitting compliance, or exact town-specific background PM2.5.

## Executive Summary

The current model points to a localized, event-dependent PM2.5 increment rather than a countywide toxic-air scenario. The project signal is not zero, and some near-source or downwind receptors can see meaningful modeled additions during certain stagnant winter events. But at the base assumed source point, most populated areas are modeled in the low-single-digit increment range.

The most important caution is siting. The modeled coordinate is an approximate Hansel Valley anchor. Public project materials identify a broad Stratos/Hansel Valley project area, not exact stack coordinates. Our own source-location sensitivity shows that 10 km shifts can materially change which blocks and communities fall into higher-increment bands.

## Current Method In Plain English

The project increments are modeled, not measured. The workflow is:

1. Load historical Utah DAQ PM2.5, wind speed, wind direction, and temperature data.
2. Detect winter inversion/stagnation events from cold-season timing, low wind, elevated hourly PM2.5, and elevated rolling 24-hour PM2.5.
3. Replay each detected event as if the assumed project source existed during that event.
4. Use a simplified plume-dispersion screen with hourly wind rotation, stable dispersion, plume rise, inversion-lid reflection, and trapped-lid fumigation.
5. Add simple screening secondary-PM assumptions for NOx, SO2, NH3, and VOC precursor cases.
6. Assign Census block and place centroids to the nearest modeled receptor.
7. Compare modeled increments with BG/BV background monitor context and SLC Hawthorne monitor context over the same event windows.

The model is more useful for first-pass screening, scenario comparison, and sensitivity checks than for exact local concentration claims.

## Emissions Scenarios

The matrix compares three assumptions:

| Scenario | Primary PM2.5 | NOx | SO2 | NH3 | VOC | Secondary treatment |
|---|---:|---:|---:|---:|---:|---|
| Direct only | 405 lb/hr | 0 | 0 | 0 | 0 | none |
| Typical secondary | 405 lb/hr | 250 lb/hr | 5 lb/hr | 40 lb/hr | 30 lb/hr | `typical_inversion` coefficients |
| Conservative worst secondary | 405 lb/hr | 250 lb/hr | 5 lb/hr | 40 lb/hr | 30 lb/hr | higher `worst_inversion` coefficients |

The conservative-worst secondary case converts NOx, SO2, NH3, and VOC at 0.60, 0.80, 0.50, and 0.20 respectively before simple nitrate/sulfate mass-uplift factors. It is a high-end sensitivity case, not a chemical-transport model.

## Population Exposure

The 70 km population table is max-over-history: each Census block is assigned its own largest modeled event-average increment across all modeled events. It answers, "how many people had at least one modeled event above this threshold?"

| Scenario | p50 added | p95 added | p99 added | Population >=2 | Population >=5 | Population >=10 |
|---|---:|---:|---:|---:|---:|---:|
| Strict BG direct only | 0.57 | 1.62 | 2.39 | 732 | 278 | 18 |
| Strict BG typical secondary | 0.61 | 1.75 | 2.58 | 738 | 345 | 18 |
| Strict BG conservative worst secondary | 0.90 | 2.57 | 3.79 | 8,368 | 514 | 50 |
| Four-year proxy direct only | 0.78 | 1.64 | 2.85 | 1,060 | 288 | 24 |
| Four-year proxy typical secondary | 0.84 | 1.76 | 3.07 | 1,092 | 360 | 24 |
| Four-year proxy conservative worst secondary | 1.24 | 2.59 | 4.52 | 9,232 | 522 | 72 |

The event-specific table is more appropriate for simultaneous exposure. In the conservative-worst runs, the event that maximized population above 2 ug/m3 had 4,960 people above that threshold during the same modeled event. Events that maximized higher thresholds had much smaller exposed populations: 261 people above 5 ug/m3 and 40 people above 10 ug/m3.

## Place-Level Findings

For the event where each place receives its maximum modeled project increment under the conservative-worst scenario:

| Period | Place | Max modeled project increment | BG/BV + increment in that event | SLC avg same window |
|---|---|---:|---:|---:|
| Strict BG | Snowville | 9.97 | 14.96 | 5.44 |
| Strict BG | Howell | 5.76 | 9.13 | 6.89 |
| Strict BG | Tremonton | 1.69 | 5.05 | 6.89 |
| Strict BG | Garland | 1.69 | 5.05 | 6.89 |
| Strict BG | Brigham City | 0.81 | 1.93 | 1.24 |
| Four-year proxy | Snowville | 9.97 | 14.96 | 5.44 |
| Four-year proxy | Howell | 5.76 | 9.13 | 6.89 |
| Four-year proxy | Tremonton | 1.77 | 25.53 | 25.55 |
| Four-year proxy | Garland | 1.77 | 25.53 | 25.55 |
| Four-year proxy | Brigham City | 0.81 | 1.93 | 1.24 |

The Tremonton/Garland high total in the four-year proxy row is mostly background monitor context during that selected event, not project increment. Their modeled project increment is about 1.77 ug/m3 in that row.

## Bad-Case Benchmark

The bad-case max-to-max comparison asks what bad modeled rural totals look like compared with bad measured SLC outcomes. Under the four-year proxy conservative-worst run:

- Snowville max arithmetic event-average total: 30.65 ug/m3
- Howell max arithmetic event-average total: 29.65 ug/m3
- Tremonton/Garland max arithmetic event-average total: 28.46 ug/m3
- SLC Hawthorne max model-window average: 28.82 ug/m3
- SLC Hawthorne winter max rolling 24-hour value: 51.71 ug/m3

This benchmark does not support a claim that the base-location screen creates unprecedented countywide PM2.5 levels. It does support a more modest concern: the project can make some inversion events measurably worse in modeled downwind places.

## Worst Physical Receptors

The highest receptor increments are much larger than the place-center values:

| Scenario | Max physical added | BG/BV avg + max physical |
|---|---:|---:|
| Strict BG conservative worst secondary | 80.46 | 89.61 |
| Four-year proxy conservative worst secondary | 87.65 | 94.52 |

These worst receptors are not necessarily populated. They should be treated as near-source/grid-sensitive warning flags that need refined source coordinates, stack parameters, building downwash, and local meteorology before being interpreted as community exposure.

## Source-Location Sensitivity

Siting is one of the largest uncertainties. In the 70 km conservative-worst runs:

| Period | Shift | Population >=2 | Population >=5 | Population >=10 | Max populated block |
|---|---|---:|---:|---:|---:|
| Strict BG | base | 8,368 | 514 | 50 | 22.1 |
| Strict BG | 10 km east | 19,472 | 664 | 238 | 40.3 |
| Strict BG | 10 km north | 12,496 | 324 | 266 | 59.3 |
| Four-year proxy | base | 9,232 | 522 | 72 | 22.1 |
| Four-year proxy | 10 km east | 32,392 | 725 | 244 | 40.3 |
| Four-year proxy | 10 km north | 12,654 | 341 | 275 | 67.5 |

That sensitivity is why exact stack/facility coordinates matter before making strong near-field claims.

## Accuracy Audit

The numbers are credible as an initial screen because:

- Utah DAQ monitor and meteorological archives drive event selection and hourly transport.
- SLC Hawthorne comparisons use measured PM2.5 over the same event windows.
- The matrix now models every detected event, not only a top-event subset.
- Event windows are modeled continuously between first and last detected candidate hour.
- Population summaries distinguish max-over-history exposure from event-specific simultaneous exposure.
- Unit tests cover wind-direction rotation, upwind zeroing, emission linearity, wind-speed response, rolling averages, continuous event windows, secondary profiles, and population-overlay behavior.

The numbers are not permit-grade because:

- Exact stack coordinates, stack count, stack height, stack temperature, exit velocity, building downwash, and hourly dispatch are not known.
- The precursor rates are illustrative assumptions, not confirmed permit or stack-test values.
- Secondary PM2.5 chemistry is represented by screening coefficients, not CAMx, CMAQ, WRF-Chem, or an accepted reduced-form chemistry model.
- One regional monitor/station context is used for background and meteorology, which cannot resolve all local valley drainage and cold-air-pool behavior.
- Background PM2.5 values are monitor context, not measured town-specific baselines.
- The analysis does not estimate mortality, toxicology, indoor exposure, or dose.

## Bottom Line

From a PM2.5 standpoint, the current screen suggests:

- Not a defensible basis for saying the project will create massive toxic PM2.5 levels across the county.
- Not a defensible basis for dismissing the project as air-quality irrelevant.
- A reasonable basis for saying the project could add measurable PM2.5 during some inversion events, especially near the source and in favored plume paths.
- A strong basis for requiring refined modeling once exact facility layout, stack parameters, emissions, dispatch profile, and site meteorology are available.

The shortest fair summary is: localized, event-dependent PM2.5 concern; broad countywide catastrophe is not supported by this screen; near-source and source-location-sensitive risk remains unresolved.

## Sources

- Utah DAQ air pollution and meteorological archives: https://air.utah.gov/dataarchive/index.htm
- Utah DAQ station information: https://air.utah.gov/network/Counties.htm
- Box Elder County Stratos project map page: https://www.boxeldercountyut.gov/644/Stratos-Project-Map
- Box Elder County Stratos project fact sheet: https://www.boxeldercountyut.gov/DocumentCenter/View/2116/Stratos-Project-Fact-Sheet
- U.S. Census 2020 Redistricting Data API: https://api.census.gov/data/2020/dec/pl.html
- U.S. Census TIGER/Line files: https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html
- EPA PM2.5 NAAQS context: https://www.epa.gov/particle-pollution-designations/particle-pollution-designations-2024-revised-annual-pm-naaqs-where
