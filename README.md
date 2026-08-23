# Teiko Technical Assessment

Analysis of immune-cell population data using Python, SQLite, and an interactive Streamlit dashboard.

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

## Development tools

Visual Studio Code is the primary IDE.

AI assistance from OpenAI Codex using GPT-5.6 Sol with high reasoning effort was used to support implementation and review while following software engineering best practices.
