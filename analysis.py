"""Generate the required analysis outputs from SQLite."""

from __future__ import annotations

import csv
import os
import sqlite3
from contextlib import closing
from pathlib import Path

import matplotlib
import numpy as np
from scipy.stats import ttest_ind

from load_data import POPULATIONS


matplotlib.use("Agg")
from matplotlib import pyplot as plt  # noqa: E402


ROOT = Path(__file__).resolve().parent
DATABASE_PATH = ROOT / "cell_counts.db"
OUTPUT_PATH = ROOT / "outputs" / "cell_frequencies.csv"
STATISTICS_OUTPUT_PATH = ROOT / "outputs" / "statistical_results.csv"
BOXPLOT_OUTPUT_PATH = ROOT / "outputs" / "responder_boxplots.png"

OUTPUT_COLUMNS = (
    "sample",
    "total_count",
    "population",
    "count",
    "percentage",
)

STATISTICS_COLUMNS = (
    "population",
    "responder_n",
    "non_responder_n",
    "responder_mean_percentage",
    "non_responder_mean_percentage",
    "mean_difference",
    "t_statistic",
    "p_value",
    "significant",
)

POPULATION_LABELS = {
    "b_cell": "B cell",
    "cd8_t_cell": "CD8 T cell",
    "cd4_t_cell": "CD4 T cell",
    "nk_cell": "NK cell",
    "monocyte": "Monocyte",
}

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

