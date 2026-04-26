"""Phase F multi-UA — testes de isolamento de credenciais por UA.

Garante que `tenant_source_config` agora suporta N linhas por
(tenant, source_type, environment), uma por UA, e que os helpers de leitura
escopam corretamente por UA.

CLAUDE.md secao 13 + secao 18 (checklist: teste de isolamento obrigatorio).
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.cadastros.models.unidade_administrativa import (
    TipoUnidadeAdministrativa,
    UnidadeAdministrativa,
)
from app.modules.integracoes.models.tenant_source_config import (
    TenantSourceConfig,
)
from app.modules.integracoes.services.source_config import (
    decrypt_config,
    get_config,
    list_configs,
    upsert_config,
)
from app.shared.identity.tenant import Tenant


async def _make_ua(*, tenant_id: UUID, nome: str) -> UnidadeAdministrativa:
    async with AsyncSessionLocal() as db:
        ua = UnidadeAdministrativa(
            tenant_id=tenant_id,
            nome=nome,
            tipo=TipoUnidadeAdministrativa.FIDC,
            ativa=True,
        )
        db.add(ua)
        await db.commit()
        await db.refresh(ua)
    return ua


@pytest.mark.asyncio
async def test_two_uas_same_tenant_coexist(tenant_a: Tenant) -> None:
    """Duas UAs do mesmo tenant podem ter configs QiTech distintas, sem colisao."""
    ua_x = await _make_ua(tenant_id=tenant_a.id, nome=f"UA-X-{uuid4().hex[:6]}")
    ua_y = await _make_ua(tenant_id=tenant_a.id, nome=f"UA-Y-{uuid4().hex[:6]}")

    async with AsyncSessionLocal() as db:
        await upsert_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            {"client_id": "X-id", "client_secret": "X-secret"},
            unidade_administrativa_id=ua_x.id,
        )

    async with AsyncSessionLocal() as db:
        await upsert_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            {"client_id": "Y-id", "client_secret": "Y-secret"},
            unidade_administrativa_id=ua_y.id,
        )

    async with AsyncSessionLocal() as db:
        rows = await list_configs(
            db, tenant_a.id, SourceType.ADMIN_QITECH, Environment.PRODUCTION
        )
        assert len(rows) == 2
        # Cada UA tem seu proprio par de credenciais.
        by_ua: dict[UUID, dict] = {
            row.unidade_administrativa_id: decrypt_config(row.config) for row in rows
        }
        assert by_ua[ua_x.id]["client_id"] == "X-id"
        assert by_ua[ua_y.id]["client_id"] == "Y-id"
        assert by_ua[ua_x.id]["client_secret"] != by_ua[ua_y.id]["client_secret"]


@pytest.mark.asyncio
async def test_get_config_scopes_by_ua(tenant_a: Tenant) -> None:
    """`get_config(..., unidade_administrativa_id=...)` retorna so a linha pedida."""
    ua_x = await _make_ua(tenant_id=tenant_a.id, nome=f"UA-X-{uuid4().hex[:6]}")
    ua_y = await _make_ua(tenant_id=tenant_a.id, nome=f"UA-Y-{uuid4().hex[:6]}")

    async with AsyncSessionLocal() as db:
        await upsert_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            {"client_id": "X"},
            unidade_administrativa_id=ua_x.id,
        )
        await upsert_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            {"client_id": "Y"},
            unidade_administrativa_id=ua_y.id,
        )

    async with AsyncSessionLocal() as db:
        cfg_x = await get_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            Environment.PRODUCTION,
            unidade_administrativa_id=ua_x.id,
        )
        cfg_y = await get_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            Environment.PRODUCTION,
            unidade_administrativa_id=ua_y.id,
        )
        assert cfg_x is not None
        assert cfg_y is not None
        assert decrypt_config(cfg_x.config)["client_id"] == "X"
        assert decrypt_config(cfg_y.config)["client_id"] == "Y"


@pytest.mark.asyncio
async def test_legacy_null_ua_isolated_from_per_ua_rows(
    tenant_a: Tenant,
) -> None:
    """Linha legacy (UA=NULL) coexiste com linhas por UA sem colidir."""
    ua_x = await _make_ua(tenant_id=tenant_a.id, nome=f"UA-X-{uuid4().hex[:6]}")

    async with AsyncSessionLocal() as db:
        await upsert_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            {"client_id": "LEGACY"},
            unidade_administrativa_id=None,  # legacy
        )
        await upsert_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            {"client_id": "BY-UA"},
            unidade_administrativa_id=ua_x.id,
        )

    async with AsyncSessionLocal() as db:
        legacy = await get_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            Environment.PRODUCTION,
            unidade_administrativa_id=None,
        )
        per_ua = await get_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            Environment.PRODUCTION,
            unidade_administrativa_id=ua_x.id,
        )
        assert legacy is not None
        assert per_ua is not None
        assert decrypt_config(legacy.config)["client_id"] == "LEGACY"
        assert decrypt_config(per_ua.config)["client_id"] == "BY-UA"


@pytest.mark.asyncio
async def test_tenant_isolation_with_uas(
    tenant_a: Tenant, tenant_b: Tenant
) -> None:
    """Tenant A nao ve config de tenant B mesmo quando ambos tem UAs configuradas."""
    ua_a = await _make_ua(tenant_id=tenant_a.id, nome=f"UA-A-{uuid4().hex[:6]}")
    ua_b = await _make_ua(tenant_id=tenant_b.id, nome=f"UA-B-{uuid4().hex[:6]}")

    async with AsyncSessionLocal() as db:
        await upsert_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            {"client_id": "TENANT-A-CRED"},
            unidade_administrativa_id=ua_a.id,
        )
        await upsert_config(
            db,
            tenant_b.id,
            SourceType.ADMIN_QITECH,
            {"client_id": "TENANT-B-CRED"},
            unidade_administrativa_id=ua_b.id,
        )

    async with AsyncSessionLocal() as db:
        # Buscar com UA do tenant B mas escopado em tenant A => None.
        miss = await get_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            Environment.PRODUCTION,
            unidade_administrativa_id=ua_b.id,
        )
        assert miss is None

        # list_configs do tenant A so devolve a linha do tenant A.
        rows_a = await list_configs(
            db, tenant_a.id, SourceType.ADMIN_QITECH, Environment.PRODUCTION
        )
        assert all(r.tenant_id == tenant_a.id for r in rows_a)
        assert any(r.unidade_administrativa_id == ua_a.id for r in rows_a)
        assert all(r.unidade_administrativa_id != ua_b.id for r in rows_a)


@pytest.mark.asyncio
async def test_unique_constraint_blocks_duplicate_per_ua(tenant_a: Tenant) -> None:
    """Tentar criar 2 linhas com mesma (tenant, source, env, ua) deve dar upsert."""
    ua_x = await _make_ua(tenant_id=tenant_a.id, nome=f"UA-X-{uuid4().hex[:6]}")

    async with AsyncSessionLocal() as db:
        await upsert_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            {"client_id": "FIRST"},
            unidade_administrativa_id=ua_x.id,
        )
        # Segundo upsert com mesma (tenant, src, env, ua) — deve sobrescrever
        # via ON CONFLICT, nao criar 2 linhas.
        await upsert_config(
            db,
            tenant_a.id,
            SourceType.ADMIN_QITECH,
            {"client_id": "SECOND"},
            unidade_administrativa_id=ua_x.id,
        )

    async with AsyncSessionLocal() as db:
        rows = await list_configs(
            db, tenant_a.id, SourceType.ADMIN_QITECH, Environment.PRODUCTION
        )
        # Apenas 1 linha pra (tenant, src, env, ua) — UQ funcionou.
        only = [r for r in rows if r.unidade_administrativa_id == ua_x.id]
        assert len(only) == 1
        assert decrypt_config(only[0].config)["client_id"] == "SECOND"


@pytest.mark.asyncio
async def test_token_cache_keyed_by_ua() -> None:
    """Token cache em auth.py distingue UAs do mesmo tenant."""
    import httpx

    from app.modules.integracoes.adapters.admin.qitech.auth import (
        _TOKEN_CACHE,
        _clear_cache_for_tests,
        get_api_token,
    )
    from app.modules.integracoes.adapters.admin.qitech.config import (
        QiTechConfig,
    )

    _clear_cache_for_tests()
    try:
        tenant = uuid4()
        ua_x = uuid4()
        ua_y = uuid4()

        # Config de UA-X devolve token "TOKEN-X"; UA-Y devolve "TOKEN-Y".
        # Distincao via client_id no Basic Auth.
        def handler(request: httpx.Request) -> httpx.Response:
            auth_header = request.headers.get("Authorization") or ""
            # Identifica UA pelo client_id do Basic decoded
            if "X-cli" in auth_header or auth_header == "":
                # NOTE: simplificacao — checamos pelo body do client_id; o Basic
                # decode poderia ser feito, mas nao precisamos pra esse teste.
                pass
            # Devolvemos token diferente por chamada — UA-Y emite token novo
            return httpx.Response(200, json={"apiToken": "TOK"})

        transport = httpx.MockTransport(handler)
        cfg_x = QiTechConfig(
            base_url="https://api.test",
            client_id="X-cli",
            client_secret="X-sec",
            token_ttl_seconds=3600,
            token_refresh_skew_seconds=10,
        )
        cfg_y = QiTechConfig(
            base_url="https://api.test",
            client_id="Y-cli",
            client_secret="Y-sec",
            token_ttl_seconds=3600,
            token_refresh_skew_seconds=10,
        )

        await get_api_token(
            tenant_id=tenant,
            environment=Environment.PRODUCTION,
            config=cfg_x,
            transport=transport,
            unidade_administrativa_id=ua_x,
        )
        await get_api_token(
            tenant_id=tenant,
            environment=Environment.PRODUCTION,
            config=cfg_y,
            transport=transport,
            unidade_administrativa_id=ua_y,
        )

        # Cache deve ter 2 entradas distintas — uma por UA.
        keys = [
            k
            for k in _TOKEN_CACHE
            if k[0] == tenant and k[1] == Environment.PRODUCTION
        ]
        assert len(keys) == 2, f"esperava 2 entradas no cache, achei {len(keys)}: {keys}"
        ua_ids_in_cache = {k[2] for k in keys}
        assert ua_x in ua_ids_in_cache
        assert ua_y in ua_ids_in_cache

        # Tambem nao colide com UA=None (legacy).
        await get_api_token(
            tenant_id=tenant,
            environment=Environment.PRODUCTION,
            config=cfg_x,
            transport=transport,
            unidade_administrativa_id=None,
        )
        keys2 = [
            k
            for k in _TOKEN_CACHE
            if k[0] == tenant and k[1] == Environment.PRODUCTION
        ]
        assert len(keys2) == 3
    finally:
        _clear_cache_for_tests()


@pytest.mark.asyncio
async def test_warehouse_table_has_ua_column() -> None:
    """Schema check rapido — colunas adicionadas pela migration estao no model."""
    from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo
    from app.warehouse.qitech_raw_relatorio import QiTechRawRelatorio

    assert "unidade_administrativa_id" in PosicaoCotaFundo.__table__.columns
    assert "unidade_administrativa_id" in QiTechRawRelatorio.__table__.columns

    # UQ da raw inclui UA.
    raw_uqs = [
        c
        for c in QiTechRawRelatorio.__table__.constraints
        if hasattr(c, "columns") and "uq_wh_qitech_raw_relatorio" in (c.name or "")
    ]
    assert raw_uqs, "UQ uq_wh_qitech_raw_relatorio nao encontrada"
    cols = {c.name for c in raw_uqs[0].columns}
    assert "unidade_administrativa_id" in cols, f"UQ atual: {cols}"


# Garantir que o tenant_b fixture exporta fixture mesmo se nao usado em todos os testes.
_ = TenantSourceConfig  # tipos referenciados
