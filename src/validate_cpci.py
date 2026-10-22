"""Validate the new CPCI pipeline.

  python3 src/validate_cpci.py legacy             # new code vs a transcription of the senior's notebook
  python3 src/validate_cpci.py legacy --metrics cpci,degree --first 20110925 --last 20120930
  python3 src/validate_cpci.py senior --senior-dir <folder with the senior's Results/ output>

`legacy` needs only the data and shows whether the new code reproduces the notebook's logic
(and where the notebook's assumptions break).  `senior` compares with the senior's saved
Excel outputs (2.Inbound/*.xlsx, 3.Outbound/*.xlsx, 6.Centrality/...), the final check.
Reports are written to data/qa/.
"""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpci import Config, QuarterNetwork, discover_quarters, read_quarter  # noqa: E402
from cpci import metrics as M  # noqa: E402
from cpci.legacy_senior import legacy_quarter  # noqa: E402
from cpci.ranking import rank_desc  # noqa: E402

TOP_K = 20


def compare_frames(new: pd.DataFrame, old: pd.DataFrame, cols) -> list:
    """Per-column comparison of two score tables indexed by port code."""
    rows = []
    for c in cols:
        if c not in new.columns or c not in old.columns:
            continue
        a, b = new[c], old[c]
        common = a.index.intersection(b.index)
        only_new, only_old = len(a.index.difference(b.index)), len(b.index.difference(a.index))
        x, y = a.loc[common].astype(float), b.loc[common].astype(float)
        scale = max(float(np.abs(y).max()), 1e-12)
        diff = float(np.abs(x - y).max()) if len(common) else float("nan")
        rx = rank_desc(x)
        ry = rank_desc(y)
        # tau on the (tie-safe) ranks, so 1e-66 vs exactly 0 does not count as a disagreement
        tau = kendalltau(rx, ry)[0] if len(common) > 2 else float("nan")
        top_x = set(rx[rx <= TOP_K].index)
        top_y = set(ry[ry <= TOP_K].index)
        rows.append({
            "column": c, "n_common": len(common), "only_new": only_new, "only_old": only_old,
            "max_abs_diff": diff, "max_rel_diff": diff / scale, "kendall_tau": tau,
            "rank_equal_share": float((rx == ry).mean()) if len(common) else float("nan"),
            "top%d_overlap" % TOP_K: len(top_x & top_y) / float(max(len(top_x), len(top_y), 1)),
        })
    return rows


