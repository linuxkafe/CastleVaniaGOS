"""
Benchmark harness for cold-layer retrieval contenders (T052).

Measures (a) BM25, (b) PPR, (c) Hybrid BM25→PPR on precision@k, recall@k, latency.
"""

from __future__ import annotations

import time
import csv
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Ensure AES root is on path
_aes_root = str(Path(__file__).resolve().parent.parent.parent)
if _aes_root not in sys.path:
    sys.path.insert(0, _aes_root)

from lib.memory.relevance import bm25_search
from lib.epistemic.cold_retrieval import build_shadow_graph, hybrid_bm25_ppr, power_iteration

SHADOW_DIR = Path(_aes_root) / "aes" / "shadow"
ARCHIVE_DIR = SHADOW_DIR / "archive"
PREMISE_DIR = Path(_aes_root) / "aes" / "premises"


def load_all_shadow_docs(include_body: bool = False) -> Dict[str, str]:
    """Load all shadow docs (hot + archive).

    Args:
        include_body: If True, include body content after frontmatter.
                     If False (default), only title + synthesis — preserves
                     English signal for BM25 against Portuguese corpus.
    """
    import yaml
    documents = {}
    for d in [SHADOW_DIR, ARCHIVE_DIR]:
        for fpath in sorted(d.glob("*.md")):
            if fpath.name in ("README.md", ".gitkeep"):
                continue
            content = fpath.read_text()
            if content.startswith("---"):
                parts = content.split("---", 2)
                if len(parts) >= 3:
                    try:
                        fm = yaml.safe_load(parts[1])
                        title = fm.get("title", fpath.stem)
                        synthesis = fm.get("synthesis", "")
                        doc_text = f"{title}\n{synthesis}"
                        if include_body:
                            body = parts[2].strip()
                            if body:
                                doc_text += f"\n{body}"
                        documents[fpath.stem] = doc_text
                    except:
                        pass
    return documents


# ── Queries and gold standard ──────────────────────────────────────────
# Each query is a (query_text, gold_set) tuple.
# Gold = set of shadow doc IDs that are relevant to this query.
# Sourced from actual ticket texts (T047+) and their context.

