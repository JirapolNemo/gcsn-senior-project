"""Unit tests on small synthetic networks.  Run:  python3 tests/test_cpci.py   (or pytest)."""
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from cpci import Config, QuarterNetwork, discover_quarters, metric, read_quarter  # noqa: E402
from cpci import metrics as M  # noqa: E402
from cpci.ranking import monotonicity, rank_desc  # noqa: E402


def toy(n=6, seed=0):
    rng = np.random.default_rng(seed)
    ports = ["P%d" % i for i in range(n)]
    rows = []
    for o in ports:
        for d in ports:
            if o != d and rng.random() < 0.7:
                rows.append(dict(origin=o, destination=d,
                                 distinct_services=int(rng.integers(1, 9)), num_companies=int(rng.integers(1, 5)),
                                 num_vessels=int(rng.integers(1, 20)), weekly_teu=float(rng.integers(100, 9000)),
                                 max_vessel=int(rng.integers(500, 20000)), max_days=int(rng.integers(0, 15))))
    return pd.DataFrame(rows)


def test_lsci_and_components_sum():
    net = QuarterNetwork(toy())
    assert abs(net.links["lsci"].max() - 1.0) < 1e-12
    comp = net.links[["c1", "c2", "c3", "c4", "c5"]].sum(axis=1)
    assert np.allclose(comp, net.links["lsci"])
    assert np.allclose(sum(net.A), net.L)


def test_cpci_equations_and_decomposition():
    net = QuarterNetwork(toy(12))
    h = net.hits
    # lambda x = L^T y ,  lambda y = L x
    assert np.allclose(h.lam * h.auth, net.L.T @ h.hub)
    assert np.allclose(h.lam * h.hub, net.L @ h.auth)
    assert abs(np.linalg.norm(h.auth) - 1) < 1e-12 and abs(np.linalg.norm(h.hub) - 1) < 1e-12
    assert h.residual < 1e-12                      # components add back to the score
    assert abs(h.lam - np.sqrt(np.linalg.eigvalsh(net.L @ net.L.T).max())) < 1e-10


def test_ranks_and_monotonicity():
    s = pd.Series([0.5, 0.5, 0.1, 0.9])
    assert list(rank_desc(s)) == [2, 2, 4, 1]
    assert monotonicity(pd.Series([1, 2, 3, 4])) == 1.0
    assert monotonicity(pd.Series([1, 1, 1, 1])) == 0.0
    # one tied pair among 4: (1 - 2/12)^2
    assert abs(monotonicity(rank_desc(s)) - (1 - 2 / 12) ** 2) < 1e-12
    # float noise must not break a tie
    assert rank_desc(pd.Series([0.0, 1e-66, 0.3]))[0] == rank_desc(pd.Series([0.0, 1e-66, 0.3]))[1] == 2


def test_closeness_matches_networkx_and_edge_times_by_key():
    import networkx as nx
    df = toy(10, seed=3).sample(frac=1.0, random_state=1)  # shuffled rows: positions must not matter
    net = QuarterNetwork(df)
    G = nx.DiGraph(net.graph)
    mine = M.compute(net, ["closeness"])
    assert np.allclose(mine["ClosenessTo"], [nx.closeness_centrality(G)[p] for p in net.ports])
    assert np.allclose(mine["ClosenessFrom"], [nx.closeness_centrality(G.reverse())[p] for p in net.ports])
    for _, r in df.iterrows():
        assert net.graph[r.origin][r.destination]["time"] == r.max_days


def test_all_builtin_metrics_run_and_columns_unique():
    net = QuarterNetwork(toy(8))
    out = M.compute(net)
    assert len(out) == net.n and out.columns.is_unique and not out.isna().any().any()
    assert {"Inbound", "Outbound", "Degree", "ClosenessTo", "BetweennessLink", "BetweennessTime"} <= set(out.columns)


def test_registry_accepts_new_metric_and_rejects_duplicates():
    @metric("test_total_lsci", columns=["TotalLSCI_test"], group="test")
    def total(net):
        return {"TotalLSCI_test": net.L.sum(axis=0) + net.L.sum(axis=1)}

    net = QuarterNetwork(toy())
    out = M.compute(net, ["test_total_lsci"])
    assert np.allclose(out["TotalLSCI_test"], net.L.sum(axis=0) + net.L.sum(axis=1))
    try:
        @metric("another", columns=["TotalLSCI_test"])
        def dup(net):
            return {}
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate column name must be rejected")
    M.REGISTRY.pop("test_total_lsci", None)
    M._COLUMN_OWNER.pop("TotalLSCI_test", None)


def test_loader_handles_bom_and_missing_optional_columns():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "20110925.csv"
        df = toy()
        df["min_days"] = 1
        df.rename(columns={"origin": "﻿origin"}).to_csv(p, index=False, encoding="utf-8")
        out = read_quarter(p)
        assert "origin" in out.columns and len(out) == len(df)


def test_source_rules_one_file_per_quarter_and_overlap_error():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for folder, qs in [("2011-2017", ["20170625", "20170924"]), ("2017-2026", ["20170924", "20171231"])]:
            (root / "data" / "sources" / folder).mkdir(parents=True)
            for q in qs:
                toy().to_csv(root / "data" / "sources" / folder / (q + ".csv"), index=False)
        cfg = Config(root=root)
        cfg.source_rules = [("2011-2017", "20110925", "20170924"), ("2017-2026", "20171231", None)]
        got = [(f.quarter, f.folder) for f in discover_quarters(cfg)]
        # 20170924 exists in both folders but the rule picks it only from 2011-2017
        assert got == [("20170625", "2011-2017"), ("20170924", "2011-2017"), ("20171231", "2017-2026")]
        cfg.source_rules = [("2011-2017", "20110925", None), ("2017-2026", "20170924", None)]
        try:
            discover_quarters(cfg)
        except ValueError:
            pass
        else:
            raise AssertionError("overlapping rules must raise")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print("ok  ", fn.__name__)
    print("%d tests passed" % len(fns))
