"""CPCI pipeline for the GCSN senior project.

Typical use from a notebook (run from the repo root):

    import sys; sys.path.insert(0, "src")
    from cpci import Config, run_pipeline
    run_pipeline(Config())

See docs/CPCI_PIPELINE.md for the full guide.
"""
from .config import Config, QuarterFile, discover_quarters
from .loader import read_quarter
from .network import QuarterNetwork
from .pipeline import process_quarter, run_pipeline
from .metrics import metric, available_metrics

__all__ = [
    "Config", "QuarterFile", "discover_quarters", "read_quarter", "QuarterNetwork",
    "process_quarter", "run_pipeline", "metric", "available_metrics",
]
