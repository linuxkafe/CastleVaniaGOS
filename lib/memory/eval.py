"""
Evaluation harness for cold-layer retrieval (Part 1: Retrieval Quality).

Runs the 20-query benchmark, produces paper-ready tables, and adds
diagnostic analysis: per-query breakdown, graph connectivity, and
failure mode identification.

Usage:
    PYTHONPATH=/opt/aes python3 -m lib.memory.eval
"""

from __future__ import annotations

import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

_aes_root = str(Path(__file__).resolve().parent.parent.parent)
if _aes_root not in sys.path:
    sys.path.insert(0, _aes_root)

from lib.memory.benchmark import (
    BENCHMARK_QUERIES,
    load_all_shadow_docs,
    precision_at_k,
    recall_at_k,
)
from lib.memory.relevance import bm25_search
from lib.memory.embeddings import embedding_search
from lib.epistemic.cold_retrieval import (
    _bm25_confidence,
    build_shadow_graph,
    hybrid_bm25_ppr,
    power_iteration,
)


# ── Per-query detailed results ──────────────────────────────────────────

def run_per_query_analysis() -> List[Dict]:
    """Run all contenders on each query, return detailed per-query results."""
    documents = load_all_shadow_docs()
    adj = build_shadow_graph()

    # Pre-build embedding index (once, shared across queries)
    print("  Building embedding index...")
    from lib.memory.embeddings import build_index
    from lib.memory.retrieval import unified_search
    build_index(documents, force_rebuild=True)

    # Load frontmatter-only docs for BM25/embeddings
    fm_docs = load_all_shadow_docs(include_body=False)

    results = []
    for qi, (query, gold) in enumerate(BENCHMARK_QUERIES):
        # BM25 (frontmatter-only)
        bm25_res = bm25_search(query, fm_docs, top_k=10)
        bm25_ids = [doc_id for doc_id, _ in bm25_res]
        bm25_conf = _bm25_confidence(bm25_res)

        # PPR (uniform seeds — full body for graph edges)
        if adj:
            seed_weights = {node: 1.0 for node in adj}
            ppr_scores = power_iteration(adj, seed_weights)
            ppr_res = sorted(ppr_scores.items(), key=lambda x: x[1], reverse=True)[:10]
        else:
            ppr_res = []
        ppr_ids = [doc_id for doc_id, _ in ppr_res]

        # Hybrid (BM25 + PPR, adaptive weighting)
        hybrid_res = hybrid_bm25_ppr(query, bm25_search, fm_docs, adj)
        hybrid_ids = [doc_id for doc_id, _ in hybrid_res]

        # Embeddings (semantic, frontmatter-only)
        embed_res = embedding_search(query, fm_docs, top_k=10)
        embed_ids = [doc_id for doc_id, _ in embed_res]

        # Unified (BM25 + Embeddings + PPR)
        unified_res = unified_search(query, top_k=10)
        unified_ids = [doc_id for doc_id, _ in unified_res]

        results.append({
            "query_idx": qi,
            "query_text": query[:80] + ("..." if len(query) > 80 else ""),
            "gold": sorted(gold),
            "gold_size": len(gold),
            "bm25_confidence": round(bm25_conf, 3),
            "bm25": {
                "retrieved": bm25_ids,
                "p@5": precision_at_k(bm25_ids, gold, 5),
                "r@5": recall_at_k(bm25_ids, gold, 5),
                "hits_at_5": [d for d in bm25_ids[:5] if d in gold],
                "misses_at_5": [d for d in bm25_ids[:5] if d not in gold],
            },
            "ppr": {
                "retrieved": ppr_ids,
                "p@5": precision_at_k(ppr_ids, gold, 5),
                "r@5": recall_at_k(ppr_ids, gold, 5),
                "hits_at_5": [d for d in ppr_ids[:5] if d in gold],
            },
            "hybrid": {
                "retrieved": hybrid_ids,
                "p@5": precision_at_k(hybrid_ids, gold, 5),
                "r@5": recall_at_k(hybrid_ids, gold, 5),
                "hits_at_5": [d for d in hybrid_ids[:5] if d in gold],
            },
            "embeddings": {
                "retrieved": embed_ids,
                "p@5": precision_at_k(embed_ids, gold, 5),
                "r@5": recall_at_k(embed_ids, gold, 5),
                "hits_at_5": [d for d in embed_ids[:5] if d in gold],
            },
            "unified": {
                "retrieved": unified_ids,
                "p@5": precision_at_k(unified_ids, gold, 5),
                "r@5": recall_at_k(unified_ids, gold, 5),
                "hits_at_5": [d for d in unified_ids[:5] if d in gold],
            },
        })

    return results


