"""BDC cadastral PJ — resolve public_code -> consulta -> bronze -> mapper.

Entry point on-demand do enriquecimento cadastral de empresa. Espelha o
padrao do `serasa_pj_query` (service dono das suas transacoes), adaptado
para credencial GLOBAL (provedor_dados_credencial, sem tenant_id) e para
resolucao WHITE-LABEL: o caller passa um `public_code` neutro (ex.:
"CAD-PJ"); o service descobre vendor + dataset + API e NUNCA vaza isso de
volta — o resultado tipado expoe apenas dado canonico.

Pipeline:
    1. Resolve `public_code` -> provedor_dados_dataset (provider_api,
       provider_dataset_code, enabled_for_sale). [read tx]
    2. Carrega provedor_dados + credencial ativa, decifra envelope. [read tx]
    3. client.query_entity(...) -> envelope BDC cru. [rede, PAGO]
    4. INSERT bronze (wh_bdc_raw_consulta) + commit. [bronze tx isolada]
    5. map_basic_data(payload) -> CadastralFields.

NAO escreve em credit_dossier_company — isso e responsabilidade do modulo
credito (boundary §11.3). Este service devolve os campos mapeados; o
credito persiste o silver. Exposto via `integracoes/public.py`.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
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
from app.modules.integracoes.adapters.data.bigdatacorp.mappers.cadastral import (
    CadastralFields,
    map_basic_data,
)
from app.modules.integracoes.adapters.data.bigdatacorp.version import (
    ADAPTER_VERSION,
)
from app.shared.crypto.envelope import decrypt_envelope
from app.shared.data_providers.enums import DataProviderSlug
from app.shared.data_providers.models.credential import DataProviderCredential
from app.shared.data_providers.models.dataset import DataProviderDataset
from app.shared.data_providers.models.provider import DataProvider
from app.warehouse.bdc_raw_consulta import BdcRawConsulta

logger = logging.getLogger("gr.integracoes.bdc_cadastral")


@dataclass(frozen=True)
class CadastralQueryResult:
    """Resultado tipado do enriquecimento cadastral PJ (white-label).

    NAO carrega identidade do vendor pra fora — `public_code` e neutro.
    """

    ok: bool
    found: bool
    cnpj: str
    public_code: str
    raw_id: UUID | None
    query_id: str | None
    status_code: int | None
    dataset_status_code: int | None
    fields: CadastralFields | None
    adapter_version: str
    errors: list[str]


def _sha256_of_payload(payload: dict) -> str:
    """SHA256 estavel do envelope cru (chaves ordenadas)."""
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


async def fetch_cadastral_pj(
    *,
    tenant_id: UUID,
    cnpj: str,
    triggered_by: str,
    public_code: str = "CAD-PJ",
) -> CadastralQueryResult:
    """Consulta cadastral PJ via public_code e persiste bronze.

    Args:
        tenant_id: dono da consulta (escopo da raw).
        cnpj: 14 digitos (mascarado ou nao — o client normaliza).
        triggered_by: rastreio livre (`dossie:<id>`, `user:<id>`, ...).
        public_code: codigo neutro do dataset (default "CAD-PJ").

    Returns:
        `CadastralQueryResult`. `ok=False` + `errors` em qualquer falha de
        resolucao/credencial/rede; `found=False` quando o CNPJ nao retornou
        dados (Result vazio) — nesse caso `ok=True`, sem erro.
    """
    errors: list[str] = []

    def _fail(msg: str) -> CadastralQueryResult:
        errors.append(msg)
        logger.warning("BDC cadastral falhou (cnpj=%s): %s", cnpj, msg)
        return CadastralQueryResult(
            ok=False,
            found=False,
            cnpj=cnpj,
            public_code=public_code,
            raw_id=None,
            query_id=None,
            status_code=None,
            dataset_status_code=None,
            fields=None,
            adapter_version=ADAPTER_VERSION,
            errors=errors,
        )

    # ─── 1+2. Resolve dataset + provider + credencial (read tx) ───────────
    async with AsyncSessionLocal() as db:
        dataset = (
            await db.execute(
                select(DataProviderDataset).where(
                    DataProviderDataset.public_code == public_code
                )
            )
        ).scalar_one_or_none()
        if dataset is None:
            return _fail(
                f"public_code {public_code!r} nao mapeado em "
                "provedor_dados_dataset"
            )
        if not dataset.enabled_for_sale:
            return _fail(
                f"dataset {public_code!r} nao esta habilitado (enabled_for_sale=false)"
            )

        provider = await db.get(DataProvider, dataset.provider_id)
        if provider is None:
            return _fail(f"provedor_dados {dataset.provider_id} nao existe")
        if not provider.enabled:
            return _fail(
                f"provedor {provider.slug.value} desligado (enabled=false)"
            )
        if provider.slug != DataProviderSlug.BIGDATACORP:
            return _fail(
                f"public_code {public_code!r} resolve pra provider "
                f"{provider.slug.value}, mas este service so atende BigDataCorp"
            )

        base_url = provider.base_url
        provider_api = dataset.provider_api
        provider_dataset_code = dataset.provider_dataset_code
        # Nome tecnico que vai no campo `Datasets` da query — difere do code
        # de billing do /precos (ex.: "BASIC_DATA_V1" -> "basic_data"). Usa o
        # override curado; cai no code quando o mantenedor nao curou.
        query_dataset_name = (
            dataset.provider_query_name or provider_dataset_code
        )

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
            return _fail(
                f"provider {provider.slug.value} sem credencial ativa em "
                "provedor_dados_credencial"
            )
        try:
            plain = decrypt_envelope(credential.encrypted_payload)
            config = BigDataCorpConfig.from_dict(plain)
        except Exception as e:
            return _fail(
                f"falha ao decifrar credencial alias={credential.alias!r}: "
                f"{type(e).__name__}: {e}"
            )

    # ─── 3. Chamada de rede (PAGA) ────────────────────────────────────────
    try:
        result = await query_entity(
            config=config,
            base_url=base_url,
            doc=cnpj,
            datasets=query_dataset_name,
            limit=1,
        )
    except BigDataCorpAdapterError as e:
        return _fail(f"consulta BDC: {type(e).__name__}: {e}")

    # ─── 4. Bronze (tx isolada — sobrevive a bug no mapper) ───────────────
    mapped = map_basic_data(result.payload, dataset=query_dataset_name)
    raw_id: UUID | None = None
    try:
        async with AsyncSessionLocal() as db:
            raw = BdcRawConsulta(
                tenant_id=tenant_id,
                cnpj="".join(ch for ch in cnpj if ch.isdigit()),
                public_code=public_code,
                provider_api=provider_api,
                datasets=query_dataset_name,
                query_id=mapped.query_id,
                found=mapped.found,
                status_code=result.status_code,
                dataset_status_code=mapped.dataset_status_code,
                payload=result.payload,
                payload_sha256=_sha256_of_payload(result.payload),
                latency_ms=result.latency_ms,
                triggered_by=triggered_by,
                fetched_by_version=ADAPTER_VERSION,
            )
            db.add(raw)
            await db.flush()
            raw_id = raw.id
            await db.commit()
    except Exception as e:
        # Bronze falhou, mas a consulta ja custou — loga o payload pra
        # post-mortem e devolve os campos mapeados em memoria mesmo assim.
        logger.exception(
            "BDC cadastral: INSERT bronze falhou (cnpj=%s, query_id=%s)",
            cnpj,
            mapped.query_id,
        )
        errors.append(f"bronze insert: {type(e).__name__}: {e}")

    # ─── 4b. Silver canonico wh_pj_cadastro (tx isolada) ──────────────────
    # integracoes popula o warehouse (§11.3). Tx separada da bronze: se o
    # upsert do silver falhar, a raw (ja commitada) sobrevive.
    if mapped.found and mapped.fields is not None:
        from app.modules.integracoes.services.pj_cadastro_silver import (
            upsert_pj_cadastro,
        )

        try:
            async with AsyncSessionLocal() as db:
                await upsert_pj_cadastro(
                    db,
                    tenant_id=tenant_id,
                    cnpj=cnpj,
                    fields=mapped.fields,
                    raw_id=raw_id,
                    hash_origem=_sha256_of_payload(result.payload),
                    ingested_by_version=ADAPTER_VERSION,
                )
                await db.commit()
        except Exception as e:
            logger.exception(
                "BDC cadastral: upsert wh_pj_cadastro falhou (cnpj=%s)", cnpj
            )
            errors.append(f"silver pj_cadastro: {type(e).__name__}: {e}")

    # ─── 5. Resultado (mapper ja rodou) ───────────────────────────────────
    return CadastralQueryResult(
        ok=True,
        found=mapped.found,
        cnpj=cnpj,
        public_code=public_code,
        raw_id=raw_id,
        query_id=mapped.query_id,
        status_code=result.status_code,
        dataset_status_code=mapped.dataset_status_code,
        fields=mapped.fields,
        adapter_version=ADAPTER_VERSION,
        errors=errors,
    )
