"""Island manager for the ILHA/PEDRA memory system.

Ported from Grilo Falante v3 (app/ilhas/gerenciador.py).
Uses file-based storage instead of PostgreSQL/MemPalace.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any

from lib.epistemic.memory.estados import EstadoIlha, TipoRelacao
from lib.epistemic.memory.models import Ilha, Pedra, MembroIlha, RelacaoIlha


class ArmazenamentoIlhas:
    def __init__(self, path: Path):
        self.path = path
        self.path.mkdir(parents=True, exist_ok=True)

    def _ilha_path(self, ilha_id: str) -> Path:
        return self.path / f"{ilha_id}.json"

    def criar(self, ilha: Ilha) -> None:
        p = self._ilha_path(ilha.id)
        p.write_text(json.dumps(ilha.para_dict(), indent=2, ensure_ascii=False))

    def obter(self, ilha_id: str) -> Optional[Ilha]:
        p = self._ilha_path(ilha_id)
        if not p.exists():
            return None
        return Ilha.de_dict(json.loads(p.read_text()))

    def atualizar(self, ilha: Ilha) -> None:
        self.criar(ilha)

    def listar(self, estado: Optional[str] = None, limit: int = 100) -> List[Ilha]:
        resultado = []
        for p in sorted(self.path.glob("ILHA-*.json"))[:limit]:
            ilha = Ilha.de_dict(json.loads(p.read_text()))
            if estado is None or ilha.estado.value == estado:
                resultado.append(ilha)
        return resultado

    def listar_ativas(self, threshold: float = 0.5) -> List[Ilha]:
        return [i for i in self.listar() if i.score_ativacao >= threshold]

    def remover(self, ilha_id: str) -> bool:
        p = self._ilha_path(ilha_id)
        if p.exists():
            p.unlink()
            return True
        return False

    def adicionar_membro(self, ilha_id: str, membro: MembroIlha) -> bool:
        ilha = self.obter(ilha_id)
        if not ilha:
            return False
        ilha.adicionar_membro(membro)
        self.atualizar(ilha)
        return True


class GestorIlhas:
    def __init__(self, armazenamento: ArmazenamentoIlhas):
        self.armazenamento = armazenamento

    def criar_ilha_de_pedra(self, pedra: Pedra) -> Ilha:
        ilha = Ilha.criar_de_pedra(pedra)
        ilha.estado = EstadoIlha.EMBRIONARIA
        self.armazenamento.criar(ilha)
        return ilha

    def adicionar_membro(self, ilha_id: str, membro: MembroIlha) -> bool:
        ilha = self.armazenamento.obter(ilha_id)
        if not ilha:
            return False
        if ilha.tem_membro(membro.member_id):
            return True
        ilha.adicionar_membro(membro)
        self.armazenamento.atualizar(ilha)
        return True

    def remover_membro(self, ilha_id: str, member_id: str) -> bool:
        ilha = self.armazenamento.obter(ilha_id)
        if not ilha:
            return False
        if ilha.remover_membro(member_id):
            self.armazenamento.atualizar(ilha)
            return True
        return False

    def combinar_ilhas(
        self,
        ilha1_id: str,
        ilha2_id: str,
        forca_relacao: float = 0.8,
    ) -> Optional[Ilha]:
        ilha1 = self.armazenamento.obter(ilha1_id)
        ilha2 = self.armazenamento.obter(ilha2_id)
        if not ilha1 or not ilha2:
            return None
        for membro in ilha2.membros:
            if not ilha1.tem_membro(membro.member_id):
                ilha1.adicionar_membro(membro)
        relacao = RelacaoIlha(
            ilha_id=ilha2_id,
            tipo=TipoRelacao.AGREGADO_EM,
            forca=forca_relacao,
        )
        ilha1.adicionar_relacao(relacao)
        ilha1.grau_consolidacao = min(
            1.0, (ilha1.grau_consolidacao + ilha2.grau_consolidacao) / 2
        )
        ilha1.score_ativacao = max(ilha1.score_ativacao, ilha2.score_ativacao)
        if len(ilha2.membros) >= 10:
            ilha1.estado = EstadoIlha.CONSOLIDADA
        self.armazenamento.atualizar(ilha1)
        ilha2.estado = EstadoIlha.DORMINTE
        self.armazenamento.atualizar(ilha2)
        return ilha1

    def obter_ilha(self, ilha_id: str) -> Optional[Ilha]:
        return self.armazenamento.obter(ilha_id)

    def listar_ilhas(self, estado: Optional[str] = None, limit: int = 100) -> List[Ilha]:
        return self.armazenamento.listar(estado=estado, limit=limit)

    def listar_ativas(self, threshold: float = 0.5) -> List[Ilha]:
        return self.armazenamento.listar_ativas(threshold=threshold)

    def actualizar_estado_ilha(self, ilha_id: str, novo_estado: EstadoIlha) -> bool:
        ilha = self.armazenamento.obter(ilha_id)
        if not ilha:
            return False
        ilha.estado = novo_estado
        self.armazenamento.atualizar(ilha)
        return True

    def adicionar_lacuna(self, ilha_id: str, lacuna: str) -> bool:
        ilha = self.armazenamento.obter(ilha_id)
        if not ilha:
            return False
        if lacuna not in ilha.lacunas_identificadas:
            ilha.lacunas_identificadas.append(lacuna)
            self.armazenamento.atualizar(ilha)
        return True

    def get_resumo_sistema(self) -> Dict[str, Any]:
        todas = self.listar_ilhas(limit=1000)
        activas = [i for i in todas if i.score_ativacao >= 0.5]
        erodindo = [i for i in todas if 0.1 <= i.score_ativacao < 0.5]
        dormintes = [i for i in todas if i.score_ativacao < 0.1]
        return {
            "total_ilhas": len(todas),
            "activas": len(activas),
            "erodindo": len(erodindo),
            "dormintes": len(dormintes),
            "total_membros": sum(len(i.membros) for i in todas),
            "total_lacunas": sum(len(i.lacunas_identificadas) for i in todas),
        }
