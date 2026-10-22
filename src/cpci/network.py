"""One quarter as a weighted directed network (LSCI weights) plus its derived objects.

Formula (Bartholdi et al. 2016, as implemented by the senior's 0.CPCI.ipynb):
  for each of the 5 statistics s_k:  a_k = s_k / max(s_k)           (over all links)
  tot = a_1 + ... + a_5;           LSCI = tot / max(tot)            (in (0,1], max = 1)
  component shares:                c_k  = a_k / max(tot)            (so  sum_k c_k = LSCI)
  L[i, j] = LSCI of link i->j, A_k[i, j] = c_k of link i->j  (0 where no link).
"""
from __future__ import annotations

from functools import cached_property
from typing import List

import numpy as np
import pandas as pd

from .config import LSCI_COLUMNS
from .hits import HitsResult, principal_scores, decompose


class QuarterNetwork:
    def __init__(self, df: pd.DataFrame, quarter: str = "", time_column: str = "max_days"):
        self.quarter = quarter
        self.time_column = time_column
        self.raw = df
        self.links = self._build_links(df, time_column)
        ports = sorted(set(self.links["origin"]) | set(self.links["destination"]))
        self.ports: List[str] = ports
        self.n = len(ports)
        self.index = {p: i for i, p in enumerate(ports)}
        self._oi = self.links["origin"].map(self.index).to_numpy()
        self._di = self.links["destination"].map(self.index).to_numpy()

    # ---- links ---------------------------------------------------------
    @staticmethod
    def _build_links(df: pd.DataFrame, time_column: str) -> pd.DataFrame:
        a = {c: df[c] / df[c].max() for c in LSCI_COLUMNS}
        tot = sum(a.values())
        tmax = tot.max()
        out = pd.DataFrame({"origin": df["origin"], "destination": df["destination"]})
        out["lsci"] = tot / tmax
        for k, c in enumerate(LSCI_COLUMNS, start=1):
            out["c%d" % k] = a[c] / tmax
        out["time"] = df[time_column].astype(float)
        if out.duplicated(["origin", "destination"]).any():
            out = out.groupby(["origin", "destination"], as_index=False, sort=True).mean()
        return out.sort_values(["origin", "destination"]).reset_index(drop=True)

    @property
    def n_links(self) -> int:
        return len(self.links)

    def _matrix(self, col: str) -> np.ndarray:
        m = np.zeros((self.n, self.n))
        m[self._oi, self._di] = self.links[col].to_numpy()
        return m

    # ---- matrices ------------------------------------------------------
    @cached_property
    def L(self) -> np.ndarray:
        """LSCI matrix, rows = origin, columns = destination, ports sorted by code."""
        return self._matrix("lsci")

    @cached_property
    def A(self) -> List[np.ndarray]:
        """Component matrices A_1..A_5 (they sum to L)."""
        return [self._matrix("c%d" % k) for k in range(1, len(LSCI_COLUMNS) + 1)]

    @cached_property
    def adjacency(self) -> np.ndarray:
        """Binary adjacency (1 where a link exists)."""
        return (self.L > 0).astype(np.int8)

    # ---- HITS / CPCI ---------------------------------------------------
    @cached_property
    def hits(self) -> HitsResult:
        res = principal_scores(self.L)
        res.in_components, res.out_components = decompose(self.A, res.hub, res.auth, res.lam)
        return res

    # ---- graph (networkx) ---------------------------------------------
    @cached_property
    def graph(self):
        import networkx as nx
        G = nx.DiGraph()
        G.add_nodes_from(self.ports)  # keeps isolated ports and a fixed node order
        G.add_edges_from(
            zip(self.links["origin"], self.links["destination"]))
        # edge length keyed by (origin, destination), NOT by row position
        nx.set_edge_attributes(
            G,
            {(o, d): t for o, d, t in zip(self.links["origin"], self.links["destination"], self.links["time"])},
            name="time",
        )
        return G
