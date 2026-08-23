"""Interactive dashboard for the assessment analysis outputs."""

from __future__ import annotations

import csv
import io
import sqlite3
from collections import defaultdict
from contextlib import closing

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from load_data import DATABASE_PATH, POPULATIONS, ROOT

STATISTICS_PATH = ROOT / "outputs" / "statistical_results.csv"
BASELINE_PATH = ROOT / "outputs" / "baseline_samples.csv"
SUMMARY_PATH = ROOT / "outputs" / "subset_summary.csv"

POPULATION_LABELS = {
    "b_cell": "B cell",
    "cd8_t_cell": "CD8 T cell",
    "cd4_t_cell": "CD4 T cell",
    "nk_cell": "NK cell",
    "monocyte": "Monocyte",
}

POPULATION_COLORS = {
    "b_cell": "#234E70",
    "cd8_t_cell": "#D39B2A",
    "cd4_t_cell": "#D26A3A",
    "nk_cell": "#728C4A",
    "monocyte": "#B85C8A",
}

RESPONSE_STYLES = {
    "no": {
        "label": "Non-responder",
        "color": "#234E70",
        "fill": "rgba(35, 78, 112, 0.22)",
        "symbol": "circle",
    },
    "yes": {
        "label": "Responder",
        "color": "#138A8A",
        "fill": "rgba(19, 138, 138, 0.22)",
        "symbol": "triangle-up",
    },
}

RESPONDER_QUERY = """
    SELECT
        projects.project_name,
        subjects.subject_name,
        frequencies.population,
        subjects.response,
        frequencies.percentage
    FROM sample_cell_frequencies AS frequencies
    JOIN samples ON samples.sample_name = frequencies.sample
    JOIN subjects USING (subject_id)
    JOIN projects USING (project_id)
    WHERE subjects.condition = 'melanoma'
      AND subjects.treatment = 'miraclib'
      AND samples.sample_type = 'PBMC'
      AND subjects.response IN ('yes', 'no')
    ORDER BY frequencies.population, subjects.response, samples.sample_name
"""


def require_artifacts() -> None:
    required_paths = (DATABASE_PATH, STATISTICS_PATH, BASELINE_PATH, SUMMARY_PATH)
    missing = [path.relative_to(ROOT) for path in required_paths if not path.is_file()]
    if missing:
        names = ", ".join(str(path) for path in missing)
        st.error(f"Missing required outputs: {names}. Run `make pipeline` first.")
        st.stop()


@st.cache_data(show_spinner=False)
def load_overview() -> dict[str, int]:
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        return {
            "projects": connection.execute("SELECT COUNT(*) FROM projects").fetchone()[
                0
            ],
            "subjects": connection.execute("SELECT COUNT(*) FROM subjects").fetchone()[
                0
            ],
            "samples": connection.execute("SELECT COUNT(*) FROM samples").fetchone()[0],
            "populations": connection.execute(
                "SELECT COUNT(*) FROM cell_populations"
            ).fetchone()[0],
        }


@st.cache_data(show_spinner=False)
def load_sample_names() -> list[str]:
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        return [
            row[0]
            for row in connection.execute(
                "SELECT sample_name FROM samples ORDER BY sample_name"
            )
        ]


@st.cache_data(show_spinner=False)
def load_sample_frequencies(sample: str) -> list[dict[str, object]]:
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        rows = connection.execute(
            """
            SELECT population, count, total_count, percentage
            FROM sample_cell_frequencies
            WHERE sample = ?
            ORDER BY CASE population
                WHEN 'b_cell' THEN 1
                WHEN 'cd8_t_cell' THEN 2
                WHEN 'cd4_t_cell' THEN 3
                WHEN 'nk_cell' THEN 4
                WHEN 'monocyte' THEN 5
            END
            """,
            (sample,),
        ).fetchall()
    return [
        {
            "population": str(population),
            "count": int(count),
            "total_count": int(total_count),
            "percentage": float(percentage),
        }
        for population, count, total_count, percentage in rows
    ]


@st.cache_data(show_spinner=False)
def load_responder_frequencies() -> dict[str, dict[str, list[float]]]:
    subject_measurements: dict[tuple[str, str, str, str], list[float]] = defaultdict(
        list
    )
    with closing(sqlite3.connect(DATABASE_PATH)) as connection:
        for project, subject, population, response, percentage in connection.execute(
            RESPONDER_QUERY
        ):
            subject_measurements[(population, response, project, subject)].append(
                float(percentage)
            )

    frequencies = {population: {"no": [], "yes": []} for population in POPULATIONS}
    for (population, response, _, _), percentages in subject_measurements.items():
        frequencies[population][response].append(float(np.mean(percentages)))
    return frequencies


