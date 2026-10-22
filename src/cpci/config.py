"""Paths and source-selection rules.

Everything is relative to the repository root, so the project runs the same on
any machine (no C:\\... paths).  The root is found from this file's location
(<root>/src/cpci/config.py); set the environment variable GCSN_ROOT to override.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

# (folder under data/sources, first quarter, last quarter or None = open ended)
# Decision (2026-10): 2011-2017 up to 20170924, then 2017-2026 from 20171231.
# The 2015-2023 folder is NOT used: it duplicates both of the others and uses
# the new port codes for 2015-2017 (see data/qa/source_decisions.md).
DEFAULT_SOURCE_RULES: List[Tuple[str, str, Optional[str]]] = [
    ("Dataset (2011-2017)", "20110925", "20170924"),
    ("Dataset (2017-2026)", "20171231", None),
]

# The five LSCI statistics, in the order that defines components C1..C5.
LSCI_COLUMNS = [
    "distinct_services",  # C1  number of liner services calling
    "num_companies",      # C2  number of liner companies
    "num_vessels",        # C3  number of ships
    "weekly_teu",         # C4  combined capacity (TEU)
    "max_vessel",         # C5  largest ship calling
]

QUARTER_RE = re.compile(r"^(\d{8})\.csv$")


def _default_root() -> Path:
    env = os.environ.get("GCSN_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


@dataclass
class Config:
    root: Path = field(default_factory=_default_root)
    source_rules: List[Tuple[str, str, Optional[str]]] = field(
        default_factory=lambda: list(DEFAULT_SOURCE_RULES))
    # Which column is the edge length for time-weighted betweenness.
    time_column: str = "max_days"

    def __post_init__(self):
        self.root = Path(self.root)

    # ---- folders -------------------------------------------------------
    @property
    def sources_dir(self) -> Path:
        return self.root / "data" / "sources"

    @property
    def reference_dir(self) -> Path:
        return self.root / "data" / "reference"

    @property
    def qa_dir(self) -> Path:
        return self.root / "data" / "qa"

    @property
    def out_dir(self) -> Path:
        return self.root / "data" / "processed" / "cpci"


@dataclass(frozen=True)
class QuarterFile:
    quarter: str          # "YYYYMMDD" taken from the file name
    path: Path
    folder: str           # source folder name, e.g. "2017-2026"

    @property
    def date(self) -> datetime:
        return datetime.strptime(self.quarter, "%Y%m%d")


def discover_quarters(cfg: Config, first: Optional[str] = None,
                      last: Optional[str] = None) -> List[QuarterFile]:
    """One file per quarter, chosen by cfg.source_rules.  Raises on overlaps."""
    found = {}
    for folder, lo, hi in cfg.source_rules:
        d = cfg.sources_dir / folder
        if not d.is_dir():
            raise FileNotFoundError(f"source folder not found: {d}")
        for p in sorted(d.iterdir()):
            m = QUARTER_RE.match(p.name)
            if not m:
                continue
            q = m.group(1)
            if q < lo or (hi is not None and q > hi):
                continue
            if q in found:
                raise ValueError(
                    f"quarter {q} selected from two folders: "
                    f"{found[q].folder} and {folder}; fix source_rules")
            found[q] = QuarterFile(q, p, folder)
    out = [found[q] for q in sorted(found)]
    if first:
        out = [f for f in out if f.quarter >= first]
    if last:
        out = [f for f in out if f.quarter <= last]
    return out


def check_gaps(files: List[QuarterFile], max_gap_days: int = 105) -> List[str]:
    """Human-readable warnings for missing quarters (gap much longer than ~91 days)."""
    msgs = []
    for a, b in zip(files, files[1:]):
        gap = (b.date - a.date).days
        if gap > max_gap_days:
            msgs.append(f"gap of {gap} days between {a.quarter} and {b.quarter}")
    return msgs
