"""get_expected_classes — catalogo de classes por UA (DB).

Cobre vigencia, scoping por endpoint, fallback (set vazio) e isolamento de
tenant (CLAUDE.md §10).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

import pytest

from app.core.database import AsyncSessionLocal
from app.modules.cadastros.models.unidade_administrativa import (
    TipoUnidadeAdministrativa,
    UnidadeAdministrativa,
)
from app.modules.integracoes.models.qitech_ua_classe import QiTechUaClasse
from app.modules.integracoes.services.qitech_ua_classe import (
    get_expected_classes,
)
from app.shared.identity.tenant import Tenant

_ON = date(2026, 5, 25)


async def _make_ua(tenant_id: UUID, nome: str = "REALINVEST FIDC") -> UUID:
    async with AsyncSessionLocal() as db:
        ua = UnidadeAdministrativa(
            tenant_id=tenant_id,
            nome=nome,
            tipo=TipoUnidadeAdministrativa.FIDC,
        )
        db.add(ua)
        await db.commit()
        await db.refresh(ua)
        return ua.id


async def _add_classe(
    tenant_id: UUID,
    ua_id: UUID,
    cliente_id: str,
    papel: str,
    *,
    ativo_desde: date = date(2021, 1, 1),
    ativo_ate: date | None = None,
) -> None:
    async with AsyncSessionLocal() as db:
        db.add(
            QiTechUaClasse(
                tenant_id=tenant_id,
                unidade_administrativa_id=ua_id,
                cliente_id=cliente_id,
                cliente_nome=cliente_id,
                fundo_cnpj="42449234000160",
                papel=papel,
                ativo_desde=ativo_desde,
                ativo_ate=ativo_ate,
            )
        )
        await db.commit()


async def _seed_3_classes(tenant_id: UUID, ua_id: UUID) -> None:
    await _add_classe(tenant_id, ua_id, "REALINVEST", "SUBORDINADA")
    await _add_classe(tenant_id, ua_id, "REALINVEST MEZ", "MEZANINO")
    await _add_classe(tenant_id, ua_id, "REALINVEST SEN", "SENIOR")


@pytest.mark.asyncio
async def test_mec_expects_all_three_classes(tenant_a: Tenant):
    ua_id = await _make_ua(tenant_a.id)
    await _seed_3_classes(tenant_a.id, ua_id)
    async with AsyncSessionLocal() as db:
        got = await get_expected_classes(
            db,
            tenant_id=tenant_a.id,
            unidade_administrativa_id=ua_id,
            tipo_de_mercado="mec",
            on_date=_ON,
        )
    assert got == {"REALINVEST", "REALINVEST MEZ", "REALINVEST SEN"}


@pytest.mark.asyncio
async def test_cpr_scopes_to_subordinada_only(tenant_a: Tenant):
    ua_id = await _make_ua(tenant_a.id)
    await _seed_3_classes(tenant_a.id, ua_id)
    async with AsyncSessionLocal() as db:
        got = await get_expected_classes(
            db,
            tenant_id=tenant_a.id,
            unidade_administrativa_id=ua_id,
            tipo_de_mercado="cpr",  # consolidado -> so a Sub
            on_date=_ON,
        )
    assert got == {"REALINVEST"}


@pytest.mark.asyncio
async def test_vigencia_excludes_closed_class(tenant_a: Tenant):
    ua_id = await _make_ua(tenant_a.id)
    await _add_classe(tenant_a.id, ua_id, "REALINVEST", "SUBORDINADA")
    await _add_classe(tenant_a.id, ua_id, "REALINVEST MEZ", "MEZANINO")
    # Senior encerrada em 2026-05-20 -> nao esperada em 2026-05-25.
    await _add_classe(
        tenant_a.id, ua_id, "REALINVEST SEN", "SENIOR",
        ativo_ate=date(2026, 5, 20),
    )
    async with AsyncSessionLocal() as db:
        got = await get_expected_classes(
            db,
            tenant_id=tenant_a.id,
            unidade_administrativa_id=ua_id,
            tipo_de_mercado="mec",
            on_date=_ON,
        )
    assert got == {"REALINVEST", "REALINVEST MEZ"}


@pytest.mark.asyncio
async def test_unknown_tipo_returns_empty(tenant_a: Tenant):
    ua_id = await _make_ua(tenant_a.id)
    await _seed_3_classes(tenant_a.id, ua_id)
    async with AsyncSessionLocal() as db:
        got = await get_expected_classes(
            db,
            tenant_id=tenant_a.id,
            unidade_administrativa_id=ua_id,
            tipo_de_mercado="fidc-estoque",  # fora do mapa
            on_date=_ON,
        )
    assert got == set()


@pytest.mark.asyncio
async def test_no_catalog_returns_empty(tenant_a: Tenant):
    ua_id = await _make_ua(tenant_a.id)  # sem classes cadastradas
    async with AsyncSessionLocal() as db:
        got = await get_expected_classes(
            db,
            tenant_id=tenant_a.id,
            unidade_administrativa_id=ua_id,
            tipo_de_mercado="mec",
            on_date=_ON,
        )
    assert got == set()


@pytest.mark.asyncio
async def test_ua_none_returns_empty(tenant_a: Tenant):
    async with AsyncSessionLocal() as db:
        got = await get_expected_classes(
            db,
            tenant_id=tenant_a.id,
            unidade_administrativa_id=None,
            tipo_de_mercado="mec",
            on_date=_ON,
        )
    assert got == set()


@pytest.mark.asyncio
async def test_tenant_isolation(tenant_a: Tenant, tenant_b: Tenant):
    ua_a = await _make_ua(tenant_a.id)
    await _seed_3_classes(tenant_a.id, ua_a)
    # tenant_b nao tem catalogo; mesmo passando a UA do A, escopo por tenant_b
    # nao deve enxergar nada.
    async with AsyncSessionLocal() as db:
        got = await get_expected_classes(
            db,
            tenant_id=tenant_b.id,
            unidade_administrativa_id=ua_a,
            tipo_de_mercado="mec",
            on_date=_ON,
        )
    assert got == set()
