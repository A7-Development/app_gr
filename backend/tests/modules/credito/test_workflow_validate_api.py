"""POST /credito/workflows/_validate — semantic validation endpoint.

Regression tests for the response shape, especially `produced_by_node`
which the editor frontend RefField (variable picker) depends on. Dropping
it makes the picker silently show "nenhuma variavel disponivel" even when
upstream nodes declare typed fields — bug 2026-05-06.
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


_GRAPH_HUMAN_TO_BUREAU = {
    "nodes": [
        {
            "id": "trigger",
            "type": "trigger",
            "label": "Inicio",
            "config": {},
        },
        {
            "id": "form",
            "type": "human_input",
            "label": "Cadastro empresa",
            "config": {
                "form_id": "cadastro_empresa",
                "fields": [
                    {
                        "key": "cnpj",
                        "label": "CNPJ",
                        "type": "cnpj",
                        "required": True,
                    },
                    {
                        "key": "razao_social",
                        "label": "Razao social",
                        "type": "string",
                    },
                ],
            },
        },
        {
            "id": "bureau",
            "type": "bureau_query",
            "label": "Serasa PJ",
            "config": {
                "adapter": "serasa_pj",
                "entity_ref": "{{node.form.output.cnpj}}",
                "environment": "production",
            },
        },
    ],
    "edges": [
        {"id": "e1", "source": "trigger", "target": "form", "condition": None},
        {"id": "e2", "source": "form", "target": "bureau", "condition": None},
    ],
}


async def test_validate_response_includes_produced_by_node(
    client: AsyncClient,
    user_in_tenant_a: User,
) -> None:
    """RefField (variable picker) precisa do produced_by_node para listar
    o que cada upstream publica. Sem isso o picker mostra 'nenhuma variavel
    disponivel' silenciosamente, mesmo com fields declarados upstream."""
    token = await _login(client, user_in_tenant_a.email)
    r = await client.post(
        f"{API_BASE}/workflows/_validate",
        json=_GRAPH_HUMAN_TO_BUREAU,
        headers=_auth(token),
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # Shape contract.
    assert "has_errors" in body
    assert "errors" in body
    assert "produced_by_node" in body, (
        "produced_by_node FALTA da response — frontend RefField nao consegue "
        "listar variaveis upstream sem ele."
    )

    produced = body["produced_by_node"]

    # human_input com fields=[cnpj, razao_social] deve publicar ambos.
    assert "form" in produced
    assert produced["form"].get("cnpj") == "cnpj"
    assert produced["form"].get("razao_social") == "string"

    # trigger publica os campos canonicos do dossie.
    assert "trigger" in produced
    assert "cnpj" in produced["trigger"]


async def test_validate_response_keeps_existing_fields(
    client: AsyncClient,
    user_in_tenant_a: User,
) -> None:
    """has_errors + errors continuam presentes apos a adicao de
    produced_by_node — nao quebrar o consumidor existente."""
    token = await _login(client, user_in_tenant_a.email)
    r = await client.post(
        f"{API_BASE}/workflows/_validate",
        json=_GRAPH_HUMAN_TO_BUREAU,
        headers=_auth(token),
    )
    body = r.json()

    assert isinstance(body["has_errors"], bool)
    assert isinstance(body["errors"], list)
