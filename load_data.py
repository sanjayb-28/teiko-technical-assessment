"""Create and populate the assessment SQLite database."""

from __future__ import annotations

import csv
import os
import sqlite3
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CSV_PATH = ROOT / "cell-count.csv"
DATABASE_PATH = ROOT / "cell_counts.db"
SCHEMA_PATH = ROOT / "schema.sql"

POPULATIONS = (
    "b_cell",
    "cd8_t_cell",
    "cd4_t_cell",
    "nk_cell",
    "monocyte",
)

METADATA_COLUMNS = (
    "project",
    "subject",
    "condition",
    "age",
    "sex",
    "treatment",
    "response",
    "sample",
    "sample_type",
    "time_from_treatment_start",
)

REQUIRED_COLUMNS = METADATA_COLUMNS + POPULATIONS


def parse_non_negative_integer(value: str, column: str, row_number: int) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(
            f"Row {row_number}: {column} must be an integer, received {value!r}."
        ) from exc

    if parsed < 0:
        raise ValueError(
            f"Row {row_number}: {column} must be non-negative, received {parsed}."
        )
    return parsed


def normalize_response(value: str, row_number: int) -> str | None:
    response = value.strip().lower()
    if response == "":
        return None
    if response not in {"yes", "no"}:
        raise ValueError(
            f"Row {row_number}: response must be yes, no, or blank, received {value!r}."
        )
    return response


def validate_header(fieldnames: list[str] | None) -> None:
    if fieldnames is None:
        raise ValueError("The CSV does not contain a header row.")

    missing = [column for column in REQUIRED_COLUMNS if column not in fieldnames]
    unexpected = [column for column in fieldnames if column not in REQUIRED_COLUMNS]
    if missing or unexpected:
        details = []
        if missing:
            details.append(f"missing columns: {', '.join(missing)}")
        if unexpected:
            details.append(f"unexpected columns: {', '.join(unexpected)}")
        raise ValueError("Invalid CSV header (" + "; ".join(details) + ").")


