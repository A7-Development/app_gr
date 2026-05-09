"""Receiver HTTP /api/v1/integracoes/webhooks/qitech/job-callback -- E2E."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

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


def _callback_url(*, ref: str | UUID, token: str = "") -> str:
    base = "/api/v1/integracoes/webhooks/qitech/job-callback"
    return f"{base}?ref={ref}&token={token}"


@pytest.mark.asyncio
async def test_receiver_aceita_payload_real_e_processa(
    client: AsyncClient, tenant_a: Tenant, csv_text: str
):
    """Payload identico ao callback real do job 908aaf59 — receiver deve
    aceitar, baixar CSV mockado, gravar raw + canonico, retornar accepted=true."""
    qitech_job_id = f"job-recv-{uuid4().hex}"

    # 1. Pre-criar job (simulando POST anterior). Capturamos o `id` UUID
    #    porque ele e o `ref` que o callback precisa carregar.
    async with AsyncSessionLocal() as db:
        job = QitechReportJob(
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
        db.add(job)
        await db.commit()
        await db.refresh(job)
        ref = str(job.id)

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
    # qualquer token. Em DEV/test e ok — o `ref` ainda precisa ser UUID
    # valido pra passar do guard de tipagem.
    with patch("httpx.AsyncClient.get", new=_download):
        r = await client.post(_callback_url(ref=ref), json=body)

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
        r = await client.post(
            _callback_url(ref=str(uuid4()), token="errado"), json=body
        )

    assert r.status_code == 401
    assert "token" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_receiver_ref_ausente_retorna_401(client: AsyncClient):
    """Sem `?ref=` na query string -> 401 (ref vazio nao e UUID valido)."""
    body = {
        "webhookId": 1,
        "jobId": "qualquer",
        "eventType": "fidcEstoque",
        "data": {"fileLink": "https://x"},
    }
    r = await client.post(
        "/api/v1/integracoes/webhooks/qitech/job-callback", json=body
    )
    assert r.status_code == 401
    assert "ref" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_receiver_ref_nao_uuid_retorna_401(client: AsyncClient):
    """ref que nao e UUID valido -> 401."""
    body = {
        "webhookId": 1,
        "jobId": "qualquer",
        "eventType": "fidcEstoque",
        "data": {"fileLink": "https://x"},
    }
    r = await client.post(_callback_url(ref="nao-eh-uuid"), json=body)
    assert r.status_code == 401
    assert "ref" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_receiver_token_correto_passa(
    client: AsyncClient, tenant_a: Tenant, csv_text: str
):
    """Token HMAC correto: receiver aceita."""
    qitech_job_id = f"job-tok-{uuid4().hex}"
    secret = "abc" * 10

    async with AsyncSessionLocal() as db:
        job = QitechReportJob(
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
        db.add(job)
        await db.commit()
        await db.refresh(job)
        ref = str(job.id)

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
        token = compute_callback_token(ref=ref)
        r = await client.post(_callback_url(ref=ref, token=token), json=body)

    assert r.status_code == 200, r.text
    assert r.json()["accepted"] is True


@pytest.mark.asyncio
async def test_receiver_ref_desconhecido_retorna_404(client: AsyncClient):
    """Callback com ref UUID valido mas que nao existe no DB -> 404."""
    body = {
        "webhookId": 1,
        "jobId": f"orfao-{uuid4().hex}",
        "eventType": "fidcEstoque",
        "data": {"fileLink": "https://x"},
    }
    r = await client.post(_callback_url(ref=str(uuid4())), json=body)
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_receiver_event_type_desconhecido_aceita_silenciosamente(
    client: AsyncClient,
):
    """Tipo nao mapeado retorna 200 (nao expoe estado interno pra QiTech).

    Como o handler nao chega a tocar o DB pelo `local_job_id`, basta
    qualquer UUID valido pra passar do guard de tipo.
    """
    body = {
        "webhookId": 1,
        "jobId": f"x-{uuid4().hex}",
        "eventType": "fidcMovimentacaoFutura",  # nao mapeado
        "data": {"fileLink": "https://x"},
    }
    r = await client.post(_callback_url(ref=str(uuid4())), json=body)
    # 200 com accepted=true mesmo sem mapper — nao queremos a QiTech
    # parar de mandar callbacks por causa disso.
    assert r.status_code == 200
    assert r.json()["accepted"] is True


@pytest.mark.asyncio
async def test_receiver_body_invalido_retorna_422(client: AsyncClient):
    """Body sem jobId -> 422 (Pydantic validation error)."""
    r = await client.post(
        _callback_url(ref=str(uuid4())),
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
        job = QitechReportJob(
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
        db.add(job)
        await db.commit()
        await db.refresh(job)
        ref = str(job.id)

    async def _download(self, url, *args, **kwargs):
        return httpx.Response(200, text=csv_text, request=httpx.Request("GET", url))

    body = {
        "webhookId": 1,
        "jobId": qitech_job_id,
        "eventType": "fidcEstoque",
        "data": {"fileLink": "https://x.csv"},
    }

    with patch("httpx.AsyncClient.get", new=_download):
        r1 = await client.post(_callback_url(ref=ref), json=body)
        r2 = await client.post(_callback_url(ref=ref), json=body)

    assert r1.status_code == 200
    assert r1.json()["idempotent"] is False
    assert r2.status_code == 200
    assert r2.json()["idempotent"] is True
