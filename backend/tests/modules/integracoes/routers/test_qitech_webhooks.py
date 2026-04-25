"""Receiver HTTP /api/v1/integracoes/webhooks/qitech/job-callback -- E2E."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.report_jobs import (
    compute_callback_token,
)
from app.modules.integracoes.models.qitech_report_job import (
    QitechJobStatus,
    QitechReportJob,
)
from app.shared.identity.tenant import Tenant

CSV_PATH = (
    Path(__file__).resolve().parents[4]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-08"
    / "fidc-estoque.csv"
)


@pytest.fixture
def csv_text() -> str:
    return CSV_PATH.read_text(encoding="utf-8")


def _callback_url(token: str | None = None) -> str:
    base = "/api/v1/integracoes/webhooks/qitech/job-callback"
    return f"{base}?token={token}" if token else base


@pytest.mark.asyncio
async def test_receiver_aceita_payload_real_e_processa(
    client: AsyncClient, tenant_a: Tenant, csv_text: str
):
    """Payload identico ao callback real do job 908aaf59 — receiver deve
    aceitar, baixar CSV mockado, gravar raw + canonico, retornar accepted=true."""
    qitech_job_id = f"job-recv-{uuid4().hex}"

    # 1. Pre-criar job (simulando POST anterior)
    async with AsyncSessionLocal() as db:
        db.add(
            QitechReportJob(
                tenant_id=tenant_a.id,
                environment=Environment.PRODUCTION,
                report_type="fidc-estoque",
                cnpj_fundo="42449234000160",
                reference_date=date(2026, 1, 8),
                request_body={"x": 1},
                qitech_job_id=qitech_job_id,
                callback_url_used="https://test/callback",
                callback_token="x" * 32,
                status=QitechJobStatus.WAITING,
                triggered_by="test",
            )
        )
        await db.commit()

    # 2. Mockar download do S3
    async def _download(self, url, *args, **kwargs):
        return httpx.Response(200, text=csv_text, request=httpx.Request("GET", url))

    body = {
        "webhookId": 809341,
        "jobId": qitech_job_id,
        "eventType": "fidcEstoque",
        "data": {"fileLink": "https://fidc-custodia.s3.amazonaws.com/x.csv"},
    }

    # Sem QITECH_WEBHOOK_SECRET configurado, verify_callback_token aceita
    # qualquer token. Em DEV/test e ok.
    with patch("httpx.AsyncClient.get", new=_download):
        r = await client.post(_callback_url(), json=body)

    assert r.status_code == 200, r.text
    payload = r.json()
    assert payload["accepted"] is True
    assert payload["idempotent"] is False


@pytest.mark.asyncio
async def test_receiver_token_invalido_retorna_401(
    client: AsyncClient,
):
    """Com QITECH_WEBHOOK_SECRET configurado, token errado bloqueia."""
    body = {
        "webhookId": 1,
        "jobId": "qualquer",
        "eventType": "fidcEstoque",
        "data": {"fileLink": "https://x"},
    }

    # Forca secret configurado pra ativar validacao
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.report_jobs.get_settings"
    ) as gs:
        gs.return_value.QITECH_WEBHOOK_SECRET = "abc" * 10
        r = await client.post(_callback_url(token="errado"), json=body)

    assert r.status_code == 401
    assert "token" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_receiver_token_correto_passa(
    client: AsyncClient, tenant_a: Tenant, csv_text: str
):
    """Token HMAC correto: receiver aceita."""
    qitech_job_id = f"job-tok-{uuid4().hex}"
    secret = "abc" * 10

    async with AsyncSessionLocal() as db:
        db.add(
            QitechReportJob(
                tenant_id=tenant_a.id,
                environment=Environment.PRODUCTION,
                report_type="fidc-estoque",
                cnpj_fundo="42449234000160",
                reference_date=date(2026, 1, 8),
                request_body={"x": 1},
                qitech_job_id=qitech_job_id,
                callback_url_used="https://test/callback",
                callback_token="x" * 32,
                status=QitechJobStatus.WAITING,
                triggered_by="test",
            )
        )
        await db.commit()

    async def _download(self, url, *args, **kwargs):
        return httpx.Response(200, text=csv_text, request=httpx.Request("GET", url))

    body = {
        "webhookId": 1,
        "jobId": qitech_job_id,
        "eventType": "fidcEstoque",
        "data": {"fileLink": "https://x.csv"},
    }

    with (
        patch(
            "app.modules.integracoes.adapters.admin.qitech.report_jobs.get_settings"
        ) as gs,
        patch("httpx.AsyncClient.get", new=_download),
    ):
        gs.return_value.QITECH_WEBHOOK_SECRET = secret
        token = compute_callback_token(qitech_job_id=qitech_job_id)
        r = await client.post(_callback_url(token=token), json=body)

    assert r.status_code == 200, r.text
    assert r.json()["accepted"] is True


@pytest.mark.asyncio
async def test_receiver_jobid_desconhecido_retorna_404(client: AsyncClient):
    """Callback com jobId que nao existe -> 404 (orfao/spoof)."""
    body = {
        "webhookId": 1,
        "jobId": f"orfao-{uuid4().hex}",
        "eventType": "fidcEstoque",
        "data": {"fileLink": "https://x"},
    }
    r = await client.post(_callback_url(), json=body)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_receiver_event_type_desconhecido_aceita_silenciosamente(
    client: AsyncClient,
):
    """Tipo nao mapeado retorna 200 (nao expoe estado interno pra QiTech)."""
    body = {
        "webhookId": 1,
        "jobId": f"x-{uuid4().hex}",
        "eventType": "fidcMovimentacaoFutura",  # nao mapeado
        "data": {"fileLink": "https://x"},
    }
    r = await client.post(_callback_url(), json=body)
    # 200 com accepted=true mesmo sem mapper — nao queremos a QiTech
    # parar de mandar callbacks por causa disso.
    assert r.status_code == 200
    assert r.json()["accepted"] is True


@pytest.mark.asyncio
async def test_receiver_body_invalido_retorna_422(client: AsyncClient):
    """Body sem jobId -> 422 (Pydantic validation error)."""
    r = await client.post(
        _callback_url(),
        json={"webhookId": 1, "eventType": "fidcEstoque", "data": {}},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_receiver_idempotente(
    client: AsyncClient, tenant_a: Tenant, csv_text: str
):
    """2 callbacks identicos -> 1o processa, 2o retorna idempotent=true."""
    qitech_job_id = f"job-idem-recv-{uuid4().hex}"
    async with AsyncSessionLocal() as db:
        db.add(
            QitechReportJob(
                tenant_id=tenant_a.id,
                environment=Environment.PRODUCTION,
                report_type="fidc-estoque",
                cnpj_fundo="42449234000160",
                reference_date=date(2026, 1, 8),
                request_body={"x": 1},
                qitech_job_id=qitech_job_id,
                callback_url_used="https://test/callback",
                callback_token="x" * 32,
                status=QitechJobStatus.WAITING,
                triggered_by="test",
            )
        )
        await db.commit()

    async def _download(self, url, *args, **kwargs):
        return httpx.Response(200, text=csv_text, request=httpx.Request("GET", url))

    body = {
        "webhookId": 1,
        "jobId": qitech_job_id,
        "eventType": "fidcEstoque",
        "data": {"fileLink": "https://x.csv"},
    }

    with patch("httpx.AsyncClient.get", new=_download):
        r1 = await client.post(_callback_url(), json=body)
        r2 = await client.post(_callback_url(), json=body)

    assert r1.status_code == 200
    assert r1.json()["idempotent"] is False
    assert r2.status_code == 200
    assert r2.json()["idempotent"] is True
