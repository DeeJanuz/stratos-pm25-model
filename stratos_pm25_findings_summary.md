# Stratos PM2.5 Screening Findings

> Superseded note: the current evidence-first comparison is
> `stratos_pm25_population_comparison_summary.md`, based on the all-events
> 70 km screening matrix in `runs/screening_matrix/20260507_all_events_70km_screen`.
> This earlier narrative summary is retained for run history but should not be
> treated as the current comparison document.

## Executive Summary

We built a screening model to estimate what the Stratos-area power plant could have added to PM2.5 pollution during historical Utah winter inversion events. After audit fixes, the key finding is more conditional than the first summary: **for the approximate Hansel Valley center point, major population centers still avoid the modeled worst impact zones, but exact stack siting can materially change exposure for small nearby communities.**

The model now separates two types of runs:

- **Strict local-background run:** 2024-2025 only, using Brigham City `BG` PM2.5 where that station is available in the Utah DAQ archive.
- **Four-year proxy run:** 2022-2025, explicitly allowing PM2.5 fallback stations for years where `BG` is missing from the archive CSVs.

In the worst precursor-chemistry scenario, the physically worst modeled receptor additions rose when the grid was refined from 5 km to 2.5 km. The highest physical receptor values should therefore be treated as grid-sensitive screening estimates, not stable point predictions. Population exposure remains much lower than the physical maxima at the base location, but 5-10 km source-location shifts can increase exposure for small populated areas.

## Data Sources

The model used public data from:

- Utah DAQ air pollution and meteorological archives: https://air.utah.gov/dataarchive/index.htm
- Utah DAQ station information, including Brigham City `BG` and Salt Lake City Hawthorne `HW`: https://air.utah.gov/network/Counties.htm
- Box Elder County Stratos project map page: https://www.boxeldercountyut.gov/644/Stratos-Project-Map
- U.S. Census 2020 Redistricting Data (PL 94-171) block population: https://api.census.gov/data/2020/dec/pl.html
- U.S. Census TIGER/Line block geography: https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html
- EPA PM2.5 NAAQS context: https://www.epa.gov/particle-pollution-designations/particle-pollution-designations-2024-revised-annual-pm-naaqs-where

EPA's current PM2.5 standards provide useful scale: the annual primary PM2.5 standard is **9.0 ug/m3**, and the 24-hour standard remains **35 ug/m3**.

## Modeling Methodology

The original script only estimated a centerline Gaussian plume. We replaced it with a more realistic screening model:

1. **Historical meteorology:** pulled hourly wind speed, wind direction, temperature, and PM2.5 from Utah DAQ archive CSVs for 2022-2025.
2. **Inversion detection:** identified winter inversion/stagnation events using elevated PM2.5 and low-wind/cold conditions.
3. **Source scenario:** modeled the original direct PM2.5 assumption of **405 lb/hr** plus an illustrative precursor case:
   - NOx: **250 lb/hr**
   - SO2: **5 lb/hr**
   - NH3: **40 lb/hr**
   - VOC: **30 lb/hr**
4. **Secondary PM2.5 screen:** converted portions of NOx, SO2, NH3, and VOC into PM2.5-equivalent mass using a worst-inversion screening profile. This is a sensitivity estimate, not a full atmospheric chemistry model.
5. **Dispersion:** used a receptor grid around an approximate Hansel Valley project center, hourly wind rotation, crosswind dispersion, plume rise, inversion-lid reflection, and a trapped-lid fumigation floor.
6. **Regional accumulation:** added a separate mixed-box calculation for broad trapped-basin accumulation.
7. **Population overlay:** used a reproducible `population_overlay.py` script with 2020 Census block population and assigned populated block centroids to the nearest modeled receptor to estimate how many people fall under different modeled increment levels.
8. **SLC comparison:** compared modeled increments to actual PM2.5 recorded at Salt Lake City's Hawthorne `HW` monitor over the same historical inversion windows.

## Historical Inversion Results

Across the top historical inversion events, the refined 2.5 km worst-precursor model estimated:

- Worst physical receptor additions: roughly **16-39 ug/m3** event-average PM2.5 depending on event set and station treatment.
- Broad regional/mixed-box additions: about **1.7-3.3 ug/m3**.
- Most major populated towns: generally low single-digit additions at the base assumed site location.

These are incremental additions, not total PM2.5. Total PM2.5 would be local background plus the modeled increment.

