"""Generate the required analysis outputs from SQLite."""

from __future__ import annotations

import csv
import os
import sqlite3
from contextlib import closing
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATABASE_PATH = ROOT / "cell_counts.db"
OUTPUT_PATH = ROOT / "outputs" / "cell_frequencies.csv"

OUTPUT_COLUMNS = (
    "sample",
    "total_count",
    "population",
    "count",
    "percentage",
)

FREQUENCY_QUERY = """
    SELECT
        frequencies.sample,
        frequencies.total_count,
        frequencies.population,
        frequencies.count,
        frequencies.percentage
    FROM sample_cell_frequencies AS frequencies
    JOIN cell_populations
        ON cell_populations.population_name = frequencies.population
    ORDER BY frequencies.sample, cell_populations.population_id
"""


def export_cell_frequencies(
    database_path: Path = DATABASE_PATH,
    output_path: Path = OUTPUT_PATH,
) -> int:
    if not database_path.is_file():
        raise FileNotFoundError(
            f"Database not found: {database_path}. Run python load_data.py first."
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.name + ".tmp")
    temporary_path.unlink(missing_ok=True)

    row_count = 0
    try:
        with closing(sqlite3.connect(database_path)) as connection:
            cursor = connection.execute(FREQUENCY_QUERY)
            with temporary_path.open("w", newline="", encoding="utf-8") as output_file:
                writer = csv.writer(output_file, lineterminator="\n")
                writer.writerow(OUTPUT_COLUMNS)
                for sample, total_count, population, count, percentage in cursor:
                    if percentage is None:
                        raise ValueError(f"Sample {sample} has a total cell count of zero.")
                    writer.writerow(
                        (
                            sample,
                            total_count,
                            population,
                            count,
                            f"{percentage:.6f}",
                        )
                    )
                    row_count += 1

            expected_rows = connection.execute(
                "SELECT COUNT(*) FROM samples"
            ).fetchone()[0] * connection.execute(
                "SELECT COUNT(*) FROM cell_populations"
            ).fetchone()[0]

        if row_count != expected_rows:
            raise RuntimeError(
                f"Expected {expected_rows} frequency rows, generated {row_count}."
            )

        os.replace(temporary_path, output_path)
        return row_count
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def main() -> None:
    row_count = export_cell_frequencies()
    print(f"Created {OUTPUT_PATH.relative_to(ROOT)} with {row_count} rows.")


if __name__ == "__main__":
    main()
