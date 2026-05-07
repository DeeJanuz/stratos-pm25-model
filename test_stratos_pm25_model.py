import datetime as dt
import csv
import tempfile
import unittest
from pathlib import Path

import compare_model_runs
import population_overlay
import stratos_pm25_model as model


class DispersionMathTests(unittest.TestCase):
    def test_wind_rotation_treats_meteorological_direction_as_from(self):
        downwind, crosswind = model.rotate_to_downwind(1000.0, 0.0, 270.0)
        self.assertGreater(downwind, 999.0)
        self.assertAlmostEqual(crosswind, 0.0, places=6)

    def test_pasquill_gifford_sigmas_are_positive(self):
        self.assertGreater(model.pg_sigma_y(1000.0, "F"), 0.0)
        self.assertGreater(model.pg_sigma_z(1000.0, "F"), 0.0)

    def test_crosswind_concentration_is_lower_than_centerline(self):
        source = model.Source("test")
        hour = model.MetHour(
            timestamp=dt.datetime(2025, 1, 1),
            wind_speed_m_s=2.0,
            wind_dir_deg=270.0,
            ambient_temp_c=-3.0,
            pm25_ug_m3=35.0,
        )
        config = model.ModelConfig(meander_sigma_deg=0.0, inversion_lid_reflection=True)
        center = model.Receptor("center", 10_000.0, 0.0, 10.0, 90.0, 0.0, 0.0)
        side = model.Receptor("side", 10_000.0, 4_000.0, 10.8, 68.0, 0.0, 0.0)
        c_center, _ = model.gaussian_receptor_concentration_ug_m3(
            source, center, hour, config, model.SECONDARY_PROFILES["none"]
        )
        c_side, _ = model.gaussian_receptor_concentration_ug_m3(
            source, side, hour, config, model.SECONDARY_PROFILES["none"]
        )
        self.assertGreater(c_center, c_side)

    def test_upwind_receptor_has_zero_gaussian_concentration(self):
        source = model.Source("test")
        hour = model.MetHour(
            timestamp=dt.datetime(2025, 1, 1),
            wind_speed_m_s=2.0,
            wind_dir_deg=270.0,
            ambient_temp_c=-3.0,
            pm25_ug_m3=35.0,
        )
        config = model.ModelConfig(meander_sigma_deg=0.0)
        upwind = model.Receptor("upwind", -10_000.0, 0.0, 10.0, 270.0, 0.0, 0.0)
        concentration, _ = model.gaussian_receptor_concentration_ug_m3(
            source, upwind, hour, config, model.SECONDARY_PROFILES["none"]
        )
        self.assertEqual(concentration, 0.0)

    def test_concentration_scales_linearly_with_primary_emissions(self):
        hour = model.MetHour(
            timestamp=dt.datetime(2025, 1, 1),
            wind_speed_m_s=2.0,
            wind_dir_deg=270.0,
            ambient_temp_c=-3.0,
            pm25_ug_m3=35.0,
        )
        config = model.ModelConfig(meander_sigma_deg=0.0)
        receptor = model.Receptor("center", 10_000.0, 0.0, 10.0, 90.0, 0.0, 0.0)
        base, _ = model.gaussian_receptor_concentration_ug_m3(
            model.Source("base", primary_pm25_g_s=10.0),
            receptor,
            hour,
            config,
            model.SECONDARY_PROFILES["none"],
        )
        doubled, _ = model.gaussian_receptor_concentration_ug_m3(
            model.Source("double", primary_pm25_g_s=20.0),
            receptor,
            hour,
            config,
            model.SECONDARY_PROFILES["none"],
        )
        self.assertAlmostEqual(doubled / base, 2.0, places=6)

    def test_higher_wind_reduces_same_receptor_concentration(self):
        source = model.Source("test", primary_pm25_g_s=10.0)
        receptor = model.Receptor("center", 10_000.0, 0.0, 10.0, 90.0, 0.0, 0.0)
        config = model.ModelConfig(meander_sigma_deg=0.0)
        calm = model.MetHour(dt.datetime(2025, 1, 1), 1.0, 270.0, -3.0, 35.0)
        breezy = model.MetHour(dt.datetime(2025, 1, 1), 4.0, 270.0, -3.0, 35.0)
        calm_c, _ = model.gaussian_receptor_concentration_ug_m3(
            source, receptor, calm, config, model.SECONDARY_PROFILES["none"]
        )
        breezy_c, _ = model.gaussian_receptor_concentration_ug_m3(
            source, receptor, breezy, config, model.SECONDARY_PROFILES["none"]
        )
        self.assertGreater(calm_c, breezy_c)


