"""Fold wh_boleto_evento -> wh_boleto_vigente (projecao). Fatia 3 do rebuild.

Le a timeline de eventos e projeta o estado VIGENTE de cada boleto (banco, UA,
nosso_numero) aplicando a regra deterministica validada:

  - ordena os eventos por (data_ocorrencia, prioridade), com prioridade
    abre < modifica/info < fecha/rejeita -- assim, no mesmo dia, o terminal
    e processado DEPOIS do abre (entrada + baixa no mesmo dia => fechado);
  - o estado final vem do ultimo evento de estado (efeito abre/fecha/rejeita);
  - valor_atual / vencimento = ultimo valor/venc nao-nulo visto no walk.

Reescreve a vigente do tenant (delete + insert) -- e uma projecao, sempre
re-derivavel. Idempotente.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.cobranca.eventos import (
    DECODER_VERSION,
    EFEITO_ABRE,
    EFEITO_FECHA,
    EFEITO_REJEITA,
    TIPO_BAIXA,
    TIPO_ENTRADA_REJEITADA,
)
from app.warehouse.boleto_evento import BoletoEvento
from app.warehouse.boleto_vigente import (
    ESTADO_ATIVO,
    ESTADO_BAIXADO,
    ESTADO_LIQUIDADO,
    ESTADO_REJEITADO,
    BoletoVigente,
)

_CHUNK = 1000

# Prioridade de processamento no mesmo dia: abre primeiro, terminal por ultimo.
_PRIORIDADE = {EFEITO_ABRE: 0, EFEITO_FECHA: 2, EFEITO_REJEITA: 2}


def _estado_final(efeito: str, tipo: str) -> str:
    if efeito == EFEITO_ABRE:
        return ESTADO_ATIVO
    if efeito == EFEITO_REJEITA:
        return ESTADO_REJEITADO
    # EFEITO_FECHA: baixa vs liquidacao pelo tipo do evento.
    if tipo in (TIPO_BAIXA, TIPO_ENTRADA_REJEITADA):
        return ESTADO_BAIXADO
    return ESTADO_LIQUIDADO


async def project_tenant_vigente(
    db: AsyncSession, *, tenant_id: UUID, banco: str | None = None
) -> dict[str, Any]:
    """Reprojeta a vigente do tenant a partir da timeline. Returns resumo."""
    stmt = select(BoletoEvento).where(BoletoEvento.tenant_id == tenant_id)
    if banco is not None:
        stmt = stmt.where(BoletoEvento.banco_origem == banco)
    eventos = (await db.execute(stmt)).scalars().all()

    # Agrupa por boleto (banco, ua, nosso_numero).
    por_boleto: dict[tuple[str, int | None, str], list[BoletoEvento]] = defaultdict(
        list
    )
    for e in eventos:
        # Identidade do boleto = par (nosso_numero, numero_documento). O banco
        # REUSA o nosso_numero ao longo do tempo (reciclagem do sequencial apos
        # o boleto fechar); so o par e estavel/unico. Empiricamente 635 nossos
        # numeros aparecem para >1 documento.
        por_boleto[
            (e.banco_origem, e.ua_id, e.nosso_numero, e.numero_documento)
        ].append(e)

    projected_at = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for (banco_origem, ua_id, nosso, numero_documento), evs in por_boleto.items():
        evs.sort(
            key=lambda e: (e.data_ocorrencia, _PRIORIDADE.get(e.efeito_estado, 1))
        )
        estado = ESTADO_REJEITADO  # default conservador ate ver um abre
        tipo_vig = evs[-1].tipo_evento
        cod_vig: str | None = None
        data_vig: date = evs[-1].data_ocorrencia
        valor_atual: Decimal | None = None
        venc: date | None = None
        valor_pago: Decimal | None = None
        data_pgto: date | None = None
        ua_nome = None
        sacado_doc = sacado_nome = None
        for e in evs:
            if e.ua_nome:
                ua_nome = e.ua_nome
            if e.sacado_documento:
                sacado_doc = e.sacado_documento
            if e.sacado_nome:
                sacado_nome = e.sacado_nome
            if e.valor_titulo is not None:
                valor_atual = e.valor_titulo
            if e.data_vencimento is not None:
                venc = e.data_vencimento
            if e.valor_pago is not None:
                valor_pago = e.valor_pago
            if e.data_pagamento is not None:
                data_pgto = e.data_pagamento
            # Evento de estado define o vigente (ultimo vence; terminal vence
            # empate de dia via prioridade na ordenacao).
            if e.efeito_estado in (EFEITO_ABRE, EFEITO_FECHA, EFEITO_REJEITA):
                estado = _estado_final(e.efeito_estado, e.tipo_evento)
                tipo_vig = e.tipo_evento
                cod_vig = e.codigo_ocorrencia
                data_vig = e.data_ocorrencia

        rows.append(
            {
                "id": uuid4(),
                "tenant_id": tenant_id,
                "banco_origem": banco_origem,
                "ua_id": ua_id,
                "ua_nome": ua_nome,
                "nosso_numero": nosso,
                "numero_documento": numero_documento,
                "sacado_documento": sacado_doc,
                "sacado_nome": sacado_nome,
                "estado": estado,
                "valor_atual": valor_atual,
                "data_vencimento": venc,
                "valor_pago": valor_pago,
                "data_pagamento": data_pgto,
                "tipo_evento_vigente": tipo_vig,
                "codigo_ocorrencia_vigente": cod_vig,
                "data_ocorrencia_vigente": data_vig,
                "primeiro_evento_em": evs[0].data_ocorrencia,
                "n_eventos": len(evs),
                "projected_at": projected_at,
                "projected_by_version": DECODER_VERSION,
            }
        )

    # Reescreve a vigente (projecao -> delete + insert).
    del_stmt = delete(BoletoVigente).where(BoletoVigente.tenant_id == tenant_id)
    if banco is not None:
        del_stmt = del_stmt.where(BoletoVigente.banco_origem == banco)
    await db.execute(del_stmt)
    for i in range(0, len(rows), _CHUNK):
        await db.execute(BoletoVigente.__table__.insert(), rows[i : i + _CHUNK])
    await db.commit()

    ativos = [r for r in rows if r["estado"] == ESTADO_ATIVO]
    valor_ativo = sum((r["valor_atual"] or Decimal(0)) for r in ativos)
    return {
        "boletos": len(rows),
        "ativos": len(ativos),
        "valor_ativo": str(valor_ativo),
    }
