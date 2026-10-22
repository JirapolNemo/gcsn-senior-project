"""CPCI = principal singular pair of the LSCI matrix (Eqs. 6-9 of Jarumaneeroj et al.).

   lambda * x = L^T y      (x = inbound score,  authority)
   lambda * y = L   x      (y = outbound score, hub)

We take the top singular triplet of L with an SVD, which gives x, y and lambda
already paired (the senior used two separate np.linalg.eig calls and *assumed*
that the dominant eigenvalue comes out first, which np.linalg.eig does not
guarantee).  For a non-negative matrix the top vectors are non-negative, so we
take abs() like the original.  Vectors have unit length.

Decomposition (Eqs. 8-9): with L = sum_k A_k,
   inbound_k  = A_k^T y / lambda,        outbound_k = A_k x / lambda,
and  sum_k inbound_k = x,  sum_k outbound_k = y  (checked in `residual`).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

import numpy as np


@dataclass
class HitsResult:
    hub: np.ndarray            # outbound score y (unit length)
    auth: np.ndarray           # inbound score  x (unit length)
    lam: float                 # principal singular value (carries the absolute magnitude)
    gap: float                 # (s1 - s2) / s1, small gap => dominant pair not unique
    in_components: Optional[np.ndarray] = field(default=None, repr=False)   # (K, n)
    out_components: Optional[np.ndarray] = field(default=None, repr=False)  # (K, n)

    @property
    def residual(self) -> float:
        """max |sum of components - score|; ~1e-15 if the decomposition is exact."""
        if self.in_components is None:
            return float("nan")
        r_in = np.abs(self.in_components.sum(axis=0) - self.auth).max()
        r_out = np.abs(self.out_components.sum(axis=0) - self.hub).max()
        return float(max(r_in, r_out))


def principal_scores(L: np.ndarray) -> HitsResult:
    if L.size == 0 or not np.any(L):
        raise ValueError("empty LSCI matrix")
    U, s, Vt = np.linalg.svd(L, full_matrices=False)
    hub = np.abs(U[:, 0])
    auth = np.abs(Vt[0])
    gap = float((s[0] - s[1]) / s[0]) if len(s) > 1 else 1.0
    return HitsResult(hub=hub, auth=auth, lam=float(s[0]), gap=gap)


def decompose(A: List[np.ndarray], hub: np.ndarray, auth: np.ndarray,
              lam: float) -> Tuple[np.ndarray, np.ndarray]:
    inc = np.vstack([Ak.T @ hub / lam for Ak in A])
    out = np.vstack([Ak @ auth / lam for Ak in A])
    return inc, out
