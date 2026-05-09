"""QiTech relatorios assincronos -- familia /v2/queue/scheduler/report/*.

Diferente dos endpoints sincronos /netreport/* (resp JSON imediata), aqui
funciona via job + callback:

    1. POST /v2/queue/scheduler/report/<tipo> body={callbackUrl, cnpjFundo, date}
       -> retorna {jobId, status:WAITING}
    2. QiTech processa (~10s a varios minutos)
    3. POST callback {WEBHOOK_BASE}/...?ref=<uuid_local>&token=<hmac>
       body: {webhookId, jobId, eventType, data:{fileLink}}
    4. fileLink e URL S3 presigned com TTL ~24h (CSV)

Modulo expoe:
- `request_fidc_estoque_report(...)` -- dispara POST e cria QitechReportJob
- `process_fidc_estoque_callback(...)` -- ao receber callback: valida token,
  baixa CSV, salva raw, mapper, upsert canonico, atualiza job
- `compute_callback_token(...)` -- HMAC-SHA256 truncado de um `ref` opaco
- `_extract_s3_expiry(...)` -- parse `Expires=<unix>` do query string

Anti-spoof: a QiTech NAO assina o callback. Defesa = HMAC de um UUID local
nosso (`ref`) embutido no callbackUrl como `?ref=<uuid>&token=<hmac>`. O
UUID e o `id` do `QitechReportJob` (pre-gerado antes do POST), garantindo
que o token possa ser computado ANTES de conhecermos o `qitech_job_id`
devolvido pela QiTech. Sem `QITECH_WEBHOOK_SECRET` ninguem forja.
"""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, date, datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

import httpx
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


def compute_callback_token(*, ref: str, secret: str | None = None) -> str:
    """HMAC-SHA256(secret, ref) truncado pra 32 hex chars.

    `ref` e um identificador opaco que vai no callbackUrl (`?ref=<...>`)
    junto com o token. Receiver computa o token esperado a partir do `ref`
    da query string e compara com o `?token=`. Sem conhecer
    `QITECH_WEBHOOK_SECRET`, atacante nao consegue forjar callback.

    No fluxo atual o `ref` e o `id` do `QitechReportJob` (UUID local
    pre-gerado antes do POST). Mantemos o param opaco pra deixar o helper
    reutilizavel se outra familia de relatorio precisar.
    """
    s = secret if secret is not None else get_settings().QITECH_WEBHOOK_SECRET
    if not s:
        # Sem secret configurado, callback funciona mas sem proteçao.
        # Retornamos string vazia — receiver tem que tratar igual.
        return ""
    digest = hmac.new(s.encode("utf-8"), ref.encode("utf-8"), hashlib.sha256)
    return digest.hexdigest()[:_TOKEN_LEN]


def verify_callback_token(*, ref: str, token: str) -> bool:
    """Valida token vindo do query string contra o esperado para `ref`."""
    expected = compute_callback_token(ref=ref)
    if not expected:
        # Sem secret -> sem validacao. Em prod isso DEVE ser configurado.
        return True
    return hmac.compare_digest(expected, token or "")


def build_callback_url(*, ref: str, base_url: str | None = None) -> str:
    """Monta URL de callback que vai no body do POST QiTech.

    Formato: {BASE}/api/v1/integracoes/webhooks/qitech/job-callback
             ?ref=<ref>&token=<hmac>

    Quando nao ha `QITECH_WEBHOOK_SECRET` (DEV/test), o `?token=` sai vazio
    e o receiver aceita qualquer valor — `?ref=` continua presente porque
    e ele que identifica o job no DB.
    """
    base = base_url if base_url is not None else get_settings().QITECH_WEBHOOK_BASE_URL
    base = base.rstrip("/")
    token = compute_callback_token(ref=ref)
    suffix = "/api/v1/integracoes/webhooks/qitech/job-callback"
    return f"{base}{suffix}?ref={ref}&token={token}"


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

    Estrategia anti-spoof:
        Pre-geramos `local_uuid = uuid4()` que sera o `id` do job no DB.
        O callbackUrl enviado a QiTech ja vem assinado:
            ?ref=<local_uuid>&token=hmac(local_uuid)
        Quando o callback chega, receiver:
            1. Valida HMAC(ref) == token (sem consultar banco).
            2. Faz lookup do job por id == ref.
            3. Pega qitech_job_id do DB (e cross-checa com body.jobId).

    Isso resolve o catch-22 anterior: nao precisamos esperar o jobId da
    QiTech pra montar o token, porque o token assina algo que NOS
    geramos antes do POST.

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
    # 1. Pre-gera UUID local que vai assinar o token + identificar o job
    #    quando o callback voltar. Sem isso, callback chega rejeitado por
    #    token vazio (ver historico do bug 2026-04-26).
    local_uuid = uuid4()
    base_url_setting = get_settings().QITECH_WEBHOOK_BASE_URL
    base_url = base_url_setting or "https://localhost-no-callback-base-configured"
    callback_url_sent = build_callback_url(
        ref=str(local_uuid), base_url=base_url
    )
    callback_token = compute_callback_token(ref=str(local_uuid))

    # 2. POST com callbackUrl ja assinado
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

    # 3. Normaliza status (defensivo) e CNPJ (digits-only pra idempotencia).
    try:
        status = QitechJobStatus(qitech_status_raw)
    except ValueError:
        status = QitechJobStatus.WAITING
    cnpj_digits = re.sub(r"\D", "", cnpj_fundo)

    # 4. Persiste com `id=local_uuid` — esse UUID e o ref usado pelo callback
    job = QitechReportJob(
        id=local_uuid,
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
    local_job_id: UUID,
    file_link: str,
    qitech_job_id: str | None = None,
    qitech_webhook_id: int | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Processa callback SUCCESS: baixa CSV, salva raw, mapper, canonico.

    Idempotente: se `result_downloaded_at` ja preenchido, nao re-processa.

    Args:
        db: sessao SQLAlchemy.
        local_job_id: `id` do `QitechReportJob` extraido do `?ref=` da URL
            do callback (validado por HMAC pelo receiver).
        file_link: URL S3 presigned do CSV (do `data.fileLink`).
        qitech_job_id: vem do body do callback (campo `jobId`). Opcional —
            se passado, fazemos cross-check contra o que ficou salvo no
            DB e logamos warning em caso de divergencia (defense in depth).
        qitech_webhook_id: id numerico interno da QiTech (do `webhookId`).
        http_client: opcional pra mockar download em testes.

    Returns:
        Resumo com {ok, rows_canonical, raw_id, idempotent, error?}.

    Raises:
        ValueError: local_job_id nao existe (callback orfao — atacante,
            bug, ou job deletado entre POST e callback).
    """
    # 1. Lookup pelo UUID local (que o receiver validou via HMAC)
    job = await db.get(QitechReportJob, local_job_id)
    if job is None:
        raise ValueError(
            f"local_job_id {local_job_id} desconhecido — callback orfao"
        )

    # 1a. Cross-check defensivo: body.jobId deve casar com o salvo no DB.
    #     Em condicoes normais sempre bate; divergencia indica bug ou
    #     replay cruzado (ref de um job, jobId de outro).
    if qitech_job_id is not None and qitech_job_id != job.qitech_job_id:
        import logging
        logging.getLogger("gr.integracoes.qitech").warning(
            "callback jobId %r diverge do esperado %r (local_job_id=%s)",
            qitech_job_id,
            job.qitech_job_id,
            local_job_id,
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
        "qitech_job_id": job.qitech_job_id,
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
        "qitech_job_id": job.qitech_job_id,
    }
