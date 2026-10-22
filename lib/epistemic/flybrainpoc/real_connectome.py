"""REAL_AES_FULL — the real FlyWire connectome as a brian2 reservoir.

T326. This was a `NotImplementedError` on every backend, which is why the
138k-neuron connectome was "blocked". It was never blocked by hardware or by
brian2: it was blocked by nobody having written the loader.

Everything model-specific here is taken from the fly-brain reference
implementation (github.com/eonsystemspbc/fly-brain), not invented:

  LIF parameters    code/run_brian2_cuda.py, the `params` dict
  network shape     code/run_brian2_genn.py, `_create_network`
  weights           `Excitatory x Connectivity` from the parquet — and note
                    it is SIGNED: 40% of the 15,091,983 synapses are
                    inhibitory (min -2405, max 1897). T325's probe clamped
                    these to a positive floor and therefore ran an
                    excitatory-only network; the cost figure survives (event
                    counts, not weights, drive the cost) but the dynamics
                    did not.
  drive             PoissonInput on the experiment's excited neurons
  experiments       code/benchmark.py, `EXPERIMENTS`

WHAT IS NOT THE SAME AS TRIVIAL_UNIT, and this matters:

TRIVIAL_UNIT is 128 sensors -> three synthetic pools (16/12/4) -> classify.
REAL_AES_FULL is a 138,639-neuron connectome driven by Poisson noise on a set
of real neurons, read out on a set of real neurons. There is no
"mbons / central_complex / giant_fiber" mapping in the data — the parquet
carries no region labels, and the completeness CSV carries only a boolean.
So the readout is a **named cell type or experiment** from
`sez_neurons.pickle` / `EXPERIMENTS`, chosen explicitly, and it is NOT the
16/12/4 pool split. Any balanced-accuracy number produced this way is a
different measurement from the 0.965 quoted for TRIVIAL_UNIT, and the two must
not be compared.
"""

from __future__ import annotations

import os
import pickle
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from lib.epistemic.flybrainpoc.backends import _BRIAN2_OK, b2  # noqa: F401

# fly-brain: code/run_brian2_cuda.py
REAL_LIF_PARAMS: Dict[str, float] = {
    "v_0": -52e-3,      # V  (brian2 works in volts; the reference uses mV)
    "v_rst": -52e-3,
    "v_th": -45e-3,
    "t_mbr": 0.020,     # s
    "tau": 0.005,       # s
    "t_rfc": 0.0022,    # s
    "t_dly": 0.0018,    # s
    "w_syn": 0.275e-3,  # V
    "f_poi": 250.0,
}

# The full equation set, INCLUDING the constants the threshold/reset strings
# reference. Declaring them here (rather than interpolating values into
# `threshold=`/`reset=`) is what makes `v > v_th` parseable: interpolating
# produced "v > -45. mV", with a space, which is a SyntaxError.
REAL_MODEL = """
dv/dt = (v_0 - v + g) / t_mbr : volt (unless refractory)
dg/dt = -g / tau               : volt (unless refractory)
rfc                           : second
v_0                           : volt (constant)
v_rst                         : volt (constant)
v_th                          : volt (constant)
t_mbr                         : second (constant)
tau                           : second (constant)
"""

# Kept as an alias: the reference implementation's name for the same three
# differential equations.
REAL_EQS = REAL_MODEL

# The connectivity parquet, relative to the fly-brain checkout.
CONNECTIVITY_RELPATH = Path("data/2025_Connectivity_783.parquet")
COMPLETENESS_RELPATH = Path("data/2025_Completeness_783.csv")
SEZ_RELPATH = Path("data/sez_neurons.pickle")

# 'sugar' from code/benchmark.py: the 20 sugar GRNs. The default drive and
# readout because it is the experiment the reference implementation benchmarks.
DEFAULT_EXPERIMENT_FLYIDS: Tuple[int, ...] = (
    720575940624963786, 720575940630233916, 720575940637568838, 720575940638202345,
    720575940617000768, 720575940630797113, 720575940632889389, 720575940621754367,
    720575940621502051, 720575940640649691, 720575940639332736, 720575940616885538,
    720575940639198653, 720575940639259967, 720575940617937543, 720575940632425919,
    720575940633143833, 720575940612670570, 720575940628853239, 720575940629176663,
    720575940611875570,
)
DEFAULT_STIM_RATE_HZ = 200.0


def _require_pyarrow():
    try:
        import pyarrow.parquet as pq
    except ImportError as e:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "REAL_AES_FULL needs pyarrow to read the FlyWire parquet. "
            "Install it in the venv that runs the PoC."
        ) from e
    return pq