# ── Graph diagnostics ────────────────────────────────────────────────────

def graph_diagnostics(adj: Dict[str, Set[str]]) -> Dict:
    """Analyze graph connectivity and structure."""
    if not adj:
        return {"error": "empty graph"}

    nodes = set(adj.keys())
    total_edges = sum(len(neighbors) for neighbors in adj.values()) // 2

    # Degree distribution
    degrees = {node: len(adj.get(node, set())) for node in nodes}
    avg_degree = sum(degrees.values()) / len(degrees) if degrees else 0
    max_node = max(degrees, key=degrees.get) if degrees else None

    # Connected components via BFS
    visited = set()
    components = []
    for node in nodes:
        if node not in visited:
            component = set()
            queue = [node]
            while queue:
                n = queue.pop(0)
                if n in visited:
                    continue
                visited.add(n)
                component.add(n)
                for neighbor in adj.get(n, set()):
                    if neighbor not in visited:
                        queue.append(neighbor)
            components.append(component)

    components.sort(key=len, reverse=True)

    # Isolated nodes (degree 0)
    isolated = [n for n in nodes if degrees.get(n, 0) == 0]

    return {
        "total_nodes": len(nodes),
        "total_edges": total_edges,
        "avg_degree": round(avg_degree, 2),
        "max_degree_node": max_node,
        "max_degree": degrees.get(max_node, 0) if max_node else 0,
        "num_components": len(components),
        "largest_component_size": len(components[0]) if components else 0,
        "largest_component_pct": round(
            len(components[0]) / len(nodes) * 100, 1
        ) if components and nodes else 0,
        "isolated_nodes": sorted(isolated),
        "component_sizes": [len(c) for c in components[:10]],
    }


# ── Failure analysis ─────────────────────────────────────────────────────

def failure_analysis(per_query: List[Dict], adj: Dict) -> Dict:
    """Identify systematic failure modes."""
    all_bm25_retrieved = set()
    all_ppr_retrieved = set()
    all_hybrid_retrieved = set()
    all_embed_retrieved = set()
    all_unified_retrieved = set()
    for q in per_query:
        all_bm25_retrieved.update(q["bm25"]["retrieved"])
        all_ppr_retrieved.update(q["ppr"]["retrieved"])
        all_hybrid_retrieved.update(q["hybrid"]["retrieved"])
        all_embed_retrieved.update(q["embeddings"]["retrieved"])
        all_unified_retrieved.update(q["unified"]["retrieved"])

    all_gold = set()
    for _, gold in BENCHMARK_QUERIES:
        all_gold.update(gold)

    never_retrieved_bm25 = all_gold - all_bm25_retrieved
    never_retrieved_ppr = all_gold - all_ppr_retrieved
    never_retrieved_hybrid = all_gold - all_hybrid_retrieved
    never_retrieved_embed = all_gold - all_embed_retrieved
    never_retrieved_unified = all_gold - all_unified_retrieved

    # Per-query zero-precision count
    zero_p5_bm25 = sum(1 for q in per_query if q["bm25"]["p@5"] == 0)
    zero_p5_ppr = sum(1 for q in per_query if q["ppr"]["p@5"] == 0)
    zero_p5_hybrid = sum(1 for q in per_query if q["hybrid"]["p@5"] == 0)
    zero_p5_embed = sum(1 for q in per_query if q["embeddings"]["p@5"] == 0)
    zero_p5_unified = sum(1 for q in per_query if q["unified"]["p@5"] == 0)

    # Gold set size distribution
    gold_sizes = [q["gold_size"] for q in per_query]

    # Document length analysis (are short docs harder to retrieve?)
    documents = load_all_shadow_docs()
    doc_lengths = {doc_id: len(text.split()) for doc_id, text in documents.items()}

    retrieved_lengths = []
    missed_lengths = []
    for q in per_query:
        gold_set = set(q["gold"])
        for doc_id in q["bm25"]["retrieved"][:5]:
            if doc_id in gold_set:
                retrieved_lengths.append(doc_lengths.get(doc_id, 0))
            else:
                missed_lengths.append(doc_lengths.get(doc_id, 0))

    return {
        "never_retrieved_bm25": sorted(never_retrieved_bm25),
        "never_retrieved_ppr": sorted(never_retrieved_ppr),
        "never_retrieved_hybrid": sorted(never_retrieved_hybrid),
        "never_retrieved_embed": sorted(never_retrieved_embed),
        "never_retrieved_unified": sorted(never_retrieved_unified),
        "zero_precision_queries": {
            "bm25": zero_p5_bm25,
            "ppr": zero_p5_ppr,
            "hybrid": zero_p5_hybrid,
            "embeddings": zero_p5_embed,
            "unified": zero_p5_unified,
        },
        "gold_set_sizes": {
            "min": min(gold_sizes),
            "max": max(gold_sizes),
            "avg": round(sum(gold_sizes) / len(gold_sizes), 1),
        },
        "doc_length_stats": {
            "retrieved_avg_words": round(
                sum(retrieved_lengths) / len(retrieved_lengths), 0
            ) if retrieved_lengths else 0,
            "missed_avg_words": round(
                sum(missed_lengths) / len(missed_lengths), 0
            ) if missed_lengths else 0,
            "total_docs": len(doc_lengths),
        },
    }