@st.cache_data(show_spinner=False)
def load_statistics() -> list[dict[str, object]]:
    with STATISTICS_PATH.open(newline="", encoding="utf-8") as statistics_file:
        rows = list(csv.DictReader(statistics_file))
    return [
        {
            "population": row["population"],
            "responder_subject_n": int(row["responder_subject_n"]),
            "non_responder_subject_n": int(row["non_responder_subject_n"]),
            "responder_mean_percentage": float(row["responder_mean_percentage"]),
            "non_responder_mean_percentage": float(
                row["non_responder_mean_percentage"]
            ),
            "mean_difference": float(row["mean_difference"]),
            "t_statistic": float(row["t_statistic"]),
            "p_value": float(row["p_value"]),
            "adjusted_p_value": float(row["adjusted_p_value"]),
            "significant": row["significant"] == "yes",
        }
        for row in rows
    ]


@st.cache_data(show_spinner=False)
def load_subset_summary() -> list[dict[str, str]]:
    with SUMMARY_PATH.open(newline="", encoding="utf-8") as summary_file:
        return list(csv.DictReader(summary_file))


@st.cache_data(show_spinner=False)
def load_baseline_samples() -> list[dict[str, str]]:
    with BASELINE_PATH.open(newline="", encoding="utf-8") as baseline_file:
        return list(csv.DictReader(baseline_file))


def create_responder_figure(
    frequencies: dict[str, dict[str, list[float]]],
    statistics: list[dict[str, object]],
) -> go.Figure:
    figure = go.Figure()
    for response in ("no", "yes"):
        style = RESPONSE_STYLES[response]
        labels = []
        values = []
        for population in POPULATIONS:
            population_values = frequencies[population][response]
            labels.extend([POPULATION_LABELS[population]] * len(population_values))
            values.extend(population_values)
        figure.add_trace(
            go.Box(
                x=labels,
                y=values,
                name=str(style["label"]),
                boxpoints="all",
                boxmean=True,
                jitter=0.28,
                pointpos=0,
                quartilemethod="linear",
                fillcolor=str(style["fill"]),
                line={"color": str(style["color"]), "width": 1.5},
                marker={
                    "color": str(style["color"]),
                    "opacity": 0.18,
                    "size": 4,
                    "symbol": str(style["symbol"]),
                },
                hovertemplate=(
                    f"{style['label']}<br>%{{x}}: %{{y:.2f}}%<extra></extra>"
                ),
            )
        )

    significant_result = next(row for row in statistics if bool(row["significant"]))
    significant_population = str(significant_result["population"])
    figure.add_annotation(
        x=POPULATION_LABELS[significant_population],
        y=45,
        text=(
            "Significant · adjusted p = "
            f"{float(significant_result['adjusted_p_value']):.3g}"
        ),
        showarrow=False,
        bgcolor="#E8F5F3",
        bordercolor="#138A8A",
        borderpad=5,
        font={"color": "#183D3D", "size": 12},
    )
    figure.update_layout(
        height=500,
        margin={"l": 55, "r": 20, "t": 65, "b": 45},
        template="plotly_white",
        boxmode="group",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.13,
            "xanchor": "center",
            "x": 0.5,
        },
        hoverlabel={"bgcolor": "white", "font_color": "#17212B"},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        xaxis={"title": None, "showgrid": False},
        yaxis={
            "title": "Relative frequency (%)",
            "range": [0, 50],
            "dtick": 10,
        },
    )
    return figure