def run_legacy(cfg: Config, names, first, last, out_dir: Path):
    files = [f for f in discover_quarters(cfg, first, last) if f.folder == cfg.source_rules[0][0]]
    names = names or list(M.available_metrics())
    new_ok = [n for n in names if n in {"cpci", "degree", "closeness", "betweenness_link", "betweenness_time"}]
    rows, flag_rows = [], []
    for i, f in enumerate(files, 1):
        df = read_quarter(f.path)
        net = QuarterNetwork(df, f.quarter, cfg.time_column)
        new = M.compute(net, new_ok)
        old_scores, flags = legacy_quarter(df, include=new_ok)
        old = pd.concat(old_scores.values(), axis=1)
        for r in compare_frames(new, old, list(new.columns)):
            r["quarter"] = f.quarter
            rows.append(r)
        flags["quarter"] = f.quarter
        flag_rows.append(flags)
        print("  [%2d/%d] %s compared" % (i, len(files), f.quarter), flush=True)
    res, fl = pd.DataFrame(rows), pd.DataFrame(flag_rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    res.to_csv(out_dir / "cpci_validation_legacy.csv", index=False)
    fl.to_csv(out_dir / "cpci_validation_legacy_flags.csv", index=False)
    return res, fl


def summarize(res: pd.DataFrame) -> pd.DataFrame:
    g = res.groupby("column", sort=False)
    return pd.DataFrame({
        "worst_rel_diff": g["max_rel_diff"].max(),
        "worst_kendall_tau": g["kendall_tau"].min(),
        "worst_rank_equal_share": g["rank_equal_share"].min(),
        "worst_top%d_overlap" % TOP_K: g["top%d_overlap" % TOP_K].min(),
        "quarters": g["quarter"].nunique(),
    })


# ---- comparison with the senior's saved Excel outputs -------------------------------
# (sub-folder, file pattern, {column in senior's file -> our column})
SENIOR_FILES = [
    ("2.Inbound", "{q}_inbound.xlsx", {"Inbound": "Inbound", **{"C%d_i" % k: "C%d_i" % k for k in range(1, 6)}}),
    ("3.Outbound", "{q}_outbound.xlsx", {"Outbound": "Outbound", **{"C%d_o" % k: "C%d_o" % k for k in range(1, 6)}}),
    ("6.Centrality/d.Degree", "{q}_degree.xlsx", {"Degree": "Degree"}),
    ("6.Centrality/e.Indegree", "{q}_indegree.xlsx", {"In Degree": "InDegree"}),
    ("6.Centrality/f.Outdegree", "{q}_outdegree.xlsx", {"Out Degree": "OutDegree"}),
    ("6.Centrality/i.Closefrom", "{q}_closefrom.xlsx", {"ClosenessFrom": "ClosenessFrom"}),
    ("6.Centrality/j.Closeto", "{q}_closeto.xlsx", {"ClosenessTo": "ClosenessTo"}),
    ("6.Centrality/m.Betweenlink", "{q}_btwlink.xlsx", {"BetweennessLink": "BetweennessLink"}),
    ("6.Centrality/n.Betweentime", "{q}_btwtime.xlsx", {"BetweennessTime": "BetweennessTime"}),
]


def read_senior_table(path: Path, q: str, mapping) -> pd.DataFrame:
    df = pd.read_excel(path)
    df.columns = [c if c == "UNLOCODE" else (c[: -(len(q) + 1)] if c.endswith("_" + q) else c)
                  for c in df.columns]
    df = df.set_index("UNLOCODE")
    return df.rename(columns=mapping)[[v for v in mapping.values() if v in df.rename(columns=mapping).columns]]


def run_senior(cfg: Config, senior_dir: Path, names, first, last, out_dir: Path):
    files = [f for f in discover_quarters(cfg, first, last) if f.folder == cfg.source_rules[0][0]]
    rows, missing = [], []
    for f in files:
        net = None
        for sub, pat, mapping in SENIOR_FILES:
            p = senior_dir / sub / pat.format(q=f.quarter)
            if not p.exists():
                missing.append(str(p))
                continue
            if net is None:
                net = QuarterNetwork(read_quarter(f.path), f.quarter, cfg.time_column)
                mine = M.compute(net, names)
            old = read_senior_table(p, f.quarter, mapping)
            for r in compare_frames(mine, old, list(old.columns)):
                r["quarter"] = f.quarter
                rows.append(r)
        print("  %s compared" % f.quarter, flush=True)
    res = pd.DataFrame(rows)
    out_dir.mkdir(parents=True, exist_ok=True)
    if len(res):
        res.to_csv(out_dir / "cpci_validation_senior.csv", index=False)
    return res, missing


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["legacy", "senior"])
    ap.add_argument("--senior-dir", help="folder that contains 2.Inbound, 3.Outbound, 6.Centrality ...")
    ap.add_argument("--metrics", help="comma separated metric names (default: all)")
    ap.add_argument("--first")
    ap.add_argument("--last")
    ap.add_argument("--root")
    a = ap.parse_args()
    cfg = Config(root=Path(a.root)) if a.root else Config()
    names = [s.strip() for s in a.metrics.split(",")] if a.metrics else None
    pd.set_option("display.width", 200)

    if a.mode == "legacy":
        res, fl = run_legacy(cfg, names, a.first, a.last, cfg.qa_dir)
        print("\nWorst case over quarters (new pipeline vs notebook logic):")
        print(summarize(res).to_string(float_format=lambda v: "%.3g" % v))
        print("\nNotebook assumptions, number of quarters where each holds:")
        for c in fl.columns.drop("quarter"):
            print("  %-40s %d / %d" % (c, int(fl[c].sum()), int(fl[c].notna().sum())))
    else:
        if not a.senior_dir:
            ap.error("--senior-dir is required for mode 'senior'")
        res, missing = run_senior(cfg, Path(a.senior_dir), names, a.first, a.last, cfg.qa_dir)
        if len(res):
            print("\nWorst case over quarters (new pipeline vs senior's saved results):")
            print(summarize(res).to_string(float_format=lambda v: "%.3g" % v))
        if missing:
            print("\n%d expected senior files not found, e.g.:" % len(missing))
            for m in missing[:5]:
                print("  ", m)


if __name__ == "__main__":
    main()
