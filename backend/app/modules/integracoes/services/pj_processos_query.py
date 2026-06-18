"""BDC processos judiciais — consulta `processes` -> bronze -> silver.

Consulta dedicada (separada do dossie multi-dataset) porque processes e pesado
(traz andamentos por padrao) e tem reconciliacao propria (incrementa, nao
subscreve — ver pj_processo_silver). Ingere TODOS os processos (status e LENTE,
nao filtro): risco usa os vivos; garimpo de bens varre tudo.

Exposto via `integracoes/public.py` para node/tool consumirem.
"""

from __future__ import annotations

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
            qtd_execucoes_contra=0, adapter_version=ADAPTER_VERSION, errors=errors,
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

    # ─── Chamada de rede (PAGA) ───────────────────────────────────────────
    try:
        result = await query_entity(
            config=config, base_url=base_url, doc=cnpj_digits,
            datasets=query_name, limit=1,
        )
    except BigDataCorpAdapterError as e:
        return _fail(f"consulta BDC: {type(e).__name__}: {e}")

    payload = result.payload
    query_id = payload.get("QueryId")
    hash_origem = _sha256(payload)

    # ─── Bronze (tx isolada) ──────────────────────────────────────────────
    raw_id: UUID | None = None
    try:
        async with AsyncSessionLocal() as db:
            raw = BdcRawConsulta(
                tenant_id=tenant_id, cnpj=cnpj_digits, public_code=_PUBLIC_CODE,
                provider_api=provider_api, datasets=query_name, query_id=query_id,
                found=bool(payload.get("Result") or []),
                status_code=result.status_code, dataset_status_code=None,
                payload=payload, payload_sha256=hash_origem,
                latency_ms=result.latency_ms, triggered_by=triggered_by,
                fetched_by_version=ADAPTER_VERSION,
            )
            db.add(raw)
            await db.flush()
            raw_id = raw.id
            await db.commit()
    except Exception as e:
        logger.exception("BDC processos: bronze falhou (cnpj=%s)", cnpj_digits)
        errors.append(f"bronze: {type(e).__name__}: {e}")

    # ─── Map + Silver (tx isolada) ────────────────────────────────────────
    qtd_proc = qtd_partes = qtd_novos = qtd_ativos = qtd_exec = 0
    common: dict[str, Any] = {
        "raw_id": raw_id,
        "hash_origem": hash_origem,
        "ingested_by_version": ADAPTER_VERSION,
        "unidade_administrativa_id": unidade_administrativa_id,
    }
    mapped = map_processos(payload, cnpj=cnpj_digits, dataset=query_name)
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
        qtd_execucoes_contra=qtd_exec, adapter_version=ADAPTER_VERSION,
        errors=errors,
    )
