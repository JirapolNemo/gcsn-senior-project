"""Read one quarterly edge-list CSV into a clean, canonical DataFrame.

Handles the schema differences between files:
  * 20110925.csv has only 12 columns (no namea/nameb/connections/...).
  * Some files start with a UTF-8 BOM, so the first header can be '\\ufefforigin'.
  * The `period` column is a string in some files; we never use it, the
    quarter comes from the file name.
Only the columns CPCI needs are required.
"""
from __future__ import annotations

import warnings
from pathlib import Path
from typing import Union

import pandas as pd

from .config import LSCI_COLUMNS

REQUIRED = ["origin", "destination"] + LSCI_COLUMNS + ["max_days"]
OPTIONAL = ["namea", "nameb", "min_days", "median_days"]


def read_quarter(path: Union[str, Path]) -> pd.DataFrame:
    path = Path(path)
    df = pd.read_csv(path, encoding="utf-8-sig")
    df.columns = [str(c).strip().lstrip("\ufeff") for c in df.columns]

    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing required columns {missing}")

    keep = REQUIRED + [c for c in OPTIONAL if c in df.columns]
    df = df[keep].copy()
    for c in ("origin", "destination"):
        df[c] = df[c].astype(str).str.strip()
    for c in LSCI_COLUMNS + ["max_days"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    bad = df[REQUIRED].isna().any(axis=1)
    if bad.any():
        raise ValueError(f"{path.name}: {int(bad.sum())} rows with missing/non-numeric values")
    for c in LSCI_COLUMNS:
        if (df[c] < 0).any():
            raise ValueError(f"{path.name}: column {c} has negative values")
        if df[c].max() <= 0:
            raise ValueError(f"{path.name}: column {c} is all zero")
    # Zeros are legal (20110925.csv has 13 links with weekly_teu = max_vessel = 0, i.e.
    # capacity not recorded).  The senior's code keeps them as 0, so do we; the link still
    # gets LSCI > 0 from its other three statistics.  They are counted in quarter_summary.
    if ((df[LSCI_COLUMNS].sum(axis=1)) <= 0).any():
        raise ValueError(f"{path.name}: link(s) with all five statistics zero")

    n_dup = int(df.duplicated(["origin", "destination"]).sum())
    if n_dup:
        # Same behaviour as the senior's pivot_table (mean of duplicates),
        # but loudly.  Normalisation maxima were taken before this step there too,
        # so we aggregate later, inside QuarterNetwork.
        warnings.warn(f"{path.name}: {n_dup} duplicate (origin,destination) rows; averaging")
    return df.reset_index(drop=True)
