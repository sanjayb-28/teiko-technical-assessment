import csv
import hashlib
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from load_data import CSV_PATH, SCHEMA_PATH, create_database
from subset_analysis import (
    BASELINE_COLUMNS,
    SUMMARY_COLUMNS,
    load_subset_data,
    run_subset_analysis,
)


class SubsetAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_path = Path(self.temporary_directory.name)
        self.database_path = temporary_path / "test.db"
        self.baseline_output_path = temporary_path / "baseline_samples.csv"
        self.summary_output_path = temporary_path / "subset_summary.csv"
        create_database(CSV_PATH, self.database_path, SCHEMA_PATH)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_uses_exact_baseline_subset(self) -> None:
        baseline_samples, average_b_cell_count = load_subset_data(self.database_path)

        self.assertEqual(len(baseline_samples), 656)
        self.assertEqual(
            Counter(str(row[0]) for row in baseline_samples),
            {"prj1": 384, "prj3": 272},
        )
        self.assertEqual(
            Counter(str(row[5]) for row in baseline_samples),
            {"yes": 331, "no": 325},
        )
        self.assertEqual(
            Counter(str(row[6]) for row in baseline_samples),
            {"M": 344, "F": 312},
        )
        self.assertEqual(
            len({(str(row[0]), str(row[1])) for row in baseline_samples}),
            656,
        )
        self.assertTrue(all(row[3] == "melanoma" for row in baseline_samples))
        self.assertTrue(all(row[4] == "miraclib" for row in baseline_samples))
        self.assertTrue(all(row[7] == "PBMC" for row in baseline_samples))
        self.assertTrue(all(row[8] == 0 for row in baseline_samples))
        self.assertAlmostEqual(average_b_cell_count, 10206.15, places=2)

    def test_average_includes_all_sample_and_treatment_types(self) -> None:
        with CSV_PATH.open(newline="", encoding="utf-8-sig") as csv_file:
            rows = [
                row
                for row in csv.DictReader(csv_file)
                if row["condition"] == "melanoma"
                and row["sex"] == "M"
                and row["response"] == "yes"
                and row["time_from_treatment_start"] == "0"
            ]

        self.assertEqual({row["sample_type"] for row in rows}, {"PBMC", "WB"})
        self.assertEqual(
            {row["treatment"] for row in rows}, {"miraclib", "phauximab"}
        )
        expected_average = sum(int(row["b_cell"]) for row in rows) / len(rows)
        _, actual_average = load_subset_data(self.database_path)

        self.assertAlmostEqual(actual_average, expected_average)
        self.assertEqual(f"{actual_average:.2f}", "10206.15")

    def test_writes_required_outputs(self) -> None:
        baseline_count, summary_count = run_subset_analysis(
            self.database_path,
            self.baseline_output_path,
            self.summary_output_path,
        )

        with self.baseline_output_path.open(
            newline="", encoding="utf-8"
        ) as baseline_file:
            baseline_reader = csv.DictReader(baseline_file)
            baseline_rows = list(baseline_reader)
        with self.summary_output_path.open(
            newline="", encoding="utf-8"
        ) as summary_file:
            summary_reader = csv.DictReader(summary_file)
            summary_rows = list(summary_reader)

        self.assertEqual(tuple(baseline_reader.fieldnames or ()), BASELINE_COLUMNS)
        self.assertEqual(tuple(summary_reader.fieldnames or ()), SUMMARY_COLUMNS)
        self.assertEqual(baseline_count, 656)
        self.assertEqual(len(baseline_rows), 656)
        self.assertEqual(summary_count, 7)
        self.assertEqual(
            summary_rows,
            [
                {"metric": "samples_by_project", "group": "prj1", "value": "384"},
                {"metric": "samples_by_project", "group": "prj3", "value": "272"},
                {"metric": "subjects_by_response", "group": "no", "value": "325"},
                {"metric": "subjects_by_response", "group": "yes", "value": "331"},
                {"metric": "subjects_by_sex", "group": "F", "value": "312"},
                {"metric": "subjects_by_sex", "group": "M", "value": "344"},
                {
                    "metric": "average_b_cell_count",
                    "group": (
                        "melanoma_male_responders_at_baseline_all_samples_"
                        "and_treatments"
                    ),
                    "value": "10206.15",
                },
            ],
        )

    def test_outputs_are_deterministic(self) -> None:
        run_subset_analysis(
            self.database_path,
            self.baseline_output_path,
            self.summary_output_path,
        )
        first_digests = (
            hashlib.sha256(self.baseline_output_path.read_bytes()).hexdigest(),
            hashlib.sha256(self.summary_output_path.read_bytes()).hexdigest(),
        )

        run_subset_analysis(
            self.database_path,
            self.baseline_output_path,
            self.summary_output_path,
        )
        second_digests = (
            hashlib.sha256(self.baseline_output_path.read_bytes()).hexdigest(),
            hashlib.sha256(self.summary_output_path.read_bytes()).hexdigest(),
        )

        self.assertEqual(first_digests, second_digests)

    def test_requires_database(self) -> None:
        missing_database = Path(self.temporary_directory.name) / "missing.db"

        with self.assertRaisesRegex(FileNotFoundError, "Run python load_data.py first"):
            run_subset_analysis(
                missing_database,
                self.baseline_output_path,
                self.summary_output_path,
            )


if __name__ == "__main__":
    unittest.main()
