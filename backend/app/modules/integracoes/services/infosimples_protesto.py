"""Consultas de protesto via Infosimples (IEPTB/CENPROT) -- camada de QUERY.

Fluxo de 2 passos (confirmado no doc Infosimples v2.2.37):
  1. NACIONAL `ieptb/protestos` -- existencia + agregados (estado/cartorio) +
     titulos (data/valor). Devolve, por cartorio de SP, um token
     `obter_detalhes`. NAO traz credor (Provimento CNJ 225/2026).
  2. DETALHE SP `ieptb/protestos/detalhes-sp` -- por token `obter_detalhes`,
     devolve os titulos com `nome_cedente` (credor) e `nome_apresentante`.
     +R$0,06/chamada e limite diario por login -> cap de chamadas por consulta.

Grava bronze SEMPRE (sucesso ou falha com response). NAO persiste silver -- quem
materializa `wh_protesto_*` no dominio e o modulo credito (via public.py, §11.3).
O caller e responsavel pelo commit.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.data.infosimples import (
    ADAPTER_VERSION,
    build_async_client,
    consulta,
)
from app.modules.integracoes.adapters.data.infosimples.mappers import (
    ProtestoFields,
    extract_sp_detail_requests,
    map_protesto,
)
from app.modules.integracoes.services.infosimples_common import (
    digits,
    failure_message,
    is_transient,
    load_provider_and_config,
    resolve_dataset,
    store_bronze,
)

_FAMILY_PROTESTO = "protesto"

PUBLIC_CODE_PROTESTO_NACIONAL = "PROTESTO-NACIONAL"
PUBLIC_CODE_PROTESTO_SP_DETALHE = "PROTESTO-SP-DETALHE"

# Cap de chamadas ao detalhe SP por consulta (custo +R$0,06 cada + limite diario
# por login). 12 cobre o caso comum; o resto fica como agregado nacional.
_MAX_SP_DETAIL_CALLS = 12


@dataclass(slots=True)
class ProtestoParte:
    """Uma 'perna' da consulta: a nacional, ou um detalhe de cartorio SP."""

    escopo: str  # 'nacional' | 'sp_detalhe'
    fields: ProtestoFields | None
    raw_id: UUID | None
    uf: str | None = None
    cartorio: str | None = None
    cidade: str | None = None


@dataclass(slots=True)
class ProtestoConsultaResult:
    found: bool
    documento: str
    documento_tipo: str
    nacional: ProtestoParte | None = None
    detalhes_sp: list[ProtestoParte] = field(default_factory=list)
    message: str | None = None
    transient: bool = False
    adapter_version: str = ADAPTER_VERSION


def _transient_message(resp: object) -> str:
    return (
        "O CENPROT/IEPTB (portal gov.br) está instável ou lento agora e a "
        f"consulta não completou ({failure_message(resp)}). Isso NÃO significa "
        "que não há protestos — tente novamente em instantes."
    )


async def fetch_protestos(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    documento: str,
    documento_tipo: str = "cnpj",
    incluir_detalhe_sp: bool = True,
    max_detalhe_sp: int = _MAX_SP_DETAIL_CALLS,
    triggered_by: str | None = None,
) -> ProtestoConsultaResult:
    """Consulta protestos de um CPF/CNPJ (nacional + detalhe SP quando houver).

    Grava bronze de cada chamada. O caller commita.
    """
    doc = digits(documento)
    if not doc:
        raise ValueError("Informe um CPF/CNPJ.")
    doc_tipo = "cpf" if documento_tipo == "cpf" or len(doc) == 11 else "cnpj"

    provider, config = await load_provider_and_config(db)
    login = config.family_login(_FAMILY_PROTESTO)
    ds_nac = await resolve_dataset(
        db, provider_id=provider.id, public_code=PUBLIC_CODE_PROTESTO_NACIONAL
    )

    # ── 1. Consulta nacional ──────────────────────────────────────────────
    async with build_async_client(
        base_url=config.base_url, timeout_s=config.timeout_s
    ) as client:
        resp = await consulta(
            client,
            path=ds_nac.provider_query_name,
            api_key=config.api_key,
            params={**login, doc_tipo: doc},
            timeout_s=config.timeout_s,
        )

    raw_id = await store_bronze(
        db,
        tenant_id=tenant_id,
        documento=doc,
        public_code=PUBLIC_CODE_PROTESTO_NACIONAL,
        consulta_path=ds_nac.provider_query_name,
        resp=resp,
        found=resp.ok and resp.first is not None,
        triggered_by=triggered_by,
    )

    if not resp.ok:
        transient = is_transient(resp)
        return ProtestoConsultaResult(
            found=False,
            documento=doc,
            documento_tipo=doc_tipo,
            message=_transient_message(resp) if transient else failure_message(resp),
            transient=transient,
        )

    first = resp.first or {}
    nac_fields = map_protesto(first)
    nacional = ProtestoParte(escopo="nacional", fields=nac_fields, raw_id=raw_id)

    # ── 2. Detalhe SP (onde o credor aparece) ─────────────────────────────
    detalhes: list[ProtestoParte] = []
    if incluir_detalhe_sp and nac_fields.constam_protestos:
        reqs = extract_sp_detail_requests(first)[: max(0, max_detalhe_sp)]
        if reqs:
            ds_sp = await resolve_dataset(
                db,
                provider_id=provider.id,
                public_code=PUBLIC_CODE_PROTESTO_SP_DETALHE,
            )
            async with build_async_client(
                base_url=config.base_url, timeout_s=config.timeout_s
            ) as client:
                for r in reqs:
                    dresp = await consulta(
                        client,
                        path=ds_sp.provider_query_name,
                        api_key=config.api_key,
                        params={**login, "obter_detalhes": r.obter_detalhes},
                        timeout_s=config.timeout_s,
                    )
                    draw_id = await store_bronze(
                        db,
                        tenant_id=tenant_id,
                        documento=doc,
                        public_code=PUBLIC_CODE_PROTESTO_SP_DETALHE,
                        consulta_path=ds_sp.provider_query_name,
                        resp=dresp,
                        found=dresp.ok and dresp.first is not None,
                        triggered_by=triggered_by,
                    )
                    dfields = (
                        map_protesto(
                            dresp.first,
                            ctx={
                                "cartorio": r.cartorio,
                                "cidade": r.cidade,
                                "uf": r.uf or "SP",
                            },
                        )
                        if dresp.ok and dresp.first
                        else None
                    )
                    detalhes.append(
                        ProtestoParte(
                            escopo="sp_detalhe",
                            fields=dfields,
                            raw_id=draw_id,
                            uf=r.uf or "SP",
                            cartorio=r.cartorio,
                            cidade=r.cidade,
                        )
                    )

    return ProtestoConsultaResult(
        found=True,
        documento=doc,
        documento_tipo=doc_tipo,
        nacional=nacional,
        detalhes_sp=detalhes,
    )