def load_rows(connection: sqlite3.Connection, csv_path: Path) -> int:
    project_ids: dict[str, int] = {}
    subject_ids: dict[tuple[str, str], int] = {}
    subject_metadata: dict[tuple[str, str], tuple[object, ...]] = {}

    connection.executemany(
        "INSERT INTO cell_populations (population_name) VALUES (?)",
        ((population,) for population in POPULATIONS),
    )
    population_ids = {
        name: population_id
        for population_id, name in connection.execute(
            "SELECT population_id, population_name FROM cell_populations"
        )
    }

    row_count = 0
    with csv_path.open(newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.DictReader(csv_file)
        validate_header(reader.fieldnames)

        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            if None in row:
                raise ValueError(f"Row {row_number}: too many values for the CSV header.")
            missing_values = [
                column for column in REQUIRED_COLUMNS if row[column] is None
            ]
            if missing_values:
                raise ValueError(
                    f"Row {row_number}: missing values for columns: "
                    + ", ".join(missing_values)
                    + "."
                )

            project_name = row["project"].strip()
            subject_name = row["subject"].strip()
            sample_name = row["sample"].strip()
            condition = row["condition"].strip()
            sex = row["sex"].strip()
            treatment = row["treatment"].strip()
            sample_type = row["sample_type"].strip()

            required_text = {
                "project": project_name,
                "subject": subject_name,
                "sample": sample_name,
                "condition": condition,
                "sex": sex,
                "treatment": treatment,
                "sample_type": sample_type,
            }
            empty_columns = [name for name, value in required_text.items() if not value]
            if empty_columns:
                raise ValueError(
                    f"Row {row_number}: required values are blank: "
                    + ", ".join(empty_columns)
                    + "."
                )

            age = parse_non_negative_integer(row["age"], "age", row_number)
            timepoint = parse_non_negative_integer(
                row["time_from_treatment_start"],
                "time_from_treatment_start",
                row_number,
            )
            response = normalize_response(row["response"], row_number)
            counts = {
                population: parse_non_negative_integer(
                    row[population], population, row_number
                )
                for population in POPULATIONS
            }

            project_id = project_ids.get(project_name)
            if project_id is None:
                cursor = connection.execute(
                    "INSERT INTO projects (project_name) VALUES (?)",
                    (project_name,),
                )
                project_id = int(cursor.lastrowid)
                project_ids[project_name] = project_id

            subject_key = (project_name, subject_name)
            metadata = (condition, age, sex, treatment, response)
            subject_id = subject_ids.get(subject_key)
            if subject_id is None:
                cursor = connection.execute(
                    """
                    INSERT INTO subjects (
                        project_id,
                        subject_name,
                        condition,
                        age,
                        sex,
                        treatment,
                        response
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        subject_name,
                        condition,
                        age,
                        sex,
                        treatment,
                        response,
                    ),
                )
                subject_id = int(cursor.lastrowid)
                subject_ids[subject_key] = subject_id
                subject_metadata[subject_key] = metadata
            elif subject_metadata[subject_key] != metadata:
                raise ValueError(
                    f"Row {row_number}: metadata changed for subject "
                    f"{project_name}/{subject_name}."
                )

            cursor = connection.execute(
                """
                INSERT INTO samples (
                    subject_id,
                    sample_name,
                    sample_type,
                    time_from_treatment_start
                ) VALUES (?, ?, ?, ?)
                """,
                (subject_id, sample_name, sample_type, timepoint),
            )
            sample_id = int(cursor.lastrowid)

            connection.executemany(
                """
                INSERT INTO cell_counts (sample_id, population_id, count)
                VALUES (?, ?, ?)
                """,
                (
                    (sample_id, population_ids[population], counts[population])
                    for population in POPULATIONS
                ),
            )

    if row_count == 0:
        raise ValueError("The CSV contains no data rows.")
    return row_count


def validate_database(connection: sqlite3.Connection, csv_row_count: int) -> None:
    sample_count = connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
    count_rows = connection.execute("SELECT COUNT(*) FROM cell_counts").fetchone()[0]
    population_count = connection.execute(
        "SELECT COUNT(*) FROM cell_populations"
    ).fetchone()[0]
    incomplete_samples = connection.execute(
        """
        SELECT COUNT(*)
        FROM (
            SELECT sample_id
            FROM cell_counts
            GROUP BY sample_id
            HAVING COUNT(*) != ?
        )
        """,
        (len(POPULATIONS),),
    ).fetchone()[0]
    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()

    if sample_count != csv_row_count:
        raise RuntimeError(
            f"Expected {csv_row_count} samples, found {sample_count}."
        )
    if count_rows != csv_row_count * len(POPULATIONS):
        raise RuntimeError(
            f"Expected {csv_row_count * len(POPULATIONS)} cell counts, "
            f"found {count_rows}."
        )
    if population_count != len(POPULATIONS):
        raise RuntimeError(
            f"Expected {len(POPULATIONS)} populations, found {population_count}."
        )
    if incomplete_samples:
        raise RuntimeError(
            f"Found {incomplete_samples} samples without exactly "
            f"{len(POPULATIONS)} cell counts."
        )
    if foreign_key_errors:
        raise RuntimeError(f"Foreign-key validation failed: {foreign_key_errors}")


def create_database(
    csv_path: Path = CSV_PATH,
    database_path: Path = DATABASE_PATH,
    schema_path: Path = SCHEMA_PATH,
) -> dict[str, int]:
    for path, label in ((csv_path, "CSV"), (schema_path, "schema")):
        if not path.is_file():
            raise FileNotFoundError(f"{label} file not found: {path}")

    temporary_path = database_path.with_name(database_path.name + ".tmp")
    temporary_path.unlink(missing_ok=True)

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(temporary_path)
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(schema_path.read_text(encoding="utf-8"))
        with connection:
            csv_row_count = load_rows(connection, csv_path)
            validate_database(connection, csv_row_count)

        summary = {
            "projects": connection.execute(
                "SELECT COUNT(*) FROM projects"
            ).fetchone()[0],
            "subjects": connection.execute(
                "SELECT COUNT(*) FROM subjects"
            ).fetchone()[0],
            "samples": connection.execute("SELECT COUNT(*) FROM samples").fetchone()[
                0
            ],
            "cell_counts": connection.execute(
                "SELECT COUNT(*) FROM cell_counts"
            ).fetchone()[0],
        }
        connection.close()
        connection = None
        os.replace(temporary_path, database_path)
        return summary
    except Exception:
        if connection is not None:
            connection.close()
        temporary_path.unlink(missing_ok=True)
        raise


def main() -> None:
    summary = create_database()
    print(f"Created {DATABASE_PATH.name}")
    print(
        "Loaded "
        f"{summary['projects']} projects, "
        f"{summary['subjects']} subjects, "
        f"{summary['samples']} samples, and "
        f"{summary['cell_counts']} cell counts."
    )


if __name__ == "__main__":
    main()
