"""
Shared configuration resolution for AES memory/index tooling.

The repo convention (see scripts/adversarial-gate.sh) is that gates read
.aes/config.mk directly — environment overrides win, then .aes/config.mk,
then the code default. Python scripts historically only read the env var,
so a budget set in .aes/config.mk was silently ignored when the script was
invoked directly (not via a Makefile target that exports it). Centralising
the resolver here keeps generate-index.py, token-budget-trace.py and
discovery-tax.py consistent (SD-OPS-079).
"""

import os
from pathlib import Path

AES_ROOT = Path(__file__).resolve().parent.parent.parent

# Default raised from 4000 to 7000 (SD-OPS-079), then 7000 to 8500 (SD-OPS-105),
# then 8500 to 10000 (legitimate corpus growth — SD-OPS-108..114 + flybrain docs):
# T268 forces ALL shadow docs into INDEX.md (staleness check requires every id
# present), so the hard cap is a soft scaling signal, not a memory bound.
# Corpus ~135 docs at ~67 tokens/doc ≈ ~9092 tokens; 10000 gives headroom to
# ~148 docs at the current rate. Policy raises with legitimate corpus growth —
# never cut real docs to fit (SD-OPS-079), never disable the gate.
# 10000 → 10500 (T302: SD-OPS-154/155 legitimate lessons; 153 docs, ~10098 tokens).
# NOTE: in this repo .aes/config.mk is git-tracked (not ignored), so the policy
# must be bumped in BOTH the tracked config.mk and this default (fresh clones
# receive config.mk via git; the default covers clones that lack it).
#
# T314/T312: AES_INDEX_TOKEN_BUDGET is GONE, and replaced by two corpus-relative
# limits. The absolute total was not a signal — it was a fact.
#
# INDEX.md keeps EVERY shadow doc (T268: the staleness check requires every id),
# so its token count grows monotonically with the corpus. An absolute threshold
# on a monotonic quantity can only ever do one of two things: fire on healthy
# growth, or be raised. It fired seven times (4000 → 7000 → 8500 → 10000 →
# 10500 → 11000 → 11600 → 12200) and was raised seven times. It never once
# caught a defect, and it cost a full check cycle each time it fired.
#
# What IS a signal is the distribution: a doc that is anomalously large, or a
# corpus whose mean entry size is creeping up (which means someone started
# inlining content into the index instead of linking). Both are independent of
# how many docs exist.
#
# Measured on the current corpus (190 docs): min 23, median 58, mean 64,
# p90 101, max 131 tokens. The limits below leave roughly 50% headroom over the
# observed max and 55% over the observed mean — enough that ordinary growth
# never trips them, tight enough that real bloat does.
DEFAULT_MAX_DOC_TOKENS = 200
DEFAULT_MAX_MEAN_TOKENS = 100

# Kept only so that a stale AES_INDEX_TOKEN_BUDGET in someone's config.mk or CI
# is reported rather than silently ignored. A leftover absolute budget is a
# configuration lie: it looks load-bearing and does nothing.
_DEPRECATED_TOKEN_BUDGET = "AES_INDEX_TOKEN_BUDGET"


def _resolve_int(env_name: str, default: int) -> int:
    """Resolve an integer setting: env > .aes/config.mk > default."""
    env_val = os.environ.get(env_name, "")
    if env_val.strip().isdigit():
        return int(env_val.strip())
    cfg = AES_ROOT / ".aes" / "config.mk"
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            if line.startswith(env_name):
                val = line.split("=", 1)[1].strip()
                if val.isdigit():
                    return int(val)
    return default


def resolve_max_doc_tokens() -> int:
    """Max tokens for a single INDEX.md entry (AES_INDEX_MAX_DOC_TOKENS)."""
    return _resolve_int("AES_INDEX_MAX_DOC_TOKENS", DEFAULT_MAX_DOC_TOKENS)


def resolve_max_mean_tokens() -> int:
    """Max mean tokens per INDEX.md entry (AES_INDEX_MAX_MEAN_TOKENS)."""
    return _resolve_int("AES_INDEX_MAX_MEAN_TOKENS", DEFAULT_MAX_MEAN_TOKENS)


def derived_index_budget(n_entries: int) -> int:
    """A budget DERIVED from the corpus, for consumers that need one.

    `discovery-tax.py` and `token-budget-trace.py` both want "how many tokens is
    the index allowed to be" as an input to a cost model. The old answer was a
    configured absolute number that had to be bumped every time the corpus grew
    — so the "budget" in those models was really "the last number someone typed".

    This derives it: the mean-per-entry limit times the number of entries. It
    is never stale, never bumped, and it is the same quantity the gate checks,
    so the report and the gate cannot disagree.
    """
    return max(1, n_entries) * resolve_max_mean_tokens()


def deprecated_token_budget() -> int | None:
    """The old absolute budget, if one is still configured anywhere.

    Reported by index-check as a warning. It gates nothing: keeping it would
    re-introduce exactly the ratchet this replaced.
    """
    env_val = os.environ.get(_DEPRECATED_TOKEN_BUDGET, "")
    if env_val.strip().isdigit():
        return int(env_val.strip())
    cfg = AES_ROOT / ".aes" / "config.mk"
    if cfg.exists():
        for line in cfg.read_text().splitlines():
            if line.startswith(_DEPRECATED_TOKEN_BUDGET):
                val = line.split("=", 1)[1].strip()
                if val.isdigit():
                    return int(val)
    return None