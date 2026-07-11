"""Testes do monitoramento SERPRO (F3): enrolamento, inscricao, ciclo de vida,

alerta e receiver do webhook.

Chaves geradas por teste (`_chave()`): o truncate do gr_db_test roda so no
inicio da sessao, entao chave fixa colidiria com monitores de tenants de
testes anteriores.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.enums import SourceType
from app.modules.integracoes.adapters.data.serpro.monitoring import (
    MOTIVO_DUPLICATA_A_VENCER,
    SITUACOES_CRITICAS,
    _alertar_se_critico,
    encerrar_fora_do_escopo,
    enrolar_chaves_no_escopo,
    inscrever_pendentes,
    processar_ping,
    verify_webhook_token,
    webhook_token,
)
from app.modules.integracoes.models.serpro_nfe_monitor import SerproNfeMonitor
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.shared.identity.tenant import Tenant
from app.warehouse.fiscal_nfe import Nfe, NfeDuplicata, NfeRawDocumento


def _chave() -> str:
    """Chave de acesso sintetica unica (44 digitos)."""
    return f"352606{uuid4().int % 10**38:038d}"


async def _criar_nfe(
    tenant_id, chave: str, vencimento: date, *, numero: int = 1
) -> None:
    async with AsyncSessionLocal() as db:
        raw = NfeRawDocumento(
            tenant_id=tenant_id,
            chave_acesso=chave,
            documento={"NFe": {}},
            nome_arquivo_xml=f"{chave}.xml",
            payload_sha256="0" * 64,
            fetched_by_version="test",
        )
        db.add(raw)
        await db.flush()
        nfe = Nfe(
            tenant_id=tenant_id,
            raw_documento_id=raw.id,
            chave_acesso=chave,
            numero=numero,
            emitente_documento="11222333000144",
            autorizada=True,
            source_type=SourceType.DOCUMENT_NFE,
            source_id=chave,
            ingested_by_version="test",
        )
        db.add(nfe)
        await db.flush()
        db.add(
            NfeDuplicata(
                tenant_id=tenant_id,
                nfe_id=nfe.id,
                numero="001",
                vencimento=vencimento,
                valor=1000,
            )
        )
        await db.commit()


class _FakePushClient:
    """Stub do SerproClient so com o metodo usado pela inscricao."""

    def __init__(self) -> None:
        self.lotes: list[list[str]] = []

    async def push_criar_solicitacao(self, chaves: list[str]) -> dict:
        self.lotes.append(chaves)
        return {"solicitacaoId": f"SOL-{len(self.lotes)}"}


# ---- Enrolamento -------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrola_so_duplicata_a_vencer(tenant_a: Tenant) -> None:
    chave_ok, chave_vencida = _chave(), _chave()
    hoje = date.today()
    await _criar_nfe(tenant_a.id, chave_ok, hoje + timedelta(days=30), numero=1)
    await _criar_nfe(tenant_a.id, chave_vencida, hoje - timedelta(days=30), numero=2)

    async with AsyncSessionLocal() as db:
        novos = await enrolar_chaves_no_escopo(db, tenant_a.id)
        await db.commit()
    assert novos == 1

    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                sa.select(SerproNfeMonitor).where(
                    SerproNfeMonitor.tenant_id == tenant_a.id
                )
            )
        ).scalars().all()
    assert [r.chave_acesso for r in rows] == [chave_ok]
    assert rows[0].motivo == MOTIVO_DUPLICATA_A_VENCER
    assert rows[0].ativo is True

    # Idempotente: segunda passada nao duplica.
    async with AsyncSessionLocal() as db:
        assert await enrolar_chaves_no_escopo(db, tenant_a.id) == 0


@pytest.mark.asyncio
async def test_enrolamento_isola_tenant(tenant_a: Tenant, tenant_b: Tenant) -> None:
    """§10.4: enrolar B nao ve as notas de A."""
    await _criar_nfe(tenant_a.id, _chave(), date.today() + timedelta(days=10))
    async with AsyncSessionLocal() as db:
        await enrolar_chaves_no_escopo(db, tenant_b.id)
        await db.commit()
        rows_b = (
            await db.execute(
                sa.select(SerproNfeMonitor).where(
                    SerproNfeMonitor.tenant_id == tenant_b.id
                )
            )
        ).scalars().all()
    assert rows_b == []


# ---- Inscricao push ----------------------------------------------------------


@pytest.mark.asyncio
async def test_inscreve_pendentes_marca_solicitacao(tenant_a: Tenant) -> None:
    chave = _chave()
    await _criar_nfe(tenant_a.id, chave, date.today() + timedelta(days=10))
    fake = _FakePushClient()
    async with AsyncSessionLocal() as db:
        await enrolar_chaves_no_escopo(db, tenant_a.id)
        inscritas = await inscrever_pendentes(db, fake, tenant_a.id)  # type: ignore[arg-type]
        await db.commit()
    assert inscritas == 1
    assert fake.lotes == [[chave]]

    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                sa.select(SerproNfeMonitor).where(
                    SerproNfeMonitor.tenant_id == tenant_a.id
                )
            )
        ).scalar_one()
        assert row.solicitacao_id == "SOL-1"
        assert row.solicitacao_expira_em is not None

        # Segunda passada: solicitacao valida -> nada a inscrever.
        assert await inscrever_pendentes(db, fake, tenant_a.id) == 0  # type: ignore[arg-type]


# ---- Ciclo de vida -----------------------------------------------------------


@pytest.mark.asyncio
async def test_encerra_vencida_e_nota_morta(tenant_a: Tenant) -> None:
    chave_vencida, chave_morta = _chave(), _chave()
    async with AsyncSessionLocal() as db:
        db.add(
            SerproNfeMonitor(
                tenant_id=tenant_a.id,
                chave_acesso=chave_vencida,
                motivo=MOTIVO_DUPLICATA_A_VENCER,
                referencia_vencimento=date.today() - timedelta(days=30),
            )
        )
        db.add(
            SerproNfeMonitor(
                tenant_id=tenant_a.id,
                chave_acesso=chave_morta,
                motivo=MOTIVO_DUPLICATA_A_VENCER,
                referencia_vencimento=date.today() + timedelta(days=30),
                ultima_situacao="cancelada_fora_prazo",
            )
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        encerrados = await encerrar_fora_do_escopo(db, tenant_a.id)
        await db.commit()
    assert encerrados == 2

    async with AsyncSessionLocal() as db:
        rows = {
            r.chave_acesso: r
            for r in (
                await db.execute(
                    sa.select(SerproNfeMonitor).where(
                        SerproNfeMonitor.tenant_id == tenant_a.id
                    )
                )
            ).scalars()
        }
    assert rows[chave_vencida].encerrado_motivo == "vencida"
    assert rows[chave_morta].encerrado_motivo == "nota_morta"
    assert not rows[chave_vencida].ativo and not rows[chave_morta].ativo


# ---- Alerta ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerta_critico_uma_vez(tenant_a: Tenant) -> None:
    async with AsyncSessionLocal() as db:
        monitor = SerproNfeMonitor(
            tenant_id=tenant_a.id,
            chave_acesso=_chave(),
            motivo=MOTIVO_DUPLICATA_A_VENCER,
            referencia_vencimento=date.today() + timedelta(days=10),
        )
        db.add(monitor)
        await db.flush()

        assert "cancelada" in SITUACOES_CRITICAS
        assert await _alertar_se_critico(db, monitor, "autorizada") is False
        assert await _alertar_se_critico(db, monitor, "cancelada") is True
        # Ja alertado: nao duplica.
        assert await _alertar_se_critico(db, monitor, "cancelada") is False
        await db.commit()

    async with AsyncSessionLocal() as db:
        alertas = (
            await db.execute(
                sa.select(DecisionLog).where(
                    DecisionLog.tenant_id == tenant_a.id,
                    DecisionLog.decision_type == DecisionType.ALERT,
                    DecisionLog.rule_or_model == "serpro_monitor",
                )
            )
        ).scalars().all()
    assert len(alertas) == 1
    assert alertas[0].output["situacao"] == "cancelada"


# ---- processar_ping (sem rede) -----------------------------------------------


@pytest.mark.asyncio
async def test_ping_chave_nao_monitorada(tenant_a: Tenant) -> None:
    async with AsyncSessionLocal() as db:
        result = await processar_ping(
            db, chave=_chave(), data_hora_envio="2026-07-11T10:00:00Z"
        )
    assert result.accepted is True
    assert result.reason == "chave_nao_monitorada"


@pytest.mark.asyncio
async def test_ping_rate_limited_nao_consulta(tenant_a: Tenant) -> None:
    """Consulta recente -> ping nao dispara nova chamada (nem exige client)."""
    chave = _chave()
    async with AsyncSessionLocal() as db:
        db.add(
            SerproNfeMonitor(
                tenant_id=tenant_a.id,
                chave_acesso=chave,
                motivo=MOTIVO_DUPLICATA_A_VENCER,
                referencia_vencimento=date.today() + timedelta(days=10),
                ultima_consulta_em=datetime.now(UTC),
            )
        )
        await db.commit()

    async with AsyncSessionLocal() as db:
        result = await processar_ping(
            db, chave=chave, data_hora_envio="2026-07-11T10:00:00Z"
        )
    assert result.accepted is True
    assert result.reason == "rate_limited"
    assert result.consultado is False


# ---- Receiver HTTP -----------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_token_derivado_e_estavel() -> None:
    t1, t2 = webhook_token(), webhook_token()
    assert t1 == t2
    if t1:  # com secret configurado no ambiente de teste
        assert verify_webhook_token(t1) is True
        assert verify_webhook_token("errado") is False


@pytest.mark.asyncio
async def test_receiver_token_invalido_401(client: AsyncClient) -> None:
    if not webhook_token():
        pytest.skip("sem secret no ambiente — validacao aberta em DEV")
    resp = await client.post(
        "/api/v1/integracoes/webhooks/serpro/nfe-push?token=spoof",
        json={"chaveNFe": _chave(), "dataHoraEnvio": "2026-07-11T10:00:00Z"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_receiver_chave_desconhecida_200(client: AsyncClient) -> None:
    resp = await client.post(
        f"/api/v1/integracoes/webhooks/serpro/nfe-push?token={webhook_token()}",
        json={"chaveNFe": _chave(), "dataHoraEnvio": "2026-07-11T10:00:00Z"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["accepted"] is True
    assert body["reason"] == "chave_nao_monitorada"
