"""Ranks and the 'monotonicity' tie measure used by the senior's notebook."""
from __future__ import annotations

import numpy as np
import pandas as pd


RANK_DECIMALS = 12


def rank_desc(values: pd.Series, decimals: int = RANK_DECIMALS) -> pd.Series:
    """Rank 1 = highest score; ties share the best (minimum) rank.

    Scores are rounded to `decimals` places first so that floating-point noise
    (e.g. 1e-66 instead of exactly 0 for ports outside the dominant component) cannot
    break a genuine tie, which would make ranks differ between machines/BLAS builds.
    """
    return values.round(decimals).rank(ascending=False, method="min").astype(int)


def monotonicity(ranks: pd.Series) -> float:
    """(1 - sum_g m_g (m_g - 1) / (n (n - 1)))^2 over groups g of tied ranks.

    1.0 = all ranks distinct, 0.0 = everything tied.
    """
    n = len(ranks)
    if n < 2:
        return 1.0
    sizes = ranks.value_counts().to_numpy(dtype=float)
    return float((1.0 - (sizes * (sizes - 1)).sum() / (n * (n - 1))) ** 2)