def create_sample_figure(rows: list[dict[str, object]]) -> go.Figure:
    populations = [str(row["population"]) for row in rows]
    percentages = [float(row["percentage"]) for row in rows]
    counts = [int(row["count"]) for row in rows]
    figure = go.Figure(
        go.Bar(
            x=[POPULATION_LABELS[population] for population in populations],
            y=percentages,
            customdata=counts,
            text=[f"{percentage:.1f}%" for percentage in percentages],
            textposition="outside",
            cliponaxis=False,
            marker_color=[POPULATION_COLORS[population] for population in populations],
            hovertemplate=(
                "%{x}<br>Relative frequency: %{y:.2f}%"
                "<br>Cell count: %{customdata:,}<extra></extra>"
            ),
        )
    )
    figure.update_layout(
        height=390,
        margin={"l": 55, "r": 20, "t": 25, "b": 45},
        template="plotly_white",
        yaxis={
            "title": "Relative frequency (%)",
            "range": [0, max(percentages) + 7],
            "rangemode": "tozero",
        },
        xaxis={"title": None},
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure


def create_baseline_figure(summary: list[dict[str, str]]) -> go.Figure:
    grouped = {
        metric: {
            row["group"]: int(float(row["value"]))
            for row in summary
            if row["metric"] == metric
        }
        for metric in (
            "samples_by_project",
            "subjects_by_response",
            "subjects_by_sex",
        )
    }
    figure = make_subplots(
        rows=1,
        cols=3,
        subplot_titles=(
            "Samples by project",
            "Subjects by response",
            "Subjects by sex",
        ),
    )
    chart_data = (
        (
            list(grouped["samples_by_project"]),
            list(grouped["samples_by_project"].values()),
            ["#234E70", "#6D8CA3"],
        ),
        (
            ["No", "Yes"],
            [
                grouped["subjects_by_response"]["no"],
                grouped["subjects_by_response"]["yes"],
            ],
            ["#234E70", "#138A8A"],
        ),
        (
            ["Female", "Male"],
            [grouped["subjects_by_sex"]["F"], grouped["subjects_by_sex"]["M"]],
            ["#A7B8C4", "#234E70"],
        ),
    )
    for column, (labels, values, colors) in enumerate(chart_data, start=1):
        figure.add_trace(
            go.Bar(
                x=labels,
                y=values,
                text=[f"{value:,}" for value in values],
                textposition="outside",
                cliponaxis=False,
                marker_color=colors,
                hovertemplate="%{x}: %{y:,}<extra></extra>",
                showlegend=False,
            ),
            row=1,
            col=column,
        )
        figure.update_yaxes(rangemode="tozero", showgrid=True, row=1, col=column)
        figure.update_xaxes(showgrid=False, row=1, col=column)
    figure.update_layout(
        height=360,
        margin={"l": 35, "r": 20, "t": 65, "b": 35},
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    figure.update_annotations(font={"color": "#17212B", "size": 14})
    return figure


def format_statistics_table(
    statistics: list[dict[str, object]],
) -> list[dict[str, str]]:
    return [
        {
            "Population": POPULATION_LABELS[str(row["population"])],
            "Responders": f"{int(row['responder_subject_n']):,}",
            "Non-responders": f"{int(row['non_responder_subject_n']):,}",
            "Mean difference": f"{float(row['mean_difference']):+.3f} pp",
            "t statistic": f"{float(row['t_statistic']):.3f}",
            "Raw p": f"{float(row['p_value']):.4f}",
            "Adjusted p": f"{float(row['adjusted_p_value']):.4f}",
            "Significant": "Yes" if bool(row["significant"]) else "No",
        }
        for row in statistics
    ]


def rows_to_csv(rows: list[dict[str, str]]) -> str:
    if not rows:
        return ""
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=rows[0], lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def apply_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #F5F7F8; color: #17212B; }
        .block-container { max-width: 1480px; padding-top: 2rem; padding-bottom: 4rem; }
        .hero-title { color: #17212B; font-size: clamp(2.1rem, 4vw, 3.5rem); font-weight: 720; letter-spacing: -0.04em; line-height: 1.02; margin: 0.35rem 0 0.7rem; }
        .hero-copy { color: #52616B; font-size: 1.05rem; max-width: 780px; margin-bottom: 1.5rem; }
        [data-testid="stMetric"] { background: white; border: 1px solid #E1E7EA; border-radius: 12px; padding: 1rem 1.1rem; box-shadow: 0 8px 24px rgba(23, 33, 43, 0.04); }
        [data-testid="stMetricLabel"] { color: #60717C; }
        [data-testid="stMetricValue"] { color: #17212B; }
        .finding { background: #E8F5F3; border-left: 4px solid #138A8A; border-radius: 0 10px 10px 0; color: #183D3D; padding: 1rem 1.15rem; margin: 1rem 0 1.5rem; }
        .section-kicker { color: #138A8A; font-size: 0.75rem; font-weight: 700; letter-spacing: 0.12em; text-transform: uppercase; margin-top: 2rem; }
        .source-note { background: white; border: 1px solid #E1E7EA; border-radius: 10px; color: #52616B; font-size: 0.9rem; padding: 0.9rem 1rem; }
        div[data-testid="stPlotlyChart"] { background: white; border: 1px solid #E1E7EA; border-radius: 12px; padding: 0.35rem; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_header() -> None:
    st.markdown(
        '<div class="section-kicker">Loblaw Bio Clinical Analytics</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="hero-title">Immune cell response analysis</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="hero-copy">Explore immune-cell composition, compare miraclib responders with non-responders, and review the verified baseline cohort.</div>',
        unsafe_allow_html=True,
    )


def render_dashboard() -> None:
    require_artifacts()
    overview = load_overview()
    statistics = load_statistics()
    frequencies = load_responder_frequencies()
    summary = load_subset_summary()
    baseline_samples = load_baseline_samples()

    render_header()
    metric_columns = st.columns(4)
    metric_columns[0].metric("Samples", f"{overview['samples']:,}")
    metric_columns[1].metric("Subjects", f"{overview['subjects']:,}")
    metric_columns[2].metric("Projects", f"{overview['projects']:,}")
    metric_columns[3].metric("Cell populations", f"{overview['populations']:,}")

    cd4 = next(row for row in statistics if row["population"] == "cd4_t_cell")
    st.markdown(
        "<div class='finding'><strong>Verified finding:</strong> CD4 T-cell relative frequency is higher in responders by "
        f"{float(cd4['mean_difference']):.2f} percentage points "
        f"(adjusted p = {float(cd4['adjusted_p_value']):.4f}). "
        "This is an association across treatment timepoints, not a validated predictive model.</div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="section-kicker">Treatment response</div>',
        unsafe_allow_html=True,
    )
    st.header("Responder comparison")
    st.caption(
        "Melanoma · miraclib · PBMC · one mean per subject across days 0, 7, and 14"
    )
    st.plotly_chart(
        create_responder_figure(frequencies, statistics),
        width="stretch",
        config={"displayModeBar": False, "responsive": True},
    )
    with st.expander("View statistical results"):
        st.dataframe(
            format_statistics_table(statistics),
            hide_index=True,
            width="stretch",
        )

    st.markdown(
        '<div class="section-kicker">Cell composition</div>',
        unsafe_allow_html=True,
    )
    st.header("Sample frequency explorer")
    st.caption("Choose any sample to inspect its five immune-cell populations.")
    selected_sample = st.selectbox("Sample", load_sample_names(), index=0)
    sample_rows = load_sample_frequencies(selected_sample)
    chart_column, table_column = st.columns((1.7, 1))
    with chart_column:
        st.plotly_chart(
            create_sample_figure(sample_rows),
            width="stretch",
            config={"displayModeBar": False, "responsive": True},
        )
    with table_column:
        st.metric("Total cell count", f"{int(sample_rows[0]['total_count']):,}")
        st.dataframe(
            [
                {
                    "Population": POPULATION_LABELS[str(row["population"])],
                    "Count": f"{int(row['count']):,}",
                    "Percentage": f"{float(row['percentage']):.2f}%",
                }
                for row in sample_rows
            ],
            hide_index=True,
            width="stretch",
        )

    st.markdown(
        '<div class="section-kicker">Early treatment subset</div>',
        unsafe_allow_html=True,
    )
    st.header("Baseline melanoma cohort")
    st.caption("PBMC · miraclib · day 0")
    summary_lookup = {(row["metric"], row["group"]): row["value"] for row in summary}
    baseline_metrics = st.columns(4)
    baseline_metrics[0].metric("Baseline samples", f"{len(baseline_samples):,}")
    baseline_metrics[1].metric(
        "Responders", f"{int(summary_lookup[('subjects_by_response', 'yes')]):,}"
    )
    baseline_metrics[2].metric(
        "Non-responders", f"{int(summary_lookup[('subjects_by_response', 'no')]):,}"
    )
    baseline_metrics[3].metric(
        "Avg. B-cell count",
        f"{float(summary_lookup[('average_b_cell_count', 'melanoma_male_responders_at_baseline_all_samples_and_treatments')]):,.2f}",
        help="Melanoma male responders at day 0 across all sample and treatment types",
    )
    st.plotly_chart(
        create_baseline_figure(summary),
        width="stretch",
        config={"displayModeBar": False, "responsive": True},
    )

    with st.expander("Browse baseline samples"):
        filter_columns = st.columns(3)
        with filter_columns[0]:
            project = st.selectbox("Project", ["All", "prj1", "prj3"])
        with filter_columns[1]:
            response = st.selectbox("Response", ["All", "no", "yes"])
        with filter_columns[2]:
            sex = st.selectbox("Sex", ["All", "F", "M"])
        filtered = [
            row
            for row in baseline_samples
            if (project == "All" or row["project"] == project)
            and (response == "All" or row["response"] == response)
            and (sex == "All" or row["sex"] == sex)
        ]
        st.caption(f"{len(filtered):,} matching samples")
        st.dataframe(filtered, hide_index=True, width="stretch", height=320)
        st.download_button(
            "Download filtered CSV",
            rows_to_csv(filtered),
            file_name="baseline_samples_filtered.csv",
            mime="text/csv",
        )

    st.markdown(
        "<div class='source-note'><strong>Source:</strong> cell-count.csv loaded into SQLite. "
        "Canonical outputs are regenerated with <code>make pipeline</code>. Statistical significance uses "
        "two-sided Welch tests with Benjamini–Hochberg correction across five populations.</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    st.set_page_config(
        page_title="Immune Cell Response Analysis",
        page_icon="🧬",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    apply_styles()
    render_dashboard()


if __name__ == "__main__":
    main()
