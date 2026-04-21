"""Integration tests -- GET /api/v1/bi/benchmark/comparativo.

Depende da ponte CVM via postgres_fdw (cvm_remote.*) populada.
Usa 2 CNPJs reais que sabidamente existem no warehouse CVM.
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.database import AsyncSessionLocal
from app.core.enums import Module, Permission
from app.core.security import hash_password
from app.shared.identity.tenant import Tenant
from app.shared.identity.user import User
from app.shared.identity.user_permission import UserModulePermission

# CNPJs reais presentes no `cvm_remote.tab_i` (snapshot 2026-03).
_VALECRED = "24290695000151"
_REALINVEST = "42449234000160"


async def _login(client: AsyncClient, email: str, password: str) -> str:
    r = await client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


@pytest.mark.asyncio
async def test_comparativo_happy_path_dois_fundos(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    """2 CNPJs reais devolvem ranking, series e composicao preenchidas."""
    token = await _login(client, user_in_tenant_a.email, "test-password")

    r = await client.get(
        "/api/v1/bi/benchmark/comparativo",
        params=[("cnpjs", _VALECRED), ("cnpjs", _REALINVEST), ("meses", 12)],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    data = body["data"]

    # Competencia em 'YYYY-MM' (ou vazia se o warehouse estiver seco).
    assert isinstance(data["competencia"], str)

    # Header dos fundos -- ordem preservada, cor_index 0..1.
    cnpjs_header = [f["cnpj"] for f in data["fundos"]]
    assert cnpjs_header == [_VALECRED, _REALINVEST]
    assert [f["cor_index"] for f in data["fundos"]] == [0, 1]

    # Ranking -- 10 indicadores canonicos, cada um com valores pros 2 cnpjs.
    ranking = data["ranking"]
    assert len(ranking) == 10
    keys = {linha["key"] for linha in ranking}
    assert {"pl", "pl_medio", "pct_inad_total", "top1_cedente"} <= keys
    for linha in ranking:
        assert linha["direction"] in ("asc", "desc")
        assert linha["unidade"] in ("BRL", "%", "un", "dias")
        cnpjs_valores = {v["cnpj"] for v in linha["valores"]}
        assert cnpjs_valores == {_VALECRED, _REALINVEST}

    # Series -- dict de indicadores chave -> lista de pontos.
    series = data["series"]
    assert "pl" in series and "pct_inad_total" in series

    # Composicoes -- uma entrada por cnpj.
    comp_cnpjs = {c["cnpj"] for c in data["composicoes"]}
    assert comp_cnpjs == {_VALECRED, _REALINVEST}

    # Proveniencia dado publico CVM.
    assert body["provenance"]["source_type"] == "public:cvm_fidc"
    assert body["provenance"]["trust_level"] == "high"


@pytest.mark.asyncio
async def test_comparativo_422_cnpjs_de_menos(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    """Menos de 2 cnpjs -> 422."""
    token = await _login(client, user_in_tenant_a.email, "test-password")
    r = await client.get(
        "/api/v1/bi/benchmark/comparativo",
        params=[("cnpjs", _VALECRED)],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_comparativo_422_cnpjs_de_mais(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    """Mais de 5 cnpjs -> 422."""
    token = await _login(client, user_in_tenant_a.email, "test-password")
    seis = [
        "24290695000151",
        "42449234000160",
        "11111111111111",
        "22222222222222",
        "33333333333333",
        "44444444444444",
    ]
    r = await client.get(
        "/api/v1/bi/benchmark/comparativo",
        params=[("cnpjs", c) for c in seis],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_comparativo_422_cnpj_mal_formado(
    client: AsyncClient, user_in_tenant_a: User
) -> None:
    """CNPJ com mascara ou com menos de 14 digitos -> 422 (pattern)."""
    token = await _login(client, user_in_tenant_a.email, "test-password")
    r = await client.get(
        "/api/v1/bi/benchmark/comparativo",
        params=[("cnpjs", "24.290.695/0001-51"), ("cnpjs", _REALINVEST)],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_comparativo_403_usuario_sem_bi_read(
    client: AsyncClient, tenant_a: Tenant
) -> None:
    """Usuario sem permissao em BI -> 403 (require_module)."""
    email = f"user-no-bi-{uuid4().hex[:8]}@example.com"
    async with AsyncSessionLocal() as db:
        u = User(
            tenant_id=tenant_a.id,
            email=email,
            name="No BI",
            password_hash=hash_password("test-password"),
            ativo=True,
        )
        db.add(u)
        await db.flush()
        # Permissao NONE em BI + ADMIN em outros (ruido).
        db.add(UserModulePermission(user_id=u.id, module=Module.BI, permission=Permission.NONE))
        for m in Module:
            if m != Module.BI:
                db.add(UserModulePermission(user_id=u.id, module=m, permission=Permission.ADMIN))
        await db.commit()

    token = await _login(client, email, "test-password")

    r = await client.get(
        "/api/v1/bi/benchmark/comparativo",
        params=[("cnpjs", _VALECRED), ("cnpjs", _REALINVEST)],
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_comparativo_401_sem_token(client: AsyncClient) -> None:
    """Sem Authorization -> 401."""
    r = await client.get(
        "/api/v1/bi/benchmark/comparativo",
        params=[("cnpjs", _VALECRED), ("cnpjs", _REALINVEST)],
    )
    assert r.status_code == 401