# ── Markdown output ──────────────────────────────────────────────────────

def format_paper_table(per_query: List[Dict]) -> str:
    """Format Table 1: Per-query P@5 for all contenders with BM25 confidence."""
    lines = []
    lines.append("### Table 1: Per-Query Precision@5 and BM25 Confidence")
    lines.append("")
    lines.append("| # | Query (truncated) | Gold | Conf | BM25 | PPR | Hybrid | Embed | Unified |")
    lines.append("|---|-------------------|------|------|------|-----|--------|-------|---------|")
    for q in per_query:
        qi = q["query_idx"]
        query = q["query_text"][:50]
        gs = q["gold_size"]
        conf = q["bm25_confidence"]
        bm25 = q["bm25"]["p@5"]
        ppr = q["ppr"]["p@5"]
        hybrid = q["hybrid"]["p@5"]
        embed = q["embeddings"]["p@5"]
        unified = q["unified"]["p@5"]
        lines.append(f"| {qi+1} | {query} | {gs} | {conf:.2f} | {bm25:.3f} | {ppr:.3f} | {hybrid:.3f} | {embed:.3f} | {unified:.3f} |")
    lines.append("")
    return "\n".join(lines)


def format_summary_table(results: Dict[str, Dict]) -> str:
    """Format Table 2: Aggregate results."""
    lines = []
    lines.append("### Table 2: Aggregate Retrieval Quality")
    lines.append("")
    lines.append("| Contender | P@1 | P@3 | P@5 | P@10 | R@1 | R@3 | R@5 | R@10 | Latency (ms) |")
    lines.append("|-----------|-----|-----|-----|------|-----|-----|-----|------|-------------|")
    for name in ["BM25", "PPR", "Hybrid", "Embeddings", "Unified"]:
        r = results[name]
        p = r["precision"]
        rec = r["recall"]
        lat = r["avg_latency_ms"]
        lines.append(
            f"| {name} | {p[1]:.3f} | {p[3]:.3f} | {p[5]:.3f} | {p[10]:.3f} | "
            f"{rec[1]:.3f} | {rec[3]:.3f} | {rec[5]:.3f} | {rec[10]:.3f} | {lat:.1f} |"
        )
    lines.append("")
    return "\n".join(lines)


