# GCSN Senior Project

Global Container Shipping Network (GCSN) — disruption-impact analysis on port
connectivity. This repo continues and extends a graduated senior's original
work: full historical coverage (through the latest available quarter),
cleaned/verified raw data, and a master port reference table.

## Folder structure

```
data/
  sources/        # the 3 duplicate raw-data folders from the local machine,
                   # kept separate until verified (2011-2017, 2015-2023, 2017-2026)
  raw/             # the de-duplicated, single-source-of-truth quarterly CSVs
  qa/              # diff reports / verification output (content_differences.xlsx, etc.)
  reference/       # master_ports.csv and other lookup tables
  processed/       # derived datasets used directly by the notebooks
notebooks/         # the 6 analysis notebooks (CPCI, Overtime, Visualize_graph,
                    # Kendall Tau, Spectral, Similarity)
src/                # reusable Python modules (e.g. diff_tools.py)
docs/               # verification log, methodology notes
tests/              # tests for src/ modules
```

## Status

- [ ] Raw data verified across the 3 source folders (keyed diff, not positional)
- [ ] master_ports.csv populated from verified data
- [ ] Notebooks re-run against the full, verified date range
- [ ] Known bugs fixed (eigenvalue selection, Jaccard normalization, betweenness weighting)

See `docs/verification_log.md` for details as they're filled in.
