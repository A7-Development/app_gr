"""Sentinela da regra serasa_liminar_v1 -- maquina de estados + alertas.

Roda a cada consulta Serasa PJ ingerida (relay Bitfin + consulta direta +
backfill cronologico). Mantem `lab_serasa_liminar_estado` (1 linha por
tenant+CNPJ) e grava toda transicao em `decision_log` (ALERT, append-only).

Desenho (decisao 2026-06-10 com Ricardo):

1. CNPJ que recebeu "NADA CONSTA" entra na maquina e NUNCA sai
   silenciosamente — so transiciona, com evento auditavel.
2. Transicoes:
   - (sem estado) + NADA CONSTA      -> suspeita_ativa     (entrada)
   - suspeita_ativa + NADA CONSTA    -> (confirma, sem evento)
   - suspeita_ativa + negativos      -> liminar_caida      (ALERTA credito:
     o que estava escondido voltou)
   - suspeita_ativa + limpo s/ msg   -> transicao_ambigua  (liminar expirou
     OU Serasa mudou o marcador)
   - caida/ambigua + NADA CONSTA     -> suspeita_ativa     (reativada)
3. Sentinela SISTEMICA: N transicoes ambiguas na janela => provavelmente
   NAO e coincidencia juridica — e a Serasa que mudou o comportamento.
   Gera ALERT `mudanca_comportamento_suspeita` (1x por janela de
   supressao, sem spam).
4. Invariante de vocabulario: `negativeSummary.message` fora do universo
   conhecido (classify == desconhecida) => ALERT `mensagem_desconhecida`
   (possivel formato novo) — sem mudanca de estado.
5. Guarda de ordem: consulta com `consulted_at` anterior a ultima ja
   avaliada e ignorada (replay/remap historico nao regride estado).

Threshold sistemico: >= 3 transicoes ambiguas em 30 dias (coorte atual:
32 CNPJs; 3+ expirando juntos sem negativos reaparecerem e implausivel).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.bureau.serasa_pj.liminar import (
    LIMINAR_RULE_VERSION,
    MSG_DESCONHECIDA,
    MSG_NADA_CONSTA,
    classify_negative_summary_message,
)
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.warehouse.serasa_liminar_estado import SerasaLiminarEstado

logger = logging.getLogger("gr.integracoes.serasa_liminar_sentinela")

_RULE_NAME = "serasa_liminar_sentinela"

# Estados canonicos (valores da coluna lab_serasa_liminar_estado.estado).
ESTADO_SUSPEITA_ATIVA = "suspeita_ativa"
ESTADO_LIMINAR_CAIDA = "liminar_caida"
ESTADO_TRANSICAO_AMBIGUA = "transicao_ambigua"
ESTADOS = (
    ESTADO_SUSPEITA_ATIVA,
    ESTADO_LIMINAR_CAIDA,
    ESTADO_TRANSICAO_AMBIGUA,
)

# Transicoes (gravadas em decision_log.output.transicao).
TRANSICAO_ENTRADA = "entrada_suspeita"
TRANSICAO_LIMINAR_CAIDA = "liminar_caida"
TRANSICAO_AMBIGUA = "transicao_ambigua"
TRANSICAO_REATIVADA = "suspeita_reativada"

# Sentinela sistemica: >= N transicoes ambiguas em JANELA dias.
_SISTEMICO_MIN_AMBIGUAS = 3
_SISTEMICO_JANELA_DIAS = 30
# Supressao de alerta sistemico repetido (1x por semana no maximo).
_SISTEMICO_SUPRESSAO_DIAS = 7

ALERTA_SISTEMICO = "mudanca_comportamento_suspeita"
ALERTA_MSG_DESCONHECIDA = "mensagem_desconhecida"


@dataclass(frozen=True)
class ConsultaAvaliada:
    """Fatos de uma consulta que o detector precisa (independente da fonte)."""

    tenant_id: UUID
    cnpj: str
    raw_id: UUID
    consulted_at: datetime
    negative_summary_message: str | None
    negativos_visiveis: bool
    triggered_by: str


def has_negativos_visiveis(consulta: dict[str, Any]) -> bool:
    """Negativos visiveis no header silver (dict do mapper ou row ORM).

    Qualquer categoria com ocorrencia conta — inclusive facts (acoes
    judiciais, falencias): nos payloads com liminar TUDO vem zerado, entao
    qualquer coisa visivel descaracteriza a supressao total.
    """
    return any(
        int(consulta.get(k) or 0) > 0
        for k in (
            "count_pefin",
            "count_refin",
            "count_protesto",
            "count_cheque",
            "count_falencias",
            "count_acoes_judiciais",
        )
    )


def decidir_transicao(
    estado_atual: str | None,
    *,
    nada_consta: bool,
    negativos_visiveis: bool,
) -> tuple[str | None, str | None]:
    """Nucleo PURO da maquina de estados.

    Returns:
        (novo_estado, transicao) — ambos None quando nada muda.
    """
    if estado_atual is None:
        if nada_consta:
            return ESTADO_SUSPEITA_ATIVA, TRANSICAO_ENTRADA
        return None, None

    if nada_consta:
        if estado_atual == ESTADO_SUSPEITA_ATIVA:
            return None, None  # confirma — sem evento
        return ESTADO_SUSPEITA_ATIVA, TRANSICAO_REATIVADA

    if estado_atual == ESTADO_SUSPEITA_ATIVA:
        if negativos_visiveis:
            return ESTADO_LIMINAR_CAIDA, TRANSICAO_LIMINAR_CAIDA
        return ESTADO_TRANSICAO_AMBIGUA, TRANSICAO_AMBIGUA

    # caida/ambigua + consulta sem carimbo: estado terminal ate novo
    # NADA CONSTA — sem evento.
    return None, None


async def process_consulta(
    db: AsyncSession,
    consulta: ConsultaAvaliada,
) -> str | None:
    """Avalia 1 consulta contra a maquina de estados (mesma tx do silver).

    Caller commita. Retorna o nome da transicao disparada (ou None).
    """
    classification = classify_negative_summary_message(
        consulta.negative_summary_message
    )

    # Invariante de vocabulario (item 4 do desenho): valor nunca visto.
    if classification == MSG_DESCONHECIDA:
        db.add(
            _alert_entry(
                consulta,
                alerta=ALERTA_MSG_DESCONHECIDA,
                explanation=(
                    "negativeSummary.message com valor fora do universo "
                    f"conhecido: {consulta.negative_summary_message!r}. "
                    "Possivel mudanca de formato da Serasa — revisar regra "
                    f"{LIMINAR_RULE_VERSION}."
                ),
            )
        )

    nada_consta = classification == MSG_NADA_CONSTA

    estado_row = (
        await db.execute(
            select(SerasaLiminarEstado).where(
                SerasaLiminarEstado.tenant_id == consulta.tenant_id,
                SerasaLiminarEstado.cnpj == consulta.cnpj,
            )
        )
    ).scalar_one_or_none()

    # Guarda de ordem cronologica: replay de consulta antiga nao regride.
    if (
        estado_row is not None
        and consulta.consulted_at <= estado_row.ultima_consulta_at
    ):
        return None

    novo_estado, transicao = decidir_transicao(
        estado_row.estado if estado_row else None,
        nada_consta=nada_consta,
        negativos_visiveis=consulta.negativos_visiveis,
    )

    if estado_row is None and novo_estado is None:
        return None  # CNPJ fora da maquina, consulta normal

    if estado_row is None:
        estado_row = SerasaLiminarEstado(
            tenant_id=consulta.tenant_id,
            cnpj=consulta.cnpj,
            estado=novo_estado,
            primeira_evidencia_raw_id=consulta.raw_id,
            primeira_evidencia_at=consulta.consulted_at,
            ultima_consulta_raw_id=consulta.raw_id,
            ultima_consulta_at=consulta.consulted_at,
            ultima_transicao_at=consulta.consulted_at,
            regra_version=LIMINAR_RULE_VERSION,
        )
        db.add(estado_row)
    else:
        estado_row.ultima_consulta_raw_id = consulta.raw_id
        estado_row.ultima_consulta_at = consulta.consulted_at
        estado_row.updated_at = consulta.consulted_at
        if novo_estado is not None:
            estado_row.estado = novo_estado
            estado_row.ultima_transicao_at = consulta.consulted_at
            estado_row.regra_version = LIMINAR_RULE_VERSION

    if transicao is not None:
        db.add(
            _alert_entry(
                consulta,
                alerta=transicao,
                explanation=_EXPLANATIONS[transicao].format(
                    cnpj=consulta.cnpj
                ),
            )
        )
        logger.info(
            "serasa_liminar_sentinela: %s cnpj=%s raw=%s",
            transicao,
            consulta.cnpj,
            consulta.raw_id,
        )

    if transicao == TRANSICAO_AMBIGUA:
        await _check_sentinela_sistemica(db, consulta)

    return transicao


_EXPLANATIONS = {
    TRANSICAO_ENTRADA: (
        "CNPJ {cnpj}: Serasa retornou 'NADA CONSTA' explicito — padrao de "
        "supressao judicial de apontamentos (possivel liminar). Conclusao "
        "derivada pelo Strata."
    ),
    TRANSICAO_LIMINAR_CAIDA: (
        "CNPJ {cnpj}: apontamentos negativos VOLTARAM a aparecer apos "
        "periodo sob 'NADA CONSTA' — liminar provavelmente cassada/expirada. "
        "O que estava judicialmente escondido esta visivel; revisar credito."
    ),
    TRANSICAO_AMBIGUA: (
        "CNPJ {cnpj}: deixou de vir 'NADA CONSTA' mas segue sem negativos "
        "visiveis. Ou a liminar expirou com ficha limpa (raro), ou a Serasa "
        "mudou o marcador. Sentinela sistemica monitora o agregado."
    ),
    TRANSICAO_REATIVADA: (
        "CNPJ {cnpj}: 'NADA CONSTA' voltou apos transicao — nova supressao "
        "judicial (ou liminar restabelecida)."
    ),
}


def _alert_entry(
    consulta: ConsultaAvaliada,
    *,
    alerta: str,
    explanation: str,
    output_extra: dict[str, Any] | None = None,
) -> DecisionLog:
    return DecisionLog(
        tenant_id=consulta.tenant_id,
        decision_type=DecisionType.ALERT,
        rule_or_model=_RULE_NAME,
        rule_or_model_version=LIMINAR_RULE_VERSION,
        triggered_by=consulta.triggered_by,
        inputs_ref={
            "cnpj": consulta.cnpj,
            "raw_id": str(consulta.raw_id),
            "consulted_at": consulta.consulted_at.isoformat(),
            "negative_summary_message": consulta.negative_summary_message,
            "negativos_visiveis": consulta.negativos_visiveis,
        },
        output={"alerta": alerta, "transicao": alerta},
        explanation=explanation,
    )


async def _check_sentinela_sistemica(
    db: AsyncSession, consulta: ConsultaAvaliada
) -> None:
    """N transicoes ambiguas na janela => alerta de mudanca de comportamento.

    Mudanca de formato da Serasa quebra a coorte EM BLOCO; evento juridico
    real (liminar expirada) acontece um a um — e essa assimetria que
    separa os dois.
    """
    ref = consulta.consulted_at
    janela_inicio = ref - timedelta(days=_SISTEMICO_JANELA_DIAS)

    ambiguas = (
        await db.execute(
            select(func.count())
            .select_from(DecisionLog)
            .where(
                DecisionLog.tenant_id == consulta.tenant_id,
                DecisionLog.rule_or_model == _RULE_NAME,
                DecisionLog.decision_type == DecisionType.ALERT,
                DecisionLog.output["alerta"].astext == TRANSICAO_AMBIGUA,
                DecisionLog.occurred_at >= janela_inicio,
            )
        )
    ).scalar_one()

    # +1 pela transicao desta consulta (entry ainda nao commitada pode nao
    # contar dependendo do flush — soma explicita pra nao depender disso).
    if ambiguas + 1 < _SISTEMICO_MIN_AMBIGUAS:
        return

    # Supressao: ja alertamos nos ultimos N dias?
    supressao_inicio = ref - timedelta(days=_SISTEMICO_SUPRESSAO_DIAS)
    ja_alertado = (
        await db.execute(
            select(func.count())
            .select_from(DecisionLog)
            .where(
                DecisionLog.tenant_id == consulta.tenant_id,
                DecisionLog.rule_or_model == _RULE_NAME,
                DecisionLog.output["alerta"].astext == ALERTA_SISTEMICO,
                DecisionLog.occurred_at >= supressao_inicio,
            )
        )
    ).scalar_one()
    if ja_alertado:
        return

    db.add(
        _alert_entry(
            consulta,
            alerta=ALERTA_SISTEMICO,
            explanation=(
                f">= {_SISTEMICO_MIN_AMBIGUAS} CNPJs deixaram de vir "
                f"'NADA CONSTA' sem negativos reaparecerem em "
                f"{_SISTEMICO_JANELA_DIAS} dias — provavel MUDANCA DE "
                f"COMPORTAMENTO da Serasa (nao coincidencia juridica). "
                f"Regra {LIMINAR_RULE_VERSION} em revisao: conclusoes "
                "existentes congelam (nao limpar badges) ate regra v2."
            ),
        )
    )
    logger.warning(
        "serasa_liminar_sentinela: ALERTA SISTEMICO — possivel mudanca de "
        "comportamento Serasa (tenant=%s)",
        consulta.tenant_id,
    )
