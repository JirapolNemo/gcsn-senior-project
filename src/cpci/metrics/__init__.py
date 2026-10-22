"""Metric registry: add a new indicator by dropping a decorated function in this folder.

    # src/cpci/metrics/my_metric.py
    from . import metric

    @metric("pagerank", columns=["PageRank"], group="centrality",
            description="PageRank on the LSCI-weighted graph")
    def pagerank(net):                      # net is a cpci.network.QuarterNetwork
        import networkx as nx
        G = net.graph
        pr = nx.pagerank(G)
        return {"PageRank": [pr[p] for p in net.ports]}   # one value per net.ports, in order

A metric function receives a QuarterNetwork and returns either a dict {column: values}
(values aligned to net.ports) or a DataFrame indexed by port code.  Every returned column
must be declared in `columns`; column names must be unique across all metrics.  Higher
score = more important (ranks are computed 1 = highest).  Nothing else needs editing:
files in this folder are discovered automatically and run by `python3 src/run_cpci.py`.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

import numpy as np
import pandas as pd


@dataclass
class Metric:
    name: str
    func: Callable
    columns: List[str]
    group: str = ""
    description: str = ""
    heavy: bool = False   # slow (e.g. betweenness); shown by `run_cpci.py --list-metrics`
    rank: bool = True     # add rank_<column> columns


REGISTRY: Dict[str, Metric] = {}
_COLUMN_OWNER: Dict[str, str] = {}
_discovered = False


def metric(name: str, columns: List[str], group: str = "", description: str = "",
           heavy: bool = False, rank: bool = True):
    def deco(fn: Callable):
        if name in REGISTRY and REGISTRY[name].func is not fn:
            raise ValueError("metric %r already registered" % name)
        for c in columns:
            owner = _COLUMN_OWNER.get(c)
            if owner is not None and owner != name:
                raise ValueError("column %r already produced by metric %r" % (c, owner))
            _COLUMN_OWNER[c] = name
        REGISTRY[name] = Metric(name, fn, list(columns), group, description, heavy, rank)
        return fn
    return deco


def _discover() -> None:
    global _discovered
    if _discovered:
        return
    for mod in pkgutil.iter_modules(__path__):  # type: ignore[name-defined]
        importlib.import_module("%s.%s" % (__name__, mod.name))
    _discovered = True


def available_metrics() -> Dict[str, Metric]:
    _discover()
    return dict(REGISTRY)


def resolve(names: Optional[List[str]]) -> List[Metric]:
    reg = available_metrics()
    if not names:
        return list(reg.values())
    unknown = [n for n in names if n not in reg]
    if unknown:
        raise KeyError("unknown metric(s) %s; available: %s" % (unknown, sorted(reg)))
    return [reg[n] for n in names]


def compute(net, names: Optional[List[str]] = None) -> pd.DataFrame:
    """Run metrics on one QuarterNetwork -> DataFrame indexed by port code."""
    frames = []
    for m in resolve(names):
        out = m.func(net)
        if isinstance(out, pd.DataFrame):
            df = out.reindex(net.ports)
        else:
            df = pd.DataFrame({k: np.asarray(v, dtype=float) for k, v in dict(out).items()},
                              index=net.ports)
        if set(df.columns) != set(m.columns):
            raise ValueError("metric %r returned columns %s, declared %s"
                             % (m.name, list(df.columns), m.columns))
        if len(df) != net.n:
            raise ValueError("metric %r returned %d rows, expected %d" % (m.name, len(df), net.n))
        frames.append(df[m.columns])
    res = pd.concat(frames, axis=1)
    res.index.name = "port"
    return res


def score_columns(names: Optional[List[str]] = None, rank_only: bool = False) -> List[str]:
    cols: List[str] = []
    for m in resolve(names):
        if rank_only and not m.rank:
            continue
        cols.extend(m.columns)
    return cols
