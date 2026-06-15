"""Gate de seleção (opção B) do official_document_fetch — fases do node v2.

Mocka o DB (sem doc existente) + as funções da junta. Não toca JUCESP nem banco.

pytest tests/agentic/playbooks/nodes/test_official_document_fetch_gate.py --noconftest
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.agentic.playbooks.nodes._base import NodeContext
from app.agentic.playbooks.nodes.official_document_fetch import (
    OfficialDocumentFetchNode,
)
from app.modules.credito.services import junta as junta_svc
from app.modules.credito.services.junta import SocialContractOptions


def _ctx(node_id: str, previous_outputs: dict | None = None) -> NodeContext:
    return NodeContext(
        run_id=uuid4(),
        tenant_id=uuid4(),
        node_id=node_id,
        initiated_by=None,
        previous_outputs=previous_outputs or {},
        trigger_data={"dossier_id": str(uuid4())},
    )


def _db_no_existing_doc() -> MagicMock:
    """db.execute(...).scalar_one_or_none() -> None (sem doc social já anexado)."""
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


_OPTIONS = [
    {"registro": "415.509/20-8", "protocolo": "0838427200", "descricao": "ALTERAÇÃO. CONSOLIDAÇÃO.", "data": "04/11/2020", "disponivel": True, "suggested": False},
    {"registro": "417.748/24-3", "protocolo": "2892593244", "descricao": "ENCERRAMENTO DA FILIAL. CONSOLIDAÇÃO DA MATRIZ.", "data": "19/12/2024", "disponivel": True, "suggested": True},
]


@pytest.mark.asyncio
async def test_select_phase1_pausa_com_opcoes(monkeypatch) -> None:
    monkeypatch.setattr(
        junta_svc,
        "prepare_social_contract_options",
        AsyncMock(
            return_value=SocialContractOptions(
                found_company=True, message="", nire="354123", documentos=[], options=_OPTIONS
            )
        ),
    )
    node = OfficialDocumentFetchNode({"document": "social_contract_jucesp", "mode": "select"})
    out = await node.execute(_ctx("fetch_x"), _db_no_existing_doc())
    assert out.should_pause is True
    assert out.data["phase"] == "select"
    assert out.data["nire"] == "354123"
    assert out.data["options"] == _OPTIONS
    # o sugerido vai na lista (a UI marca o badge)
    assert any(o["suggested"] for o in out.data["options"])


@pytest.mark.asyncio
async def test_select_phase1_sem_empresa_cai_no_manual(monkeypatch) -> None:
    monkeypatch.setattr(
        junta_svc,
        "prepare_social_contract_options",
        AsyncMock(
            return_value=SocialContractOptions(
                found_company=False, message="Empresa não encontrada na JUCESP.", nire=None, documentos=[], options=[]
            )
        ),
    )
    node = OfficialDocumentFetchNode({"document": "social_contract_jucesp", "mode": "select"})
    out = await node.execute(_ctx("fetch_x"), _db_no_existing_doc())
    # found=false → aresta found==false roteia pro document_request (sem pausar)
    assert out.should_pause is False
    assert out.data["found"] is False


@pytest.mark.asyncio
async def test_select_phase2_usar_baixa_e_pausa_homologacao(monkeypatch) -> None:
    fake_doc = MagicMock()
    fake_doc.id = uuid4()
    fake_doc.original_filename = "JUCESP_354123_417.748-24-3_CONSOLIDACAO.pdf"
    fake_doc.doc_type.value = "social_contract"
    download = AsyncMock(return_value=fake_doc)
    monkeypatch.setattr(junta_svc, "download_social_contract_by_registro", download)

    node = OfficialDocumentFetchNode({"document": "social_contract_jucesp", "mode": "select"})
    prev = {
        "fetch_x": {
            "output": {"phase": "select", "nire": "354123", "options": _OPTIONS},
            "pending_input": {"action": "use", "registro": "417.748/24-3", "protocolo": "2892593244"},
        }
    }
    out = await node.execute(_ctx("fetch_x", prev), _db_no_existing_doc())
    assert out.data["found"] is True
    assert out.data["document_id"] == str(fake_doc.id)
    # baixou o registro ESCOLHIDO, com o NIRE preservado da fase 1
    _, kwargs = download.call_args
    assert kwargs["registro"] == "417.748/24-3"
    assert kwargs["nire"] == "354123"
    # após anexar, pausa pro analista homologar a conferência
    assert out.should_pause is True


@pytest.mark.asyncio
async def test_select_phase2_manual_found_false() -> None:
    node = OfficialDocumentFetchNode({"document": "social_contract_jucesp", "mode": "select"})
    prev = {"fetch_x": {"output": {"nire": "354123"}, "pending_input": {"action": "manual"}}}
    out = await node.execute(_ctx("fetch_x", prev), _db_no_existing_doc())
    assert out.data["found"] is False
    assert out.should_pause is False


def test_config_rejeita_mode_invalido() -> None:
    with pytest.raises(ValueError, match="mode"):
        OfficialDocumentFetchNode({"document": "social_contract_jucesp", "mode": "xpto"})
