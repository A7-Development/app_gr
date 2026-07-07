"""BureauQueryNode — wiring com Serasa PJ + placeholders."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest

from app.agentic.workflows.nodes._base import NodeContext
from app.agentic.workflows.nodes.bureau_query import BureauQueryNode
from app.core.enums import Environment


def _ctx(tenant_id=None, run_id=None) -> NodeContext:
    return NodeContext(
        run_id=run_id or uuid4(),
        tenant_id=tenant_id or uuid4(),
        node_id="bureau_pj",
        initiated_by=None,
    )


# ─── validate_config ──────────────────────────────────────────────────────


def test_validate_rejects_unsupported_adapter() -> None:
    with pytest.raises(ValueError, match="nao suportado"):
        BureauQueryNode(config={"adapter": "experian", "entity_ref": "x"})


def test_validate_serasa_pj_requires_entity_ref() -> None:
    with pytest.raises(ValueError, match="entity_ref"):
        BureauQueryNode(config={"adapter": "serasa_pj"})


def test_validate_serasa_pj_rejects_invalid_environment() -> None:
    with pytest.raises(ValueError, match="environment"):
        BureauQueryNode(
            config={
                "adapter": "serasa_pj",
                "entity_ref": "12345678000199",
                "environment": "homolog",  # invalido
            }
        )


def test_validate_placeholder_adapter_does_not_require_entity_ref() -> None:
    # bigdatacorp ainda nao wired — config minima nao deve bloquear.
    node = BureauQueryNode(config={"adapter": "bigdatacorp"})
    assert node.type == "bureau_query"


# ─── execute (placeholder) ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_placeholder_adapter_returns_em_breve() -> None:
    node = BureauQueryNode(config={"adapter": "infosimples"})
    out = await node.execute(_ctx(), db=None)  # type: ignore[arg-type]
    assert out.data["adapter"] == "infosimples"
    assert out.data["status"] == "not_implemented"
    assert out.status_hint == "em breve"


# ─── execute (serasa_pj wired) ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_serasa_pj_happy_path_returns_consulta_id() -> None:
    """Sucesso devolve consulta_id + counts pra downstream consumir."""
    fake_summary = {
        "ok": True,
        "raw_id": uuid4(),
        "consulta_id": uuid4(),
        "cnpj": "12345678000199",
        "requested_report": "RELATORIO_AVANCADO_PJ_ANALITICO",
        "actual_report_returned": "RELATORIO_AVANCADO_PJ_ANALITICO",
        "reciprocity_downgrade": False,
        "latency_ms": 1234.5,
        "counts": {
            "socios": 0,
            "restricoes": 5,
            "restricao_summaries": 5,
            "participacoes": 0,
            "enderecos": 1,
            "pagamento_buckets": 6,
            "consultas_listadas_detalhe": 3,
        },
        "errors": [],
    }

    node = BureauQueryNode(
        config={
            "adapter": "serasa_pj",
            "entity_ref": "12.345.678/0001-99",
        }
    )

    with patch(
        "app.agentic.workflows.nodes.bureau_query.execute_serasa_pj_query",
        return_value=fake_summary,
    ) as mock_exec:
        out = await node.execute(_ctx(), db=None)  # type: ignore[arg-type]

    mock_exec.assert_awaited_once()
    kwargs = mock_exec.call_args.kwargs
    # CNPJ vem como na config — adapter normaliza internamente.
    assert kwargs["cnpj"] == "12.345.678/0001-99"
    # Default ambiente = producao.
    assert kwargs["environment"] == Environment.PRODUCTION
    # triggered_by carrega o run_id pra rastreio em decision_log/raw.
    assert "workflow_run:" in kwargs["triggered_by"]

    assert out.data["status"] == "ok"
    assert out.data["adapter"] == "serasa_pj"
    assert out.data["consulta_id"] == str(fake_summary["consulta_id"])
    assert out.data["raw_id"] == str(fake_summary["raw_id"])
    assert out.data["counts"]["restricoes"] == 5


@pytest.mark.asyncio
async def test_serasa_pj_uses_sandbox_environment_when_configured() -> None:
    fake_summary = {
        "ok": True,
        "raw_id": uuid4(),
        "consulta_id": uuid4(),
        "cnpj": "12345678000199",
        "requested_report": "X",
        "actual_report_returned": "X",
        "reciprocity_downgrade": False,
        "latency_ms": 0,
        "counts": {},
        "errors": [],
    }

    node = BureauQueryNode(
        config={
            "adapter": "serasa_pj",
            "entity_ref": "12345678000199",
            "environment": "sandbox",
        }
    )
    with patch(
        "app.agentic.workflows.nodes.bureau_query.execute_serasa_pj_query",
        return_value=fake_summary,
    ) as mock_exec:
        await node.execute(_ctx(), db=None)  # type: ignore[arg-type]

    assert mock_exec.call_args.kwargs["environment"] == Environment.SANDBOX


@pytest.mark.asyncio
async def test_serasa_pj_failure_raises_to_engine() -> None:
    """Quando consulta falha (auth, rede, contrato), nó levanta — engine
    marca workflow_node_run como FAILED. Operador reprocessa ou pula."""
    fake_summary = {
        "ok": False,
        "raw_id": None,
        "consulta_id": None,
        "cnpj": "12345678000199",
        "errors": [
            "query: SerasaPjAuthError: credenciais rejeitadas",
            "query.status_code: 401",
        ],
    }

    node = BureauQueryNode(
        config={"adapter": "serasa_pj", "entity_ref": "12345678000199"}
    )

    with (
        patch(
            "app.agentic.workflows.nodes.bureau_query.execute_serasa_pj_query",
            return_value=fake_summary,
        ),
        pytest.raises(RuntimeError, match=r"serasa_pj.*nao concluiu"),
    ):
        await node.execute(_ctx(), db=None)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_serasa_pj_propagates_run_id_in_triggered_by() -> None:
    """triggered_by carrega o workflow_run.id — vai pra raw + decision_log
    pra rastreio (qual run consultou esse CNPJ)."""
    fake_summary = {
        "ok": True,
        "raw_id": uuid4(),
        "consulta_id": uuid4(),
        "cnpj": "12345678000199",
        "requested_report": "X",
        "actual_report_returned": "X",
        "reciprocity_downgrade": False,
        "latency_ms": 0,
        "counts": {},
        "errors": [],
    }
    run_id = uuid4()
    ctx = _ctx(run_id=run_id)

    node = BureauQueryNode(
        config={"adapter": "serasa_pj", "entity_ref": "12345678000199"}
    )
    with patch(
        "app.agentic.workflows.nodes.bureau_query.execute_serasa_pj_query",
        return_value=fake_summary,
    ) as mock_exec:
        await node.execute(ctx, db=None)  # type: ignore[arg-type]

    assert mock_exec.call_args.kwargs["triggered_by"] == (
        f"workflow_run:{run_id}"
    )
