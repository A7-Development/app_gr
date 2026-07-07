"""Tests for get_historico_estoque_papel — trajetoria de um papel no estoque.

Regressao alvo (2026-07-07): a tool era ancorada no dia SELECIONADO na tela
(`scope.extras['data_d0']`) e olhava SO pra tras (`between(d0 - dias, d0)`).
Com a tela em 25/06 e o warehouse ate 06/07, a trajetoria parava em 25/06 e o
LLM concluia, erradamente, "warehouse nao sincronizado depois de 25/06".

Estes testes travam o novo contrato:
- a trajetoria e AGNOSTICA ao dia da tela (range vem de data_inicio/data_fim);
- default de data_fim = ULTIMA data do warehouse (nao a tela, nao 'hoje');
- o retorno distingue `data_max_papel` (ate quando o papel existiu) de
  `data_max_warehouse` (ate quando ha dado) — o farol que mata a alucinacao;
- a query e escopada por tenant (§10).
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.agentic._scope import ScopedContext
from app.agentic.tools.controladoria.cota_sub import get_historico_estoque_papel
from app.core.database import AsyncSessionLocal
from app.core.enums import Module, Permission, SourceType
from app.modules.cadastros.models.unidade_administrativa import (
    TipoUnidadeAdministrativa,
    UnidadeAdministrativa,
)
from app.shared.identity.tenant import Tenant
from app.warehouse.estoque_recebivel import EstoqueRecebivel

_FUNDO_DOC = "12345678000199"


def _papel_row(
    *,
    tenant_id: UUID,
    data_referencia: date,
    seu_numero: str,
    numero_documento: str,
    valor_presente: Decimal,
) -> EstoqueRecebivel:
    """Uma linha minima de estoque — so o necessario pra tool responder."""
    return EstoqueRecebivel(
        tenant_id=tenant_id,
        data_referencia=data_referencia,
        fundo_doc=_FUNDO_DOC,
        fundo_nome="FIDC Teste",
        gestor_doc="00000000000191",
        gestor_nome="Gestor Teste",
        originador_doc=_FUNDO_DOC,
        originador_nome="Originador Teste",
        cedente_doc="11111111000111",
        cedente_nome="QUIMASSA INFRAESTRUTURA LTDA",
        sacado_doc="22222222000122",
        sacado_nome="Sacado Teste",
        seu_numero=seu_numero,
        numero_documento=numero_documento,
        tipo_recebivel="Duplicata",
        valor_nominal=Decimal("1000000.00"),
        valor_presente=valor_presente,
        valor_aquisicao=Decimal("950000.00"),
        valor_pdd=Decimal("0.00"),
        faixa_pdd="A",
        prazo=30,
        prazo_anual=Decimal("13.0000"),
        situacao_recebivel="A Vencer",
        taxa_cessao=Decimal("0.0100000000"),
        taxa_recebivel=Decimal("0.0100000000"),
        coobrigacao=False,
        # Auditable (§14):
        source_type=SourceType.ADMIN_QITECH,
        source_id=f"{_FUNDO_DOC}|{seu_numero}|{data_referencia.isoformat()}",
        ingested_by_version="test_v1",
    )


async def _seed_fundo(db, tenant_id: UUID) -> UUID:
    """Cria a UA (FIDC) + dois papeis com trajetorias distintas.

    - KEEP (seu_numero DID-KEEP / doc 9001): presente 24/06..06/07 (9 datas,
      espelha a QUIMASSA real). Fim do papel == fim do warehouse.
    - EXIT (seu_numero DID-EXIT / doc 9002): presente SO 24/06..26/06 — saiu do
      estoque antes do fim do warehouse (liquidado/recomprado).

    Warehouse max do fundo = 06/07 (vem do KEEP).
    """
    ua = UnidadeAdministrativa(
        tenant_id=tenant_id,
        nome="FIDC Teste",
        cnpj=_FUNDO_DOC,
        tipo=TipoUnidadeAdministrativa.FIDC,
    )
    db.add(ua)
    await db.flush()

    keep_dates = [
        date(2026, 6, 24), date(2026, 6, 25), date(2026, 6, 26),
        date(2026, 6, 29), date(2026, 6, 30), date(2026, 7, 1),
        date(2026, 7, 2), date(2026, 7, 3), date(2026, 7, 6),
    ]
    for i, d in enumerate(keep_dates):
        db.add(_papel_row(
            tenant_id=tenant_id, data_referencia=d,
            seu_numero="DID-KEEP", numero_documento="9001",
            valor_presente=Decimal("1030000.00") + Decimal(i) * Decimal("3000"),
        ))

    for d in (date(2026, 6, 24), date(2026, 6, 25), date(2026, 6, 26)):
        db.add(_papel_row(
            tenant_id=tenant_id, data_referencia=d,
            seu_numero="DID-EXIT", numero_documento="9002",
            valor_presente=Decimal("500000.00"),
        ))

    await db.commit()
    return ua.id


def _scope(db, tenant_id: UUID, ua_id: UUID, *, tela: str) -> ScopedContext:
    """Scope com o dia da tela em `tela` — de proposito DIFERENTE do fim real."""
    return ScopedContext(
        tenant_id=tenant_id,
        empresa_id=None,
        user_id=uuid4(),
        module=Module.CONTROLADORIA,
        permissions={Module.CONTROLADORIA: Permission.ADMIN},
        db=db,
        extras={"ua_id": str(ua_id), "data_d0": tela},
    )


@pytest.mark.asyncio
async def test_range_agnostico_a_tela(tenant_a: Tenant) -> None:
    """Tela em 25/06, sem data_fim: retorna ate o fim do warehouse (06/07)."""
    async with AsyncSessionLocal() as db:
        ua_id = await _seed_fundo(db, tenant_a.id)

    async with AsyncSessionLocal() as db:
        scope = _scope(db, tenant_a.id, ua_id, tela="2026-06-25")
        raw = await get_historico_estoque_papel(
            scope, {"numero_documento": "9001", "data_inicio": "2026-06-20"},
        )
    r = json.loads(raw)

    # Nao para na tela: pega os 9 snapshots, ate 06/07.
    assert r["n"] == 9
    assert r["range"] == ["2026-06-20", "2026-07-06"]
    assert r["data_max_warehouse"] == "2026-07-06"
    assert r["data_max_papel"] == "2026-07-06"
    datas = [h["data_referencia"] for h in r["historico"]]
    assert datas[-1] == "2026-07-06"
    # E CRUCIAL: ha linhas DEPOIS do dia da tela (25/06) — o bug era pará-las.
    assert any(d > "2026-06-25" for d in datas)


@pytest.mark.asyncio
async def test_distingue_papel_saiu_de_falta_de_sync(tenant_a: Tenant) -> None:
    """Papel que saiu do estoque: data_max_papel < data_max_warehouse."""
    async with AsyncSessionLocal() as db:
        ua_id = await _seed_fundo(db, tenant_a.id)

    async with AsyncSessionLocal() as db:
        scope = _scope(db, tenant_a.id, ua_id, tela="2026-07-06")
        raw = await get_historico_estoque_papel(scope, {"numero_documento": "9002"})
    r = json.loads(raw)

    assert r["data_max_papel"] == "2026-06-26"
    assert r["data_max_warehouse"] == "2026-07-06"
    # O agente consegue afirmar "papel saiu", NAO "warehouse sem sync".
    assert r["data_max_papel"] < r["data_max_warehouse"]


@pytest.mark.asyncio
async def test_range_explicito_respeitado(tenant_a: Tenant) -> None:
    """data_inicio+data_fim explicitos limitam a janela sem vazar pra frente."""
    async with AsyncSessionLocal() as db:
        ua_id = await _seed_fundo(db, tenant_a.id)

    async with AsyncSessionLocal() as db:
        scope = _scope(db, tenant_a.id, ua_id, tela="2026-06-25")
        raw = await get_historico_estoque_papel(scope, {
            "numero_documento": "9001",
            "data_inicio": "2026-06-24",
            "data_fim": "2026-06-26",
        })
    r = json.loads(raw)

    assert r["n"] == 3
    assert r["range"] == ["2026-06-24", "2026-06-26"]
    # Os faroes seguem apontando o universo real, nao o range pedido.
    assert r["data_max_warehouse"] == "2026-07-06"
    assert r["data_max_papel"] == "2026-07-06"


@pytest.mark.asyncio
async def test_escopo_por_tenant(tenant_a: Tenant, tenant_b: Tenant) -> None:
    """Estoque semeado em A nao vaza para um scope de B (§10)."""
    async with AsyncSessionLocal() as db:
        ua_id_a = await _seed_fundo(db, tenant_a.id)

    # Scope de B usando o mesmo ua_id/tela — B nao tem estoque do fundo.
    async with AsyncSessionLocal() as db:
        scope_b = _scope(db, tenant_b.id, ua_id_a, tela="2026-07-06")
        raw = await get_historico_estoque_papel(
            scope_b, {"numero_documento": "9001"},
        )
    r = json.loads(raw)

    # UA pertence ao tenant A -> nem a UA e visivel para B.
    assert "erro" in r or r.get("n") == 0
