"""Helpers compartilhados das consultas Infosimples (provider, bronze, erros).

Extraido para servir tanto JUCESP quanto protestos sem duplicar a mecanica de
provider/credencial/bronze. O `infosimples_junta` mantem suas copias privadas
(zero regressao); novos servicos (protesto, ...) consomem daqui.

O bronze e o MESMO `wh_infosimples_raw_consulta` (generico por public_code +
consulta_path); guarda so o RESPONSE (o request carrega login de portal/PII).
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.data.infosimples import (
    ADAPTER_VERSION,
    InfosimplesConfig,
)
from app.modules.integracoes.adapters.data.infosimples.errors import (
    InfosimplesAdapterError,
)
from app.shared.crypto.envelope import decrypt_envelope
from app.shared.data_providers.models.credential import DataProviderCredential
from app.shared.data_providers.models.dataset import DataProviderDataset
from app.shared.data_providers.models.provider import DataProvider
from app.warehouse import InfosimplesRawConsulta

PROVIDER_SLUG = "INFOSIMPLES"

# Codigos aplicacionais da Infosimples que indicam o PORTAL DA FONTE (gov.br /
# CENPROT / JUCESP) instavel, fora do ar ou lento -- TRANSITORIOS e re-tentaveis,
# NAO "nao encontrado". Familia 606-615. (Ver infosimples_junta para o detalhe
# de cada code; mesma familia vale pro CENPROT.)
TRANSIENT_SOURCE_CODES = frozenset(range(606, 616))


def digits(raw: Any) -> str:
    return re.sub(r"\D", "", str(raw or ""))


def is_transient(resp: Any) -> bool:
    return int(getattr(resp, "code", 0) or 0) in TRANSIENT_SOURCE_CODES


def failure_message(resp: Any) -> str:
    """Mensagem legivel: code_message + motivo real do vendor (errors[0])."""
    msg = f"{resp.code} · {resp.code_message}"
    if resp.errors:
        first = str(resp.errors[0]).strip()
        if first and first not in msg:
            msg = f"{msg} — {first}"
    return msg


async def load_provider_and_config(
    db: AsyncSession,
) -> tuple[DataProvider, InfosimplesConfig]:
    """Provedor habilitado + credencial ativa decifrada (envelope Fernet)."""
    provider = (
        await db.execute(
            select(DataProvider).where(DataProvider.slug == PROVIDER_SLUG)
        )
    ).scalar_one_or_none()
    if provider is None or not provider.enabled:
        raise InfosimplesAdapterError(
            "Provedor Infosimples não cadastrado/habilitado."
        )
    credential = (
        (
            await db.execute(
                select(DataProviderCredential)
                .where(
                    DataProviderCredential.provider_id == provider.id,
                    DataProviderCredential.active.is_(True),
                )
                .order_by(DataProviderCredential.updated_at.desc())
                .limit(1)
            )
        )
        .scalars()
        .first()
    )
    if credential is None:
        raise InfosimplesAdapterError(
            "Nenhuma credencial Infosimples ativa. Cadastre em "
            "/admin/dados/provedores."
        )
    plain = decrypt_envelope(credential.encrypted_payload)
    return provider, InfosimplesConfig.from_dict(
        plain,
        base_url=provider.base_url,
        timeout_ms=provider.default_timeout_ms,
    )


async def resolve_dataset(
    db: AsyncSession, *, provider_id: UUID, public_code: str
) -> DataProviderDataset:
    """Resolve o dataset pelo public_code (white-label). O path tecnico vem de
    `provider_query_name` -- divergencia com a doc se corrige por UPDATE."""
    dataset = (
        await db.execute(
            select(DataProviderDataset).where(
                DataProviderDataset.provider_id == provider_id,
                DataProviderDataset.public_code == public_code,
            )
        )
    ).scalar_one_or_none()
    if dataset is None or not dataset.provider_query_name:
        raise InfosimplesAdapterError(
            f"Dataset {public_code!r} não cadastrado no catálogo do Infosimples."
        )
    return dataset


async def store_bronze(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    documento: str,
    public_code: str,
    consulta_path: str,
    resp: Any,
    found: bool,
    triggered_by: str | None,
) -> UUID:
    """Grava o RESPONSE no bronze generico. Caller commita. Retorna o raw_id."""
    payload: dict[str, Any] = getattr(resp, "raw", {}) or {}
    sha = hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    row = InfosimplesRawConsulta(
        tenant_id=tenant_id,
        documento=documento[:20],
        public_code=public_code,
        consulta_path=consulta_path[:128],
        api_code=getattr(resp, "code", None),
        found=found,
        status_code=getattr(resp, "http_status", 0),
        payload=payload,
        payload_sha256=sha,
        latency_ms=getattr(resp, "latency_ms", None),
        triggered_by=triggered_by,
        fetched_by_version=ADAPTER_VERSION,
    )
    db.add(row)
    await db.flush()
    return row.id
