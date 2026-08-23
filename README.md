# Teiko Technical Assessment

Analysis of immune-cell population data using Python, SQLite, and an interactive Streamlit dashboard.

## Setup

Python 3.10 or newer is required.

```bash
python -m pip install -r requirements.txt
```

## Data management

Run the loader from the repository root:

```bash
python load_data.py
```

The command validates `cell-count.csv` and creates `cell_counts.db` in the repository root. Each run rebuilds the database, so repeated execution produces the same records without duplicates.

### Database schema

| Table | Purpose |
| --- | --- |
| `projects` | One record per clinical project |
| `subjects` | Subject attributes and project membership |
| `samples` | Biological sample type and treatment timepoint |
| `cell_populations` | Reference list of immune-cell populations |
| `cell_counts` | One count per sample and cell population |

The normalized design separates project, subject, sample, and measurement data. Foreign keys preserve relationships, unique constraints prevent duplicate source identifiers, and checks reject negative ages, timepoints, and cell counts. Analysis indexes cover the condition, treatment, response, sex, sample type, timepoint, and population filters used by the project.

Keeping cell measurements in a long-form table allows new populations to be added without changing the sample schema. This structure can support hundreds of projects and thousands of samples while keeping population-level queries consistent. SQLite is appropriate for this self-contained assessment; the same relational model can move to a server database if concurrent writes or substantially larger workloads are required.

### Part 1 tests

```bash
python -m unittest discover -s tests
```

## Data overview

After creating the database, generate the cell-frequency summary:

```bash
python analysis.py
```

The command writes `outputs/cell_frequencies.csv`. Each sample has five rows with the required `sample`, `total_count`, `population`, `count`, and `percentage` columns. Percentages are calculated as the population count divided by the sample's total cell count, multiplied by 100.

## Statistical analysis

`python analysis.py` also compares relative frequencies for melanoma PBMC samples from miraclib-treated responders and non-responders. Each subject's percentages are averaged across days 0, 7, and 14 before running a two-sided Welch t-test for each population. Benjamini–Hochberg correction controls the false discovery rate across the five tests, with significance defined as adjusted `p < 0.05`.

The analysis creates:

- `outputs/statistical_results.csv`
- `outputs/responder_boxplots.png`

CD4 T cells show a significant difference between responders and non-responders (raw `p = 0.0045`, adjusted `p = 0.0226`). The other four populations do not meet the adjusted `p < 0.05` threshold.

The results table includes subject counts, mean percentages, mean differences, test statistics, raw and adjusted p-values, and significance. The analysis identifies associations with response; it does not train or validate a predictive model.

## Data subset analysis

Run the Part 4 analysis after creating the database:

```bash
python subset_analysis.py
```

The command creates:

- `outputs/baseline_samples.csv`, containing the 656 melanoma PBMC samples collected at day 0 from subjects treated with miraclib
- `outputs/subset_summary.csv`, containing sample counts by project, distinct subject counts by response and sex, and the requested average B-cell count

The baseline subset contains 384 samples from `prj1` and 272 from `prj3`. It includes 331 responders and 325 non-responders, with 312 female and 344 male subjects. For melanoma male responders at day 0 across all sample and treatment types, the average B-cell count is `10206.15`.

## Development tools

Visual Studio Code is the primary IDE.

AI assistance from OpenAI Codex using GPT-5.6 Sol with high reasoning effort was used to support implementation and review while following software engineering best practices.
