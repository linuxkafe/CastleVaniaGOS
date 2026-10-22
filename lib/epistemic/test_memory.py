"""Unit tests for the ILHA/PEDRA memory system.

Split from test_memory.py for maintainability (T163).
"""

from pathlib import Path
from datetime import datetime, timedelta

import pytest

from lib.epistemic.memory.estados import (
    EstadoIlha,
    EstadoPedra,
    EstadoClaim,
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
)
from lib.epistemic.memory.dormir import (
    ProcessadorBatch,
    ir_dormir,
)

# Re-export for backward compatibility
from lib.epistemic.test_memory_models import TestSaliencia  # noqa: F401
from lib.epistemic.test_memory_models import TestPedra  # noqa: F401
from lib.epistemic.test_memory_models import TestIlha  # noqa: F401
from lib.epistemic.test_memory_models import TestClaim  # noqa: F401
from lib.epistemic.test_memory_saliencia import TestCalculadorSaliencia  # noqa: F401
from lib.epistemic.test_memory_saliencia import TestCalculadorFrequencia  # noqa: F401
from lib.epistemic.test_memory_saliencia import TestCalculadorIntensidade  # noqa: F401
from lib.epistemic.test_memory_saliencia import TestCalculadorNovidade  # noqa: F401
from lib.epistemic.test_memory_saliencia import TestCalculadorRelevancia  # noqa: F401
from lib.epistemic.test_memory_saliencia import TestCalcularSalienciaCompleta  # noqa: F401
from lib.epistemic.test_memory_erosao import TestDinamicaErosao  # noqa: F401
from lib.epistemic.test_memory_erosao import TestGestorReativacoes  # noqa: F401
from lib.epistemic.test_memory_gerenciador import TestArmazenamentoIlhas  # noqa: F401
from lib.epistemic.test_memory_gerenciador import TestGestorIlhas  # noqa: F401
from lib.epistemic.test_memory_relacoes import TestCalculadorSimilaridade  # noqa: F401
from lib.epistemic.test_memory_relacoes import TestGestorRelacoes  # noqa: F401
from lib.epistemic.test_memory_batch import TestProcessadorBatch  # noqa: F401
