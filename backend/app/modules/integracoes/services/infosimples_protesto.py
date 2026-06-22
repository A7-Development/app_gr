"""Consultas de protesto via Infosimples — camada de QUERY (2 fontes).

FONTES (escolha por `fonte`):
  - cenprot_sp  -> `cenprot-sp/protestos`  (Central de Protesto SP, protestosp.com.br)
                  1 chamada, SO `token`+cnpj/cpf (SEM login gov.br). Robusta.
                  Traz cartorio + valor + cancelamento + quitacao. NAO traz credor;
                  so 1a pagina (`retornou_todos_os_protestos_do_site`); so SP.
  - ieptb_credor-> `ieptb/protestos` -> `ieptb/protestos/detalhes-sp`
                  2 passos, PRECISA login gov.br (familia `protesto`). O detalhe SP
                  traz o CREDOR (nome_cedente/nome_apresentante). Fonte gov.br
                  (mais fragil). Cobertura nacional (existencia) + detalhe SP.

Grava bronze SEMPRE (sucesso/falha-com-response). NAO persiste silver — quem
materializa `wh_protesto_*` e o modulo credito (via public.py, §11.3). O caller
commita.
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

# Fontes (valor do parametro `fonte`).
FONTE_CENPROT_SP = "cenprot_sp"
FONTE_IEPTB_CREDOR = "ieptb_credor"
FONTES_VALIDAS = (FONTE_CENPROT_SP, FONTE_IEPTB_CREDOR)

# Escopos gravados no silver (header.escopo) por fonte — usados no filtro da view.
ESCOPO_CENPROT_SP = "cenprot_sp"
ESCOPO_IEPTB_NACIONAL = "ieptb_nacional"
ESCOPO_IEPTB_DETALHE = "ieptb_detalhe"
ESCOPOS_POR_FONTE: dict[str, tuple[str, ...]] = {
    FONTE_CENPROT_SP: (ESCOPO_CENPROT_SP,),
    FONTE_IEPTB_CREDOR: (ESCOPO_IEPTB_NACIONAL, ESCOPO_IEPTB_DETALHE),
}

# Public codes no catalogo (provedor_dados_dataset).
PUBLIC_CODE_CENPROT_SP = "PROTESTO-SP-CENPROT"
PUBLIC_CODE_IEPTB_NACIONAL = "PROTESTO-NACIONAL"
PUBLIC_CODE_IEPTB_DETALHE_SP = "PROTESTO-SP-DETALHE"

# Cap de chamadas ao detalhe SP por consulta (custo +R$0,06 + limite/login).
_MAX_SP_DETAIL_CALLS = 12


@dataclass(slots=True)
class ProtestoParte:
    """Uma 'perna' da consulta (escopo distinto) materializavel no silver."""

    escopo: str
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
    fonte: str
    partes: list[ProtestoParte] = field(default_factory=list)
    message: str | None = None
    transient: bool = False
    adapter_version: str = ADAPTER_VERSION


def _transient_message(resp: object) -> str:
    return (
        "A fonte de protesto (portal de origem) está instável ou lenta agora e a "
        f"consulta não completou ({failure_message(resp)}). Isso NÃO significa que "
        "não há protestos — tente novamente em instantes."
    )


async def fetch_protestos(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    documento: str,
    fonte: str = FONTE_CENPROT_SP,
    documento_tipo: str | None = None,
    max_detalhe_sp: int = _MAX_SP_DETAIL_CALLS,
    triggered_by: str | None = None,
) -> ProtestoConsultaResult:
    """Consulta protestos de um CNPJ/CPF na `fonte` escolhida. Caller commita."""
    if fonte not in FONTES_VALIDAS:
        raise ValueError(f"fonte inválida: {fonte!r}")
    doc = digits(documento)
    if not doc:
        raise ValueError("Informe um CPF/CNPJ.")
    doc_tipo = "cpf" if documento_tipo == "cpf" or len(doc) == 11 else "cnpj"

    provider, config = await load_provider_and_config(db)

    if fonte == FONTE_CENPROT_SP:
        return await _fetch_cenprot_sp(
            db, tenant_id=tenant_id, doc=doc, doc_tipo=doc_tipo,
            config=config, provider_id=provider.id, triggered_by=triggered_by,
        )
    return await _fetch_ieptb(
        db, tenant_id=tenant_id, doc=doc, doc_tipo=doc_tipo, config=config,
        provider_id=provider.id, max_detalhe_sp=max_detalhe_sp,
        triggered_by=triggered_by,
    )


async def _fetch_cenprot_sp(
    db: AsyncSession, *, tenant_id: UUID, doc: str, doc_tipo: str,
    config, provider_id: UUID, triggered_by: str | None,
) -> ProtestoConsultaResult:
    """1 chamada `cenprot-sp/protestos` (sem login gov.br)."""
    ds = await resolve_dataset(db, provider_id=provider_id, public_code=PUBLIC_CODE_CENPROT_SP)
    async with build_async_client(base_url=config.base_url, timeout_s=config.timeout_s) as client:
        resp = await consulta(
            client, path=ds.provider_query_name, api_key=config.api_key,
            params={doc_tipo: doc}, timeout_s=config.timeout_s,
        )
    raw_id = await store_bronze(
        db, tenant_id=tenant_id, documento=doc, public_code=PUBLIC_CODE_CENPROT_SP,
        consulta_path=ds.provider_query_name, resp=resp,
        found=resp.ok and resp.first is not None, triggered_by=triggered_by,
    )
    if not resp.ok:
        transient = is_transient(resp)
        return ProtestoConsultaResult(
            found=False, documento=doc, documento_tipo=doc_tipo, fonte=FONTE_CENPROT_SP,
            message=_transient_message(resp) if transient else failure_message(resp),
            transient=transient,
        )
    fields = map_protesto(resp.first or {})
    return ProtestoConsultaResult(
        found=True, documento=doc, documento_tipo=doc_tipo, fonte=FONTE_CENPROT_SP,
        partes=[ProtestoParte(escopo=ESCOPO_CENPROT_SP, fields=fields, raw_id=raw_id, uf="SP")],
    )


async def _fetch_ieptb(
    db: AsyncSession, *, tenant_id: UUID, doc: str, doc_tipo: str, config,
    provider_id: UUID, max_detalhe_sp: int, triggered_by: str | None,
) -> ProtestoConsultaResult:
    """2 passos IEPTB: nacional -> detalhe SP (com credor). Precisa login gov.br."""
    login = config.family_login(_FAMILY_PROTESTO)  # InfosimplesMissingFamilyCredentialError se faltar
    ds_nac = await resolve_dataset(db, provider_id=provider_id, public_code=PUBLIC_CODE_IEPTB_NACIONAL)

    async with build_async_client(base_url=config.base_url, timeout_s=config.timeout_s) as client:
        resp = await consulta(
            client, path=ds_nac.provider_query_name, api_key=config.api_key,
            params={**login, doc_tipo: doc}, timeout_s=config.timeout_s,
        )
    raw_id = await store_bronze(
        db, tenant_id=tenant_id, documento=doc, public_code=PUBLIC_CODE_IEPTB_NACIONAL,
        consulta_path=ds_nac.provider_query_name, resp=resp,
        found=resp.ok and resp.first is not None, triggered_by=triggered_by,
    )
    if not resp.ok:
        transient = is_transient(resp)
        return ProtestoConsultaResult(
            found=False, documento=doc, documento_tipo=doc_tipo, fonte=FONTE_IEPTB_CREDOR,
            message=_transient_message(resp) if transient else failure_message(resp),
            transient=transient,
        )

    first = resp.first or {}
    partes = [ProtestoParte(escopo=ESCOPO_IEPTB_NACIONAL, fields=map_protesto(first), raw_id=raw_id)]

    nac_fields = partes[0].fields
    if nac_fields and nac_fields.constam_protestos:
        reqs = extract_sp_detail_requests(first)[: max(0, max_detalhe_sp)]
        if reqs:
            ds_sp = await resolve_dataset(db, provider_id=provider_id, public_code=PUBLIC_CODE_IEPTB_DETALHE_SP)
            async with build_async_client(base_url=config.base_url, timeout_s=config.timeout_s) as client:
                for r in reqs:
                    dresp = await consulta(
                        client, path=ds_sp.provider_query_name, api_key=config.api_key,
                        params={**login, "obter_detalhes": r.obter_detalhes},
                        timeout_s=config.timeout_s,
                    )
                    draw_id = await store_bronze(
                        db, tenant_id=tenant_id, documento=doc,
                        public_code=PUBLIC_CODE_IEPTB_DETALHE_SP,
                        consulta_path=ds_sp.provider_query_name, resp=dresp,
                        found=dresp.ok and dresp.first is not None, triggered_by=triggered_by,
                    )
                    dfields = (
                        map_protesto(dresp.first)
                        if dresp.ok and dresp.first else None
                    )
                    partes.append(ProtestoParte(
                        escopo=ESCOPO_IEPTB_DETALHE, fields=dfields, raw_id=draw_id,
                        uf=r.uf or "SP", cartorio=r.cartorio, cidade=r.cidade,
                    ))

    return ProtestoConsultaResult(
        found=True, documento=doc, documento_tipo=doc_tipo, fonte=FONTE_IEPTB_CREDOR,
        partes=partes,
    )
