"""Classical centralities used for comparison with CPCI (degree, closeness, betweenness)."""
import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import shortest_path

from . import metric


@metric("degree", columns=["Degree", "InDegree", "OutDegree"], group="centrality",
        description="number of links (Degree = in + out, a reciprocal pair counts twice)")
def degree(net):
    a = net.adjacency
    out = a.sum(axis=1)
    inn = a.sum(axis=0)
    return {"Degree": inn + out, "InDegree": inn, "OutDegree": out}


def _closeness(dist: np.ndarray, axis: int) -> np.ndarray:
    """Wasserman-Faust closeness (networkx default).  axis=1: distances *from* each node,
    axis=0: distances *to* each node."""
    n = dist.shape[0]
    d = dist.copy()
    np.fill_diagonal(d, np.nan)
    d[np.isinf(d)] = np.nan
    reach = np.sum(~np.isnan(d), axis=axis).astype(float)
    tot = np.nansum(d, axis=axis)
    with np.errstate(divide="ignore", invalid="ignore"):
        c = np.where(tot > 0, (reach / tot) * (reach / (n - 1)), 0.0)
    return c


@metric("closeness", columns=["ClosenessFrom", "ClosenessTo"], group="centrality",
        description="hop-count closeness: From = outgoing distances, To = incoming distances")
def closeness(net):
    sp = shortest_path(csr_matrix(net.adjacency), directed=True, unweighted=True)
    return {"ClosenessFrom": _closeness(sp, axis=1), "ClosenessTo": _closeness(sp, axis=0)}


@metric("betweenness_link", columns=["BetweennessLink"], group="centrality", heavy=True,
        description="betweenness, shortest paths by number of links (unnormalised)")
def betweenness_link(net):
    import networkx as nx
    b = nx.betweenness_centrality(net.graph, normalized=False)
    return {"BetweennessLink": [b[p] for p in net.ports]}


@metric("betweenness_time", columns=["BetweennessTime"], group="centrality", heavy=True,
        description="betweenness, shortest paths by transit time (edge length = cfg.time_column, "
                    "matched to links by (origin,destination))")
def betweenness_time(net):
    import networkx as nx
    b = nx.betweenness_centrality(net.graph, weight="time", normalized=False)
    return {"BetweennessTime": [b[p] for p in net.ports]}