## Population Exposure Findings

Within 50 km of the approximate Hansel Valley project center, the 2020 Census block overlay found about **24,417 people** in populated blocks.

### Strict BG Local-Background Run, 2024-2025

This is the cleaner apples-to-apples local-background run, but it covers only the years where Brigham City `BG` appears in the Utah DAQ PM2.5 archive.

| Modeled added PM2.5 threshold | Population in blocks at or above threshold |
|---:|---:|
| >= 10 ug/m3 | 14 people |
| >= 7.5 ug/m3 | 18 people |
| >= 5 ug/m3 | 244 people |
| >= 3 ug/m3 | 289 people |
| >= 2 ug/m3 | 324 people |
| >= 1 ug/m3 | 769 people |

Weighted by population, the modeled event-average increment distribution was:

| Population-weighted percentile | Added PM2.5 |
|---:|---:|
| p50 | 0.26 ug/m3 |
| p75 | 0.30 ug/m3 |
| p90 | 0.50 ug/m3 |
| p95 | 0.74 ug/m3 |
| p99 | 4.07 ug/m3 |

### Four-Year Proxy Run, 2022-2025

This run covers more historical events but uses explicit PM2.5 fallback stations for 2022-2023 because `BG` was not present in those archive CSVs.

| Modeled added PM2.5 threshold | Population in blocks at or above threshold |
|---:|---:|
| >= 10 ug/m3 | 0 people |
| >= 7.5 ug/m3 | 10 people |
| >= 5 ug/m3 | 49 people |
| >= 3 ug/m3 | 489 people |
| >= 2 ug/m3 | 569 people |
| >= 1 ug/m3 | 22,635 people |

Population-weighted increment distribution:

| Population-weighted percentile | Added PM2.5 |
|---:|---:|
| p50 | 1.32 ug/m3 |
| p75 | 1.44 ug/m3 |
| p90 | 1.55 ug/m3 |
| p95 | 1.71 ug/m3 |
| p99 | 3.44 ug/m3 |

Interpretation: most residents within the 50 km screen remain in a low-increment band. However, the strict BG run shows a higher small-population tail than the first draft, and the four-year proxy run is not a true local-background comparison for 2022-2023.

## Source Location Sensitivity

Because the exact stack coordinates are not yet known, source-location sensitivity is now a required part of the interpretation. Using the same modeled grids but shifting the assumed source point:

| Run | Source shift | Population >=2 ug/m3 | Population >=5 ug/m3 | Population >=10 ug/m3 | Max populated-block increment |
|---|---|---:|---:|---:|---:|
| Strict BG 2024-2025 | base | 324 | 244 | 14 | 11.1 ug/m3 |
| Strict BG 2024-2025 | 10 km east | 515 | 131 | 6 | 26.5 ug/m3 |
| Strict BG 2024-2025 | 10 km north | 301 | 260 | 191 | 27.1 ug/m3 |
| Four-year proxy | base | 569 | 49 | 0 | 10.0 ug/m3 |
| Four-year proxy | 10 km east | 2,428 | 239 | 53 | 15.1 ug/m3 |
| Four-year proxy | 10 km north | 409 | 77 | 14 | 26.3 ug/m3 |

This is the most important correction to the original conclusion: **the base-location population result is not robust to source-location uncertainty.**

## Place-Level Screen

Approximate place-centroid results:

| Place | 2020 population | Distance from assumed project center | Max modeled addition |
|---|---:|---:|---:|
| Snowville | 163 | 22.6 km | 6.13 ug/m3 in strict BG run; 3.44 ug/m3 in four-year proxy |
| Howell | 240 | 17.3 km | 0.96 ug/m3 in strict BG run; 3.56 ug/m3 in four-year proxy |
| Portage | 273 | 41.1 km | 1.15-1.79 ug/m3 |
| Thatcher CDP | 807 | 29.7 km | up to 1.66 ug/m3 |
| Tremonton | 9,894 | 39.2 km | about 1.44 ug/m3 in four-year proxy |
| Garland | 2,589 | 41.2 km | about 1.44 ug/m3 in four-year proxy |
| Riverside CDP | 971 | 43.0 km | about 1.42 ug/m3 in four-year proxy |
| Fielding | 546 | 44.9 km | about 1.35 ug/m3 in four-year proxy |

This suggests that Snowville and Howell remain the most relevant small populated communities for the higher exposure side of the screen, but their relative ranking changes depending on which historical years and source-location assumptions are used. Tremonton, Garland, Riverside, and Fielding remain lower in the base-location screen.

