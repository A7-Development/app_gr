"""BDC processos judiciais — consulta `processes` -> bronze -> silver.

Consulta dedicada (separada do dossie multi-dataset) porque processes e pesado
(traz andamentos por padrao) e tem reconciliacao propria (incrementa, nao
subscreve — ver pj_processo_silver). Ingere TODOS os processos (status e LENTE,
nao filtro): risco usa os vivos; garimpo de bens varre tudo.

Exposto via `integracoes/public.py` para node/tool consumirem.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.data.bigdatacorp.client import query_entity
from app.modules.integracoes.adapters.data.bigdatacorp.config import (
    BigDataCorpConfig,
)
from app.modules.integracoes.adapters.data.bigdatacorp.errors import (
    BigDataCorpAdapterError,
)
from app.modules.integracoes.adapters.data.bigdatacorp.mappers.processos import (
    map_processos,
)
from app.modules.integracoes.adapters.data.bigdatacorp.version import (
    ADAPTER_VERSION,
)
from app.modules.integracoes.services.pj_processo_silver import (
    upsert_pj_processo_resumo,
    upsert_pj_processos,
)
from app.shared.crypto.envelope import decrypt_envelope
from app.shared.data_providers.enums import DataProviderSlug
from app.shared.data_providers.models.credential import DataProviderCredential
from app.shared.data_providers.models.dataset import DataProviderDataset
from app.shared.data_providers.models.provider import DataProvider
from app.warehouse.bdc_raw_consulta import BdcRawConsulta

logger = logging.getLogger("gr.integracoes.bdc_processos")

_PUBLIC_CODE = "PROCESSOS-PJ"
# Teto de paginas (BDC pagina ~100 processos/pagina via NextPageId; CADA pagina
# e uma chamada PAGA). 10 paginas = ~1000 processos cobre a quase totalidade;
# acima disso `truncado=True` DISCLOSA o corte (§14.6), nao esconde.
_MAX_PAGINAS = 10


def _lawsuits_block(payload: dict) -> dict | None:
    res = payload.get("Result") or []
    if not res:
        return None
    block = res[0].get("Lawsuits")
    return block if isinstance(block, dict) else None


def _merge_pages(payloads: list[dict]) -> dict | None:
    """Concatena os processos de todas as paginas num payload combinado.

    Mantem os agregados de entidade da 1a pagina (Last30/365, datas, totais —
    iguais em toda pagina); junta as listas `Lawsuits` -> map roda 1x sobre o
    conjunto completo (resumo correto).
    """
    if not payloads:
        return None
    base = copy.deepcopy(payloads[0])
    block = _lawsuits_block(base)
    if block is None:
        return base
    all_lw: list = []
    for pl in payloads:
        b = _lawsuits_block(pl)
        all_lw.extend((b or {}).get("Lawsuits") or [])
    block["Lawsuits"] = all_lw
    block.pop("NextPageId", None)
    return base


@dataclass(frozen=True)
class ProcessosResult:
    ok: bool
    found: bool
    cnpj: str
    raw_id: UUID | None
    query_id: str | None
    qtd_processos: int
    qtd_partes: int
    qtd_andamentos_novos: int
    qtd_ativos: int
    qtd_execucoes_contra: int
    paginas: int
    truncado: bool
    adapter_version: str
    errors: list[str]


def _sha256(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def fetch_bdc_processos_pj(
    *,
    tenant_id: UUID,
    cnpj: str,
    triggered_by: str,
    unidade_administrativa_id: UUID | None = None,
) -> ProcessosResult:
    """Consulta BDC processes e materializa o silver de processos judiciais."""
    errors: list[str] = []
    cnpj_digits = "".join(ch for ch in (cnpj or "") if ch.isdigit())

    def _fail(msg: str) -> ProcessosResult:
        errors.append(msg)
        logger.warning("BDC processos falhou (cnpj=%s): %s", cnpj_digits, msg)
        return ProcessosResult(
            ok=False, found=False, cnpj=cnpj_digits, raw_id=None, query_id=None,
            qtd_processos=0, qtd_partes=0, qtd_andamentos_novos=0, qtd_ativos=0,
            qtd_execucoes_contra=0, paginas=0, truncado=False,
            adapter_version=ADAPTER_VERSION, errors=errors,
        )

    # ─── Resolve dataset + provider + credencial ──────────────────────────
    async with AsyncSessionLocal() as db:
        ds = (
            await db.execute(
                select(DataProviderDataset).where(
                    DataProviderDataset.public_code == _PUBLIC_CODE
                )
            )
        ).scalars().first()
        if ds is None or not ds.enabled_for_sale:
            return _fail(f"dataset {_PUBLIC_CODE} ausente ou desabilitado")
        query_name = ds.provider_query_name or ds.provider_dataset_code
        provider_api = ds.provider_api

        provider = await db.get(DataProvider, ds.provider_id)
        if provider is None or not provider.enabled:
            return _fail("provedor BDC inexistente ou desligado")
        if provider.slug != DataProviderSlug.BIGDATACORP:
            return _fail("public_code resolve pra provider != BigDataCorp")
        base_url = provider.base_url

        credential = (
            await db.execute(
                select(DataProviderCredential)
                .where(DataProviderCredential.provider_id == provider.id)
                .where(DataProviderCredential.active.is_(True))
                .order_by(DataProviderCredential.updated_at.desc())
                .limit(1)
            )
        ).scalars().first()
        if credential is None:
            return _fail("BigDataCorp sem credencial ativa")
        try:
            config = BigDataCorpConfig.from_dict(
                decrypt_envelope(credential.encrypted_payload)
            )
        except Exception as e:
            return _fail(f"falha ao decifrar credencial: {type(e).__name__}: {e}")

    # ─── Rede PAGINADA (cada pagina = chamada PAGA; .next(<id>) no Datasets) ─
    pages: list = []
    next_id: str | None = None
    truncado = False
    for _ in range(_MAX_PAGINAS):
        ds = query_name if not next_id else f"{query_name}.next({next_id})"
        try:
            result = await query_entity(
                config=config, base_url=base_url, doc=cnpj_digits,
                datasets=ds, limit=1,
            )
        except BigDataCorpAdapterError as e:
            if not pages:
                return _fail(f"consulta BDC: {type(e).__name__}: {e}")
            errors.append(f"paginacao parou: {type(e).__name__}: {e}")
            break
        pages.append(result)
        block = _lawsuits_block(result.payload)
        next_id = (block or {}).get("NextPageId") or None
        if not next_id or not (block or {}).get("Lawsuits"):
            next_id = None
            break
    else:
        truncado = bool(next_id)  # saiu por _MAX_PAGINAS e ainda havia next
    if truncado:
        # Nao e erro (ok segue True) — `truncado` e a disclosure §14.6.
        logger.warning(
            "BDC processos: paginacao capada em %d paginas (cnpj=%s) — ha mais",
            _MAX_PAGINAS, cnpj_digits,
        )

    query_id = pages[0].payload.get("QueryId") if pages else None

    # ─── Bronze: 1 row por pagina (raw fiel ao vendor) ────────────────────
    raw_id: UUID | None = None
    try:
        async with AsyncSessionLocal() as db:
            for result in pages:
                pl = result.payload
                raw = BdcRawConsulta(
                    tenant_id=tenant_id, cnpj=cnpj_digits, public_code=_PUBLIC_CODE,
                    provider_api=provider_api, datasets=query_name,
                    query_id=pl.get("QueryId"),
                    found=bool(pl.get("Result") or []),
                    status_code=result.status_code, dataset_status_code=None,
                    payload=pl, payload_sha256=_sha256(pl),
                    latency_ms=result.latency_ms, triggered_by=triggered_by,
                    fetched_by_version=ADAPTER_VERSION,
                )
                db.add(raw)
                await db.flush()
                if raw_id is None:
                    raw_id = raw.id  # linka silver a 1a pagina (representativo)
            await db.commit()
    except Exception as e:
        logger.exception("BDC processos: bronze falhou (cnpj=%s)", cnpj_digits)
        errors.append(f"bronze: {type(e).__name__}: {e}")

    # ─── Merge das paginas -> 1 payload -> map 1x (resumo sobre o todo) ────
    combined = _merge_pages([r.payload for r in pages])
    hash_origem = _sha256(combined) if combined else None
    qtd_proc = qtd_partes = qtd_novos = qtd_ativos = qtd_exec = 0
    common: dict[str, Any] = {
        "raw_id": raw_id,
        "hash_origem": hash_origem,
        "ingested_by_version": ADAPTER_VERSION,
        "unidade_administrativa_id": unidade_administrativa_id,
    }
    mapped = map_processos(combined or {}, cnpj=cnpj_digits, dataset=query_name)
    try:
        async with AsyncSessionLocal() as db:
            if mapped.processos:
                qtd_proc, qtd_partes, qtd_novos = await upsert_pj_processos(
                    db, tenant_id=tenant_id, cnpj=cnpj_digits,
                    processos=mapped.processos, **common,
                )
            if mapped.resumo is not None:
                qtd_ativos = mapped.resumo.qtd_ativos
                qtd_exec = mapped.resumo.qtd_execucoes_contra
                await upsert_pj_processo_resumo(
                    db, tenant_id=tenant_id, cnpj=cnpj_digits,
                    resumo=mapped.resumo, **common,
                )
            await db.commit()
    except Exception as e:
        logger.exception("BDC processos: silver falhou (cnpj=%s)", cnpj_digits)
        errors.append(f"silver: {type(e).__name__}: {e}")

    return ProcessosResult(
        ok=not errors, found=mapped.found, cnpj=cnpj_digits, raw_id=raw_id,
        query_id=query_id, qtd_processos=qtd_proc, qtd_partes=qtd_partes,
        qtd_andamentos_novos=qtd_novos, qtd_ativos=qtd_ativos,
        qtd_execucoes_contra=qtd_exec, paginas=len(pages), truncado=truncado,
        adapter_version=ADAPTER_VERSION, errors=errors,
    )
