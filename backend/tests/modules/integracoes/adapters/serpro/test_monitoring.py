"""Testes do monitoramento SERPRO (F3): enrolamento, inscricao, ciclo de vida,

alerta e receiver do webhook.

Regra de escopo (Ricardo 2026-07-11): titulo EM ABERTO (situacao=0) =>
vigia a chave; titulo liquidado/baixado => sai. Vencimento nao governa.

Chaves/titulo_ids gerados por teste: o truncate do gr_db_test roda so no
inicio da sessao, entao valores fixos colidiriam com dados de testes
anteriores na mesma sessao.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count
from uuid import uuid4

import pytest
import sqlalchemy as sa
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.enums import SourceType
from app.modules.integracoes.adapters.data.serpro.monitoring import (
    MOTIVO_TITULO_EM_ABERTO,
    SITUACAO_TITULO_EM_ABERTO,
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
from app.warehouse.titulo import Titulo
from app.warehouse.titulo_fiscal import WhTituloFiscal

_TITULO_SEQ = count(900_000_000)
_SITUACAO_LIQUIDADO = 1


def _chave() -> str:
    """Chave de acesso sintetica unica (44 digitos)."""
    return f"352606{uuid4().int % 10**38:038d}"


async def _criar_titulo(
    tenant_id,
    chave: str,
    *,
    situacao: int = SITUACAO_TITULO_EM_ABERTO,
) -> int:
    """Cria wh_titulo + ponte wh_titulo_fiscal. Retorna o titulo_id."""
    tid = next(_TITULO_SEQ)
    agora = datetime.now(UTC)
    async with AsyncSessionLocal() as db:
        db.add(
            Titulo(
                tenant_id=tenant_id,
                titulo_id=tid,
                sigla="DM",
                numero=f"{tid}/1",
                data_de_emissao=agora,
                data_de_vencimento=agora + timedelta(days=30),
                data_de_vencimento_efetiva=agora + timedelta(days=30),
                data_de_cadastro=agora,
                data_da_situacao=agora,
                valor=1000,
                situacao=situacao,
                sacado_id=1,
                conta_operacional_id=1,
                unidade_administrativa_id=1,
                operacao_id=1,
                source_type=SourceType.ERP_BITFIN,
                source_id=str(tid),
                ingested_by_version="test",
            )
        )
        db.add(
            WhTituloFiscal(
                tenant_id=tenant_id,
                titulo_id=tid,
                nota_fiscal_eletronica_id=tid,
                chave_acesso=chave,
                valor_associado=1000,
                source_type=SourceType.ERP_BITFIN,
                source_id=f"{tid}:{tid}",
                ingested_by_version="test",
            )
        )
        await db.commit()
    return tid


async def _set_situacao(tenant_id, titulo_id: int, situacao: int) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            sa.update(Titulo)
            .where(Titulo.tenant_id == tenant_id, Titulo.titulo_id == titulo_id)
            .values(situacao=situacao)
        )
        await db.commit()


async def _monitores(tenant_id) -> dict[str, SerproNfeMonitor]:
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                sa.select(SerproNfeMonitor).where(
                    SerproNfeMonitor.tenant_id == tenant_id
                )
            )
        ).scalars().all()
    return {r.chave_acesso: r for r in rows}


class _FakePushClient:
    """Stub do SerproClient so com o metodo usado pela inscricao."""

    def __init__(self) -> None:
        self.lotes: list[list[str]] = []

    async def push_criar_solicitacao(self, chaves: list[str]) -> dict:
        self.lotes.append(chaves)
        return {"solicitacaoId": f"SOL-{len(self.lotes)}"}


# ---- Enrolamento -------------------------------------------------------------


@pytest.mark.asyncio
async def test_enrola_so_titulo_em_aberto(tenant_a: Tenant) -> None:
    chave_aberto, chave_liquidado = _chave(), _chave()
    await _criar_titulo(tenant_a.id, chave_aberto)
    await _criar_titulo(tenant_a.id, chave_liquidado, situacao=_SITUACAO_LIQUIDADO)

    async with AsyncSessionLocal() as db:
        novos = await enrolar_chaves_no_escopo(db, tenant_a.id)
        await db.commit()
    assert novos == 1

    rows = await _monitores(tenant_a.id)
    assert list(rows) == [chave_aberto]
    assert rows[chave_aberto].motivo == MOTIVO_TITULO_EM_ABERTO
    assert rows[chave_aberto].ativo is True

    # Idempotente: segunda passada nao duplica.
    async with AsyncSessionLocal() as db:
        assert await enrolar_chaves_no_escopo(db, tenant_a.id) == 0


@pytest.mark.asyncio
async def test_enrola_multiplas_chaves_de_uma_vez(tenant_a: Tenant) -> None:
    """Regressao (ativacao 2026-07-11): INSERT..SELECT com default Python do
    id virava UUID CONSTANTE -> PK duplicada com 2+ chaves no mesmo tick."""
    chaves = [_chave() for _ in range(3)]
    for c in chaves:
        await _criar_titulo(tenant_a.id, c)

    async with AsyncSessionLocal() as db:
        novos = await enrolar_chaves_no_escopo(db, tenant_a.id)
        await db.commit()
    assert novos == 3
    assert set(await _monitores(tenant_a.id)) == set(chaves)


@pytest.mark.asyncio
async def test_enrolamento_isola_tenant(tenant_a: Tenant, tenant_b: Tenant) -> None:
    """§10.4: enrolar B nao ve os titulos de A."""
    await _criar_titulo(tenant_a.id, _chave())
    async with AsyncSessionLocal() as db:
        await enrolar_chaves_no_escopo(db, tenant_b.id)
        await db.commit()
    assert await _monitores(tenant_b.id) == {}


# ---- Inscricao push ----------------------------------------------------------


@pytest.mark.asyncio
async def test_inscreve_pendentes_marca_solicitacao(tenant_a: Tenant) -> None:
    chave = _chave()
    await _criar_titulo(tenant_a.id, chave)
    fake = _FakePushClient()
    async with AsyncSessionLocal() as db:
        await enrolar_chaves_no_escopo(db, tenant_a.id)
        inscritas = await inscrever_pendentes(db, fake, tenant_a.id)  # type: ignore[arg-type]
        await db.commit()
    assert inscritas == 1
    assert fake.lotes == [[chave]]

    rows = await _monitores(tenant_a.id)
    assert rows[chave].solicitacao_id == "SOL-1"
    assert rows[chave].solicitacao_expira_em is not None

    async with AsyncSessionLocal() as db:
        # Segunda passada: solicitacao valida -> nada a inscrever.
        assert await inscrever_pendentes(db, fake, tenant_a.id) == 0  # type: ignore[arg-type]


# ---- Ciclo de vida -----------------------------------------------------------


@pytest.mark.asyncio
async def test_titulo_liquidado_sai_do_monitoramento(tenant_a: Tenant) -> None:
    """Regra central: em aberto entra; liquidado sai — vencimento nao importa."""
    chave = _chave()
    titulo_id = await _criar_titulo(tenant_a.id, chave)

    async with AsyncSessionLocal() as db:
        await enrolar_chaves_no_escopo(db, tenant_a.id)
        # Titulo em aberto: encerrar nao remove.
        assert await encerrar_fora_do_escopo(db, tenant_a.id) == 0
        await db.commit()

    await _set_situacao(tenant_a.id, titulo_id, _SITUACAO_LIQUIDADO)
    async with AsyncSessionLocal() as db:
        encerrados = await encerrar_fora_do_escopo(db, tenant_a.id)
        await db.commit()
    assert encerrados == 1

    rows = await _monitores(tenant_a.id)
    assert rows[chave].ativo is False
    assert rows[chave].encerrado_motivo == "titulo_encerrado"


@pytest.mark.asyncio
async def test_titulo_reaberto_reativa_monitoramento(tenant_a: Tenant) -> None:
    """Estorno de baixa: titulo volta a aberto -> monitor reativa e re-inscreve."""
    chave = _chave()
    titulo_id = await _criar_titulo(tenant_a.id, chave)
    async with AsyncSessionLocal() as db:
        await enrolar_chaves_no_escopo(db, tenant_a.id)
        await db.commit()

    await _set_situacao(tenant_a.id, titulo_id, _SITUACAO_LIQUIDADO)
    async with AsyncSessionLocal() as db:
        await encerrar_fora_do_escopo(db, tenant_a.id)
        await db.commit()

    await _set_situacao(tenant_a.id, titulo_id, SITUACAO_TITULO_EM_ABERTO)
    async with AsyncSessionLocal() as db:
        reativados = await enrolar_chaves_no_escopo(db, tenant_a.id)
        await db.commit()
    assert reativados == 1

    rows = await _monitores(tenant_a.id)
    assert rows[chave].ativo is True
    assert rows[chave].encerrado_motivo is None
    assert rows[chave].solicitacao_id is None  # forca re-inscricao no push


@pytest.mark.asyncio
async def test_nota_morta_sai_e_nao_reativa(tenant_a: Tenant) -> None:
    chave = _chave()
    await _criar_titulo(tenant_a.id, chave)  # titulo SEGUE em aberto
    async with AsyncSessionLocal() as db:
        await enrolar_chaves_no_escopo(db, tenant_a.id)
        await db.execute(
            sa.update(SerproNfeMonitor)
            .where(SerproNfeMonitor.chave_acesso == chave)
            .values(ultima_situacao="cancelada_fora_prazo")
        )
        encerrados = await encerrar_fora_do_escopo(db, tenant_a.id)
        await db.commit()
    assert encerrados == 1

    rows = await _monitores(tenant_a.id)
    assert rows[chave].encerrado_motivo == "nota_morta"

    # Titulo continua em aberto, mas nota morta NAO ressuscita.
    async with AsyncSessionLocal() as db:
        assert await enrolar_chaves_no_escopo(db, tenant_a.id) == 0


# ---- Alerta ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_alerta_critico_uma_vez(tenant_a: Tenant) -> None:
    async with AsyncSessionLocal() as db:
        monitor = SerproNfeMonitor(
            tenant_id=tenant_a.id,
            chave_acesso=_chave(),
            motivo=MOTIVO_TITULO_EM_ABERTO,
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
                motivo=MOTIVO_TITULO_EM_ABERTO,
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