BENCHMARK_QUERIES: List[Tuple[str, Set[str]]] = [
    (
        "Fix non-conformities from epistemic audit: remove reference copies, fix sleep idempotence, add pre-push hook, update kanban state",  # T047
        {"SD-HOSTILE-INSIGHT", "SD-META-001", "SD-META-002", "SD-CI-001", "SD-CAP-002"},
    ),
    (
    # T048
        "Adopt Truth Maintenance System semantics in the propagator, JTMS retraction, NOGOOD detection through odd-cycle DFS",
        {"SD-CAP-025", "SD-META-001", "SD-GF-001", "SD-CAP-019", "SD-CAP-011"},
    ),
    (
    # T049
        "AGM belief revision epistemic entrenchment scoring formalize composite score as entrenchment ordering minimal change demotion",
        {"SD-CAP-025", "SD-META-001", "SD-CAP-019", "SD-CAP-007"},
    ),
    (
    # T050
        "Dung abstract argumentation attack relations grounded extension over claim graph, skeptical semantics for conflict resolution",
        {"SD-CAP-025", "SD-META-001", "SD-CAP-019"},
    ),
    (
    # T051
        "BM25 lexical relevance retrieval time relevance term make wake archive resurfacing third leg of composite score",
        {"SD-CAP-019", "SD-CAP-025", "SD-CAP-011", "SD-META-001", "SD-CAP-002"},
    ),
    (
    # T052
        "Cold layer graph retrieval HippoRAG Personalized PageRank over premise shadow graph benchmark BM25 vs PPR",
        {"SD-CAP-025", "SD-CAP-019", "SD-CAP-011", "SD-CAP-007"},
    ),
    (
    # T053
        "Provenance interoperability W3C PROV-O nanopublication mapping for shadow document frontmatter",
        {"SD-CAP-025", "SD-CAP-001", "SD-PRO-001"},
    ),
    (
    # T054
        "Goal Structuring Notation assurance case view generate GSN argument from quality gates and epistemic claims",
        {"SD-CAP-025", "SD-CAP-019", "SD-CAP-007"},
    ),
    (
    # T055
        "LongMemEval LoCoMo memory benchmark harness for the epistemic memory layer evaluation",
        {"SD-CAP-019", "SD-CAP-025", "SD-CAP-011", "SD-CAP-002"},
    ),
    (
    # T056
        "Paper workspace From Orality to Print for LLMs CSCW academic paper under epistemic governance regime",
        {"SD-CAP-025", "SD-CAP-019", "SD-META-001", "SD-CAP-002"},
    ),
    (
    # Sleep/wake consolidation
        "Governed consolidation demotion merge duplicate detection sleep cycle score recomputation INDEX regeneration",
        {"SD-CAP-019", "SD-CAP-011", "SD-META-002", "SD-CAP-002"},
    ),
    (
    # Epistemic claims and falsification
        "Falsification claim verification epistemic status SUPORTADA NAO SUPORTAVEL VERIFICAVEL conformance suite",
        {"SD-CAP-025", "SD-GF-001", "SD-META-001"},
    ),
    (
    # Shadow document management
        "Documento Sombra shadow document lifecycle creation scoring demotion to archive provenance merged_from tracking",
        {"SD-001-documento-sombra-definicao", "SD-CAP-019", "SD-CAP-011"},
    ),
    (
    # Memory scoring
        "ACT-R activation decay composite scoring entropy entrenchment centrality pinning memory efficacy metric",
        {"SD-CAP-019", "SD-CAP-025", "SD-CAP-011", "SD-CAP-002"},
    ),
    (
    # Premise graph propagation
        "Propagator premise verification cascade graph propagation epistemic integrity TMS JTMS claim labeling IN OUT",
        {"SD-GF-001", "SD-CAP-025", "SD-CAP-019"},
    ),
    (
    # Model-agnostic conformance
        "Model agnostic conformance suite same behavior any LLM printing press claim falsifiable",
        {"SD-CAP-002", "SD-CAP-019", "SD-META-001"},
    ),
    (
    # Identity and renaming
        "Identity gate rename project to Ambrosio Grilo Falante exit criteria unlocking",
        {"SD-META-001", "SD-CAP-019", "SD-AMB-001", "SD-AMB-002"},
    ),
    (
    # Skill activation
        "Skill activation protocol PINA rule method not auto triggered ACORDAR loaded but not activated",
        {"SD-META-001", "SD-META-002", "SD-CAP-019"},
    ),
    (
    # Kanban consistency
        "Kanban frontmatter consistency check column status sprint table validation generator deduplication",
        {"SD-CI-001", "SD-CAP-002", "SD-META-002"},
    ),
    (
    # Quality gates
        "Quality gates make check lint validate test coverage premise integrity pre-push verification gate",
        {"SD-CI-001", "SD-CAP-002", "SD-META-002", "SD-CAP-019"},
    ),
    (
    # Memory loop detection
        "Open loop detection epistemic loop closure HIGH criticality promotion gate demotion blocking premise dependency",
        {"SD-CAP-025", "SD-META-002", "SD-GF-001", "SD-CAP-019"},
    ),
]


def precision_at_k(
    retrieved: List[str], gold: Set[str], k: int
) -> float:
    """Precision@k: fraction of top-k retrieved that are relevant."""
    top_k = retrieved[:k]
    if not top_k:
        return 0.0
    relevant = sum(1 for doc in top_k if doc in gold)
    return relevant / len(top_k)


def recall_at_k(
    retrieved: List[str], gold: Set[str], k: int
) -> float:
    """Recall@k: fraction of relevant docs in top-k."""
    if not gold:
        return 0.0
    top_k = retrieved[:k]
    relevant = sum(1 for doc in top_k if doc in gold)
    return relevant / len(gold)


def run_bm25_contender(
    query: str, documents: Dict[str, str], **kwargs
) -> List[Tuple[str, float]]:
    """Contender (a): pure BM25."""
    return bm25_search(query, documents, top_k=10)


def run_ppr_contender(
    query: str,
    documents: Dict[str, str],
    adj: Dict[str, Set[str]],
    **kwargs,
) -> List[Tuple[str, float]]:
    """Contender (b): PPR over shadow graph only (no BM25 seeding)."""
    if not adj:
        return []

    # Use uniform seed distribution (no BM25)
    seed_weights = {node: 1.0 for node in adj}
    ppr_scores = power_iteration(adj, seed_weights)

    # Sort by PPR score
    results = sorted(ppr_scores.items(), key=lambda x: x[1], reverse=True)
    return results[:10]


