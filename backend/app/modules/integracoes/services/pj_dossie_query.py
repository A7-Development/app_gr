"""BDC dossie PJ — consulta MULTI-DATASET unica -> bronze -> todos os silver.

O "node multi-consulta": uma chamada `query_entity` com os datasets de
cadastral + societario + KYC (o BDC aceita `Datasets` separado por virgula =
1 round-trip, cobrado por dataset), materializando todos os silver de uma vez:

    basic_data                  -> wh_pj_cadastro
    relationships               -> wh_pj_vinculo
    economic_group_first_level  -> wh_pj_grupo_indicador
    kyc + owners_kyc            -> wh_pj_kyc (+ _ocorrencia)

Resolve white-label por public_code (CAD-PJ / VINCULOS-PJ / GRUPO-PJ / KYC-PJ /
KYC-SOCIOS-PJ); so consulta os que estiverem `enabled_for_sale`. Exposto via
`integracoes/public.py` para o `BureauQueryNode` consumir.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
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
from app.modules.integracoes.adapters.data.bigdatacorp.mappers.cadastral import (
    map_basic_data,
)
from app.modules.integracoes.adapters.data.bigdatacorp.mappers.kyc import (
    map_kyc,
    map_owners_kyc,
)
from app.modules.integracoes.adapters.data.bigdatacorp.mappers.societario import (
    map_economic_group,
    map_relationships,
)
from app.modules.integracoes.adapters.data.bigdatacorp.version import (
    ADAPTER_VERSION,
)
from app.modules.integracoes.services.pj_cadastro_silver import upsert_pj_cadastro
from app.modules.integracoes.services.pj_kyc_silver import replace_pj_kyc
from app.modules.integracoes.services.pj_societario_silver import (
    replace_pj_vinculos,
    upsert_pj_grupo_indicador,
)
from app.shared.crypto.envelope import decrypt_envelope
from app.shared.data_providers.enums import DataProviderSlug
from app.shared.data_providers.models.credential import DataProviderCredential
from app.shared.data_providers.models.dataset import DataProviderDataset
from app.shared.data_providers.models.provider import DataProvider
from app.warehouse.bdc_raw_consulta import BdcRawConsulta

logger = logging.getLogger("gr.integracoes.bdc_dossie")

# public_code -> papel no dossie. Ordem = ordem no campo Datasets.
_PLAN: list[tuple[str, str]] = [
    ("CAD-PJ", "cadastral"),
    ("VINCULOS-PJ", "vinculos"),
    ("GRUPO-PJ", "grupo"),
    ("KYC-PJ", "kyc_empresa"),
    ("KYC-SOCIOS-PJ", "kyc_socios"),
]


@dataclass(frozen=True)
class DossieResult:
    ok: bool
    found: bool
    cnpj: str
    raw_id: UUID | None
    query_id: str | None
    cadastral_found: bool
    vinculos_count: int
    grupo_found: bool
    kyc_subjects: int
    kyc_ocorrencias: int
    adapter_version: str
    errors: list[str]


def _sha256(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.year in (1, 1900):
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


async def fetch_bdc_dossie_pj(
    *,
    tenant_id: UUID,
    cnpj: str,
    triggered_by: str,
    unidade_administrativa_id: UUID | None = None,
) -> DossieResult:
    """Consulta multi-dataset BDC e materializa cadastral + societario + KYC."""
    errors: list[str] = []
    cnpj_digits = "".join(ch for ch in (cnpj or "") if ch.isdigit())

    def _fail(msg: str) -> DossieResult:
        errors.append(msg)
        logger.warning("BDC dossie falhou (cnpj=%s): %s", cnpj_digits, msg)
        return DossieResult(
            ok=False, found=False, cnpj=cnpj_digits, raw_id=None, query_id=None,
            cadastral_found=False, vinculos_count=0, grupo_found=False,
            kyc_subjects=0, kyc_ocorrencias=0, adapter_version=ADAPTER_VERSION,
            errors=errors,
        )

    # ─── Resolve datasets + provider + credencial ─────────────────────────
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(DataProviderDataset).where(
                    DataProviderDataset.public_code.in_([c for c, _ in _PLAN])
                )
            )
        ).scalars().all()
        by_code = {r.public_code: r for r in rows}
        role_query: dict[str, str] = {}  # papel -> query_name
        provider_id = None
        provider_api = None
        for code, role in _PLAN:
            ds = by_code.get(code)
            if ds is None or not ds.enabled_for_sale:
                # dataset ausente/desligado: pula esse papel (degradacao graciosa)
                logger.info("BDC dossie: %s indisponivel, pulando", code)
                continue
            role_query[role] = ds.provider_query_name or ds.provider_dataset_code
            provider_id = ds.provider_id
            provider_api = ds.provider_api
        if not role_query:
            return _fail("nenhum dataset do dossie habilitado")

        provider = await db.get(DataProvider, provider_id)
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

    datasets_param = ",".join(role_query.values())

    # ─── Chamada de rede (PAGA, 1 round-trip multi-dataset) ───────────────
    try:
        result = await query_entity(
            config=config, base_url=base_url, doc=cnpj_digits,
            datasets=datasets_param, limit=1,
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
                tenant_id=tenant_id, cnpj=cnpj_digits, public_code="DOSSIE-PJ",
                provider_api=provider_api, datasets=datasets_param,
                query_id=query_id,
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
        logger.exception("BDC dossie: bronze falhou (cnpj=%s)", cnpj_digits)
        errors.append(f"bronze: {type(e).__name__}: {e}")

    # ─── Map + Silver (tx isolada) ────────────────────────────────────────
    cad_found = False
    vinc_count = 0
    grupo_found = False
    kyc_subjects = 0
    kyc_occ = 0
    common: dict[str, Any] = {
        "raw_id": raw_id,
        "hash_origem": hash_origem,
        "ingested_by_version": ADAPTER_VERSION,
        "unidade_administrativa_id": unidade_administrativa_id,
    }
    try:
        async with AsyncSessionLocal() as db:
            if "cadastral" in role_query:
                cad = map_basic_data(payload, dataset=role_query["cadastral"])
                if cad.found and cad.fields is not None:
                    cad_found = True
                    await upsert_pj_cadastro(
                        db, tenant_id=tenant_id, cnpj=cnpj_digits,
                        fields=cad.fields,
                        source_updated_at=_parse_dt(
                            cad.fields.basic_data.get("LastUpdateDate")
                        ),
                        **common,
                    )

            if "vinculos" in role_query:
                rel = map_relationships(payload, dataset=role_query["vinculos"])
                vinc_count = await replace_pj_vinculos(
                    db, tenant_id=tenant_id, cnpj=cnpj_digits,
                    vinculos=rel.vinculos, **common,
                )

            if "grupo" in role_query:
                grp = map_economic_group(payload, dataset=role_query["grupo"])
                if grp.found and grp.fields is not None:
                    grupo_found = True
                    await upsert_pj_grupo_indicador(
                        db, tenant_id=tenant_id, cnpj=cnpj_digits,
                        fields=grp.fields, **common,
                    )

            subjects = []
            if "kyc_empresa" in role_query:
                subjects += map_kyc(
                    payload, cnpj=cnpj_digits, dataset=role_query["kyc_empresa"]
                ).subjects
            if "kyc_socios" in role_query:
                subjects += map_owners_kyc(
                    payload, dataset=role_query["kyc_socios"]
                ).subjects
            if subjects:
                kyc_subjects, kyc_occ = await replace_pj_kyc(
                    db, tenant_id=tenant_id, cnpj=cnpj_digits,
                    subjects=subjects, **common,
                )

            await db.commit()
    except Exception as e:
        logger.exception("BDC dossie: silver falhou (cnpj=%s)", cnpj_digits)
        errors.append(f"silver: {type(e).__name__}: {e}")

    return DossieResult(
        ok=not errors,
        found=bool(payload.get("Result") or []),
        cnpj=cnpj_digits, raw_id=raw_id, query_id=query_id,
        cadastral_found=cad_found, vinculos_count=vinc_count,
        grupo_found=grupo_found, kyc_subjects=kyc_subjects,
        kyc_ocorrencias=kyc_occ, adapter_version=ADAPTER_VERSION,
        errors=errors,
    )
