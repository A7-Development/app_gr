"""File Gateway -- servico da landing zone multi-tenant (Strata Collector).

Porta de entrada UNICA de arquivos externos (CLAUDE.md: plano Landing Zone
2026-07-06). Tres origens convergem aqui: agente no servidor do cliente,
upload de UI (features novas) e API futura. Responsabilidades:

- autenticar o agente por token opaco (sha256 em `agent_credential`);
- validar (tamanho, quantidade, source_label permitido pela watch_config);
- deduplicar por sha256 dentro de (tenant, source_label);
- gravar blob no `StorageBackend` + linha no registry `file_landing`;
- auditar o batch no `decision_log` (§14.2).
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.modules.integracoes.models.agent_credential import AgentCredential
from app.modules.integracoes.models.file_landing import FileLanding
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.shared.storage import get_storage_backend

GATEWAY_VERSION = "1.0.0"
_TOKEN_PREFIX = "strata_agt_"

STATUS_RECEIVED = "received"
STATUS_DUPLICATE = "duplicate"
STATUS_REJECTED = "rejected"


@dataclass(frozen=True)
class IncomingFile:
    """Arquivo de um batch de upload, ja lido em memoria."""

    nome_arquivo: str
    content_type: str | None
    body: bytes


@dataclass(frozen=True)
class FileReceipt:
    """Resultado por arquivo devolvido ao agente."""

    nome_arquivo: str
    status: str  # received | duplicate | rejected
    sha256: str | None = None
    motivo: str | None = None


# ---- Tokens ----------------------------------------------------------------


def generate_token() -> str:
    """Token plaintext exibido UMA vez na criacao da credencial."""
    return _TOKEN_PREFIX + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def get_active_credential(
    db: AsyncSession, token: str
) -> AgentCredential | None:
    """Lookup por hash; None quando inexistente ou revogada."""
    if not token:
        return None
    row = (
        await db.execute(
            select(AgentCredential).where(
                AgentCredential.token_hash == hash_token(token),
                AgentCredential.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    return row


def allowed_source_labels(credential: AgentCredential) -> set[str]:
    """Labels que a watch_config autoriza este agente a entregar."""
    watches = (credential.watch_config or {}).get("watches", [])
    return {
        w["source_label"]
        for w in watches
        if isinstance(w, dict) and w.get("source_label")
    }


async def touch_heartbeat(
    db: AsyncSession, credential: AgentCredential, *, agent_version: str | None
) -> None:
    """Atualiza last_seen_at (+ versao reportada) no /ping e no /upload."""
    credential.last_seen_at = datetime.now(UTC)
    if agent_version:
        credential.agent_version = agent_version[:32]
    await db.flush()


# ---- Upload ----------------------------------------------------------------


def _storage_key(
    *,
    tenant_id: UUID,
    ua_id: UUID | None,
    source_label: str,
    sha256: str,
    received: datetime,
) -> str:
    ua_segment = str(ua_id) if ua_id else "sem-ua"
    return (
        f"{tenant_id}/{ua_segment}/{source_label}/"
        f"{received:%Y}/{received:%m}/{sha256}"
    )


async def receive_files(
    db: AsyncSession,
    credential: AgentCredential,
    *,
    source_label: str,
    files: list[IncomingFile],
    agent_version: str | None,
) -> list[FileReceipt]:
    """Processa um batch de upload do agente. Commita registry + decision_log.

    Dedup em 3 niveis: dentro do batch (sha visto), contra o registry
    (SELECT por shas) e — backstop de corrida — UNIQUE no banco.
    """
    settings = get_settings()
    storage = get_storage_backend()
    now = datetime.now(UTC)

    receipts: list[FileReceipt] = []
    allowed = allowed_source_labels(credential)
    if source_label not in allowed:
        # Politica mora no servidor: label fora da watch_config = batch inteiro
        # rejeitado (agente desatualizado ou mal configurado).
        receipts = [
            FileReceipt(
                nome_arquivo=f.nome_arquivo,
                status=STATUS_REJECTED,
                motivo=f"source_label '{source_label}' nao autorizado para este agente",
            )
            for f in files
        ]
        await _log_batch(
            db, credential, source_label=source_label,
            agent_version=agent_version, receipts=receipts,
        )
        await db.commit()
        return receipts

    # Shas ja conhecidos no escopo (tenant, label) — dedup contra o registry.
    shas = {hashlib.sha256(f.body).hexdigest() for f in files}
    existing = set(
        (
            await db.execute(
                select(FileLanding.sha256).where(
                    FileLanding.tenant_id == credential.tenant_id,
                    FileLanding.source_label == source_label,
                    FileLanding.sha256.in_(shas),
                )
            )
        ).scalars()
    )

    seen_in_batch: set[str] = set()
    for f in files:
        if not f.body:
            receipts.append(
                FileReceipt(
                    nome_arquivo=f.nome_arquivo,
                    status=STATUS_REJECTED,
                    motivo="arquivo vazio",
                )
            )
            continue
        if len(f.body) > settings.FILEDROP_MAX_FILE_BYTES:
            receipts.append(
                FileReceipt(
                    nome_arquivo=f.nome_arquivo,
                    status=STATUS_REJECTED,
                    motivo=(
                        f"arquivo excede o limite de "
                        f"{settings.FILEDROP_MAX_FILE_BYTES} bytes"
                    ),
                )
            )
            continue

        sha = hashlib.sha256(f.body).hexdigest()
        if sha in existing or sha in seen_in_batch:
            receipts.append(
                FileReceipt(
                    nome_arquivo=f.nome_arquivo, status=STATUS_DUPLICATE, sha256=sha
                )
            )
            continue
        seen_in_batch.add(sha)

        key = _storage_key(
            tenant_id=credential.tenant_id,
            ua_id=credential.unidade_administrativa_id,
            source_label=source_label,
            sha256=sha,
            received=now,
        )
        await storage.put(key, f.body)
        db.add(
            FileLanding(
                tenant_id=credential.tenant_id,
                unidade_administrativa_id=credential.unidade_administrativa_id,
                source_label=source_label,
                nome_arquivo=f.nome_arquivo[:512],
                sha256=sha,
                size_bytes=len(f.body),
                content_type=f.content_type,
                storage_key=key,
                agent_credential_id=credential.id,
                agent_version=(agent_version or None),
            )
        )
        receipts.append(
            FileReceipt(nome_arquivo=f.nome_arquivo, status=STATUS_RECEIVED, sha256=sha)
        )

    await touch_heartbeat(db, credential, agent_version=agent_version)
    await _log_batch(
        db, credential, source_label=source_label,
        agent_version=agent_version, receipts=receipts,
    )
    await db.commit()
    return receipts


async def _log_batch(
    db: AsyncSession,
    credential: AgentCredential,
    *,
    source_label: str,
    agent_version: str | None,
    receipts: list[FileReceipt],
) -> None:
    counts = {
        STATUS_RECEIVED: 0,
        STATUS_DUPLICATE: 0,
        STATUS_REJECTED: 0,
    }
    for r in receipts:
        counts[r.status] += 1
    db.add(
        DecisionLog(
            tenant_id=credential.tenant_id,
            decision_type=DecisionType.SYNC,
            rule_or_model="file_gateway",
            rule_or_model_version=GATEWAY_VERSION,
            endpoint_name=source_label,
            triggered_by=f"agent:{credential.id}",
            inputs_ref={
                "agent_credential_id": str(credential.id),
                "agent_name": credential.name,
                "agent_version": agent_version,
                "n_files": len(receipts),
            },
            output={
                "received": counts[STATUS_RECEIVED],
                "duplicates": counts[STATUS_DUPLICATE],
                "rejected": counts[STATUS_REJECTED],
                "rejected_files": [
                    {"nome_arquivo": r.nome_arquivo, "motivo": r.motivo}
                    for r in receipts
                    if r.status == STATUS_REJECTED
                ],
            },
            explanation=(
                f"Batch filedrop '{source_label}': {counts[STATUS_RECEIVED]} novos, "
                f"{counts[STATUS_DUPLICATE]} duplicados, {counts[STATUS_REJECTED]} rejeitados."
            ),
        )
    )
    await db.flush()
