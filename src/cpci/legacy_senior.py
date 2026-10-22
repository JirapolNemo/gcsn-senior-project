"""In-memory transcription of the senior's 0.CPCI.ipynb, used ONLY to validate the new code.

It deliberately keeps the notebook's way of working (np.linalg.eig + "take column 0",
labels from df['origin'].unique(), edge times assigned by position in G.edges()) so that
differences between this and the new pipeline point at real problems in either one.
Nothing is written to disk and there are no machine-specific paths.

legacy_quarter(df) returns (scores, flags):
  scores : {metric_name: DataFrame indexed by port code}  (same column names as the new pipeline)
  flags  : dict of diagnostics about the notebook's assumptions for this file
"""
from __future__ import annotations

import copy
import math
from typing import Dict, Iterable, Tuple

import numpy as np
import pandas as pd

ALL = ("cpci", "degree", "closeness", "betweenness_link", "betweenness_time")


def legacy_quarter(df: pd.DataFrame, include: Iterable[str] = ALL) -> Tuple[Dict[str, pd.DataFrame], dict]:
    include = set(include)
    df = df.copy()
    flags: dict = {}
    scores: Dict[str, pd.DataFrame] = {}

    df_a = df['distinct_services'] / max(df['distinct_services'])
    df_b = df['num_companies'] / max(df['num_companies'])
    df_c = df['num_vessels'] / max(df['num_vessels'])
    df_d = df['weekly_teu'] / max(df['weekly_teu'])
    df_e = df['max_vessel'] / max(df['max_vessel'])
    tot_ele = (df_a + df_b + df_c + df_d + df_e)
    lsci = tot_ele / max(tot_ele)

    w = pd.DataFrame({
        'origin': df['origin'], 'destination': df['destination'], 'LSCI': lsci,
        'num_services': df_a / max(tot_ele), 'num_companies': df_b / max(tot_ele),
        'num_vessels': df_c / max(tot_ele), 'weekly_teu': df_d / max(tot_ele),
        'max_vessel': df_e / max(tot_ele)})
    w = w.sort_values('LSCI', axis=0, ascending=False, kind='mergesort')

    port = df['origin'].unique()

    def pivot(col):
        m = pd.pivot_table(w, values=col, index='origin', columns='destination')
        m.fillna(0, inplace=True)
        return m

    matrix = pivot('LSCI')
    A1, A2, A3, A4, A5 = (pivot(c) for c in
                          ['num_services', 'num_companies', 'num_vessels', 'weekly_teu', 'max_vessel'])
    flags['square_same_order'] = bool(list(matrix.index) == list(matrix.columns))
    flags['labels_match_pivot_order'] = bool(list(port) == list(matrix.index))

    if 'cpci' in include:
        hub, V5 = np.linalg.eig(matrix @ matrix.T)
        aut, V6 = np.linalg.eig(matrix.T @ matrix)
        hub_abs, aut_abs = np.abs(hub), np.abs(aut)
        flags['eig_hub_first_is_max'] = bool(hub_abs[0] >= hub_abs.max() * (1 - 1e-12))
        flags['eig_aut_first_is_max'] = bool(aut_abs[0] >= aut_abs.max() * (1 - 1e-12))
        ld = math.sqrt(pd.DataFrame(abs(hub)).iloc[0, 0])
        autscore = abs(pd.DataFrame(V6)[0])
        hubscore = abs(pd.DataFrame(V5)[0])

        auts = pd.DataFrame({'UNLOCODE': port})
        auts['Inbound'] = autscore
        for k, A in enumerate([A1, A2, A3, A4, A5], start=1):
            auts['C%d_i' % k] = pd.DataFrame(np.dot(A.T, hubscore) * (1 / ld))[0]
        hubs = pd.DataFrame({'UNLOCODE': port})
        hubs['Outbound'] = hubscore
        for k, A in enumerate([A1, A2, A3, A4, A5], start=1):
            hubs['C%d_o' % k] = pd.DataFrame(np.dot(autscore, A.T) * (1 / ld))[0]
        scores['cpci'] = pd.concat([auts.set_index('UNLOCODE'), hubs.set_index('UNLOCODE')], axis=1)
        scores['cpci'].index.name = 'port'

    need_graph = include & {"degree", "closeness", "betweenness_link", "betweenness_time"}
    if need_graph:
        import networkx as nx
        adj = copy.deepcopy(matrix)
        adj[adj > 0] = int(1)
        adj = adj.astype(int)
        G = nx.from_pandas_adjacency(adj, create_using=nx.DiGraph)

        if 'degree' in include:
            d = pd.DataFrame(G.degree, columns=['port', 'Degree']).set_index('port')
            di = pd.DataFrame(G.in_degree, columns=['port', 'InDegree']).set_index('port')
            do = pd.DataFrame(G.out_degree, columns=['port', 'OutDegree']).set_index('port')
            scores['degree'] = pd.concat([d, di, do], axis=1)
        if 'closeness' in include:
            cf = pd.Series(nx.closeness_centrality(G.reverse()), name='ClosenessFrom')
            ct = pd.Series(nx.closeness_centrality(G), name='ClosenessTo')
            scores['closeness'] = pd.concat([cf, ct], axis=1).rename_axis('port')
        if 'betweenness_link' in include:
            b = pd.Series(nx.betweenness_centrality(G, normalized=False), name='BetweennessLink')
            scores['betweenness_link'] = b.to_frame().rename_axis('port')
        if 'betweenness_time' in include:
            weights = {}
            for i, x in enumerate(G.edges()):          # notebook: weight_time()
                weights[x] = df['max_days'][i]
            by_key = {(o, d_): t for o, d_, t in zip(df['origin'], df['destination'], df['max_days'])}
            flags['time_weights_positional_equal_keyed'] = bool(
                all(weights[e] == by_key.get(e) for e in weights) and len(weights) == len(by_key))
            nx.set_edge_attributes(G, values=weights, name='weight')
            b = pd.Series(nx.betweenness_centrality(G, weight='weight', normalized=False),
                          name='BetweennessTime')
            scores['betweenness_time'] = b.to_frame().rename_axis('port')
    return scores, flags
