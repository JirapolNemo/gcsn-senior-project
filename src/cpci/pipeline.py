"""Run CPCI (and any registered metric) on every quarter and write tidy CSV outputs.

Outputs in <root>/data/processed/cpci/ (git-ignored):
  scores.csv           one row per (quarter, port): scores, ranks, port_id, name...
  quarter_summary.csv  one row per quarter: sizes, lambda, checks, monotonicity per column
  run_info.json        which metrics / source rules / files produced this run
  links/<q>_lsci.csv   (optional) LSCI + C1..C5 for every link
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from . import metrics as M
from .config import LSCI_COLUMNS, Config, QuarterFile, check_gaps, discover_quarters
from .loader import read_quarter
from .network import QuarterNetwork
from .ports import META_COLUMNS, load_port_id_map, load_ports_reference
from .ranking import monotonicity, rank_desc


def process_quarter(qf: QuarterFile, cfg: Config, metric_names: Optional[List[str]] = None,
                    ref: Optional[pd.DataFrame] = None, id_map: Optional[Dict[str, str]] = None,
                    save_links: bool = False) -> Tuple[pd.DataFrame, dict]:
    t0 = time.time()
    ref = load_ports_reference(cfg) if ref is None else ref
    id_map = load_port_id_map(cfg) if id_map is None else id_map

    raw = read_quarter(qf.path)
    net = QuarterNetwork(raw, quarter=qf.quarter, time_column=cfg.time_column)
    scores = M.compute(net, metric_names)

    out = scores.copy()
    summary = {}
    for col in M.score_columns(metric_names, rank_only=True):
        r = rank_desc(scores[col])
        out["rank_" + col] = r
        summary["mono_" + col] = monotonicity(r)

    out.insert(0, "port_id", [id_map.get(p, p) for p in out.index])
    meta = ref.reindex(out.index)
    for i, c in enumerate(META_COLUMNS):
        out.insert(1 + i, c, meta[c].to_numpy())
    out.insert(0, "date", qf.date.strftime("%Y-%m-%d"))
    out.insert(0, "quarter", qf.quarter)
    out = out.reset_index()  # 'port' column
    out.insert(2, "port", out.pop("port"))

    h = net.hits
    head = {
        "quarter": qf.quarter, "date": qf.date.strftime("%Y-%m-%d"),
        "source_folder": qf.folder, "source_file": qf.path.name,
        "n_ports": net.n, "n_links": net.n_links,
        "links_with_zero_stat": int((raw[LSCI_COLUMNS] == 0).any(axis=1).sum()),
        "lambda1": h.lam, "lambda_gap": h.gap, "decomp_residual": h.residual,
        "ports_not_in_reference": int(sum(p not in ref.index for p in net.ports)),
    }
    for col in ("Inbound", "Outbound"):
        if col in scores.columns:
            head["zero_%s" % col.lower()] = int((scores[col].round(12) == 0).sum())
    head.update(summary)
    head["seconds"] = round(time.time() - t0, 2)

    if save_links:
        d = cfg.out_dir / "links"
        d.mkdir(parents=True, exist_ok=True)
        net.links.to_csv(d / ("%s_lsci.csv" % qf.quarter), index=False)
    return out, head


def _worker(args):
    qf, cfg, names, ref, id_map, save_links = args
    return process_quarter(qf, cfg, names, ref, id_map, save_links)


def run_pipeline(cfg: Optional[Config] = None, metric_names: Optional[List[str]] = None,
                 first: Optional[str] = None, last: Optional[str] = None, jobs: int = 1,
                 save_links: bool = False, verbose: bool = True) -> Dict[str, object]:
    cfg = cfg or Config()
    files = discover_quarters(cfg, first, last)
    if not files:
        raise SystemExit("no quarter files found under %s" % cfg.sources_dir)
    for msg in check_gaps(files):
        print("WARNING:", msg, file=sys.stderr)
    names = metric_names
    M.resolve(names)  # fail early on a typo
    ref, id_map = load_ports_reference(cfg), load_port_id_map(cfg)
    cfg.out_dir.mkdir(parents=True, exist_ok=True)

    if verbose:
        print("%d quarters (%s .. %s), metrics: %s, jobs=%d"
              % (len(files), files[0].quarter, files[-1].quarter,
                 ",".join(names) if names else "all", jobs))
    tasks = [(f, cfg, names, ref, id_map, save_links) for f in files]
    results = []
    t0 = time.time()
    if jobs > 1:
        with ProcessPoolExecutor(max_workers=jobs) as ex:
            for i, res in enumerate(ex.map(_worker, tasks), 1):
                results.append(res)
                if verbose:
                    print("  [%2d/%d] %s done (%.1fs)" % (i, len(files), res[1]["quarter"], res[1]["seconds"]))
    else:
        for i, t in enumerate(tasks, 1):
            res = _worker(t)
            results.append(res)
            if verbose:
                print("  [%2d/%d] %s done (%.1fs)" % (i, len(files), res[1]["quarter"], res[1]["seconds"]))

    scores = pd.concat([r[0] for r in results], ignore_index=True)
    summary = pd.DataFrame([r[1] for r in results])
    p_scores, p_sum = cfg.out_dir / "scores.csv", cfg.out_dir / "quarter_summary.csv"
    scores.to_csv(p_scores, index=False)
    summary.to_csv(p_sum, index=False)
    info = {
        "metrics": [m.name for m in M.resolve(names)],
        "source_rules": cfg.source_rules,
        "time_column": cfg.time_column,
        "quarters": [f.quarter for f in files],
        "numpy": np.__version__, "pandas": pd.__version__,
        "master_ports_loaded": bool(id_map),
        "seconds": round(time.time() - t0, 1),
    }
    (cfg.out_dir / "run_info.json").write_text(json.dumps(info, indent=2, default=str))
    if verbose:
        print("wrote", p_scores, "and", p_sum, "in %.0fs" % (time.time() - t0))
    return {"scores": scores, "summary": summary, "paths": [p_scores, p_sum]}
