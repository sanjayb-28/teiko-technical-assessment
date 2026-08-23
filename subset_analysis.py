"""Generate the required Part 4 subset analysis outputs."""

from __future__ import annotations

import csv
import os
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from load_data import DATABASE_PATH, ROOT


BASELINE_OUTPUT_PATH = ROOT / "outputs" / "baseline_samples.csv"
SUMMARY_OUTPUT_PATH = ROOT / "outputs" / "subset_summary.csv"

BASELINE_COLUMNS = (
    "project",
    "subject",
    "sample",
    "condition",
    "treatment",
    "response",
    "sex",
    "sample_type",
    "time_from_treatment_start",
)

SUMMARY_COLUMNS = ("metric", "group", "value")

BASELINE_SAMPLES_QUERY = """
    SELECT
        projects.project_name,
        subjects.subject_name,
        samples.sample_name,
        subjects.condition,
        subjects.treatment,
        subjects.response,
        subjects.sex,
        samples.sample_type,
        samples.time_from_treatment_start
    FROM samples
    JOIN subjects USING (subject_id)
    JOIN projects USING (project_id)
    WHERE subjects.condition = 'melanoma'
      AND subjects.treatment = 'miraclib'
      AND samples.sample_type = 'PBMC'
      AND samples.time_from_treatment_start = 0
    ORDER BY projects.project_name, samples.sample_name
"""

BASELINE_B_CELL_AVERAGE_QUERY = """
    SELECT AVG(cell_counts.count)
    FROM cell_counts
    JOIN cell_populations USING (population_id)
    JOIN samples USING (sample_id)
    JOIN subjects USING (subject_id)
    WHERE subjects.condition = 'melanoma'
      AND subjects.sex = 'M'
      AND subjects.response = 'yes'
      AND samples.time_from_treatment_start = 0
      AND cell_populations.population_name = 'b_cell'
"""


def load_subset_data(
    database_path: Path = DATABASE_PATH,
) -> tuple[list[tuple[object, ...]], float]:
    if not database_path.is_file():
        raise FileNotFoundError(
            f"Database not found: {database_path}. Run python load_data.py first."
        )

    with closing(sqlite3.connect(database_path)) as connection:
        baseline_samples = list(connection.execute(BASELINE_SAMPLES_QUERY))
        average_b_cell_count = connection.execute(
            BASELINE_B_CELL_AVERAGE_QUERY
        ).fetchone()[0]

    if not baseline_samples:
        raise RuntimeError("No samples matched the Part 4 baseline criteria.")
    if average_b_cell_count is None:
        raise RuntimeError("No samples matched the B-cell average criteria.")

    return baseline_samples, float(average_b_cell_count)


def calculate_subset_summary(
    baseline_samples: list[tuple[object, ...]],
    average_b_cell_count: float,
) -> list[tuple[str, str, object]]:
    samples_by_project: Counter[str] = Counter()
    subjects_by_response: dict[str, set[tuple[str, str]]] = defaultdict(set)
    subjects_by_sex: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for row in baseline_samples:
        project = str(row[0])
        subject = str(row[1])
        response = str(row[5])
        sex = str(row[6])
        subject_key = (project, subject)

        samples_by_project[project] += 1
        subjects_by_response[response].add(subject_key)
        subjects_by_sex[sex].add(subject_key)

    unexpected_responses = set(subjects_by_response) - {"no", "yes"}
    unexpected_sexes = set(subjects_by_sex) - {"F", "M"}
    if unexpected_responses or unexpected_sexes:
        raise RuntimeError("The baseline subset contains unexpected subject metadata.")

    summary: list[tuple[str, str, object]] = []
    summary.extend(
        ("samples_by_project", project, count)
        for project, count in sorted(samples_by_project.items())
    )
    summary.extend(
        ("subjects_by_response", response, len(subjects_by_response[response]))
        for response in ("no", "yes")
    )
    summary.extend(
        ("subjects_by_sex", sex, len(subjects_by_sex[sex])) for sex in ("F", "M")
    )
    summary.append(
        (
            "average_b_cell_count",
            "melanoma_male_responders_at_baseline_all_samples_and_treatments",
            f"{average_b_cell_count:.2f}",
        )
    )
    return summary


def write_csv(
    rows: list[tuple[object, ...]],
    columns: tuple[str, ...],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.name + ".tmp")
    temporary_path.unlink(missing_ok=True)

    try:
        with temporary_path.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.writer(output_file, lineterminator="\n")
            writer.writerow(columns)
            writer.writerows(rows)
        os.replace(temporary_path, output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def run_subset_analysis(
    database_path: Path = DATABASE_PATH,
    baseline_output_path: Path = BASELINE_OUTPUT_PATH,
    summary_output_path: Path = SUMMARY_OUTPUT_PATH,
) -> tuple[int, int]:
    baseline_samples, average_b_cell_count = load_subset_data(database_path)
    summary = calculate_subset_summary(baseline_samples, average_b_cell_count)
    write_csv(baseline_samples, BASELINE_COLUMNS, baseline_output_path)
    write_csv(summary, SUMMARY_COLUMNS, summary_output_path)
    return len(baseline_samples), len(summary)


def main() -> None:
    baseline_count, summary_count = run_subset_analysis()
    print(
        f"Created {BASELINE_OUTPUT_PATH.relative_to(ROOT)} with "
        f"{baseline_count} rows."
    )
    print(
        f"Created {SUMMARY_OUTPUT_PATH.relative_to(ROOT)} with "
        f"{summary_count} rows."
    )


if __name__ == "__main__":
    main()