def run_hybrid_contender(
    query: str,
    documents: Dict[str, str],
    adj: Dict[str, Set[str]],
    **kwargs,
) -> List[Tuple[str, float]]:
    """Contender (c): BM25 seeds -> PPR expansion."""
    return hybrid_bm25_ppr(query, bm25_search, documents, adj)


def run_benchmark() -> Dict[str, Dict]:
    """Run all contenders on all queries and return results."""
    print("Loading shadow docs...")
    documents = load_all_shadow_docs()
    print(f"  Loaded {len(documents)} shadow docs")

    print("Building shadow graph...")
    adj = build_shadow_graph(shadow_dir=SHADOW_DIR)
    print(f"  Graph: {len(adj)} nodes")

    contenders = {
        "BM25": run_bm25_contender,
        "PPR": run_ppr_contender,
        "Hybrid": run_hybrid_contender,
    }

    results = {}
    for name, fn in contenders.items():
        print(f"\nRunning {name}...")
        total_prec = {k: 0.0 for k in [1, 3, 5, 10]}
        total_rec = {k: 0.0 for k in [1, 3, 5, 10]}
        total_latency = 0.0
        n = len(BENCHMARK_QUERIES)

        for i, (query, gold) in enumerate(BENCHMARK_QUERIES):
            start = time.perf_counter()
            if name == "BM25":
                ranked = fn(query, documents)
            elif name == "PPR":
                ranked = fn(query, documents, adj=adj)
            else:
                ranked = fn(query, documents, adj=adj)

            elapsed = time.perf_counter() - start
            total_latency += elapsed

            retrieved_ids = [doc_id for doc_id, _ in ranked]

            for k in [1, 3, 5, 10]:
                total_prec[k] += precision_at_k(retrieved_ids, gold, k)
                total_rec[k] += recall_at_k(retrieved_ids, gold, k)

            if (i + 1) % 5 == 0:
                print(f"  [{i+1}/{n}] queries done")

        avg_prec = {k: v / n for k, v in total_prec.items()}
        avg_rec = {k: v / n for k, v in total_rec.items()}

        results[name] = {
            "precision": avg_prec,
            "recall": avg_rec,
            "avg_latency_ms": (total_latency / n) * 1000,
            "total_latency_ms": total_latency * 1000,
        }

    return results


def print_results_table(results: Dict[str, Dict]) -> None:
    """Print a formatted results table."""
    print("\n" + "=" * 80)
    print("  COLD-LAYER RETRIEVAL BENCHMARK RESULTS")
    print("=" * 80)

    header = f"{'Contender':<12} | {'P@1':>6} {'P@3':>6} {'P@5':>6} {'P@10':>7} | {'R@1':>6} {'R@3':>6} {'R@5':>6} {'R@10':>7} | {'Lat(ms)':>8}"
    print(header)
    print("-" * len(header))

    for name in ["BM25", "PPR", "Hybrid"]:
        r = results[name]
        p = r["precision"]
        rec = r["recall"]
        print(
            f"{name:<12} | "
            f"{p[1]:>6.3f} {p[3]:>6.3f} {p[5]:>6.3f} {p[10]:>7.3f} | "
            f"{rec[1]:>6.3f} {rec[3]:>6.3f} {rec[5]:>6.3f} {rec[10]:>7.3f} | "
            f"{r['avg_latency_ms']:>8.2f}"
        )

    print("-" * len(header))

    # Winner
    best_p5 = max(results.items(), key=lambda x: x[1]["precision"][5])
    print(f"\n  Winner (precision@5): {best_p5[0]} ({best_p5[1]['precision'][5]:.3f})")
    best_r5 = max(results.items(), key=lambda x: x[1]["recall"][5])
    print(f"  Winner (recall@5):    {best_r5[0]} ({best_r5[1]['recall'][5]:.3f})")
    best_lat = min(results.items(), key=lambda x: x[1]["avg_latency_ms"])
    print(f"  Fastest:              {best_lat[0]} ({best_lat[1]['avg_latency_ms']:.2f}ms)")


if __name__ == "__main__":
    results = run_benchmark()
    print_results_table(results)
