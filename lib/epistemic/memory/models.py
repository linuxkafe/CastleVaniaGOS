"""Data models for the ILHA/PEDRA memory system.

Ported from Grilo Falante v3 (app/ontology/ilhas.py).
"""

import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

from lib.epistemic.memory.estados import (
    EstadoIlha,
    EstadoPedra,
    EstadoClaim,
    TipoInteracao,
    TipoRelacao,
)

_PESOS_PADRAO = {
    "frequencia": 0.3,
    "intensidade": 0.3,
    "novidade": 0.2,
    "relevancia": 0.2,
}


@dataclass
class Saliencia:
    valor: float = 0.0
    frequencia: float = 0.0
    intensidade: float = 0.0
    novidade: float = 0.0
    relevancia: float = 0.0

    @classmethod
    def calcular(
        cls,
        frequencia: float,
        intensidade: float,
        novidade: float,
        relevancia: float,
        pesos: Optional[Dict[str, float]] = None,
    ) -> "Saliencia":
        pesos = pesos or _PESOS_PADRAO
        valor = (
            pesos["frequencia"] * frequencia
            + pesos["intensidade"] * intensidade
            + pesos["novidade"] * novidade
            + pesos["relevancia"] * relevancia
        )
        return cls(
            valor=min(1.0, max(0.0, valor)),
            frequencia=frequencia,
            intensidade=intensidade,
            novidade=novidade,
            relevancia=relevancia,
        )

    def para_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: Dict[str, Any]) -> "Saliencia":
        return cls(**d)


@dataclass
class Pedra:
    id: str = field(default_factory=lambda: f"PEDRA-{uuid.uuid4().hex[:8]}")
    tipo_interacao: TipoInteracao = TipoInteracao.MENSAGEM
    saliencia: Saliencia = field(default_factory=Saliencia)
    impacto_criou_ilha: bool = False
    ilha_criada: Optional[str] = None
    impacto_ilhas_existentes: List[Dict] = field(default_factory=list)
    data_criacao: datetime = field(default_factory=datetime.now)
    ultima_reativacao: datetime = field(default_factory=datetime.now)
    contagem_reacoes: int = 0
    conteudo_original: str = ""
    embedding: Optional[List[float]] = None
    estado: EstadoPedra = EstadoPedra.NOVA

    def reativar(self) -> None:
        self.ultima_reativacao = datetime.now()
        self.contagem_reacoes += 1

    def transformar_em_ilha(self) -> "Ilha":
        self.estado = EstadoPedra.TRANSFORMADA
        self.impacto_criou_ilha = True
        return Ilha.criar_de_pedra(self)

    def agregar_a_ilha(self, ilha_id: str) -> None:
        self.estado = EstadoPedra.AGREGADA

    def esta_agregada(self) -> bool:
        return self.estado == EstadoPedra.AGREGADA

    def esta_transformada(self) -> bool:
        return self.estado == EstadoPedra.TRANSFORMADA

    def para_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tipo_interacao": self.tipo_interacao.value,
            "saliencia": self.saliencia.para_dict(),
            "impacto_criou_ilha": self.impacto_criou_ilha,
            "ilha_criada": self.ilha_criada,
            "data_criacao": self.data_criacao.isoformat(),
            "ultima_reativacao": self.ultima_reativacao.isoformat(),
            "contagem_reacoes": self.contagem_reacoes,
            "conteudo_original": self.conteudo_original,
            "estado": self.estado.value,
        }

    @classmethod
    def de_dict(cls, d: Dict[str, Any]) -> "Pedra":
        return cls(
            id=d["id"],
            tipo_interacao=TipoInteracao(d["tipo_interacao"]),
            saliencia=Saliencia.de_dict(d["saliencia"]),
            impacto_criou_ilha=d["impacto_criou_ilha"],
            ilha_criada=d.get("ilha_criada"),
            data_criacao=datetime.fromisoformat(d["data_criacao"]),
            ultima_reativacao=datetime.fromisoformat(d["ultima_reativacao"]),
            contagem_reacoes=d["contagem_reacoes"],
            conteudo_original=d.get("conteudo_original", ""),
            estado=EstadoPedra(d["estado"]),
        )