def format_diagnostics(graph_diag: Dict, failure: Dict) -> str:
    """Format diagnostic section."""
    lines = []
    lines.append("### Graph Diagnostics")
    lines.append("")
    lines.append(f"- **Nodes**: {graph_diag['total_nodes']}")
    lines.append(f"- **Edges**: {graph_diag['total_edges']}")
    lines.append(f"- **Avg degree**: {graph_diag['avg_degree']}")
    lines.append(f"- **Max degree**: {graph_diag['max_degree']} ({graph_diag['max_degree_node']})")
    lines.append(f"- **Components**: {graph_diag['num_components']}")
    lines.append(f"- **Largest component**: {graph_diag['largest_component_size']} nodes ({graph_diag['largest_component_pct']}%)")
    lines.append(f"- **Isolated nodes**: {len(graph_diag['isolated_nodes'])}")
    if graph_diag["isolated_nodes"]:
        for node in graph_diag["isolated_nodes"][:10]:
            lines.append(f"  - {node}")
    lines.append(f"- **Component sizes**: {graph_diag['component_sizes']}")
    lines.append("")

    lines.append("### Failure Analysis")
    lines.append("")
    lines.append(f"- **Gold set sizes**: {failure['gold_set_sizes']['min']}-{failure['gold_set_sizes']['max']} (avg {failure['gold_set_sizes']['avg']})")
    lines.append(f"- **Queries with P@5=0**: BM25={failure['zero_precision_queries']['bm25']}, PPR={failure['zero_precision_queries']['ppr']}, Hybrid={failure['zero_precision_queries']['hybrid']}, Unified={failure['zero_precision_queries']['unified']}")
    lines.append(f"- **Gold docs never retrieved by BM25**: {len(failure['never_retrieved_bm25'])}")
    for doc_id in failure["never_retrieved_bm25"]:
        lines.append(f"  - {doc_id}")
    lines.append(f"- **Gold docs never retrieved by Hybrid**: {len(failure['never_retrieved_hybrid'])}")
    for doc_id in failure["never_retrieved_hybrid"]:
        lines.append(f"  - {doc_id}")
    lines.append(f"- **Gold docs never retrieved by Unified**: {len(failure['never_retrieved_unified'])}")
    for doc_id in failure["never_retrieved_unified"]:
        lines.append(f"  - {doc_id}")
    lines.append(f"- **Doc length bias**: retrieved avg={failure['doc_length_stats']['retrieved_avg_words']}w, missed avg={failure['doc_length_stats']['missed_avg_words']}w")
    lines.append("")

    return "\n".join(lines)


# ── Main ─────────────────────────────────────────────────────────────────

def run_evaluation() -> Dict:
    """Run full evaluation, print results, return data."""
    from lib.memory.benchmark import run_benchmark

    print("=" * 70)
    print("  COLD-LAYER RETRIEVAL EVALUATION")
    print("=" * 70)

    # 1. Aggregate benchmark (BM25, PPR, Hybrid)
    print("\n[1/4] Running aggregate benchmark...")
    agg_results = run_benchmark()

    # 2. Per-query analysis (includes embeddings)
    print("\n[2/4] Running per-query analysis...")
    per_query = run_per_query_analysis()

    # 3. Compute embedding + unified aggregate from per-query data
    n = len(per_query)
    for contender in ["embeddings", "unified"]:
        agg = {"precision": {}, "recall": {}, "avg_latency_ms": 0.0}
        for k in [1, 3, 5, 10]:
            total_p = sum(
                precision_at_k(q[contender]["retrieved"], set(q["gold"]), k)
                for q in per_query
            )
            total_r = sum(
                recall_at_k(q[contender]["retrieved"], set(q["gold"]), k)
                for q in per_query
            )
            agg["precision"][k] = total_p / n
            agg["recall"][k] = total_r / n
        agg_results[contender.capitalize()] = agg

    # 4. Graph diagnostics
    print("\n[3/4] Analyzing graph structure...")
    adj = build_shadow_graph()
    graph_diag = graph_diagnostics(adj)

    # 5. Failure analysis
    print("\n[4/4] Analyzing failure modes...")
    failure = failure_analysis(per_query, adj)

    # Print results
    print("\n" + format_summary_table(agg_results))
    print(format_paper_table(per_query))
    print(format_diagnostics(graph_diag, failure))

    return {
        "aggregate": agg_results,
        "per_query": per_query,
        "graph": graph_diag,
        "failure": failure,
    }


if __name__ == "__main__":
    data = run_evaluation()
