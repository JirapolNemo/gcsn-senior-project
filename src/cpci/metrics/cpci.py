"""CPCI inbound/outbound scores and their C1..C5 decomposition."""
from . import metric
from ..config import LSCI_COLUMNS

_K = len(LSCI_COLUMNS)
_COLS = (["Inbound"] + ["C%d_i" % k for k in range(1, _K + 1)]
         + ["Outbound"] + ["C%d_o" % k for k in range(1, _K + 1)])


@metric("cpci", columns=_COLS, group="cpci",
        description="CPCI inbound (authority) / outbound (hub) + decomposition C1..C5 "
                    "(services, companies, vessels, TEU, largest vessel)")
def cpci(net):
    h = net.hits
    data = {"Inbound": h.auth, "Outbound": h.hub}
    for k in range(_K):
        data["C%d_i" % (k + 1)] = h.in_components[k]
        data["C%d_o" % (k + 1)] = h.out_components[k]
    return data
