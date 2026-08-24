import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from dashboard import (
    create_baseline_figure,
    create_responder_figure,
    create_sample_figure,
    load_baseline_samples,
    load_responder_frequencies,
    load_sample_frequencies,
    load_statistics,
    load_subset_summary,
)


class DashboardDataTests(unittest.TestCase):
    def test_sample_explorer_uses_all_five_populations(self) -> None:
        rows = load_sample_frequencies("sample00000")

        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["total_count"], 93_214)
        self.assertAlmostEqual(
            sum(float(row["percentage"]) for row in rows),
            100.0,
        )

        figure = create_sample_figure(rows)
        self.assertEqual(len(figure.data), 1)
        self.assertEqual(len(figure.data[0].x), 5)

    def test_response_figure_matches_statistical_output(self) -> None:
        frequencies = load_responder_frequencies()
        statistics = load_statistics()
        figure = create_responder_figure(frequencies, statistics)

        self.assertEqual(len(figure.data), 2)
        self.assertEqual(
            set(figure.data[0].x),
            {"B cell", "CD8 T cell", "CD4 T cell", "NK cell", "Monocyte"},
        )
        self.assertEqual(
            {row["population"] for row in statistics if bool(row["significant"])},
            {"cd4_t_cell"},
        )
        for population in frequencies.values():
            self.assertEqual(len(population["yes"]), 331)
            self.assertEqual(len(population["no"]), 325)

    def test_baseline_figure_uses_pipeline_outputs(self) -> None:
        baseline_samples = load_baseline_samples()
        summary = load_subset_summary()
        figure = create_baseline_figure(summary)

        self.assertEqual(len(baseline_samples), 656)
        self.assertEqual(len(figure.data), 3)


class DashboardAppTests(unittest.TestCase):
    def test_dashboard_renders_without_exceptions(self) -> None:
        dashboard_path = Path(__file__).resolve().parents[1] / "dashboard.py"
        app = AppTest.from_file(dashboard_path, default_timeout=20).run()

        self.assertEqual(app.exception, [])
        self.assertEqual(len(app.metric), 5)
        self.assertEqual(app.selectbox[0].value, "sample00000")
        self.assertIn("Responder comparison", [header.value for header in app.header])


if __name__ == "__main__":
    unittest.main()