@dataclass
class MembroIlha:
    member_id: str
    tipo: str
    saliencia: float
    data_insercao: datetime = field(default_factory=datetime.now)
    inserido_por: str = ""

    def para_dict(self) -> Dict[str, Any]:
        return {
            "member_id": self.member_id,
            "tipo": self.tipo,
            "saliencia": self.saliencia,
            "data_insercao": self.data_insercao.isoformat(),
            "inserido_por": self.inserido_por,
        }

    @classmethod
    def de_dict(cls, d: Dict[str, Any]) -> "MembroIlha":
        return cls(
            member_id=d["member_id"],
            tipo=d["tipo"],
            saliencia=d.get("saliencia", 0.0),
            data_insercao=datetime.fromisoformat(d["data_insercao"]),
            inserido_por=d.get("inserido_por", ""),
        )


@dataclass
class RelacaoIlha:
    ilha_id: str
    tipo: TipoRelacao
    forca: float

    def para_dict(self) -> Dict[str, Any]:
        return {
            "ilha_id": self.ilha_id,
            "tipo": self.tipo.value,
            "forca": self.forca,
        }

    @classmethod
    def de_dict(cls, d: Dict[str, Any]) -> "RelacaoIlha":
        return cls(
            ilha_id=d["ilha_id"],
            tipo=TipoRelacao(d["tipo"]),
            forca=d["forca"],
        )


@dataclass
class HistoricoReativacao:
    data: datetime = field(default_factory=datetime.now)
    tipo: str = ""
    session_id: str = ""

    def para_dict(self) -> Dict[str, Any]:
        return {
            "data": self.data.isoformat(),
            "tipo": self.tipo,
            "session_id": self.session_id,
        }

    @classmethod
    def de_dict(cls, d: Dict[str, Any]) -> "HistoricoReativacao":
        return cls(
            data=datetime.fromisoformat(d["data"]),
            tipo=d.get("tipo", ""),
            session_id=d.get("session_id", ""),
        )


