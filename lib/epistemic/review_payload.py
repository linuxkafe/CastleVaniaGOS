#!/usr/bin/env python3
"""
review_payload.py — the ONE definition of what a human review signature covers.

T313. Before this module, the signature covered `artifact_bytes` and nothing
else, so `reviewed_by.identity` and `reviewed_by.timestamp` were parsed by the
verifier and thrown away (shellcheck SC2034). Rewriting them in the manifest
kept the verdict at SUPORTADA. The schema promises three verified fields and
one was verified.

Two schemes, because a signed review mark that already exists is evidence and
destroying it is not a repair:

  "aes-review-v1"  payload = artifact_bytes
                    Identity and timestamp are NOT authenticated. Accepted
                    only when the manifest declares v1, and the verifier
                    reports the gap on stderr — see note on fallback below.

  "aes-review-v2"  payload = identity + b"\\n" + timestamp + b"\\n" + artifact_bytes
                    Identity and timestamp ARE authenticated. Required for any
                    new signature.

Why the scheme is DECLARED and never inferred:

An earlier sketch had the verifier try v2 and silently fall back to v1 when it
failed. That reintroduces the hole exactly: anyone can sign with the v1 scheme,
write whatever identity they like, and the fallback accepts it. A cutoff has
to be something the signer states, not something the verifier guesses from a
date — otherwise the attacker picks the scheme.

So: `signature_scheme: "aes-review-v2"` is required for new signatures, and a
manifest without it is treated as v1 *and says so*. The debt is visible and
countable rather than invisible and permanent.
"""

from __future__ import annotations

SCHEME_V1 = "aes-review-v1"
SCHEME_V2 = "aes-review-v2"

#: Schemes a manifest may declare. Anything else is unverified rather than
#: silently downgraded — a typo in the scheme name must not fall back to v1.
KNOWN_SCHEMES = frozenset({SCHEME_V1, SCHEME_V2})

#: The separator between the attribution fields and the artifact bytes. A
#: newline, not a NUL or a length prefix: a NUL cannot appear in a YAML scalar,
#: so there is no way to shift bytes between the identity and the artifact to
#: make two different (identity, artifact) pairs produce the same payload.
SEP = b"\n"


def normalise(field: str) -> bytes:
    """Encode an attribution field for signing.

    UTF-8, no normalisation beyond that. Two manifests that differ only in
    Unicode normalisation of the identity are different identities here, which
    is the conservative direction: a signature that verifies means exactly the
    bytes that were signed, not an equivalence class someone chose afterwards.
    """
    if field is None:
        raise ValueError("attribution field is required for v2 signatures")
    return field.encode("utf-8")


def review_payload(scheme: str, identity: str, timestamp: str, artifact_bytes: bytes) -> bytes:
    """Build the exact bytes a review signature must cover.

    Shared by the signer (scripts/skill-generate.py) and the verifier
    (scripts/adversarial-verify/human-signature). If these two ever compute the
    payload differently, every new signature fails verification — loudly, which
    is the good failure direction. A duplicated implementation that agreed by
    accident would be the bad one.
    """
    if scheme == SCHEME_V1:
        return artifact_bytes
    if scheme == SCHEME_V2:
        return normalise(identity) + SEP + normalise(timestamp) + SEP + artifact_bytes
    raise ValueError(f"unknown signature_scheme: {scheme!r} (known: {sorted(KNOWN_SCHEMES)})")
