"""GET /credito/agent-catalog — exposes per-agent metadata for editor.

Phase B1 of structured-context migration: the editor needs to render the
slot-binding UI for specialist_agent nodes, which requires the
`inputs: AgentInput[]` declared per-agent in `app.agentic.engine.catalog`.
"""

from __future__ import annotations

from httpx import AsyncClient

from app.shared.identity.user import User

API_BASE = "/api/v1/credito"


async def _login(client: AsyncClient, email: str) -> str:
    r = await client.post(
        "/api/v1/auth/login", json={"email": email, "password": "test-password"}
    )
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def test_agent_catalog_returns_all_catalog_agents(
    client: AsyncClient,
    user_in_tenant_a: User,
) -> None:
    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(f"{API_BASE}/agent-catalog", headers=_auth(token))
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)

    names = {a["name"] for a in body}
    expected = {
        "social_contract_analyst",
        "financial_analyst",
        "indebtedness_analyst",
        "legal_analyst",
        "partner_analyst",
        "commercial_visit_analyst",
        "cross_reference_analyst",
        "opinion_writer",
        "document_extractor",
        "pleito_extractor",
    }
    assert expected <= names


async def test_financial_analyst_exposes_phase_a_inputs(
    client: AsyncClient,
    user_in_tenant_a: User,
) -> None:
    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(f"{API_BASE}/agent-catalog", headers=_auth(token))
    body = r.json()

    fa = next(a for a in body if a["name"] == "financial_analyst")
    inputs_by_name = {i["name"]: i for i in fa["inputs"]}

    assert {"cnpj", "score_pj", "endividamento_total", "ebitda"} <= set(inputs_by_name)

    cnpj = inputs_by_name["cnpj"]
    assert cnpj["type"] == "cnpj"
    assert cnpj["optional"] is False
    assert cnpj["description"]  # non-empty

    score = inputs_by_name["score_pj"]
    assert score["type"] == "score"
    assert score["optional"] is True


async def test_legacy_agents_have_empty_inputs_list(
    client: AsyncClient,
    user_in_tenant_a: User,
) -> None:
    """Migrados ate aqui: financial_analyst, legal_analyst,
    indebtedness_analyst, cross_reference_analyst. Os outros 6 reportam
    inputs=[] — editor renderiza fallback (sem AgentInputBindingsField)."""
    token = await _login(client, user_in_tenant_a.email)
    r = await client.get(f"{API_BASE}/agent-catalog", headers=_auth(token))
    body = r.json()

    legacy_names = {
        "social_contract_analyst",
        "partner_analyst",
        "commercial_visit_analyst",
        "opinion_writer",
        "document_extractor",
        "pleito_extractor",
    }
    for agent in body:
        if agent["name"] in legacy_names:
            assert agent["inputs"] == [], (
                f"{agent['name']} migrou inesperadamente — esta fatia "
                "migra apenas financial/legal/indebtedness/cross_reference."
            )


async def test_agent_catalog_requires_credito_read(
    client: AsyncClient,
) -> None:
    """Endpoint deve exigir token autenticado com permissao CREDITO READ."""
    r = await client.get(f"{API_BASE}/agent-catalog")
    # Sem token -> 401 (unauthenticated)
    assert r.status_code == 401, r.text
