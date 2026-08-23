import csv
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from load_data import CSV_PATH, POPULATIONS, SCHEMA_PATH, create_database


class LoadDataTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temporary_directory.name) / "test.db"

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def load_database(self) -> dict[str, int]:
        return create_database(CSV_PATH, self.database_path, SCHEMA_PATH)

    def test_loads_expected_records(self) -> None:
        summary = self.load_database()

        self.assertEqual(
            summary,
            {
                "projects": 3,
                "subjects": 3_500,
                "samples": 10_500,
                "cell_counts": 52_500,
            },
        )

        with closing(sqlite3.connect(self.database_path)) as connection:
            populations = {
                row[0]
                for row in connection.execute(
                    "SELECT population_name FROM cell_populations"
                )
            }
            duplicate_samples = connection.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT sample_name
                    FROM samples
                    GROUP BY sample_name
                    HAVING COUNT(*) > 1
                )
                """
            ).fetchone()[0]
            invalid_sample_counts = connection.execute(
                """
                SELECT COUNT(*)
                FROM (
                    SELECT sample_id
                    FROM cell_counts
                    GROUP BY sample_id
                    HAVING COUNT(*) != 5
                )
                """
            ).fetchone()[0]
            negative_counts = connection.execute(
                "SELECT COUNT(*) FROM cell_counts WHERE count < 0"
            ).fetchone()[0]
            foreign_key_errors = connection.execute(
                "PRAGMA foreign_key_check"
            ).fetchall()
            first_sample = connection.execute(
                """
                SELECT
                    projects.project_name,
                    subjects.subject_name,
                    subjects.condition,
                    subjects.age,
                    subjects.sex,
                    subjects.treatment,
                    subjects.response,
                    samples.sample_name,
                    samples.sample_type,
                    samples.time_from_treatment_start
                FROM samples
                JOIN subjects USING (subject_id)
                JOIN projects USING (project_id)
                WHERE samples.sample_name = 'sample00000'
                """
            ).fetchone()
            database_totals = dict(
                connection.execute(
                    """
                    SELECT cell_populations.population_name, SUM(cell_counts.count)
                    FROM cell_counts
                    JOIN cell_populations USING (population_id)
                    GROUP BY cell_populations.population_name
                    """
                )
            )

        csv_totals = dict.fromkeys(POPULATIONS, 0)
        with CSV_PATH.open(newline="", encoding="utf-8") as csv_file:
            for row in csv.DictReader(csv_file):
                for population in POPULATIONS:
                    csv_totals[population] += int(row[population])

        self.assertEqual(populations, set(POPULATIONS))
        self.assertEqual(duplicate_samples, 0)
        self.assertEqual(invalid_sample_counts, 0)
        self.assertEqual(negative_counts, 0)
        self.assertEqual(foreign_key_errors, [])
        self.assertEqual(
            first_sample,
            (
                "prj1",
                "sbj000",
                "melanoma",
                57,
                "M",
                "miraclib",
                "no",
                "sample00000",
                "PBMC",
                0,
            ),
        )
        self.assertEqual(database_totals, csv_totals)

    def test_rebuild_is_idempotent(self) -> None:
        first_summary = self.load_database()
        second_summary = self.load_database()

        self.assertEqual(first_summary, second_summary)
        with closing(sqlite3.connect(self.database_path)) as connection:
            sample_count = connection.execute(
                "SELECT COUNT(*) FROM samples"
            ).fetchone()[0]
            count_rows = connection.execute(
                "SELECT COUNT(*) FROM cell_counts"
            ).fetchone()[0]

        self.assertEqual(sample_count, 10_500)
        self.assertEqual(count_rows, 52_500)

    def test_schema_rejects_negative_counts(self) -> None:
        self.load_database()

        with closing(sqlite3.connect(self.database_path)) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE cell_counts SET count = -1 WHERE sample_id = 1"
                )

    def test_failed_rebuild_preserves_existing_database(self) -> None:
        expected_summary = self.load_database()
        invalid_csv_path = Path(self.temporary_directory.name) / "invalid.csv"
        lines = CSV_PATH.read_text(encoding="utf-8").splitlines()
        values = lines[1].split(",")
        values[10] = "-1"
        invalid_csv_path.write_text(
            lines[0] + "\n" + ",".join(values) + "\n",
            encoding="utf-8",
        )

        with self.assertRaisesRegex(ValueError, "b_cell must be non-negative"):
            create_database(invalid_csv_path, self.database_path, SCHEMA_PATH)

        with closing(sqlite3.connect(self.database_path)) as connection:
            actual_summary = {
                "projects": connection.execute(
                    "SELECT COUNT(*) FROM projects"
                ).fetchone()[0],
                "subjects": connection.execute(
                    "SELECT COUNT(*) FROM subjects"
                ).fetchone()[0],
                "samples": connection.execute(
                    "SELECT COUNT(*) FROM samples"
                ).fetchone()[0],
                "cell_counts": connection.execute(
                    "SELECT COUNT(*) FROM cell_counts"
                ).fetchone()[0],
            }

        self.assertEqual(actual_summary, expected_summary)


if __name__ == "__main__":
    unittest.main()
