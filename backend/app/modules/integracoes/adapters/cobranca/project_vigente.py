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

from collections import Counter, defaultdict
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.cobranca.eventos import (
    DECODER_VERSION,
    EFEITO_ABRE,
    EFEITO_ENVIA,
    EFEITO_FECHA,
    EFEITO_REJEITA,
    TIPO_BAIXA,
    TIPO_ENTRADA_REJEITADA,
)
from app.warehouse.boleto_evento import BoletoEvento
from app.warehouse.boleto_vigente import (
    ESTADO_ATIVO,
    ESTADO_BAIXADO,
    ESTADO_ENVIADO,
    ESTADO_LIQUIDADO,
    ESTADO_REJEITADO,
    BoletoVigente,
)
from app.warehouse.dim import DimUnidadeAdministrativa
from app.warehouse.titulo import Titulo

_CHUNK = 1000

# Prioridade de processamento no mesmo dia: envia (instrucao) antes do abre
# (confirmacao); abre antes do terminal. Assim, se a remessa e o retorno de
# entrada caem no mesmo dia, o ABRE (confirmacao do banco) vence o ENVIA.
_PRIORIDADE = {EFEITO_ENVIA: -1, EFEITO_ABRE: 0, EFEITO_FECHA: 2, EFEITO_REJEITA: 2}


async def _ua_por_titulo(
    db: AsyncSession, tenant_id: UUID
) -> dict[str, tuple[int, str | None]]:
    """numero (trim) -> (ua_id, nome canonico da UA) a partir de `wh_titulo`.

    A UA do TITULO no Bitfin e a fonte de verdade da titularidade do boleto. O
    header CNAB carrega o nome da CONTA cobradora (que difere do nome da UA --
    ex.: BMP/Vortx, contas Grafeno), por isso o match por header falha. Como o
    documento do boleto cruza com `wh_titulo.numero`, a UA correta vem do titulo.
    """
    rows = (
        await db.execute(
            select(
                Titulo.numero,
                Titulo.unidade_administrativa_id,
                DimUnidadeAdministrativa.nome,
            )
            .outerjoin(
                DimUnidadeAdministrativa,
                (DimUnidadeAdministrativa.ua_id == Titulo.unidade_administrativa_id)
                & (DimUnidadeAdministrativa.tenant_id == Titulo.tenant_id),
            )
            .where(Titulo.tenant_id == tenant_id)
        )
    ).all()
    out: dict[str, tuple[int, str | None]] = {}
    for numero, ua_id, ua_nome in rows:
        if numero and ua_id is not None:
            out[numero.strip()] = (ua_id, ua_nome)
    return out


def _enriquecer_ua(
    rows: list[dict[str, Any]], ua_por_num: dict[str, tuple[int, str | None]]
) -> None:
    """Define a UA de cada boleto pelo TITULO que ele cruza (in-place).

    1. Boleto que cruza um titulo -> UA do titulo (vence o header).
    2. Boleto "so em banco" (sem titulo) -> UA majoritaria do mesmo banco entre
       os que cruzaram (1 carteira/convenio = 1 UA; ex.: BMP/Vortx = RealInvest).
    """
    maioria: dict[str, Counter[tuple[int, str | None]]] = defaultdict(Counter)
    for r in rows:
        t = ua_por_num.get((r["numero_documento"] or "").strip())
        if t is not None:
            r["ua_id"], r["ua_nome"] = t
            maioria[r["banco_origem"]][t] += 1
    banco_ua = {b: c.most_common(1)[0][0] for b, c in maioria.items() if c}
    for r in rows:
        if r["ua_id"] is None:
            fallback = banco_ua.get(r["banco_origem"])
            if fallback is not None:
                r["ua_id"], r["ua_nome"] = fallback