class DataHandlingTests(unittest.TestCase):
    def test_rolling_average_uses_available_values(self):
        values = [1.0] * 12 + [None] * 12
        rolled = model.rolling_average(values, 24)
        self.assertIsNotNone(rolled[-1])
        self.assertAlmostEqual(rolled[-1], 1.0)

    def test_old_utah_header_station_code_parsing(self):
        self.assertEqual(model.utah_header_station_code("H3-SWS"), "H3")
        self.assertEqual(model.utah_header_station_code("SM MC-CO2"), "SM")

    def test_event_detection_groups_winter_stagnation(self):
        hours = [
            model.MetHour(
                timestamp=dt.datetime(2025, 1, 1) + dt.timedelta(hours=i),
                wind_speed_m_s=1.0,
                wind_dir_deg=180.0,
                ambient_temp_c=-4.0,
                pm25_ug_m3=10.0,
                pm25_24h_ug_m3=10.0,
            )
            for i in range(14)
        ]
        events = model.detect_inversion_events(hours, min_hours=12)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].duration_hours, 14)

    def test_event_detection_models_continuous_window_between_candidates(self):
        hours = []
        for i in range(3):
            hours.append(
                model.MetHour(
                    timestamp=dt.datetime(2025, 1, 1) + dt.timedelta(hours=i),
                    wind_speed_m_s=1.0,
                    wind_dir_deg=180.0,
                    ambient_temp_c=-4.0,
                    pm25_ug_m3=10.0,
                    pm25_24h_ug_m3=10.0,
                )
            )
        hours.append(
            model.MetHour(
                timestamp=dt.datetime(2025, 1, 1, 3),
                wind_speed_m_s=4.0,
                wind_dir_deg=180.0,
                ambient_temp_c=8.0,
                pm25_ug_m3=10.0,
                pm25_24h_ug_m3=10.0,
            )
        )
        for i in range(4, 7):
            hours.append(
                model.MetHour(
                    timestamp=dt.datetime(2025, 1, 1) + dt.timedelta(hours=i),
                    wind_speed_m_s=1.0,
                    wind_dir_deg=180.0,
                    ambient_temp_c=-4.0,
                    pm25_ug_m3=10.0,
                    pm25_24h_ug_m3=10.0,
                )
            )

        events = model.detect_inversion_events(hours, min_hours=6, gap_hours=6)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].start, dt.datetime(2025, 1, 1, 0))
        self.assertEqual(events[0].end, dt.datetime(2025, 1, 1, 6))
        self.assertEqual(events[0].duration_hours, 7)

    def test_regional_box_accumulates_under_low_wind(self):
        source = model.Source("test", primary_pm25_g_s=10.0)
        hours = [
            model.MetHour(
                timestamp=dt.datetime(2025, 1, 1) + dt.timedelta(hours=i),
                wind_speed_m_s=1.0,
                wind_dir_deg=180.0,
                ambient_temp_c=-4.0,
                pm25_ug_m3=10.0,
            )
            for i in range(24)
        ]
        series = model.regional_box_timeseries_ug_m3(
            hours, [source], model.ModelConfig(), model.SECONDARY_PROFILES["none"]
        )
        self.assertGreater(series[-1][1], series[0][1])

    def test_secondary_profile_overrides_are_explicit(self):
        args = model.parse_args(
            [
                "--secondary-profile",
                "worst_inversion",
                "--nox-to-nitrate-fraction",
                "0.45",
                "--nh3-to-ammonium-fraction",
                "0.30",
            ]
        )
        profile = model.selected_secondary_profile(args)
        self.assertEqual(profile.name, "worst_inversion_custom")
        self.assertAlmostEqual(profile.nox_to_nitrate_fraction, 0.45)
        self.assertAlmostEqual(profile.nh3_to_ammonium_fraction, 0.30)

    def test_worst_secondary_profile_is_conservative_sensitivity_case(self):
        typical = model.SECONDARY_PROFILES["typical_inversion"]
        worst = model.SECONDARY_PROFILES["worst_inversion"]
        self.assertGreater(worst.nox_to_nitrate_fraction, typical.nox_to_nitrate_fraction)
        self.assertGreater(worst.so2_to_sulfate_fraction, typical.so2_to_sulfate_fraction)
        self.assertGreater(worst.nh3_to_ammonium_fraction, typical.nh3_to_ammonium_fraction)
        self.assertGreater(worst.voc_to_soa_fraction, typical.voc_to_soa_fraction)
        self.assertAlmostEqual(worst.nox_to_nitrate_fraction, 0.60)
        self.assertAlmostEqual(worst.so2_to_sulfate_fraction, 0.80)
        self.assertAlmostEqual(worst.nh3_to_ammonium_fraction, 0.50)
        self.assertAlmostEqual(worst.voc_to_soa_fraction, 0.20)

    def test_all_events_flag_is_explicit(self):
        args = model.parse_args(["--all-events"])
        self.assertTrue(args.all_events)


