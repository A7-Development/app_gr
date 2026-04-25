"""report_jobs.py -- E2E request + process_callback (DB real, fetch mockado)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment
from app.modules.integracoes.adapters.admin.qitech.auth import (
    _clear_cache_for_tests,
)
from app.modules.integracoes.adapters.admin.qitech.config import QiTechConfig
from app.modules.integracoes.adapters.admin.qitech.report_jobs import (
    build_callback_url,
    compute_callback_token,
    extract_s3_expiry,
    process_fidc_estoque_callback,
    request_fidc_estoque_report,
    verify_callback_token,
)
from app.modules.integracoes.models.qitech_report_job import (
    QitechJobStatus,
    QitechReportJob,
)
from app.shared.identity.tenant import Tenant
from app.warehouse.estoque_recebivel import EstoqueRecebivel
from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio

CSV_PATH = (
    Path(__file__).resolve().parents[5]
    / "qitech_samples"
    / "a7-credit"
    / "2026-01-08"
    / "fidc-estoque.csv"
)
DATA_REF = date(2026, 1, 8)


@pytest.fixture(autouse=True)
def _reset_token_cache():
    _clear_cache_for_tests()
    yield
    _clear_cache_for_tests()


@pytest.fixture
def csv_text() -> str:
    return CSV_PATH.read_text(encoding="utf-8")


def _cfg() -> QiTechConfig:
    return QiTechConfig(
        base_url="https://api.test", client_id="u", client_secret="p"
    )


# ---- Helpers ----


def test_compute_token_determinista():
    t1 = compute_callback_token(qitech_job_id="job-123", secret="s3cret")
    t2 = compute_callback_token(qitech_job_id="job-123", secret="s3cret")
    assert t1 == t2
    assert len(t1) == 32


def test_compute_token_difere_por_secret():
    t1 = compute_callback_token(qitech_job_id="job-123", secret="alpha")
    t2 = compute_callback_token(qitech_job_id="job-123", secret="beta")
    assert t1 != t2


def test_compute_token_difere_por_jobid():
    t1 = compute_callback_token(qitech_job_id="job-123", secret="s")
    t2 = compute_callback_token(qitech_job_id="job-456", secret="s")
    assert t1 != t2


def test_compute_token_sem_secret_retorna_vazio():
    """Sem secret configurado, token vazio. Receiver trata como ausencia
    de validacao (caso DEV/test)."""
    t = compute_callback_token(qitech_job_id="job-123", secret="")
    assert t == ""


def test_verify_token_valido():
    secret = "abcdef" * 10
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.report_jobs.get_settings"
    ) as gs:
        gs.return_value.QITECH_WEBHOOK_SECRET = secret
        token = compute_callback_token(qitech_job_id="job-x")
        assert verify_callback_token(qitech_job_id="job-x", token=token) is True
        assert verify_callback_token(qitech_job_id="job-x", token="errado") is False


def test_verify_token_sem_secret_aceita_qualquer():
    """Sem secret -> validacao desligada. Em prod isso e configuration error."""
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.report_jobs.get_settings"
    ) as gs:
        gs.return_value.QITECH_WEBHOOK_SECRET = ""
        assert verify_callback_token(qitech_job_id="job-x", token="qualquer") is True


def test_extract_s3_expiry_real_sample():
    """URL S3 real do callback do job 908aaf59 (Expires=1778942307)."""
    url = (
        "https://fidc-custodia.s3.amazonaws.com/fidcEstoque-1777142302020.csv"
        "?AWSAccessKeyId=AKIAQZRWSMGJNGVYPIWU&Expires=1778942307&Signature=x"
    )
    expiry = extract_s3_expiry(url)
    assert expiry is not None
    assert expiry.timestamp() == 1778942307


def test_extract_s3_expiry_sem_expires_retorna_none():
    assert extract_s3_expiry("https://example.com/foo.csv") is None
    assert extract_s3_expiry("https://example.com/foo.csv?bar=baz") is None


def test_build_callback_url_inclui_token():
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.report_jobs.get_settings"
    ) as gs:
        gs.return_value.QITECH_WEBHOOK_SECRET = "s3cret"
        gs.return_value.QITECH_WEBHOOK_BASE_URL = "https://callback.a7credit.com.br"
        url = build_callback_url(qitech_job_id="job-x")
        assert url.startswith(
            "https://callback.a7credit.com.br"
            "/api/v1/integracoes/webhooks/qitech/job-callback?token="
        )


# ---- request_fidc_estoque_report (POST + insert) ----


@pytest.mark.asyncio
async def test_request_fidc_estoque_cria_job(tenant_a: Tenant):
    """POST mockado retorna jobId; QitechReportJob deve ser criado."""

    unique_job_id = f"test-job-{uuid4().hex}"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v2/painel/token/api":
            return httpx.Response(200, json={"apiToken": "T"})
        if request.url.path == "/v2/queue/scheduler/report/fidc-estoque":
            assert request.method == "POST"
            body = json.loads(request.content)
            assert body["cnpjFundo"] == "42449234000160"
            assert body["date"] == "2026-01-08"
            assert body["callbackUrl"].endswith("/job-callback")
            return httpx.Response(
                200,
                json={"jobId": unique_job_id, "status": "WAITING"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    with patch(
        "app.modules.integracoes.adapters.admin.qitech.report_jobs.build_async_client",
    ) as mock_factory:
        from app.modules.integracoes.adapters.admin.qitech.connection import (
            build_async_client as real_build,
        )

        mock_factory.side_effect = lambda **kw: real_build(**kw, transport=transport)

        async with AsyncSessionLocal() as db:
            job = await request_fidc_estoque_report(
                db=db,
                tenant_id=tenant_a.id,
                environment=Environment.PRODUCTION,
                config=_cfg(),
                cnpj_fundo="42449234000160",
                reference_date=DATA_REF,
                triggered_by="user:test",
            )

    assert job.qitech_job_id == unique_job_id
    assert job.status == QitechJobStatus.WAITING
    assert job.cnpj_fundo == "42449234000160"
    assert job.reference_date == DATA_REF
    assert job.report_type == "fidc-estoque"
    assert job.triggered_by == "user:test"


# ---- process_fidc_estoque_callback (download + raw + canonical) ----


@pytest.mark.asyncio
async def test_process_callback_baixa_csv_e_grava_raw_e_canonico(
    tenant_a: Tenant, csv_text: str
):
    """Pipeline completo do callback: download mockado -> raw -> canonico."""
    qitech_job_id = f"job-{uuid4().hex}"

    # 1. Cria job manualmente (simulando POST anterior)
    async with AsyncSessionLocal() as db:
        job = QitechReportJob(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            report_type="fidc-estoque",
            cnpj_fundo="42449234000160",
            reference_date=DATA_REF,
            request_body={"cnpjFundo": "42449234000160", "date": "2026-01-08"},
            qitech_job_id=qitech_job_id,
            callback_url_used="https://test/callback",
            callback_token="t" * 32,
            status=QitechJobStatus.WAITING,
            triggered_by="user:test",
        )
        db.add(job)
        await db.commit()
        await db.refresh(job)
        job_id = job.id

    # 2. Mock download
    file_link = (
        "https://fidc-custodia.s3.amazonaws.com/fidcEstoque.csv"
        "?AWSAccessKeyId=X&Expires=1778942307&Signature=Y"
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=csv_text)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # 3. Processa callback
    async with AsyncSessionLocal() as db:
        result = await process_fidc_estoque_callback(
            db=db,
            qitech_job_id=qitech_job_id,
            file_link=file_link,
            qitech_webhook_id=809341,
            http_client=mock_client,
        )
    await mock_client.aclose()

    assert result["ok"] is True
    assert result["idempotent"] is False
    assert result["rows_canonical"] == 2390

    # 4. Confere DB
    async with AsyncSessionLocal() as db:
        # Job atualizado
        job_updated = await db.get(QitechReportJob, job_id)
        assert job_updated is not None
        assert job_updated.status == QitechJobStatus.SUCCESS
        assert job_updated.qitech_webhook_id == 809341
        assert job_updated.result_file_link == file_link
        assert job_updated.result_downloaded_at is not None
        assert job_updated.completed_at is not None
        assert job_updated.raw_relatorio_id is not None

        # Raw gravado
        raw = (
            await db.execute(
                select(QiTechRawRelatorio).where(
                    QiTechRawRelatorio.tenant_id == tenant_a.id,
                    QiTechRawRelatorio.tipo_de_mercado == "fidc-estoque",
                )
            )
        ).scalar_one()
        assert raw.payload_text == csv_text
        assert raw.payload["format"] == "csv"
        assert raw.http_status == 200

        # Canonico
        canon = (
            await db.execute(
                select(EstoqueRecebivel).where(
                    EstoqueRecebivel.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(canon) == 2390


@pytest.mark.asyncio
async def test_process_callback_idempotente(tenant_a: Tenant, csv_text: str):
    """Re-processar o mesmo callback nao duplica linhas nem re-baixa."""
    qitech_job_id = f"job-idem-{uuid4().hex}"

    async with AsyncSessionLocal() as db:
        job = QitechReportJob(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            report_type="fidc-estoque",
            cnpj_fundo="42449234000160",
            reference_date=DATA_REF,
            request_body={"x": 1},
            qitech_job_id=qitech_job_id,
            callback_url_used="https://test/callback",
            callback_token="x" * 32,
            status=QitechJobStatus.WAITING,
            triggered_by="user:test",
        )
        db.add(job)
        await db.commit()

    file_link = "https://fidc-custodia.s3.amazonaws.com/x.csv?Expires=1778942307"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=csv_text)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    # 1a chamada
    async with AsyncSessionLocal() as db:
        r1 = await process_fidc_estoque_callback(
            db=db,
            qitech_job_id=qitech_job_id,
            file_link=file_link,
            qitech_webhook_id=1,
            http_client=mock_client,
        )
    assert r1["ok"] is True
    assert r1["idempotent"] is False

    # 2a chamada - idempotente (deve retornar idempotent=True)
    async with AsyncSessionLocal() as db:
        r2 = await process_fidc_estoque_callback(
            db=db,
            qitech_job_id=qitech_job_id,
            file_link=file_link,
            qitech_webhook_id=1,
            http_client=mock_client,
        )
    await mock_client.aclose()

    assert r2["idempotent"] is True

    # DB tem 2390 (nao 4780)
    async with AsyncSessionLocal() as db:
        n = (
            await db.execute(
                select(EstoqueRecebivel).where(
                    EstoqueRecebivel.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
        assert len(n) == 2390


@pytest.mark.asyncio
async def test_process_callback_jobid_desconhecido_levanta():
    """Callback com jobId que nao existe no DB -> ValueError (orphan/spoof)."""
    with pytest.raises(ValueError, match="desconhecido"):
        async with AsyncSessionLocal() as db:
            await process_fidc_estoque_callback(
                db=db,
                qitech_job_id="orfao-nao-existe",
                file_link="https://x/y.csv",
            )


@pytest.mark.asyncio
async def test_process_callback_isolamento_tenant(
    tenant_a: Tenant, tenant_b: Tenant, csv_text: str
):
    """Job criado em tenant A: tenant B nao ve as linhas canonicas."""
    qitech_job_id = f"job-iso-{uuid4().hex}"
    async with AsyncSessionLocal() as db:
        job = QitechReportJob(
            tenant_id=tenant_a.id,
            environment=Environment.PRODUCTION,
            report_type="fidc-estoque",
            cnpj_fundo="42449234000160",
            reference_date=DATA_REF,
            request_body={"x": 1},
            qitech_job_id=qitech_job_id,
            callback_url_used="https://test/callback",
            callback_token="x" * 32,
            status=QitechJobStatus.WAITING,
            triggered_by="user:test",
        )
        db.add(job)
        await db.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=csv_text)

    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    async with AsyncSessionLocal() as db:
        await process_fidc_estoque_callback(
            db=db,
            qitech_job_id=qitech_job_id,
            file_link="https://x/y.csv?Expires=1778942307",
            qitech_webhook_id=1,
            http_client=mock_client,
        )
    await mock_client.aclose()

    async with AsyncSessionLocal() as db:
        b_canon = (
            await db.execute(
                select(EstoqueRecebivel).where(
                    EstoqueRecebivel.tenant_id == tenant_b.id
                )
            )
        ).scalars().all()
        assert b_canon == []
