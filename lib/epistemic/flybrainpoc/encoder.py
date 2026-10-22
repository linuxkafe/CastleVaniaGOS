"""encoder.py — encode GMIF island graphs as Poisson spike trains (T-3).

Maps each claim node into a sensory neuron population whose firing rate
reflects validation confidence, and whose (optionally) temporal envelope
reflects the logical operator. Contradictions drive two populations that
feed the same readout pool — the reservoir's recurrent dynamics then
integrate conflicting input.

Ablation contract (test_encoding): mode="rate_only" must ignore all timing;
mode="rate+timing" must modulate timing by operator.
"""


import numpy as np

from dataclasses import dataclass, field
from typing import Dict, Tuple


@dataclass
class SpikeTrains:
    """Container returned by Encoder.

    spike_trains: {neuron_index: array of spike times in ms}
    meta:         {neuron_index: {"claim": id, "population": str, "confidence": float}}
    duration_ms:  simulation horizon
    """

    spike_trains: Dict[int, np.ndarray] = field(default_factory=dict)
    meta: Dict[int, dict] = field(default_factory=dict)
    duration_ms: float = 400.0


# Temporal envelope windows (ms) for rate+timing mode
OP_WINDOWS_MS = {
    "G": (0, 200),      # global: sustained early drive
    "F": (0, 400),      # finally: full horizon
    "P": (0, 150),      # probabilistic: short, high rate (confidence folded in)
    "DEFAULT": (50, 300),
}

# Anti-phase windows for a contradicts pair (both claims are asserted, so
# both fire — but they are streamed into alternating drive, the spiking
# signature of mutually exclusive propositions; cf. binocular rivalry).
ANTI_PHASE_WINDOWS_MS = {
    "from": (0, 220),
    "to": (180, 400),
}

# Causal echo for implies/supports edges: the target claim re-fires in a
# later enrolment window, delayed by edge strength. Carries propagation
# structure into the reservoir's temporal integration.
ECHO_WINDOW_MS = (160, 240)
ECHO_DELAY_MS = {"strong": 0.0, "medium": 30.0, "weak": 60.0}

POSIX_EPOCH = 0.0


def parse_logical_form(logical_form: str) -> Tuple[str, float]:
    """Return (operator_family, probability_gate) from a logical_form string.

    Handles: "G(C-001)", "F(C-002)", "P>=0.9(C-003)", bare "C-004".
    """
    s = logical_form.strip()
    if not s:
        return "DEFAULT", 0.0
    head = s.split("(")[0].strip().upper() if "(" in s else ""
    if head.startswith("P") and ">=" in head:
        # Extract probability from the operator head; fallback to the literal
        try:
            prob = float("".join(ch for ch in head.split(">=")[1] if ch.isdigit() or ch == "."))
        except ValueError:
            prob = 0.9
        return "P", prob
    if head in ("G", "F", "A", "E", "X", "U"):
        return head, 1.0
    if head == "DEFAULT":
        return "DEFAULT", 0.0
    # Bare claim or unknown prefix
    return "DEFAULT", 1.0


def _window_for(op_family: str) -> Tuple[float, float]:
    return OP_WINDOWS_MS.get(op_family, OP_WINDOWS_MS["DEFAULT"])


