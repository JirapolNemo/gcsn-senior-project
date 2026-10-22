"""Port reference data and the master_ports code -> stable port_id mapping."""
from __future__ import annotations

import warnings
from typing import Dict

import pandas as pd

from .config import Config

META_COLUMNS = ["name", "country", "region"]


def load_ports_reference(cfg: Config) -> pd.DataFrame:
    """DataFrame indexed by UN/LOCODE with columns name/country/region (may be empty).

    Looks for data/reference/ports.csv (name,code,country,subregion,region,lat,lon) and
    falls back to ports_details.csv (Portname,UNLOCODE,Country,subregion,region,...).
    """
    d = cfg.reference_dir
    p1, p2 = d / "ports.csv", d / "ports_details.csv"
    if p1.exists():
        df = pd.read_csv(p1, encoding="utf-8-sig")
        df = df.rename(columns={"code": "code", "name": "name"})
    elif p2.exists():
        df = pd.read_csv(p2, encoding="utf-8-sig").rename(
            columns={"UNLOCODE": "code", "Portname": "name", "Country": "country"})
    else:
        warnings.warn("no ports reference file in %s; port names will be blank" % d)
        return pd.DataFrame(columns=META_COLUMNS)
    df["code"] = df["code"].astype(str).str.strip()
    df = df.drop_duplicates("code").set_index("code")
    for c in META_COLUMNS:
        if c not in df.columns:
            df[c] = None
    return df[META_COLUMNS]


def load_port_id_map(cfg: Config) -> Dict[str, str]:
    """code -> stable port_id from data/reference/master_ports.csv.

    Expected: a `port_id` column plus one or more of `old_code`, `new_code`, `code`,
    `current_code` (every non-empty value is mapped to that port_id).  Codes that are not
    listed map to themselves (port_id = code).  Missing file -> identity mapping.
    """
    p = cfg.reference_dir / "master_ports.csv"
    if not p.exists():
        return {}
    df = pd.read_csv(p, encoding="utf-8-sig")
    low = {c.lower().strip(): c for c in df.columns}
    if "port_id" not in low:
        warnings.warn("master_ports.csv has no port_id column; ignoring it")
        return {}
    code_cols = [low[c] for c in ("old_code", "new_code", "code", "current_code") if c in low]
    if not code_cols:
        warnings.warn("master_ports.csv has no code column (old_code/new_code/code); ignoring it")
        return {}
    mapping: Dict[str, str] = {}
    for _, row in df.iterrows():
        pid = str(row[low["port_id"]]).strip()
        for c in code_cols:
            v = row[c]
            if isinstance(v, str) and v.strip():
                mapping[v.strip()] = pid
    return mapping
