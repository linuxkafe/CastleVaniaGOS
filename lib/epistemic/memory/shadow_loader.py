"""Load shadow docs into ILHA/PEDRA memory.

Each shadow doc (SD-*.md) becomes an interaction for the ILHA sleep cycle.
Salience is computed from frontmatter metadata — epistemic_state, centrality,
tags, pinned status — not from human scoring.
"""

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end == -1:
        return {}, text
    import yaml
    try:
        meta = yaml.safe_load("\n".join(lines[1:end]))
    except Exception:
        meta = {}
    body = "\n".join(lines[end + 1:])
    return meta if isinstance(meta, dict) else {}, body


def update_last_accessed(path: Path) -> None:
    """Update last_accessed timestamp in a shadow doc's frontmatter."""
    text = path.read_text(encoding="utf-8")
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    new_text = re.sub(
        r"^last_accessed:.*$",
        f"last_accessed: {now}",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if new_text != text:
        path.write_text(new_text, encoding="utf-8")


def _compute_salience(meta: Dict[str, Any], body: str) -> Dict[str, float]:
    epistemic_state = meta.get("epistemic_state", "")
    centrality = meta.get("score", {}).get("centrality", 1.0)
    activation = meta.get("score", {}).get("activation", 0.5)
    pinned = meta.get("score", {}).get("pinned", False)
    tags = meta.get("tags", [])

    state_map = {
        "SUPORTADA": 0.9,
        "VERIFICADA": 0.8,
        "VERIFICADO": 0.8,
        "NÃO-VERIFICÁVEL": 0.5,
        "NAO-VERIFICAVEL": 0.5,
        "FALSIFICADO": 0.2,
        "FALSIFICADA": 0.2,
        "ABERTO": 0.6,
        "INFERIDA": 0.4,
        "ASSUMED": 0.3,
        "DESCONHECIDO": 0.3,
    }
    base_intensidade = state_map.get(epistemic_state, 0.5)

    pinned_bonus = 0.2 if pinned else 0.0
    intensidade = min(1.0, base_intensidade + pinned_bonus)

    frequencia = 0.9 if pinned else 0.5

    tag_set = {t.lower() for t in tags}
    if "hostile" in tag_set or "insight" in tag_set:
        novidade = 0.9
    elif "finding" in tag_set:
        novidade = 0.8
    elif "reflex" in tag_set or "import" in tag_set:
        novidade = 0.6
    else:
        novidade = 0.5

    relevancia = min(1.0, (centrality / 3.0) * 0.6 + (activation * 0.4))

    body_words = len(body.split())
    precoes = max(1, min(15, body_words // 30))
    reaccoes = precoes + (5 if pinned else 0)

    return {
        "frequencia": frequencia,
        "intensidade": intensidade,
        "novidade": novidade,
        "relevancia": relevancia,
        "reaccoes": reaccoes,
    }


def _extract_conteudo(meta: Dict[str, Any], body: str) -> str:
    title = meta.get("title", meta.get("id", ""))
    synthesis = meta.get("synthesis", "")
    body_clean = re.sub(r"^#+\s+.*$", "", body, flags=re.MULTILINE).strip()
    body_short = " ".join(body_clean.split())[:500]
    parts = [p for p in [title, synthesis, body_short] if p]
    return " — ".join(parts)


def shadow_doc_to_interacao(path: Path) -> Optional[Dict[str, Any]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    meta, body = _parse_frontmatter(text)
    sd_id = meta.get("id", path.stem)
    saliencia = _compute_salience(meta, body)
    conteudo = _extract_conteudo(meta, body)
    tags = meta.get("tags", [])

    return {
        "tipo": "SHADOW_DOC",
        "conteudo": conteudo,
        "sd_id": sd_id,
        "frequencia": saliencia["frequencia"],
        "intensidade": saliencia["intensidade"],
        "novidade": saliencia["novidade"],
        "relevancia": saliencia["relevancia"],
        "reaccoes": saliencia["reaccoes"],
        "epistemic_state": meta.get("epistemic_state", "DESCONHECIDO"),
        "tags": tags,
    }


def carregar_shadow_docs(shadow_dir: Path) -> List[Dict[str, Any]]:
    interacoes = []
    for p in sorted(shadow_dir.glob("SD-*.md")):
        if p.name == "README.md" or p.name == "index.md":
            continue
        interacao = shadow_doc_to_interacao(p)
        if interacao:
            update_last_accessed(p)
            interacoes.append(interacao)
    return interacoes


def processar_shadow_docs(
    shadow_dir: Path,
    armazenamento: Any,
    session_id: str,
) -> Dict[str, Any]:
    from lib.epistemic.memory.dormir import ir_dormir

    interacoes = carregar_shadow_docs(shadow_dir)
    if not interacoes:
        return {
            "sucesso": True,
            "message": "No shadow docs found",
            "total": 0,
        }
    report = ir_dormir(armazenamento, session_id, interacoes)
    report["shadow_docs_carregados"] = len(interacoes)

    from lib.epistemic.memory.nanopub_bridge import criar_claims
    try:
        claims_added = criar_claims(interacoes, armazenamento, session_id)
        report["claims_adicionados"] = claims_added
    except Exception as e:
        report["claims_adicionados"] = 0
        report["aviso_claims"] = str(e)

    return report


def bootstrap_shadow_docs_as_ilhas(
    shadow_dir: Path,
    armazenamento: Any,
) -> Dict[str, Any]:
    """Create ilhas from shadow docs with extracted claims.

    Each shadow doc becomes an ilha. Claims are extracted from the
    shadow doc content using GMIF classification (M1-M7).
    This is the one-time bootstrap for the memory system.
    """
    from lib.epistemic.memory.models import Ilha, MembroIlha, Saliencia
    from lib.epistemic.memory.estados import EstadoIlha
    import uuid
    import re

    interacoes = carregar_shadow_docs(shadow_dir)
    if not interacoes:
        return {"sucesso": True, "ilhas_criadas": 0, "message": "No shadow docs"}

    existing = {i.id for i in armazenamento.listar(limit=200)}
    created = 0
    skipped = 0

    for inter in interacoes:
        sd_id = inter.get("sd_id", str(uuid.uuid4())[:8])
        ilha_id = f"ilha-{sd_id}"

        if ilha_id in existing:
            skipped += 1
            continue

        conteudo = inter.get("conteudo", "")
        title = conteudo.split(" — ")[0] if " — " in conteudo else sd_id

        claims = _extract_claims_from_content(conteudo, sd_id)
        if not claims:
            skipped += 1
            continue

        saliencia = Saliencia(
            valor=inter.get("relevancia", 0.5),
            frequencia=inter.get("frequencia", 0.5),
            intensidade=inter.get("intensidade", 0.5),
            novidade=inter.get("novidade", 0.5),
            relevancia=inter.get("relevancia", 0.5),
        )

        ilha = Ilha(
            id=ilha_id,
            nome=title[:100],
            descricao=conteudo[:500],
            estado=EstadoIlha.ATIVA,
            score_ativacao=saliencia.valor,
            artefactos_fundadores=[sd_id],
        )

        for claim_text in claims:
            claim_id = f"claim-{sd_id}-{uuid.uuid4().hex[:6]}"
            membro = MembroIlha(
                member_id=claim_id,
                tipo="claim",
                saliencia=saliencia.valor,
                inserido_por="bootstrap",
            )
            membro.conteudo = claim_text
            ilha.adicionar_membro(membro)

        armazenamento.criar(ilha)
        created += 1

    return {
        "sucesso": True,
        "ilhas_criadas": created,
        "ilhas_skipped": skipped,
        "total_shadow_docs": len(interacoes),
    }


def _extract_claims_from_content(content: str, sd_id: str) -> list:
    """Extract claims from shadow doc content.

    Claims are extracted from:
    1. Headings (## level) as primary claims
    2. First paragraph of each section as supporting claims
    """
    if not content or len(content.strip()) < 20:
        return []

    claims = []
    lines = content.split("\n")
    current_section = None

    for line in lines:
        line = line.strip()
        if not line:
            continue

        if line.startswith("## "):
            heading = line[3:].strip()
            if heading and len(heading) > 5:
                claims.append(heading)
                current_section = heading
        elif line.startswith("### "):
            heading = line[4:].strip()
            if heading and len(heading) > 5:
                claims.append(heading)

    if not claims and lines:
        for line in lines:
            line = line.strip()
            if line and len(line) > 20 and not line.startswith("#") and not line.startswith("---"):
                claims.append(line[:200])
                break

    return claims[:5]
