"""Sleep cycle processor for the ILHA/PEDRA memory system.

Ported from Grilo Falante v3 (app/regime/dormir.py).
Sync version — no async, no DB, no MemPalace.
"""

from datetime import datetime
from typing import Dict, List, Any

from lib.epistemic.memory.estados import EstadoIlha
from lib.epistemic.memory.models import Pedra, Saliencia, MembroIlha
from lib.epistemic.memory.gerenciador import ArmazenamentoIlhas, GestorIlhas
from lib.epistemic.memory.saliencia import CalculadorSaliencia


class ProcessadorBatch:
    def __init__(self, armazenamento: ArmazenamentoIlhas):
        self.armazenamento = armazenamento
        self.gestor_ilhas = GestorIlhas(armazenamento)
        self.calculador_saliencia = CalculadorSaliencia()

    def executar(self, session_id: str, interacoes: List[Dict[str, Any]]) -> Dict[str, Any]:
        relatorio = {
            "session_id": session_id,
            "data": datetime.now().isoformat(),
            "passos_executados": [],
            "pedras_criadas": 0,
            "ilhas_criadas": 0,
            "ilhas_actualizadas": 0,
            "agregacoes_feitas": 0,
            "lacunas_identificadas": [],
            "sucesso": True,
            "erros": [],
        }
        try:
            relatorio["passos_executados"].append("COLETAR")
            relatorio["interacoes_recebidas"] = len(interacoes)

            pedras = self._identificar_pedras(interacoes)
            relatorio["pedras_criadas"] = len(pedras)
            relatorio["passos_executados"].append("IDENTIFICAR_PEDRAS")

            novas_ilhas = self._avaliar_transicao_pedras(pedras)
            relatorio["ilhas_criadas"] = len(novas_ilhas)
            relatorio["passos_executados"].append("AVALIAR_TRANSFORMACAO")

            agregacoes = self._agregar_em_ilhas(pedras, novas_ilhas)
            relatorio["agregacoes_feitas"] = agregacoes
            relatorio["passos_executados"].append("AGREGAR")

            actualizadas = self._actualizar_ilhas_existentes()
            relatorio["ilhas_actualizadas"] = actualizadas
            relatorio["passos_executados"].append("ACTUALIZAR_ILHAS")

            relatorio["passos_executados"].append("CONSOLIDAR")
            relatorio["passos_executados"].append("GUARDAR")
            relatorio["passos_executados"].append("RELATORIO")

        except Exception as e:
            relatorio["sucesso"] = False
            relatorio["erros"].append(str(e))

        return relatorio

    def _identificar_pedras(self, interacoes: List[Dict[str, Any]]) -> List[Pedra]:
        pedras = []
        for interacao in interacoes:
            saliencia = self.calculador_saliencia.calcular_de_interacao(interacao)
            tipo_str = interacao.get("tipo", "MENSAGEM")
            if saliencia.valor < 0.3:
                continue
            from lib.epistemic.memory.estados import TipoInteracao
            saliencia_final = Saliencia(
                valor=min(1.0, saliencia.valor * 1.25) if tipo_str == "SHADOW_DOC" else saliencia.valor,
                frequencia=saliencia.frequencia,
                intensidade=saliencia.intensidade,
                novidade=saliencia.novidade,
                relevancia=saliencia.relevancia,
            )
            pedra = Pedra(
                tipo_interacao=TipoInteracao(tipo_str),
                saliencia=saliencia_final,
                conteudo_original=interacao.get("conteudo", ""),
                contagem_reacoes=interacao.get("reaccoes", 0),
            )
            pedras.append(pedra)
        return pedras

    def _avaliar_transicao_pedras(self, pedras: List[Pedra]) -> List:
        novas_ilhas = []
        for pedra in pedras:
            if self._deve_transformar_em_ilha(pedra):
                ilha = pedra.transformar_em_ilha()
                self.armazenamento.criar(ilha)
                novas_ilhas.append(ilha)
        return novas_ilhas

    def _deve_transformar_em_ilha(self, pedra: Pedra) -> bool:
        if pedra.saliencia.valor < 0.8:
            return False
        if pedra.contagem_reacoes > 5 or pedra.impacto_criou_ilha:
            return True
        return False

    def _agregar_em_ilhas(self, pedras: List[Pedra], novas_ilhas: List) -> int:
        agregacoes = 0
        todas_ilhas = self.armazenamento.listar(limit=100)
        novas_ids = {i.id for i in novas_ilhas}
        for ilha_nova in novas_ilhas:
            if ilha_nova.id not in [i.id for i in todas_ilhas]:
                todas_ilhas.append(ilha_nova)

        for pedra in pedras:
            if pedra.esta_agregada() or pedra.esta_transformada():
                continue
            melhor_ilha = None
            melhor_score = 0.25
            ilhas_existentes = [i for i in todas_ilhas]
            from lib.epistemic.memory.relacoes import CalculadorSimilaridade
            calc = CalculadorSimilaridade()
            for ilha in ilhas_existentes:
                palavras_pedra = set(pedra.conteudo_original.lower().split())
                palavras_ilha = set(f"{ilha.nome} {ilha.descricao}".lower().split())
                overlap = len(palavras_pedra & palavras_ilha)
                uniao = len(palavras_pedra | palavras_ilha)
                score = overlap / uniao if uniao > 0 else 0
                if score > melhor_score:
                    melhor_score = score
                    melhor_ilha = ilha
            if melhor_ilha:
                membro = MembroIlha(
                    member_id=pedra.id,
                    tipo=pedra.tipo_interacao.value,
                    saliencia=pedra.saliencia.valor,
                    inserido_por="processador_batch",
                )
                melhor_ilha.adicionar_membro(membro)
                pedra.agregar_a_ilha(melhor_ilha.id)
                self.armazenamento.atualizar(melhor_ilha)
                agregacoes += 1
        return agregacoes

    def _actualizar_ilhas_existentes(self) -> int:
        ilhas = self.armazenamento.listar(limit=100)
        actualizadas = 0
        for ilha in ilhas:
            ilha.aplicar_decay(factor=0.95)
            if ilha.score_ativacao < 0.1:
                if ilha.estado != EstadoIlha.DORMINTE:
                    ilha.estado = EstadoIlha.ERODENDO
                    actualizadas += 1
            elif ilha.score_ativacao < 0.01:
                if ilha.estado != EstadoIlha.DORMINTE:
                    ilha.estado = EstadoIlha.DORMINTE
                    actualizadas += 1
            self.armazenamento.atualizar(ilha)
        return actualizadas


def ir_dormir(
    armazenamento: ArmazenamentoIlhas,
    session_id: str,
    interacoes: List[Dict[str, Any]],
) -> Dict[str, Any]:
    processador = ProcessadorBatch(armazenamento)
    return processador.executar(session_id, interacoes)