@dataclass
class Ilha:
    id: str = field(default_factory=lambda: f"ILHA-{uuid.uuid4().hex[:8]}")
    nome: str = ""
    descricao: str = ""
    artefactos_fundadores: List[str] = field(default_factory=list)
    membros: List[MembroIlha] = field(default_factory=list)
    relacoes: List[RelacaoIlha] = field(default_factory=list)
    grau_consolidacao: float = 0.0
    score_ativacao: float = 0.0
    estado: EstadoIlha = EstadoIlha.EMBRIONARIA
    data_criacao: datetime = field(default_factory=datetime.now)
    historico_reativacoes: List[HistoricoReativacao] = field(default_factory=list)
    claims_validadas: int = 0
    claims_pendentes: int = 0
    lacunas_identificadas: List[str] = field(default_factory=list)

    @classmethod
    def criar_de_pedra(cls, pedra: Pedra) -> "Ilha":
        conteudo = pedra.conteudo_original or ""
        nome = f"Ilha {pedra.id}"
        descricao = conteudo[:200]
        if " — " in conteudo:
            nome = conteudo.split(" — ")[0].strip()[:60]
        ilha = cls(nome=nome, descricao=descricao)
        ilha.artefactos_fundadores = [pedra.id]
        ilha.score_ativacao = pedra.saliencia.valor
        return ilha

    def adicionar_membro(self, membro: MembroIlha) -> None:
        if not self.tem_membro(membro.member_id):
            self.membros.append(membro)

    def remover_membro(self, member_id: str) -> bool:
        for i, m in enumerate(self.membros):
            if m.member_id == member_id:
                self.membros.pop(i)
                return True
        return False

    def tem_membro(self, member_id: str) -> bool:
        return any(m.member_id == member_id for m in self.membros)

    def adicionar_reativacao(self, tipo: str, session_id: str = "") -> None:
        self.historico_reativacoes.append(
            HistoricoReativacao(tipo=tipo, session_id=session_id)
        )

    @property
    def ultima_reativacao(self) -> datetime:
        if not self.historico_reativacoes:
            return self.data_criacao
        return max(r.data for r in self.historico_reativacoes)

    def calcular_score(self, _decay_factor: float = 0.95) -> float:
        if not self.historico_reativacoes:
            return 0.0
        agora = datetime.now()
        ultima = self.ultima_reativacao
        dias_desde = (agora - ultima).days
        recencia = max(0, 1 - (dias_desde * 0.1))
        frequencia = min(1.0, len(self.historico_reativacoes) / 20)
        relevancia = self.grau_consolidacao
        self.score_ativacao = 0.4 * recencia + 0.3 * frequencia + 0.3 * relevancia
        return self.score_ativacao

    def aplicar_decay(self, factor: float = 0.95) -> None:
        self.score_ativacao *= factor

    def adicionar_relacao(self, relacao: RelacaoIlha) -> None:
        if not self.tem_relacao(relacao.ilha_id):
            self.relacoes.append(relacao)

    def tem_relacao(self, ilha_id: str) -> bool:
        return any(r.ilha_id == ilha_id for r in self.relacoes)

    def e_ativa(self, threshold: float = 0.5) -> bool:
        return self.score_ativacao >= threshold

    def e_dorminte(self, threshold: float = 0.1) -> bool:
        return self.score_ativacao < threshold

    def para_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "nome": self.nome,
            "descricao": self.descricao,
            "estado": self.estado.value,
            "score_ativacao": self.score_ativacao,
            "grau_consolidacao": self.grau_consolidacao,
            "membros_count": len(self.membros),
            "artefactos_fundadores": self.artefactos_fundadores,
            "members": [m.para_dict() for m in self.membros],
            "relacoes": [r.para_dict() for r in self.relacoes],
            "historico_reativacoes": [h.para_dict() for h in self.historico_reativacoes],
            "claims_validadas": self.claims_validadas,
            "claims_pendentes": self.claims_pendentes,
            "lacunas": self.lacunas_identificadas,
            "data_criacao": self.data_criacao.isoformat(),
        }

    @classmethod
    def de_dict(cls, d: Dict[str, Any]) -> "Ilha":
        ilha = cls(
            id=d["id"],
            nome=d.get("nome", ""),
            descricao=d.get("descricao", ""),
            artefactos_fundadores=d.get("artefactos_fundadores", []),
            membros=[MembroIlha.de_dict(m) for m in d.get("members", [])],
            relacoes=[RelacaoIlha.de_dict(r) for r in d.get("relacoes", [])],
            grau_consolidacao=d.get("grau_consolidacao", 0.0),
            score_ativacao=d.get("score_ativacao", 0.0),
            estado=EstadoIlha(d["estado"]),
            data_criacao=datetime.fromisoformat(d["data_criacao"]),
            historico_reativacoes=[
                HistoricoReativacao.de_dict(h) for h in d.get("historico_reativacoes", [])
            ],
            claims_validadas=d.get("claims_validadas", 0),
            claims_pendentes=d.get("claims_pendentes", 0),
            lacunas_identificadas=d.get("lacunas", []),
        )
        return ilha


@dataclass
class Claim:
    id: str = field(default_factory=lambda: f"CLM-{uuid.uuid4().hex[:8]}")
    texto: str = ""
    tipo: str = "claim"
    gmif_level: str = "M3"
    gmif_confidence: float = 0.5
    estado: EstadoClaim = EstadoClaim.ESTRUTURAL
    session_id: str = ""
    data_criacao: datetime = field(default_factory=datetime.now)
    embedding: Optional[List[float]] = None
    sources: List[str] = field(default_factory=list)

    def para_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "texto": self.texto,
            "tipo": self.tipo,
            "gmif_level": self.gmif_level,
            "gmif_confidence": self.gmif_confidence,
            "estado": self.estado.value,
            "session_id": self.session_id,
            "data_criacao": self.data_criacao.isoformat(),
            "sources": self.sources,
        }

    @classmethod
    def de_dict(cls, d: Dict[str, Any]) -> "Claim":
        return cls(
            id=d["id"],
            texto=d.get("texto", ""),
            tipo=d.get("tipo", "claim"),
            gmif_level=d.get("gmif_level", "M3"),
            gmif_confidence=d.get("gmif_confidence", 0.5),
            estado=EstadoClaim(d.get("estado", "ESTRUTURAL")),
            session_id=d.get("session_id", ""),
            data_criacao=datetime.fromisoformat(d["data_criacao"]),
            embedding=d.get("embedding"),
            sources=d.get("sources", []),
        )
