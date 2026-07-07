"""CadastralEnrichmentNode — config white-label + execute wiring."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.agentic.workflows.nodes._base import NodeContext, VarType
from app.agentic.workflows.nodes.cadastral_enrichment import CadastralEnrichmentNode

_ENRICH = "app.modules.credito.services.cadastral.enrich_target_cadastral"


_DOSSIER_ID = "11111111-1111-1111-1111-111111111111"


def _ctx(*, dossier_id: str | None = _DOSSIER_ID, tenant_id=None) -> NodeContext:
    return NodeContext(
        run_id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        node_id="enriquecimento",
        initiated_by=None,
        trigger_data={"dossier_id": dossier_id} if dossier_id else {},
    )


def _outcome(*, ok=True, found=True, cnpj="02379828000128", applied=None, errors=None):
    return SimpleNamespace(
        ok=ok,
        found=found,
        cnpj=cnpj,
        company_id=uuid4(),
        raw_id=uuid4(),
        applied=applied if applied is not None else ["tax_status", "cnaes"],
        errors=errors or [],
    )


# ─── validate_config ──────────────────────────────────────────────────────


def test_validate_defaults_to_cad_pj() -> None:
    node = CadastralEnrichmentNode(config={})
    assert node.type == "cadastral_enrichment"


def test_validate_accepts_explicit_public_code() -> None:
    CadastralEnrichmentNode(config={"public_code": "CAD-PJ"})


def test_validate_rejects_empty_public_code() -> None:
    with pytest.raises(ValueError, match="public_code"):
        CadastralEnrichmentNode(config={"public_code": "  "})


def test_produces_declares_white_label_contract() -> None:
    node = CadastralEnrichmentNode(config={})
    produced = node.produces()
    assert produced["found"] == VarType.BOOLEAN
    assert produced["cnpj"] == VarType.CNPJ
    assert produced["public_code"] == VarType.STRING
    # vendor NUNCA aparece no contrato de output
    assert not any("provider" in k or "vendor" in k for k in produced)


# ─── execute ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execute_requires_dossier_id() -> None:
    node = CadastralEnrichmentNode(config={})
    with pytest.raises(RuntimeError, match="dossier_id"):
        await node.execute(_ctx(dossier_id=None), db=AsyncMock())


@pytest.mark.asyncio
async def test_execute_raises_when_outcome_not_ok() -> None:
    node = CadastralEnrichmentNode(config={})
    mock = AsyncMock(return_value=_outcome(ok=False, errors=["sem credencial"]))
    with patch(_ENRICH, new=mock), pytest.raises(RuntimeError, match="sem credencial"):
        await node.execute(_ctx(), db=AsyncMock())


@pytest.mark.asyncio
async def test_execute_found_returns_applied_fields() -> None:
    node = CadastralEnrichmentNode(config={"public_code": "CAD-PJ"})
    with patch(_ENRICH, new=AsyncMock(return_value=_outcome(found=True))):
        out = await node.execute(_ctx(), db=AsyncMock())
    assert out.data["status"] == "ok"
    assert out.data["found"] is True
    assert out.data["cnpj"] == "02379828000128"
    assert out.data["public_code"] == "CAD-PJ"
    assert out.data["applied"] == ["tax_status", "cnaes"]
    # output nao vaza vendor
    assert not any("provider" in k for k in out.data)


@pytest.mark.asyncio
async def test_execute_not_found_succeeds_with_found_false() -> None:
    node = CadastralEnrichmentNode(config={})
    with patch(_ENRICH, new=AsyncMock(return_value=_outcome(found=False, applied=[]))):
        out = await node.execute(_ctx(), db=AsyncMock())
    assert out.data["status"] == "ok"
    assert out.data["found"] is False
    assert out.data["applied"] == []