def _estado_final(efeito: str, tipo: str) -> str:
    if efeito == EFEITO_ENVIA:
        return ESTADO_ENVIADO  # enviado, aguardando confirmacao do banco
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

    # Agrupa por boleto (banco, numero_documento) -- o numero do documento (=
    # numero do titulo) e a UNICA identidade estavel entre remessa e retorno.
    # O nosso_numero NAO serve de chave: e ZEROS na remessa BMP (o banco e quem
    # atribui o nosso numero, devolvendo-o so no retorno) e RECICLADO na Vortx
    # (o mesmo nosso aparece em varios documentos ao longo do tempo). Incluir o
    # nosso na chave deixava o boleto enviado (nosso=000... ou nosso nosso) sem
    # colapsar com o seu retorno (nosso do banco) -> "enviado" fantasma mesmo o
    # banco tendo confirmado/liquidado. Validado empiricamente: 0 documento tem
    # >1 sacado (nao ha reuso entre pagadores), 662 documentos tem >1 nosso (=
    # exatamente os casos a colapsar). data: 2026-06-06.
    por_boleto: dict[tuple[str, str], list[BoletoEvento]] = defaultdict(list)
    for e in eventos:
        por_boleto[(e.banco_origem, e.numero_documento)].append(e)

    projected_at = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for (banco_origem, numero_documento), evs in por_boleto.items():
        evs.sort(
            key=lambda e: (e.data_ocorrencia, _PRIORIDADE.get(e.efeito_estado, 1))
        )
        estado = ESTADO_REJEITADO  # default conservador ate ver um abre/envia
        tipo_vig = evs[-1].tipo_evento
        cod_vig: str | None = None
        data_vig: date = evs[-1].data_ocorrencia
        valor_atual: Decimal | None = None
        venc: date | None = None
        valor_pago: Decimal | None = None
        data_pgto: date | None = None
        ua_id: int | None = None
        ua_nome = None
        nosso = ""
        sacado_doc = sacado_nome = None
        for e in evs:
            # Nosso numero representativo: prefere um nao-zerado (o do banco, vindo
            # do retorno) ao da remessa BMP (000...). Como os eventos estao
            # ordenados por data, o ultimo nao-zerado (retorno) vence.
            if e.nosso_numero and e.nosso_numero.strip("0"):
                nosso = e.nosso_numero
            if e.ua_id is not None:
                ua_id = e.ua_id
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
            # empate de dia via prioridade na ordenacao). ENVIA (remessa) e o
            # estado mais fraco -- um ABRE (retorno) posterior o sobrescreve.
            if e.efeito_estado in (
                EFEITO_ENVIA,
                EFEITO_ABRE,
                EFEITO_FECHA,
                EFEITO_REJEITA,
            ):
                estado = _estado_final(e.efeito_estado, e.tipo_evento)
                tipo_vig = e.tipo_evento
                cod_vig = e.codigo_ocorrencia
                data_vig = e.data_ocorrencia

        if not nosso:  # so vimos nosso zerado/vazio (remessa BMP sem retorno)
            nosso = evs[-1].nosso_numero or ""

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

    # UA pelo TITULO (fonte de verdade), nao pelo header CNAB. Titulo vence;
    # "so em banco" herda a UA majoritaria do banco (convenio = 1 UA).
    _enriquecer_ua(rows, await _ua_por_titulo(db, tenant_id))

    # Reescreve a vigente (projecao -> delete + insert).
    del_stmt = delete(BoletoVigente).where(BoletoVigente.tenant_id == tenant_id)
    if banco is not None:
        del_stmt = del_stmt.where(BoletoVigente.banco_origem == banco)
    await db.execute(del_stmt)
    for i in range(0, len(rows), _CHUNK):
        await db.execute(BoletoVigente.__table__.insert(), rows[i : i + _CHUNK])
    await db.commit()

    ativos = [r for r in rows if r["estado"] == ESTADO_ATIVO]
    enviados = [r for r in rows if r["estado"] == ESTADO_ENVIADO]
    valor_ativo = sum((r["valor_atual"] or Decimal(0)) for r in ativos)
    return {
        "boletos": len(rows),
        "ativos": len(ativos),
        "enviados": len(enviados),
        "valor_ativo": str(valor_ativo),
    }
