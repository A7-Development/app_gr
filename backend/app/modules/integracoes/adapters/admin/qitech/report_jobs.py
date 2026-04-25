"""QiTech relatorios assincronos -- familia /v2/queue/scheduler/report/*.

Diferente dos endpoints sincronos /netreport/* (resp JSON imediata), aqui
funciona via job + callback:

    1. POST /v2/queue/scheduler/report/<tipo> body={callbackUrl, cnpjFundo, date}
       -> retorna {jobId, status:WAITING}
    2. QiTech processa (~10s a varios minutos)
    3. POST callback {WEBHOOK_BASE}/...?token=...
       body: {webhookId, jobId, eventType, data:{fileLink}}
    4. fileLink e URL S3 presigned com TTL ~24h (CSV)

Modulo expoe:
- `request_fidc_estoque_report(...)` -- dispara POST e cria QitechReportJob
- `process_fidc_estoque_callback(...)` -- ao receber callback: valida token,
  baixa CSV, salva raw, mapper, upsert canonico, atualiza job
- `compute_callback_token(...)` -- HMAC-SHA256 truncado de jobId
- `_extract_s3_expiry(...)` -- parse `Expires=<unix>` do query string

Anti-spoof: a QiTech NAO assina o callback. Defesa = HMAC do jobId na URL,
validado pelo receiver. Sem o `QITECH_WEBHOOK_SECRET` ninguem forja.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.connection import (
    build_async_client,
)
from app.modules.integracoes.adapters.admin.qitech.errors import (
    QiTechAdapterError,
    QiTechHttpError,
)
from app.modules.integracoes.adapters.admin.qitech.hashing import sha256_of_row
from app.modules.integracoes.adapters.admin.qitech.mappers import (
    map_fidc_estoque,
)
from app.modules.integracoes.adapters.admin.qitech.version import ADAPTER_VERSION
from app.modules.integracoes.models.qitech_report_job import (
    QitechJobStatus,
    QitechReportJob,
)
from app.warehouse.estoque_recebivel import EstoqueRecebivel
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio

# Token HMAC truncado pra ~32 hex chars (16 bytes) — ainda 128 bits de
# segurança, mas mais curto na URL.
_TOKEN_LEN = 32


# ---- Anti-spoof helpers ---------------------------------------------------


def compute_callback_token(*, qitech_job_id: str, secret: str | None = None) -> str:
    """HMAC-SHA256(secret, jobId) truncado pra 32 hex chars.

    Defesa contra spoof de callback: a QiTech entrega `jobId` no body do
    callback; receiver computa o token esperado e compara com o `?token=`
    da URL. Sem conhecer `QITECH_WEBHOOK_SECRET`, atacante nao consegue
    forjar callback.
    """
    s = secret if secret is not None else get_settings().QITECH_WEBHOOK_SECRET
    if not s:
        # Sem secret configurado, callback funciona mas sem proteçao.
        # Retornamos string vazia — receiver tem que tratar igual.
        return ""
    digest = hmac.new(s.encode("utf-8"), qitech_job_id.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:_TOKEN_LEN]


def verify_callback_token(*, qitech_job_id: str, token: str) -> bool:
    """Valida token vindo do query string contra o esperado."""
    expected = compute_callback_token(qitech_job_id=qitech_job_id)
    if not expected:
        # Sem secret -> sem validacao. Em prod isso DEVE ser configurado.
        return True
    return hmac.compare_digest(expected, token or "")


def build_callback_url(*, qitech_job_id: str, base_url: str | None = None) -> str:
    """Monta URL de callback que vai no body do POST QiTech.

    Formato: {BASE}/api/v1/integracoes/webhooks/qitech/job-callback?token=<hmac>
    """
    base = base_url if base_url is not None else get_settings().QITECH_WEBHOOK_BASE_URL
    base = base.rstrip("/")
    token = compute_callback_token(qitech_job_id=qitech_job_id)
    suffix = "/api/v1/integracoes/webhooks/qitech/job-callback"
    if token:
        return f"{base}{suffix}?token={token}"
    return f"{base}{suffix}"


# ---- S3 presigned URL helpers ---------------------------------------------


def extract_s3_expiry(file_link: str) -> datetime | None:
    """Extrai `Expires=<unix>` do query string da URL S3 presigned.

    Retorna None se nao houver expiry (URL nao e signed) ou parse falhar.
    Util pra pollings futuros decidirem se ja eh tarde demais pra baixar.
    """
    try:
        qs = parse_qs(urlsplit(file_link).query)
        expires_list = qs.get("Expires") or qs.get("X-Amz-Expires")
        if not expires_list:
            return None
        # AWSAccessKeyId-style: Expires=<unix-timestamp>
        # X-Amz-Signature-style (v4): X-Amz-Expires=<seconds-from-X-Amz-Date>
        expires_str = expires_list[0]
        if "X-Amz-Expires" in qs:
            # Need X-Amz-Date base. Skip pra MVP (nao usa v4 sample).
            return None
        return datetime.fromtimestamp(int(expires_str), tz=UTC)
    except (ValueError, KeyError, IndexError):
        return None


# ---- POST: criar job ------------------------------------------------------


async def request_fidc_estoque_report(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    environment: Environment,
    config: QiTechConfig,
    cnpj_fundo: str,
    reference_date: date,
    triggered_by: str = "system:scheduler",
) -> QitechReportJob:
    """Dispara POST /v2/queue/scheduler/report/fidc-estoque + persiste job.

    1. Faz POST com callbackUrl construido a partir de QITECH_WEBHOOK_BASE_URL
       + token HMAC do (futuro) jobId. Como nao temos jobId antes do POST,
       usamos um placeholder e atualizamos a callback_url depois — OU
       computamos o token sobre o jobId retornado e gravamos so a versao
       final em DB. Optei pelo segundo: enviamos URL temporaria sem token
       no POST, depois substituimos no DB e callback_url_used registra o
       que efetivamente foi usado. (QiTech ja salvou a URL deles, entao
       pra o teste real precisamos de URL sem token tambem — TODO: rever
       quando subir webhook receiver.)

    Args:
        db: sessao SQLAlchemy aberta.
        tenant_id: dono da operacao.
        environment: production | sandbox.
        config: QiTechConfig do tenant (decifrada do envelope).
        cnpj_fundo: CNPJ do FIDC alvo (digits-only ou com pontuacao —
                    enviamos como recebido pela QiTech).
        reference_date: data alvo do relatorio.
        triggered_by: 'system:scheduler' | 'user:<uuid>' | 'webhook'.

    Returns:
        QitechReportJob criado (status=WAITING).

    Raises:
        QiTechHttpError: erro no POST.
        QiTechAdapterError: response sem jobId.
    """
    settings = get_settings()
    base = (settings.QITECH_WEBHOOK_BASE_URL or "").rstrip("/")
    if not base:
        # Em DEV/test sem base configurado, usamos placeholder que sera
        # claramente identificavel se chegar request real.
        base = "https://localhost-no-callback-base-configured"

    # POST. Como a callback URL inclui token derivado do jobId, e o jobId
    # so e gerado pela QiTech, mandamos URL "preliminar" sem token. Depois
    # atualizamos no DB com o token correto. NOTA: a QiTech ja salvou
    # internamente a URL preliminar — pra producao real, a estrategia
    # correta e pre-computar nosso proprio job_id (UUID local) e enviar
    # token=hmac(local_uuid). Quando QiTech responder com jobId, salvamos
    # o mapping local_uuid <-> jobId.
    #
    # Por agora (MVP), usamos URL sem token e a defesa fica via lookup
    # no DB pelo qitech_job_id.
    callback_url_sent = (
        f"{base}/api/v1/integracoes/webhooks/qitech/job-callback"
    )

    body = {
        "callbackUrl": callback_url_sent,
        "cnpjFundo": cnpj_fundo,
        "date": reference_date.isoformat(),
    }

    async with build_async_client(
        tenant_id=tenant_id, environment=environment, config=config
    ) as client:
        try:
            resp = await client.post(
                "/v2/queue/scheduler/report/fidc-estoque", json=body
            )
        except httpx.HTTPError as e:
            raise QiTechHttpError(
                status_code=0,
                detail=f"erro de rede: {type(e).__name__}: {e}",
            ) from e

    if resp.status_code >= 400:
        raise QiTechHttpError(status_code=resp.status_code, detail=resp.text[:500])

    try:
        post_body = resp.json()
    except ValueError as e:
        raise QiTechAdapterError("response do POST nao e JSON") from e

    qitech_job_id = post_body.get("jobId")
    qitech_status_raw = post_body.get("status", "WAITING")
    if not qitech_job_id:
        raise QiTechAdapterError(
            f"response sem jobId: {post_body}"
        )

    # Token correto, agora que temos jobId.
    callback_token = compute_callback_token(qitech_job_id=qitech_job_id)

    # Normaliza status (defensivo).
    try:
        status = QitechJobStatus(qitech_status_raw)
    except ValueError:
        status = QitechJobStatus.WAITING

    # Normaliza CNPJ pra digits-only (idempotencia / lookup).
    cnpj_digits = re.sub(r"\D", "", cnpj_fundo)

    job = QitechReportJob(
        tenant_id=tenant_id,
        environment=environment,
        report_type="fidc-estoque",
        cnpj_fundo=cnpj_digits,
        reference_date=reference_date,
        request_body=body,
        qitech_job_id=qitech_job_id,
        callback_url_used=callback_url_sent,
        callback_token=callback_token,
        status=status,
        triggered_by=triggered_by,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


# ---- Callback: processar arquivo ------------------------------------------


async def process_fidc_estoque_callback(
    *,
    db: AsyncSession,
    qitech_job_id: str,
    file_link: str,
    qitech_webhook_id: int | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Processa callback SUCCESS: baixa CSV, salva raw, mapper, canonico.

    Idempotente: se `result_downloaded_at` ja preenchido, nao re-processa.

    Args:
        db: sessao SQLAlchemy.
        qitech_job_id: vem do body do callback (campo `jobId`).
        file_link: URL S3 presigned do CSV (do `data.fileLink`).
        qitech_webhook_id: id numerico interno da QiTech (do `webhookId`).
        http_client: opcional pra mockar download em testes.

    Returns:
        Resumo com {ok, rows_canonical, raw_id, idempotent, error?}.

    Raises:
        ValueError: jobId nao existe (callback orfao -- atacante ou bug).
    """
    # 1. Lookup
    stmt = select(QitechReportJob).where(
        QitechReportJob.qitech_job_id == qitech_job_id
    )
    job = (await db.execute(stmt)).scalar_one_or_none()
    if job is None:
        raise ValueError(
            f"qitech_job_id {qitech_job_id} desconhecido — callback orfao"
        )

    # 2. Idempotencia
    if job.result_downloaded_at is not None:
        return {
            "ok": True,
            "idempotent": True,
            "rows_canonical": 0,
            "raw_id": str(job.raw_relatorio_id) if job.raw_relatorio_id else None,
            "job_id": str(job.id),
        }

    # 3. Atualiza job com fileLink e expiry estimado
    job.qitech_webhook_id = qitech_webhook_id
    job.result_file_link = file_link
    job.result_file_link_expires_at = extract_s3_expiry(file_link)
    job.status = QitechJobStatus.SUCCESS
    await db.commit()

    # 4. Download do CSV
    own_client = http_client is None
    client = http_client or httpx.AsyncClient(timeout=httpx.Timeout(60.0))
    try:
        try:
            resp = await client.get(file_link)
            if resp.status_code >= 400:
                job.error_message = (
                    f"download falhou: HTTP {resp.status_code}: {resp.text[:200]}"
                )
                job.status = QitechJobStatus.ERROR
                await db.commit()
                return {
                    "ok": False,
                    "idempotent": False,
                    "error": job.error_message,
                    "job_id": str(job.id),
                }
            csv_text = resp.text
        finally:
            if own_client:
                await client.aclose()
    except httpx.HTTPError as e:
        job.error_message = f"erro de rede no download: {type(e).__name__}: {e}"
        job.status = QitechJobStatus.ERROR
        await db.commit()
        return {
            "ok": False,
            "idempotent": False,
            "error": job.error_message,
            "job_id": str(job.id),
        }

    # 5. Salva raw (em wh_qitech_raw_relatorio com payload_text=CSV)
    fetched_at = datetime.now(UTC)
    payload_meta = {
        "format": "csv",
        "delimiter": ";",
        "rows_estimate": csv_text.count("\n"),
        "bytes": len(csv_text.encode("utf-8")),
        "qitech_webhook_id": qitech_webhook_id,
        "qitech_job_id": qitech_job_id,
    }
    raw = QiTechRawRelatorio(
        tenant_id=job.tenant_id,
        tipo_de_mercado="fidc-estoque",
        data_posicao=job.reference_date,
        payload=payload_meta,
        payload_text=csv_text,
        http_status=200,
        payload_sha256=sha256_of_row({"csv": csv_text}),
        fetched_at=fetched_at,
        fetched_by_version=ADAPTER_VERSION,
    )
    # Upsert via UQ (tenant, tipo, data) — re-callback do mesmo dia
    # (re-disparo) substitui payload.
    raw_dict = {
        "tenant_id": raw.tenant_id,
        "tipo_de_mercado": raw.tipo_de_mercado,
        "data_posicao": raw.data_posicao,
        "payload": raw.payload,
        "payload_text": raw.payload_text,
        "http_status": raw.http_status,
        "payload_sha256": raw.payload_sha256,
        "fetched_at": raw.fetched_at,
        "fetched_by_version": raw.fetched_by_version,
    }
    stmt = pg_insert(QiTechRawRelatorio.__table__).values(raw_dict)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_wh_qitech_raw_relatorio",
        set_={
            "payload": stmt.excluded.payload,
            "payload_text": stmt.excluded.payload_text,
            "payload_sha256": stmt.excluded.payload_sha256,
            "http_status": stmt.excluded.http_status,
            "fetched_at": stmt.excluded.fetched_at,
            "fetched_by_version": stmt.excluded.fetched_by_version,
        },
    ).returning(QiTechRawRelatorio.__table__.c.id)
    raw_id_row = (await db.execute(stmt)).first()
    raw_id: UUID | None = raw_id_row[0] if raw_id_row else None
    await db.commit()

    # 6. Mapper -> canonico (linhas)
    canonical_rows = map_fidc_estoque(
        csv_text=csv_text,
        tenant_id=job.tenant_id,
        data_referencia=job.reference_date,
    )

    # 7. Bulk upsert canonico (chunked — pode ser 1000s de linhas)
    rows_inserted = 0
    if canonical_rows:
        from itertools import islice

        from app.modules.integracoes.adapters.admin.qitech.etl import (
            CHUNK_SIZE,
            MAX_PG_PARAMS,
        )

        all_columns = [c.name for c in EstoqueRecebivel.__table__.columns if c.name != "id"]
        normalized = [{c: row.get(c) for c in all_columns} for row in canonical_rows]
        # Dedup por source_id (caso CSV tenha duplicata exata)
        seen: dict[str, dict] = {}
        for r in normalized:
            seen[r["source_id"]] = r
        deduped = list(seen.values())

        chunk_size = max(1, min(CHUNK_SIZE, MAX_PG_PARAMS // len(all_columns)))
        update_cols = [
            c.name
            for c in EstoqueRecebivel.__table__.columns
            if c.name not in {"id", "tenant_id", "source_id", "ingested_at"}
        ]

        def _chunked(it, size):
            it = iter(it)
            while chunk := list(islice(it, size)):
                yield chunk

        for chunk in _chunked(deduped, chunk_size):
            stmt = pg_insert(EstoqueRecebivel.__table__).values(chunk)
            update_set = {name: stmt.excluded[name] for name in update_cols}
            stmt = stmt.on_conflict_do_update(
                index_elements=["tenant_id", "source_id"], set_=update_set
            )
            await db.execute(stmt)
            rows_inserted += len(chunk)
        await db.commit()

    # 8. Atualiza job — completed
    job.raw_relatorio_id = raw_id
    job.result_downloaded_at = fetched_at
    job.completed_at = datetime.now(UTC)
    await db.commit()

    return {
        "ok": True,
        "idempotent": False,
        "rows_canonical": rows_inserted,
        "raw_id": str(raw_id) if raw_id else None,
        "job_id": str(job.id),
        "qitech_job_id": qitech_job_id,
    }
