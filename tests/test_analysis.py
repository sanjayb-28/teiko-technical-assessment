import csv
import hashlib
import struct
import tempfile
import unittest
from collections import defaultdict
from pathlib import Path

from analysis import (
    OUTPUT_COLUMNS,
    STATISTICS_COLUMNS,
    export_cell_frequencies,
    load_responder_frequencies,
    run_responder_analysis,
)
from load_data import CSV_PATH, POPULATIONS, SCHEMA_PATH, create_database


class FrequencyExportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_path = Path(self.temporary_directory.name)
        self.database_path = temporary_path / "test.db"
        self.output_path = temporary_path / "cell_frequencies.csv"
        create_database(CSV_PATH, self.database_path, SCHEMA_PATH)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_exports_required_summary_table(self) -> None:
        row_count = export_cell_frequencies(self.database_path, self.output_path)

        with self.output_path.open(newline="", encoding="utf-8") as output_file:
            reader = csv.DictReader(output_file)
            rows = list(reader)

        self.assertEqual(tuple(reader.fieldnames or ()), OUTPUT_COLUMNS)
        self.assertEqual(row_count, 52_500)
        self.assertEqual(len(rows), 52_500)
        self.assertEqual(
            rows[:5],
            [
                {
                    "sample": "sample00000",
                    "total_count": "93214",
                    "population": "b_cell",
                    "count": "10908",
                    "percentage": "11.702105",
                },
                {
                    "sample": "sample00000",
                    "total_count": "93214",
                    "population": "cd8_t_cell",
                    "count": "24440",
                    "percentage": "26.219237",
                },
                {
                    "sample": "sample00000",
                    "total_count": "93214",
                    "population": "cd4_t_cell",
                    "count": "20491",
                    "percentage": "21.982749",
                },
                {
                    "sample": "sample00000",
                    "total_count": "93214",
                    "population": "nk_cell",
                    "count": "13864",
                    "percentage": "14.873302",
                },
                {
                    "sample": "sample00000",
                    "total_count": "93214",
                    "population": "monocyte",
                    "count": "23511",
                    "percentage": "25.222606",
                },
            ],
        )

        percentages_by_sample: dict[str, list[float]] = defaultdict(list)
        populations_by_sample: dict[str, set[str]] = defaultdict(set)
        for row in rows:
            percentages_by_sample[row["sample"]].append(float(row["percentage"]))
            populations_by_sample[row["sample"]].add(row["population"])

        self.assertEqual(len(percentages_by_sample), 10_500)
        for sample, percentages in percentages_by_sample.items():
            self.assertEqual(len(percentages), 5, sample)
            self.assertAlmostEqual(sum(percentages), 100.0, places=5, msg=sample)
            self.assertEqual(populations_by_sample[sample], set(POPULATIONS), sample)

    def test_export_is_deterministic(self) -> None:
        export_cell_frequencies(self.database_path, self.output_path)
        first_digest = hashlib.sha256(self.output_path.read_bytes()).hexdigest()

        export_cell_frequencies(self.database_path, self.output_path)
        second_digest = hashlib.sha256(self.output_path.read_bytes()).hexdigest()

        self.assertEqual(first_digest, second_digest)

    def test_requires_database(self) -> None:
        missing_database = Path(self.temporary_directory.name) / "missing.db"

        with self.assertRaisesRegex(FileNotFoundError, "Run python load_data.py first"):
            export_cell_frequencies(missing_database, self.output_path)


class ResponderAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        temporary_path = Path(self.temporary_directory.name)
        self.database_path = temporary_path / "test.db"
        self.statistics_path = temporary_path / "statistical_results.csv"
        self.boxplot_path = temporary_path / "responder_boxplots.png"
        create_database(CSV_PATH, self.database_path, SCHEMA_PATH)

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def test_uses_required_sample_subset(self) -> None:
        frequencies = load_responder_frequencies(self.database_path)

        self.assertEqual(set(frequencies), set(POPULATIONS))
        for population in POPULATIONS:
            self.assertEqual(len(frequencies[population]["yes"]), 993)
            self.assertEqual(len(frequencies[population]["no"]), 975)

    def test_writes_statistics_and_boxplots(self) -> None:
        results = run_responder_analysis(
            self.database_path,
            self.statistics_path,
            self.boxplot_path,
        )

        with self.statistics_path.open(newline="", encoding="utf-8") as output_file:
            reader = csv.DictReader(output_file)
            rows = list(reader)

        self.assertEqual(tuple(reader.fieldnames or ()), STATISTICS_COLUMNS)
        self.assertEqual([row["population"] for row in rows], list(POPULATIONS))
        self.assertEqual(len(results), 5)
        self.assertEqual(
            {row["population"] for row in rows if row["significant"] == "yes"},
            {"cd4_t_cell"},
        )
        self.assertTrue(all(row["responder_n"] == "993" for row in rows))
        self.assertTrue(all(row["non_responder_n"] == "975" for row in rows))

        image = self.boxplot_path.read_bytes()
        self.assertEqual(image[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", image[16:24])
        self.assertGreaterEqual(width, 3_000)
        self.assertGreaterEqual(height, 1_000)
        self.assertGreater(len(image), 100_000)

    def test_statistics_output_is_deterministic(self) -> None:
        run_responder_analysis(
            self.database_path,
            self.statistics_path,
            self.boxplot_path,
        )
        first_digest = hashlib.sha256(self.statistics_path.read_bytes()).hexdigest()

        run_responder_analysis(
            self.database_path,
            self.statistics_path,
            self.boxplot_path,
        )
        second_digest = hashlib.sha256(self.statistics_path.read_bytes()).hexdigest()

        self.assertEqual(first_digest, second_digest)


if __name__ == "__main__":
    unittest.main()
