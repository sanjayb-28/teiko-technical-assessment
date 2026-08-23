PRAGMA foreign_keys = ON;

CREATE TABLE projects (
    project_id INTEGER PRIMARY KEY,
    project_name TEXT NOT NULL UNIQUE
);

CREATE TABLE subjects (
    subject_id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL,
    subject_name TEXT NOT NULL,
    condition TEXT NOT NULL,
    age INTEGER NOT NULL CHECK (age >= 0),
    sex TEXT NOT NULL CHECK (sex IN ('F', 'M')),
    treatment TEXT NOT NULL,
    response TEXT CHECK (response IN ('no', 'yes') OR response IS NULL),
    UNIQUE (project_id, subject_name),
    FOREIGN KEY (project_id) REFERENCES projects (project_id)
);

CREATE TABLE samples (
    sample_id INTEGER PRIMARY KEY,
    subject_id INTEGER NOT NULL,
    sample_name TEXT NOT NULL UNIQUE,
    sample_type TEXT NOT NULL,
    time_from_treatment_start INTEGER NOT NULL
        CHECK (time_from_treatment_start >= 0),
    FOREIGN KEY (subject_id) REFERENCES subjects (subject_id)
);

CREATE TABLE cell_populations (
    population_id INTEGER PRIMARY KEY,
    population_name TEXT NOT NULL UNIQUE
);

CREATE TABLE cell_counts (
    sample_id INTEGER NOT NULL,
    population_id INTEGER NOT NULL,
    count INTEGER NOT NULL CHECK (count >= 0),
    PRIMARY KEY (sample_id, population_id),
    FOREIGN KEY (sample_id) REFERENCES samples (sample_id),
    FOREIGN KEY (population_id) REFERENCES cell_populations (population_id)
);

CREATE INDEX idx_subjects_analysis
    ON subjects (condition, treatment, response);

CREATE INDEX idx_subjects_sex
    ON subjects (sex);

CREATE INDEX idx_samples_analysis
    ON samples (sample_type, time_from_treatment_start);

CREATE INDEX idx_samples_subject
    ON samples (subject_id);

CREATE INDEX idx_cell_counts_population
    ON cell_counts (population_id);

CREATE VIEW sample_cell_frequencies AS
WITH sample_totals AS (
    SELECT sample_id, SUM(count) AS total_count
    FROM cell_counts
    GROUP BY sample_id
)
SELECT
    samples.sample_name AS sample,
    sample_totals.total_count,
    cell_populations.population_name AS population,
    cell_counts.count,
    100.0 * cell_counts.count / NULLIF(sample_totals.total_count, 0) AS percentage
FROM cell_counts
JOIN sample_totals USING (sample_id)
JOIN samples USING (sample_id)
JOIN cell_populations USING (population_id);