class PopulationOverlayTests(unittest.TestCase):
    def test_event_grid_domain_radius_uses_smallest_event_domain(self):
        event_grids = {
            "wide": [{"x_m": 0.0, "y_m": 10_000.0}, {"x_m": 20_000.0, "y_m": 0.0}],
            "narrow": [{"x_m": 0.0, "y_m": 5_000.0}, {"x_m": 10_000.0, "y_m": 0.0}],
        }
        self.assertAlmostEqual(population_overlay.event_grid_domain_radius_km(event_grids), 10.0)

    def test_place_exposure_marks_outside_model_domain(self):
        places = [{"geoid": "1", "population": 10, "lat": 0.0, "lon": 0.2, "name": "Outside"}]
        event_grids = {
            "event": [
                {
                    "receptor_id": "r",
                    "x_m": 10_000.0,
                    "y_m": 0.0,
                    "avg_increment_ug_m3": 1.0,
                    "max_hourly_increment_ug_m3": 2.0,
                    "avg_increment_percent_of_event_avg_bg": 10.0,
                }
            ]
        }
        rows = population_overlay.assign_place_exposure(places, event_grids, 0.0, 0.0, model_radius_km=10.0)
        self.assertEqual(len(rows), 1)
        self.assertFalse(rows[0]["inside_model_domain"])
        self.assertGreater(rows[0]["outside_model_domain_km"], 0.0)

    def test_event_population_summary_counts_each_event_separately(self):
        blocks = [
            {"geoid": "1", "population": 10, "lat": 0.0, "lon": 0.0},
            {"geoid": "2", "population": 20, "lat": 0.0, "lon": 0.01},
        ]
        event_grids = {
            "event_low": [
                {"receptor_id": "r1", "x_m": 0.0, "y_m": 0.0, "avg_increment_ug_m3": 1.0},
                {"receptor_id": "r2", "x_m": 1113.2, "y_m": 0.0, "avg_increment_ug_m3": 1.5},
            ],
            "event_high": [
                {"receptor_id": "r1", "x_m": 0.0, "y_m": 0.0, "avg_increment_ug_m3": 3.0},
                {"receptor_id": "r2", "x_m": 1113.2, "y_m": 0.0, "avg_increment_ug_m3": 0.5},
            ],
        }
        rows = population_overlay.event_population_summary(blocks, event_grids, 0.0, 0.0, [2.0])

        self.assertEqual(rows[0]["event_id"], "event_low")
        self.assertEqual(rows[0]["population_ge_2ug_m3"], 0)
        self.assertEqual(rows[1]["event_id"], "event_high")
        self.assertEqual(rows[1]["population_ge_2ug_m3"], 10)


