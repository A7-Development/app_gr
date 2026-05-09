"""Entry point publico do adapter BDC.

Orquestra:
    1. Abre row em provedor_dados_sync_run (status=IN_PROGRESS).
    2. Le credencial ativa do provider em provedor_dados_credencial,
       decifra o envelope.
    3. Chama client.query_pricing() (a API e gratis — pode chamar sem fear).
    4. Chama pricing_sync._parse_pricing_payload() + apply_catalog_diff().
    5. Fecha sync_run com counters + status=OK ou ERROR.

Idempotente — rodar 2x seguidas com payload identico produz `unchanged`
em todas as linhas e zero entrada nova em preco_historico.

Erro em qualquer etapa => sync_run vira ERROR + error_message preenchido,
transacao da escrita do diff e revertida (run row commita separadamente
para preservar trilha mesmo em falha).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.data.bigdatacorp.client import (
    PricingResult,
    query_pricing,
)
from app.modules.integracoes.adapters.data.bigdatacorp.config import (
    BigDataCorpConfig,
)
from app.modules.integracoes.adapters.data.bigdatacorp.errors import (
    BigDataCorpAdapterError,
    BigDataCorpConfigError,
)
from app.modules.integracoes.adapters.data.bigdatacorp.pricing_sync import (
    CatalogSyncCounters,
    _parse_pricing_payload,
    apply_catalog_diff,
)
from app.modules.integracoes.adapters.data.bigdatacorp.version import (
    ADAPTER_VERSION,
)
from app.shared.crypto.envelope import decrypt_envelope
from app.shared.data_providers.enums import CatalogSyncStatus
from app.shared.data_providers.models.catalog_sync_run import (
    DataProviderCatalogSyncRun,
)
from app.shared.data_providers.models.credential import (
    DataProviderCredential,
)
from app.shared.data_providers.models.provider import DataProvider

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CatalogSyncReport:
    """Resultado terminal de um sync — devolvido pra caller (script ou cron)."""

    sync_run_id: UUID
    status: CatalogSyncStatus
    counters: CatalogSyncCounters | None
    error_message: str | None
    pricing_payload_keys: list[str] | None  # top-level keys, util pra debug
    latency_ms: float | None


async def sync_catalog_for_provider(
    *,
    db: AsyncSession,
    provider_id: UUID,
    triggered_by: str = "manual",
    save_payload_to: str | None = None,
) -> CatalogSyncReport:
    """Executa um sync de catalogo para o provider informado.

    Caller passa AsyncSession ja aberta. Esta funcao gerencia:
        - INSERT da row em sync_run
        - leitura+decifra da credencial
        - chamada de rede
        - parse + diff
        - UPDATE da row em sync_run
        - commit/rollback granulares (sync_run sempre commita pra preservar
          trilha; o diff revertido em falha)

    Args:
        db: AsyncSession aberta.
        provider_id: row do provider (ex.: BDC).
        triggered_by: "manual" | "scheduler" | "user:<email>" — texto livre
            registrado em sync_run.triggered_by.
        save_payload_to: caminho de arquivo opcional. Se passado, dump do
            payload bruto da /precos/ vai pra esse arquivo ANTES do parse —
            ajuda o operador inspecionar shape em caso de ParserError.

    Returns:
        CatalogSyncReport com sync_run_id + status + contadores ou erro.
    """
    # ─── 1. Materializa provider + credencial ─────────────────────────────
    provider = await db.get(DataProvider, provider_id)
    if provider is None:
        raise BigDataCorpConfigError(
            f"Provider {provider_id} nao existe em provedor_dados"
        )
    if not provider.enabled:
        raise BigDataCorpConfigError(
            f"Provider {provider.slug.value} (id={provider_id}) esta "
            "desligado (enabled=false). Mantenedor precisa religar antes."
        )

    credential = await _load_active_credential(db, provider_id=provider_id)
    if credential is None:
        raise BigDataCorpConfigError(
            f"Provider {provider.slug.value} nao tem credencial ativa em "
            "provedor_dados_credencial. Cadastre uma antes do 1o sync."
        )

    try:
        plain = decrypt_envelope(credential.encrypted_payload)
    except Exception as e:  # EnvelopeError ou outro
        raise BigDataCorpConfigError(
            f"Falha ao decifrar credencial alias={credential.alias!r}: "
            f"{type(e).__name__}: {e}"
        ) from e

    config = BigDataCorpConfig.from_dict(plain)

    # ─── 2. Abre sync_run + COMMIT — preserva trilha mesmo se quebrar ─────
    run = DataProviderCatalogSyncRun(
        provider_id=provider_id,
        adapter_version=ADAPTER_VERSION,
        triggered_by=triggered_by,
        started_at=datetime.now(timezone.utc),
        status=CatalogSyncStatus.IN_PROGRESS,
        credential_id=credential.id,
    )
    db.add(run)
    await db.flush()
    sync_run_id = run.id
    await db.commit()

    # ─── 3. Chamada de rede + parse + diff (em try/except) ────────────────
    try:
        result = await query_pricing(
            config=config,
            base_url=provider.base_url,
        )
        if save_payload_to:
            _dump_payload_to_file(save_payload_to, result)

        parsed = _parse_pricing_payload(result.payload)
        counters = await apply_catalog_diff(
            db=db,
            provider_id=provider_id,
            parsed=parsed,
            sync_run_id=sync_run_id,
        )

        # Atualiza run row na mesma transacao do diff e commita junto —
        # OK porque chegou aqui sem erro.
        run = await db.get(DataProviderCatalogSyncRun, sync_run_id)
        if run is not None:
            run.status = CatalogSyncStatus.OK
            run.finished_at = datetime.now(timezone.utc)
            run.datasets_added = counters.added
            run.datasets_updated = counters.updated
            run.datasets_unchanged = counters.unchanged
            run.datasets_removed = counters.removed
        await db.commit()

        return CatalogSyncReport(
            sync_run_id=sync_run_id,
            status=CatalogSyncStatus.OK,
            counters=counters,
            error_message=None,
            pricing_payload_keys=sorted(result.payload.keys()),
            latency_ms=result.latency_ms,
        )

    except BigDataCorpAdapterError as e:
        # Erro tipado — reverte diff (transacao corrente), depois UPDATE
        # da run com status=ERROR em transacao nova.
        await db.rollback()
        msg = f"{type(e).__name__}: {e}"
        await _close_run_with_error(db, sync_run_id=sync_run_id, message=msg)
        logger.warning(
            "BDC catalog sync falhou (provider=%s): %s",
            provider_id,
            msg,
        )
        return CatalogSyncReport(
            sync_run_id=sync_run_id,
            status=CatalogSyncStatus.ERROR,
            counters=None,
            error_message=msg,
            pricing_payload_keys=None,
            latency_ms=None,
        )
    except Exception as e:
        # Erro nao tipado — registra mas re-levanta pra o caller saber que
        # foi anormal (bug, nao falha de fonte).
        await db.rollback()
        msg = f"unexpected: {type(e).__name__}: {e}"
        await _close_run_with_error(db, sync_run_id=sync_run_id, message=msg)
        logger.exception(
            "BDC catalog sync ERRO INESPERADO (provider=%s)", provider_id
        )
        raise


async def _load_active_credential(
    db: AsyncSession, *, provider_id: UUID
) -> DataProviderCredential | None:
    """Le a credencial ativa do provider — a primeira encontrada com active=true.

    Multiplas credenciais ativas e cenario de rotacao (transitorio); pegamos
    a primeira por ordem de updated_at desc. Mantenedor garante que a "atual"
    e a mais recente.
    """
    stmt = (
        select(DataProviderCredential)
        .where(DataProviderCredential.provider_id == provider_id)
        .where(DataProviderCredential.active.is_(True))
        .order_by(DataProviderCredential.updated_at.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def _close_run_with_error(
    db: AsyncSession, *, sync_run_id: UUID, message: str
) -> None:
    """Marca a run como ERROR. Comita em transacao propria.

    Trunca message para caber em coluna TEXT sem explodir; nada de
    truncamento medio — TEXT do Postgres aceita dezenas de KB.
    """
    run = await db.get(DataProviderCatalogSyncRun, sync_run_id)
    if run is None:
        # Run sumiu — algo muito estranho, so loga.
        logger.error(
            "Tentou fechar sync_run %s com erro mas a row sumiu: %s",
            sync_run_id,
            message,
        )
        return
    run.status = CatalogSyncStatus.ERROR
    run.finished_at = datetime.now(timezone.utc)
    run.error_message = message[:8000]
    await db.commit()


def _dump_payload_to_file(path: str, result: PricingResult) -> None:
    """Persiste o payload + metadados pra inspecao manual."""
    import json
    from pathlib import Path

    blob: dict[str, Any] = {
        "_meta": {
            "adapter_version": result.adapter_version,
            "status_code": result.status_code,
            "latency_ms": result.latency_ms,
            "captured_at": datetime.now(timezone.utc).isoformat(),
        },
        "payload": result.payload,
    }
    Path(path).write_text(
        json.dumps(blob, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    logger.info("Payload bruto do BDC /precos/ salvo em %s", path)


__all__ = [
    "ADAPTER_VERSION",
    "CatalogSyncReport",
    "sync_catalog_for_provider",
]