## Comparison To Salt Lake City During The Same Events

For the same inversion windows, Salt Lake City's Hawthorne `HW` monitor recorded:

| Historical inversion window | SLC Hawthorne event-average PM2.5 | SLC Hawthorne peak 24h average | Worst modeled Stratos-area addition | Broad modeled box addition |
|---|---:|---:|---:|---:|
| Jan 30-Feb 7, 2023 | 28.8 ug/m3 | 51.7 ug/m3 | 26.3 ug/m3 | 3.2 ug/m3 |
| Dec 22-Dec 27, 2022 | 25.6 | 48.4 | 30.3 | 3.3 |
| Jan 16-Jan 24, 2022 | 22.7 | 43.8 | 24.2 | 3.0 |
| Mar 28-Mar 30, 2025 | 20.2 | 33.0 | 16.0 | 1.7 |
| Dec 16-Dec 20, 2023 | 28.8 | 37.5 | 23.2 | 3.1 |

The refined-grid worst physical Stratos-area additions are very large compared with SLC event averages, in some cases comparable to SLC's entire recorded event-average PM2.5. But those worst physical receptors mostly do not correspond to population centers in the base-location screen. For most residents, the modeled additions are closer to low single digits, which is much smaller than the PM2.5 levels SLC recorded during the same inversion events.

## Accuracy Audit

The numbers are credible as a screening simulation because:

- The historical meteorology and PM2.5 observations came from Utah DAQ archive data.
- The SLC comparison used the same event windows and the official Hawthorne `HW` monitoring station.
- The population screen now uses reproducible code and Census 2020 block-level population, not county-average population.
- The model records station fallback choices. Brigham City `BG` data was available for 2024-2025; earlier years require explicit fallback stations because `BG` was not present in the archive CSVs used.
- Unit tests were added for wind-direction rotation, dispersion behavior, rolling averages, event detection, and box accumulation.
- The model uses a receptor grid and wind-direction rotation rather than assuming the plume stays on one centerline.
- The worst-precursor run intentionally errs toward a higher-impact sensitivity case by including precursor conversion and trapped-lid behavior.
- The model now supports custom secondary PM2.5 conversion factors and source-location sensitivity through reproducible scripts.

The numbers are not permit-grade because:

- Exact Stratos source coordinates, stack count, stack heights, exhaust temperature, exit velocity, building downwash, and hourly load profiles are not yet known. This is now known to be a first-order uncertainty.
- The precursor emissions used here are illustrative assumptions, not confirmed permit limits.
- Secondary PM2.5 chemistry is represented by screening coefficients rather than CAMx/CMAQ/WRF-Chem or an approved regulatory reduced-form method.
- Complex terrain, cold-air-pool structure, drainage winds, snow cover, and valley-specific mixing heights are simplified.
- Census 2020 population was used as a proxy for population during 2022-2025 inversion dates.
- Exposure means outdoor ambient concentration at place/block centroid; it does not estimate indoor exposure, time-activity patterns, age, health vulnerability, or dose.
- The project-center coordinate is approximate from public map context, and 5-10 km shifts materially change exposure for small nearby communities.

## Bottom Line

The modeled environmental cost is still not best described as "a large PM2.5 increase for all of Box Elder County." It is better described as:

> A potentially meaningful PM2.5 increase over a mostly sparsely populated area near the project, with small but nonzero increases for nearby towns, and a source-location-sensitive risk tail for small communities such as Snowville and Howell.

For population exposure, the central estimate from this screening work is:

- Most residents within the base 50 km screen: low single-digit increments, generally below **2 ug/m3** in the population-weighted distribution.
- Small higher-exposure communities: Snowville and Howell are the main communities to scrutinize; base estimates range from roughly **1-6 ug/m3** depending on event set.
- Source-location sensitivity: 10 km shifts can produce populated-block maxima above **25 ug/m3** and can move dozens to hundreds of residents above **10 ug/m3** in some sensitivity cases.
- Major population centers such as Tremonton and Garland: about **1.4 ug/m3** in the four-year proxy base-location screen.

Compared with Salt Lake City during the same periods, the major Box Elder population centers remain far below SLC's recorded inversion PM2.5 levels in the base-location screen. That conclusion should be revisited when exact stack locations, plant phasing, emissions, and site meteorology are available.