def resolve_checkout(connectome_path: Path) -> Path:
    """Find the fly-brain checkout.

    Honours the convention the reservoir already used
    (`eonsystemspbc/fly-brain` relative to the repo), then the env var, then
    the sibling of the AES checkout, so a clone next to the AES just works.
    """
    candidates = [
        Path(connectome_path),
        Path(os.environ["AES_FLYBRAIN_PATH"]) if os.environ.get("AES_FLYBRAIN_PATH") else None,
        Path.cwd() / "eonsystemspbc" / "fly-brain",
        Path("/opt/aes/eonsystemspbc/fly-brain"),
        Path("/opt/fly-brain"),
    ]
    for c in candidates:
        if c and (c / CONNECTIVITY_RELPATH).exists():
            return c
    raise FileNotFoundError(
        "FlyWire connectivity parquet not found. Expected "
        f"{CONNECTIVITY_RELPATH} under one of: "
        + ", ".join(str(c) for c in candidates if c)
        + ". Clone https://github.com/eonsystemspbc/fly-brain, or set "
        "AES_FLYBRAIN_PATH."
    )


def load_connectome(checkout: Path) -> Tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Return (pre, post, weight, n_neurons) from the FlyWire parquet.

    `weight` is `Excitatory x Connectivity` — the reference implementation's
    weight column, not a rescaling of ours.
    """
    pq = _require_pyarrow()
    table = pq.read_table(
        checkout / CONNECTIVITY_RELPATH,
        columns=["Presynaptic_Index", "Postsynaptic_Index", "Excitatory x Connectivity"],
    )
    pre = table.column("Presynaptic_Index").to_numpy().astype(np.int32)
    post = table.column("Postsynaptic_Index").to_numpy().astype(np.int32)
    w = table.column("Excitatory x Connectivity").to_numpy().astype(np.float64)
    n = int(max(pre.max(), post.max())) + 1
    return pre, post, w, n


def flyid_to_index(checkout: Path, flyids: List[int]) -> List[int]:
    """Map FlyWire neuron IDs to connectome indices.

    The mapping is POSITIONAL, taken from the row order of the completeness
    CSV: `flyid2i = {id: position}` (code/run_brian2_genn.py:188). The parquet
    is keyed by that same position, so the second CSV column — `Completed`, a
    boolean — is NOT an index. An earlier version of this function read
    column 1 as the index and every lookup failed; the column is a
    completeness flag and means nothing to the parquet.
    """
    import csv

    lookup: Dict[int, int] = {}
    with open(checkout / COMPLETENESS_RELPATH, newline="") as fh:
        reader = csv.reader(fh)
        next(reader, None)  # header row
        for i, row in enumerate(reader):
            if not row:
                continue
            try:
                lookup[int(row[0])] = i
            except ValueError:
                continue
    missing = [f for f in flyids if f not in lookup]
    if missing:
        raise KeyError(
            f"{len(missing)} FlyWire IDs absent from the completeness CSV, "
            f"first: {missing[:3]}"
        )
    return [lookup[f] for f in flyids]


def sez_flyids(checkout: Path, cell_type: str) -> List[int]:
    """Real neurons of a named cell type, from the SEZ annotation pickle."""
    with open(checkout / SEZ_RELPATH, "rb") as fh:
        sez = pickle.load(fh)
    if cell_type not in sez:
        raise KeyError(
            f"cell type {cell_type!r} not in sez_neurons.pickle; "
            f"available: {sorted(sez)[:12]}"
        )
    return [int(f) for f in sez[cell_type]]


def build_full_network(
    checkout: Path,
    drive_flyids: Optional[List[int]] = None,
    readout_flyids: Optional[List[int]] = None,
    readout_name: str = "readout",
    stim_rate_hz: float = DEFAULT_STIM_RATE_HZ,
) -> Any:
    """Build the real connectome network.

    Returns a b2.Network carrying the same attributes `simulate()` expects:
    `pools` (name -> SpikeMonitor), `n_input_neurons`, and the backend's
    `pool_groups` / `pool_synapses` for symmetry with the trivial network.

    Poisson drive, not a spike-generator: the reference implementation drives
    with PoissonInput on excited neurons, and there is no 128-sensor encoding
    for a 138k-neuron brain. The consequence — REAL_AES_FULL cannot consume
    `inject()` the way TRIVIAL_UNIT does — is stated rather than papered over.
    """
    p = REAL_LIF_PARAMS
    pre, post, w, n_neurons = load_connectome(checkout)

    drive_ids = list(drive_flyids or DEFAULT_EXPERIMENT_FLYIDS)
    readout_ids = list(readout_flyids or drive_ids)
    drive_idx = np.array(flyid_to_index(checkout, drive_ids), dtype=np.int32)
    readout_idx = np.array(flyid_to_index(checkout, readout_ids), dtype=np.int32)

    b2.start_scope()
    b2.prefs.codegen.target = "numpy"

    # brian2 requires units on every assigned constant. Writing `neu.v = -0.052`
    # raises DimensionMismatchError, so every value below is built from the
    # parameter dict WITH its unit rather than converted inline.
    ns = b2.second
    volt = b2.volt

    # The equations reference v_0 / v_rst / v_th / t_mbr / tau, so they must be
    # in the group BEFORE the first assignment — brian2 creates state
    # variables from `model`, and assigning an unknown name raises. The
    # reference implementation passes them via `namespace=params`; doing it
    # inline keeps the parameters visible in one place.
    # stim_weight must be declared in the model BEFORE the PoissonInput that
    # references it by name, and before it can be assigned — brian2 rejects an
    # unknown name on assignment with AttributeError.
    model = REAL_MODEL + """
    stim_weight                    : volt (constant)
    """
    neu = b2.NeuronGroup(
        N=n_neurons,
        model=model,
        method="linear",
        # Reference the CONSTANTS BY NAME, not by interpolated value. Writing
        # `v > {-45e-3 * volt}` produces the string "v > -45. mV" — a space
        # between number and unit — which brian2 cannot parse (SyntaxError).
        # The reference implementation avoids this the same way: params
        # declare `eq_th = 'v > v_th'` and the values go in as state variables.
        threshold="v > v_th",
        reset="v = v_rst; g = 0 * volt",
        refractory="rfc",
        name="real_neurons",
    )
    neu.v = p["v_0"] * volt
    neu.g = 0 * volt
    neu.rfc = p["t_rfc"] * ns
    neu.v_0 = p["v_0"] * volt
    neu.v_rst = p["v_rst"] * volt
    neu.v_th = p["v_th"] * volt
    neu.t_mbr = p["t_mbr"] * ns
    neu.tau = p["tau"] * ns

    syn = b2.Synapses(neu, neu, "w : volt", on_pre="g += w", delay=p["t_dly"] * b2.second)
    syn.connect(i=pre, j=post)
    syn.w = w * p["w_syn"] * volt

    # Drive: ONE PoissonInput over the whole group, gated by a per-neuron
    # weight that is non-zero only on the excited set.
    #
    # This is the reference implementation's mechanism, and getting it wrong is
    # silent. The first version used `PoissonInput(N=len(drive_idx))`, which
    # drives the FIRST N neurons of the group — not the 21 sugar GRNs at their
    # scattered connectome indices. It ran, it spiked, and it was driving the
    # wrong 20 neurons. Comparing spike counts against the published
    # fly-brain benchmark is what exposed it: 1.16M spikes in 20 ms against a
    # reference ~175k spikes per SIMULATED SECOND, a factor of ~66.
    #
    # Reference: code/run_brian2_cuda.py — `PoissonInput(target=neu, N=1,
    # weight='stim_weight')` with `neu.stim_weight[exc]` set and zero elsewhere.
    drv = b2.PoissonInput(
        target=neu, target_var="v", N=1,
        rate=stim_rate_hz * b2.Hz, weight="stim_weight",
    )
    neu.stim_weight = 0 * volt
    neu.stim_weight[drive_idx] = p["w_syn"] * p["f_poi"] * volt
    # Driven neurons have no refractory period, as in the reference.
    neu.rfc[drive_idx] = 0 * b2.second

    # A brian2 subgroup needs CONTIGUOUS indices, and real neuron sets are
    # scattered across the connectome (the 20 sugar GRNs are 20 arbitrary
    # positions). So the readout is an index array, not a subgroup.
    mon = b2.SpikeMonitor(neu, name=f"mon_{readout_name}")
    net = b2.Network(neu, syn, drv, mon)

    net.pools = {readout_name: mon}
    net.pool_groups = {readout_name: neu}
    net.pool_synapses = {}
    net.n_input_neurons = len(drive_idx)
    net.n_neurons = n_neurons
    net.n_synapses = int(len(pre))
    net.readout_indices = readout_idx
    # The monitor records the whole group; `simulate()` must restrict it to the
    # readout set, so the indices travel with the network rather than being
    # baked into a subgroup.
    net.readout_mask = np.zeros(n_neurons, dtype=bool)
    net.readout_mask[readout_idx] = True
    net.drive_indices = drive_idx
    # REAL has no SpikeGeneratorGroup: the drive is Poisson, not injectable.
    net.has_injection_input = False
    return net