class ComparisonTableTests(unittest.TestCase):
    def write_csv(self, path, fields, rows):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def test_bad_case_benchmark_uses_max_total_not_max_increment_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.write_csv(
                run_dir / "station_usage.csv",
                ["year", "met_station", "pm25_station"],
                [{"year": "2025", "met_station": "BG", "pm25_station": "BG"}],
            )
            self.write_csv(
                run_dir / "historical_event_summary.csv",
                [
                    "event_id",
                    "start",
                    "end",
                    "duration_hours",
                    "avg_background_pm25_ug_m3",
                    "peak_background_pm25_ug_m3",
                ],
                [
                    {
                        "event_id": "e1",
                        "start": "2025-01-01 00:00:00",
                        "end": "2025-01-01 01:00:00",
                        "duration_hours": "2",
                        "avg_background_pm25_ug_m3": "1",
                        "peak_background_pm25_ug_m3": "2",
                    },
                    {
                        "event_id": "e2",
                        "start": "2025-01-02 00:00:00",
                        "end": "2025-01-02 01:00:00",
                        "duration_hours": "2",
                        "avg_background_pm25_ug_m3": "20",
                        "peak_background_pm25_ug_m3": "30",
                    },
                ],
            )
            self.write_csv(
                run_dir / "population_overlay" / "place_exposure_summary.csv",
                ["name", "population", "distance_km", "receptor_id", "max_avg_increment_ug_m3", "event_id"],
                [
                    {
                        "name": "Test town",
                        "population": "10",
                        "distance_km": "5",
                        "receptor_id": "r1",
                        "max_avg_increment_ug_m3": "10",
                        "event_id": "e1",
                    }
                ],
            )
            grid_fields = ["receptor_id", "avg_increment_ug_m3", "max_hourly_increment_ug_m3"]
            self.write_csv(
                run_dir / "events" / "e1_grid.csv",
                grid_fields,
                [{"receptor_id": "r1", "avg_increment_ug_m3": "10", "max_hourly_increment_ug_m3": "100"}],
            )
            self.write_csv(
                run_dir / "events" / "e2_grid.csv",
                grid_fields,
                [{"receptor_id": "r1", "avg_increment_ug_m3": "1", "max_hourly_increment_ug_m3": "2"}],
            )
            slc_values = {
                dt.datetime(2025, 1, 1, 0): 5.0,
                dt.datetime(2025, 1, 2, 0): 40.0,
            }
            slc_rolling = {
                dt.datetime(2025, 1, 1, 0): 5.0,
                dt.datetime(2025, 1, 2, 0): 35.0,
            }
            rows = compare_model_runs.build_bad_case_rows("scenario", run_dir, slc_values, slc_rolling)

        self.assertEqual(rows[0]["max_increment_window"], "2025-01-01 00:00:00 to 2025-01-01 01:00:00")
        self.assertEqual(rows[0]["max_modeled_event_avg_window"], "2025-01-02 00:00:00 to 2025-01-02 01:00:00")
        self.assertEqual(rows[0]["max_modeled_event_avg_total_ug_m3"], "21.000")

    def test_max_increment_benchmark_uses_background_from_max_increment_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.write_csv(
                run_dir / "station_usage.csv",
                ["year", "met_station", "pm25_station"],
                [{"year": "2025", "met_station": "BG", "pm25_station": "BG"}],
            )
            self.write_csv(
                run_dir / "historical_event_summary.csv",
                [
                    "event_id",
                    "start",
                    "end",
                    "duration_hours",
                    "avg_background_pm25_ug_m3",
                    "peak_background_pm25_ug_m3",
                ],
                [
                    {
                        "event_id": "e1",
                        "start": "2025-01-01 00:00:00",
                        "end": "2025-01-01 01:00:00",
                        "duration_hours": "2",
                        "avg_background_pm25_ug_m3": "4",
                        "peak_background_pm25_ug_m3": "6",
                    },
                    {
                        "event_id": "e2",
                        "start": "2025-01-02 00:00:00",
                        "end": "2025-01-02 01:00:00",
                        "duration_hours": "2",
                        "avg_background_pm25_ug_m3": "20",
                        "peak_background_pm25_ug_m3": "30",
                    },
                ],
            )
            self.write_csv(
                run_dir / "population_overlay" / "place_exposure_summary.csv",
                [
                    "name",
                    "population",
                    "distance_km",
                    "receptor_id",
                    "max_avg_increment_ug_m3",
                    "max_hourly_increment_ug_m3",
                    "event_id",
                ],
                [
                    {
                        "name": "Test town",
                        "population": "10",
                        "distance_km": "5",
                        "receptor_id": "r1",
                        "max_avg_increment_ug_m3": "8",
                        "max_hourly_increment_ug_m3": "12",
                        "event_id": "e1",
                    }
                ],
            )
            slc_values = {
                dt.datetime(2025, 1, 1, 0): 5.0,
                dt.datetime(2025, 1, 2, 0): 40.0,
            }
            slc_rolling = {
                dt.datetime(2025, 1, 1, 0): 7.0,
                dt.datetime(2025, 1, 2, 0): 35.0,
            }
            rows = compare_model_runs.build_max_increment_rows("scenario", run_dir, slc_values, slc_rolling)

        self.assertEqual(rows[0]["max_increment_window"], "2025-01-01 00:00:00 to 2025-01-01 01:00:00")
        self.assertEqual(rows[0]["background_monitor_avg_at_max_increment_ug_m3"], "4.000")
        self.assertEqual(rows[0]["modeled_increment_at_max_increment_ug_m3"], "8.000")
        self.assertEqual(rows[0]["background_monitor_plus_max_increment_ug_m3"], "12.000")
        self.assertEqual(rows[0]["slc_hawthorne_avg_same_window_ug_m3"], "5.000")


if __name__ == "__main__":
    unittest.main()
