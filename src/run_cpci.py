"""Command line entry point.  Run from the repository root:

    python3 src/run_cpci.py                         # all quarters, all metrics
    python3 src/run_cpci.py --metrics cpci,degree   # only the fast ones
    python3 src/run_cpci.py --first 20110925 --last 20170924
    python3 src/run_cpci.py --jobs 4                # use 4 CPU cores
    python3 src/run_cpci.py --list-metrics
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from cpci import Config, available_metrics, run_pipeline  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metrics", help="comma separated metric names (default: all)")
    ap.add_argument("--first", help="first quarter YYYYMMDD")
    ap.add_argument("--last", help="last quarter YYYYMMDD")
    ap.add_argument("--jobs", type=int, default=1, help="parallel processes (default 1)")
    ap.add_argument("--save-links", action="store_true", help="also write per-quarter LSCI link tables")
    ap.add_argument("--root", help="repo root (default: auto)")
    ap.add_argument("--list-metrics", action="store_true")
    a = ap.parse_args()

    if a.list_metrics:
        for m in available_metrics().values():
            print("%-18s %-10s %s%s" % (m.name, m.group, m.description, "  [slow]" if m.heavy else ""))
        return
    cfg = Config(root=Path(a.root)) if a.root else Config()
    names = [s.strip() for s in a.metrics.split(",")] if a.metrics else None
    run_pipeline(cfg, names, a.first, a.last, a.jobs, a.save_links)


if __name__ == "__main__":
    main()