RESPONDER_QUERY = """
    SELECT
        frequencies.population,
        subjects.response,
        frequencies.percentage
    FROM sample_cell_frequencies AS frequencies
    JOIN samples ON samples.sample_name = frequencies.sample
    JOIN subjects USING (subject_id)
    WHERE subjects.condition = 'melanoma'
      AND subjects.treatment = 'miraclib'
      AND samples.sample_type = 'PBMC'
      AND subjects.response IN ('yes', 'no')
    ORDER BY frequencies.population, subjects.response, samples.sample_name
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
                        raise ValueError(
                            f"Sample {sample} has a total cell count of zero."
                        )
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


def load_responder_frequencies(
    database_path: Path = DATABASE_PATH,
) -> dict[str, dict[str, list[float]]]:
    if not database_path.is_file():
        raise FileNotFoundError(
            f"Database not found: {database_path}. Run python load_data.py first."
        )

    frequencies = {
        population: {"no": [], "yes": []} for population in POPULATIONS
    }
    with closing(sqlite3.connect(database_path)) as connection:
        for population, response, percentage in connection.execute(RESPONDER_QUERY):
            frequencies[population][response].append(float(percentage))

    for population, groups in frequencies.items():
        if not groups["yes"] or not groups["no"]:
            raise RuntimeError(
                f"Responder comparison requires both groups for {population}."
            )
    return frequencies


def calculate_responder_statistics(
    frequencies: dict[str, dict[str, list[float]]],
) -> list[dict[str, object]]:
    results = []
    for population in POPULATIONS:
        responders = np.asarray(frequencies[population]["yes"], dtype=float)
        non_responders = np.asarray(frequencies[population]["no"], dtype=float)
        test_result = ttest_ind(
            responders,
            non_responders,
            equal_var=False,
            nan_policy="raise",
        )
        responder_mean = float(np.mean(responders))
        non_responder_mean = float(np.mean(non_responders))
        p_value = float(test_result.pvalue)
        results.append(
            {
                "population": population,
                "responder_n": len(responders),
                "non_responder_n": len(non_responders),
                "responder_mean_percentage": responder_mean,
                "non_responder_mean_percentage": non_responder_mean,
                "mean_difference": responder_mean - non_responder_mean,
                "t_statistic": float(test_result.statistic),
                "p_value": p_value,
                "significant": p_value < 0.05,
            }
        )
    return results


def write_statistical_results(
    results: list[dict[str, object]],
    output_path: Path = STATISTICS_OUTPUT_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(output_path.name + ".tmp")
    temporary_path.unlink(missing_ok=True)

    try:
        with temporary_path.open("w", newline="", encoding="utf-8") as output_file:
            writer = csv.DictWriter(
                output_file,
                fieldnames=STATISTICS_COLUMNS,
                lineterminator="\n",
            )
            writer.writeheader()
            for result in results:
                writer.writerow(
                    {
                        "population": result["population"],
                        "responder_n": result["responder_n"],
                        "non_responder_n": result["non_responder_n"],
                        "responder_mean_percentage": (
                            f"{result['responder_mean_percentage']:.6f}"
                        ),
                        "non_responder_mean_percentage": (
                            f"{result['non_responder_mean_percentage']:.6f}"
                        ),
                        "mean_difference": f"{result['mean_difference']:.6f}",
                        "t_statistic": f"{result['t_statistic']:.6f}",
                        "p_value": f"{result['p_value']:.10f}",
                        "significant": "yes" if result["significant"] else "no",
                    }
                )
        os.replace(temporary_path, output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def create_responder_boxplot(
    frequencies: dict[str, dict[str, list[float]]],
    results: list[dict[str, object]],
    output_path: Path = BOXPLOT_OUTPUT_PATH,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.with_name(
        output_path.stem + ".tmp" + output_path.suffix
    )
    temporary_path.unlink(missing_ok=True)

    non_responder_color = "#234E70"
    responder_color = "#138A8A"
    ink = "#17212B"
    grid = "#DCE3E8"
    result_by_population = {result["population"]: result for result in results}
    rng = np.random.default_rng(20260823)

    style = {
        "font.family": "DejaVu Sans",
        "axes.edgecolor": ink,
        "axes.labelcolor": ink,
        "axes.titlecolor": ink,
        "xtick.color": ink,
        "ytick.color": ink,
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }

    try:
        with plt.rc_context(style):
            figure, axes = plt.subplots(
                1,
                len(POPULATIONS),
                figsize=(18, 5.6),
                sharey=True,
            )

            maximum = max(
                max(frequencies[population][response])
                for population in POPULATIONS
                for response in ("no", "yes")
            )
            y_limit = np.ceil(maximum / 5.0) * 5.0 + 5.0

            for axis, population in zip(axes, POPULATIONS, strict=True):
                non_responders = np.asarray(
                    frequencies[population]["no"], dtype=float
                )
                responders = np.asarray(frequencies[population]["yes"], dtype=float)
                groups = (non_responders, responders)
                colors = (non_responder_color, responder_color)
                markers = ("o", "^")

                boxes = axis.boxplot(
                    groups,
                    positions=(1, 2),
                    widths=0.5,
                    patch_artist=True,
                    showfliers=False,
                    tick_labels=(
                        f"No\n(n={len(non_responders):,})",
                        f"Yes\n(n={len(responders):,})",
                    ),
                    medianprops={"color": ink, "linewidth": 1.8},
                    whiskerprops={"color": ink, "linewidth": 1.1},
                    capprops={"color": ink, "linewidth": 1.1},
                )

                for position, values, color, marker, box in zip(
                    (1, 2), groups, colors, markers, boxes["boxes"], strict=True
                ):
                    box.set_facecolor(color)
                    box.set_alpha(0.28)
                    box.set_edgecolor(color)
                    box.set_linewidth(1.5)
                    jitter = rng.normal(position, 0.055, len(values))
                    axis.scatter(
                        jitter,
                        values,
                        s=7,
                        marker=marker,
                        color=color,
                        alpha=0.12,
                        linewidths=0,
                        rasterized=True,
                    )
                    axis.scatter(
                        position,
                        np.mean(values),
                        s=42,
                        marker="D",
                        facecolor="white",
                        edgecolor=color,
                        linewidth=1.6,
                        zorder=4,
                    )

                result = result_by_population[population]
                p_value = float(result["p_value"])
                p_text = f"p = {p_value:.3g}"
                if result["significant"]:
                    p_text += "  •  significant"

                axis.set_title(POPULATION_LABELS[population], fontsize=12, pad=12)
                axis.text(
                    0.5,
                    0.97,
                    p_text,
                    transform=axis.transAxes,
                    ha="center",
                    va="top",
                    fontsize=9,
                    color=ink,
                )
                axis.set_ylim(0, y_limit)
                axis.grid(axis="y", color=grid, linewidth=0.8)
                axis.set_axisbelow(True)
                axis.spines["top"].set_visible(False)
                axis.spines["right"].set_visible(False)
                axis.tick_params(axis="x", length=0, pad=8)

            axes[0].set_ylabel("Relative frequency (%)", fontsize=11)
            figure.suptitle(
                "Immune cell frequencies by treatment response",
                fontsize=18,
                fontweight="bold",
                color=ink,
                y=0.98,
            )
            figure.text(
                0.5,
                0.92,
                "Melanoma · miraclib · PBMC · all treatment timepoints",
                ha="center",
                fontsize=11,
                color="#52616B",
            )
            figure.text(
                0.5,
                0.03,
                "Boxes show median and IQR; diamonds show means; "
                "points represent samples.",
                ha="center",
                fontsize=9,
                color="#52616B",
            )
            figure.subplots_adjust(
                left=0.06,
                right=0.99,
                top=0.84,
                bottom=0.19,
                wspace=0.16,
            )
            figure.savefig(
                temporary_path,
                dpi=220,
                facecolor="white",
                metadata={"Software": "Matplotlib"},
            )
            plt.close(figure)
        os.replace(temporary_path, output_path)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def run_responder_analysis(
    database_path: Path = DATABASE_PATH,
    statistics_output_path: Path = STATISTICS_OUTPUT_PATH,
    boxplot_output_path: Path = BOXPLOT_OUTPUT_PATH,
) -> list[dict[str, object]]:
    frequencies = load_responder_frequencies(database_path)
    results = calculate_responder_statistics(frequencies)
    write_statistical_results(results, statistics_output_path)
    create_responder_boxplot(frequencies, results, boxplot_output_path)
    return results


def main() -> None:
    row_count = export_cell_frequencies()
    statistical_results = run_responder_analysis()
    print(f"Created {OUTPUT_PATH.relative_to(ROOT)} with {row_count} rows.")
    print(
        f"Created {STATISTICS_OUTPUT_PATH.relative_to(ROOT)} with "
        f"{len(statistical_results)} rows."
    )
    print(f"Created {BOXPLOT_OUTPUT_PATH.relative_to(ROOT)}.")


if __name__ == "__main__":
    main()
