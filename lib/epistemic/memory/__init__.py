"""ILHA/PEDRA memory system — epistemic memory islands.

Ported from Grilo Falante v3 (app/ilhas/, app/ontology/) as part of AES
self-containment. All persistence uses local file storage (no DB, no MemPalace).
"""

from lib.epistemic.memory.estados import (
    EstadoIlha,
    EstadoPedra,
    EstadoClaim,
    EstadoArtefacto,
    TipoInteracao,
    TipoRelacao,
)

from lib.epistemic.memory.models import (
    Saliencia,
    Pedra,
    MembroIlha,
    RelacaoIlha,
    HistoricoReativacao,
    Ilha,
    Claim,
)

from lib.epistemic.memory.saliencia import (
    CalculadorSaliencia,
    CalculadorFrequencia,
    CalculadorIntensidade,
    CalculadorNovidade,
    CalculadorRelevancia,
    calcular_saliencia_completa,
)

from lib.epistemic.memory.erosao import (
    DinamicaErosao,
    GestorReativacoes,
)

from lib.epistemic.memory.gerenciador import (
    ArmazenamentoIlhas,
    GestorIlhas,
)

from lib.epistemic.memory.relacoes import (
    CalculadorSimilaridade,
    GestorRelacoes,
    sugerir_agregacoes_batch,
)

from lib.epistemic.memory.dormir import (
    ProcessadorBatch,
    ir_dormir,
)

from lib.epistemic.memory.nanopub_bridge import (
    criar_claims,
)

__all__ = [
    "EstadoIlha",
    "EstadoPedra",
    "EstadoClaim",
    "EstadoArtefacto",
    "TipoInteracao",
    "TipoRelacao",
    "Saliencia",
    "Pedra",
    "MembroIlha",
    "RelacaoIlha",
    "HistoricoReativacao",
    "Ilha",
    "Claim",
    "CalculadorSaliencia",
    "CalculadorFrequencia",
    "CalculadorIntensidade",
    "CalculadorNovidade",
    "CalculadorRelevancia",
    "calcular_saliencia_completa",
    "DinamicaErosao",
    "GestorReativacoes",
    "ArmazenamentoIlhas",
    "GestorIlhas",
    "CalculadorSimilaridade",
    "GestorRelacoes",
    "sugerir_agregacoes_batch",
    "ProcessadorBatch",
    "ir_dormir",
    "criar_claims",
]