class Encoder:
    """Convert claim graphs into Poisson spike trains.

    mode="rate_only":  rate = confidence * base_rate, entire horizon active.
    mode="rate+timing": rate scaled by confidence, but the active window
                        is shortened/positioned by the logical operator.

    layout="positional": claim position in graph determines neuron slot (index % 128).
                         Contradiction pairs land in same channels across islands.
    layout="hash": seeded hash of claim ID determines neuron slot. Randomizes
                   signature across islands; contradiction signature becomes
                   linearly undetectable (ablation control).
    """

    def __init__(self, base_rate: float = 80.0, bin_ms: float = 10.0, mode: str = "rate+timing", layout: str = "positional"):
        if mode not in ("rate_only", "rate+timing"):
            raise ValueError(f"Unknown mode: {mode!r}")
        if layout not in ("positional", "hash"):
            raise ValueError(f"Unknown layout: {layout!r}")
        self.base_rate = base_rate
        self.bin_ms = bin_ms
        self.mode = mode
        self.layout = layout

    def _neuron_for_position(self, index: int, claim_id: str = "") -> int:
        if self.layout == "hash":
            # Seeded hash of claim ID for reproducibility across runs
            import zlib
            seed = zlib.crc32(claim_id.encode("utf-8"))
            return seed % 128
        # Fixed sensory layout: claim position in the graph determines its
        # afferent slot, so structurally-consistent patterns (e.g. the
        # contradiction pair) land in the same readout channels on every
        # island. A hash-based layout would randomize the signature across
        # islands and make it linearly undetectable.
        return index % 128

    def _gen_spikes(self, rate: float, start_ms: float, end_ms: float) -> np.ndarray:
        if rate <= 0:
            return np.zeros(0, dtype=float)
        duration_ms = max(0.0, end_ms - start_ms)
        n_expected = rate * duration_ms / 1000.0  # spikes per neuron over window
        n = int(np.random.poisson(max(n_expected, 0.0)))
        if n == 0:
            return np.zeros(0, dtype=float)
        times = np.random.uniform(start_ms, end_ms, n)
        return np.sort(times)

    def encode_island(self, island: Dict) -> SpikeTrains:
        """Encode an island dict (as loaded by yaml.safe_load of a *.yaml graph).

        Returns spike trains for the simulation and metadata for the readout.
        """
        st = SpikeTrains()
        nodes = island.get("nodes", [])
        if not nodes:
            return st

        # Contradiction detection from edges
        contradictions = set()
        contrad_role: Dict[str, str] = {}
        echo_targets: Dict[str, str] = {}
        for e in island.get("edges", []):
            etype = e.get("type", "").lower()
            if etype in ("contradicts", "negates", "contradiction"):
                contradictions.add(e.get("from"))
                contradictions.add(e.get("to"))
                if e.get("from") not in contrad_role:
                    contrad_role[e.get("from")] = "from"
                if e.get("to") not in contrad_role:
                    contrad_role[e.get("to")] = "to"
            elif etype in ("implies", "supports"):
                echo_targets[e.get("to")] = e.get("strength", "medium")

        duration_ms = st.duration_ms
        for node_index, node in enumerate(nodes):
            cid = node.get("id", "?")
            neuron = self._neuron_for_position(node_index, cid)
            conf = float(node.get("validation_confidence", 0.5))
            conf = max(0.05, min(conf, 1.0))
            rate = conf * self.base_rate

            op_family, prob = parse_logical_form(node.get("logical_form", ""))

            if self.mode == "rate_only":
                st.spike_trains[neuron] = self._gen_spikes(rate, 0.0, duration_ms)
            else:
                if cid in contrad_role:
                    # Contradiction: alternate the conflicting claims across
                    # the horizon instead of co-driving — the temporal
                    # signature of a contradiction (mutual exclusivity) that
                    # carries no label by itself; the readout must discover it.
                    start, end = ANTI_PHASE_WINDOWS_MS[contrad_role[cid]]
                    st.spike_trains[neuron] = self._gen_spikes(
                        rate, start, min(end, duration_ms)
                    )
                else:
                    if op_family == "P":
                        # probabilistic gate: short window, rate reflects gate
                        rate = min(rate * (0.5 + 0.5 * prob), self.base_rate)
                        start, end = _window_for("P")
                    elif op_family in ("F", "E", "U"):
                        start, end = _window_for("F")
                    elif op_family in ("G", "A", "X"):
                        start, end = _window_for("G")
                    else:
                        start, end = _window_for("DEFAULT")
                    train = self._gen_spikes(rate, start, min(end, duration_ms))
                    if cid in echo_targets:
                        # Causal echo: the target of an implies/supports edge
                        # re-fires after a strength-scaled delay.
                        delta = ECHO_DELAY_MS.get(echo_targets[cid], 30.0)
                        echo_s, echo_e = ECHO_WINDOW_MS
                        echo = self._gen_spikes(
                            0.5 * rate,
                            echo_s + delta,
                            min(echo_e + delta, duration_ms),
                        )
                        train = np.concatenate([train, echo])
                    st.spike_trains[neuron] = np.sort(train)

            st.meta[neuron] = {
                "claim": cid,
                "population": "sensory",
                "confidence": conf,
                "operator": op_family,
                "is_contradiction": cid in contradictions,
            }
        return st


def synapse_weights(island: Dict) -> Dict[Tuple[int, int], float]:
    """Map graph edges to an adjacency weight matrix keyed by neuron pairs.

    Used by the reservoir to bias recurrent coupling between claim input
    pools that the graph already relates. A 'contradicts' edge is given a
    negative (inhibitory) weight; implies/supports get a positive weight.
    """
    nodes = island.get("nodes", [])
    nodes_by_id = {n.get("id"): i for i, n in enumerate(nodes)}
    enc = Encoder()
    weights: Dict[Tuple[int, int], float] = {}
    for e in island.get("edges", []):
        src = e.get("from")
        dst = e.get("to")
        if src not in nodes_by_id or dst not in nodes_by_id:
            continue
        a = enc._neuron_for_position(nodes_by_id[src])
        b = enc._neuron_for_position(nodes_by_id[dst])
        etype = e.get("type", "").lower()
        strength = e.get("strength", "medium")
        base = {"strong": 1.0, "medium": 0.5, "weak": 0.25}.get(strength, 0.5)
        if etype in ("contradicts", "negates"):
            w = -base
        elif etype in ("implies", "supports"):
            w = base
        elif etype in ("equal", "equivalent"):
            w = base * 1.2
        else:
            w = 0.0
        if w != 0.0:
            weights[(a, b)] = w
    return weights