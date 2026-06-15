"""JUCESP no dossiê — busca direta do contrato social na fonte oficial.

Orquestra (consumindo `integracoes/public.py`, §11.3):
  1. ficha cadastral completa da JUCESP (CNPJ da empresa-alvo)
  2. persiste o QSA/arquivamentos oficiais em
     `credit_dossier_company.junta_data` (insumo dos cruzamentos)
  3. localiza o documento societário mais recente arquivado (contrato /
     alteração / consolidação)
  4. baixa a cópia digitalizada e a transforma em `credit_dossier_document`
     (doc_type SOCIAL_CONTRACT) — a extração multimodal dispara em seguida,
     entrando no MESMO fluxo de conferência do upload manual.

A cópia digitalizada da JUCESP não tem valor jurídico — serve à análise e à
contraprova ("o documento que o cedente mandou é o último arquivado?").
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CompanyRole, DocumentType
from app.modules.credito.models.company import CreditDossierCompany
from app.modules.credito.models.document import CreditDossierDocument
from app.modules.integracoes.public import (
    fetch_junta_documento,
    fetch_junta_ficha,
    fetch_junta_lista_documentos,
)


class JuntaFetchError(Exception):
    """Falha de negócio na busca JUCESP (mensagem segura pro analista)."""


_DOC_SOCIETARIO_RE = re.compile(
    r"CONTRATO|ALTERA|CONSOLIDA|CONSTITUI", re.IGNORECASE
)
# Contrato CONSOLIDADO = retrato vigente completo da sociedade — o melhor doc
# único pra análise. Preferido sobre os demais atos societários.
_CONSOLIDA_RE = re.compile(r"CONSOLIDA", re.IGNORECASE)


def _digits(raw: Any) -> str:
    return re.sub(r"\D", "", str(raw or ""))


def _registro_of(doc: dict[str, Any]) -> str | None:
    # "numdoc" e a chave oficial dos arquivamentos JUCESP (doc Infosimples);
    # as demais cobrem variacoes de layout da lista de digitalizados.
    for key in ("numdoc", "registro", "numero", "protocolo"):
        value = doc.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _searchable_text(doc: dict[str, Any]) -> str:
    """Descrição do ato + tipos de eventos, num blob pro regex.

    GOTCHA (2026-06-14): a JUCESP/Infosimples manda a descrição do ato no campo
    `texto` (consulta `completa`) ou `descricao` (consulta `lista-dcs`) — NÃO em
    `tipo`/`eventos`, que vêm null. Sem ler `texto`, o regex não casava nada e o
    pick caía no fallback por data (pegava encerramento de filial, etc.).
    """
    parts = [
        str(doc.get("texto") or ""),
        str(doc.get("descricao") or ""),
        str(doc.get("tipo") or ""),
    ]
    eventos = doc.get("eventos")
    if isinstance(eventos, list):
        parts.extend(
            str(e.get("tipo") or "") for e in eventos if isinstance(e, dict)
        )
    return " ".join(p for p in parts if p)


def _sort_key(doc: dict[str, Any]) -> tuple:
    """Mais recente primeiro: data (dd/mm/aaaa) > registro numérico."""
    # "sessao" e a data oficial do arquivamento na JUCESP (dd/mm/aaaa).
    raw_date = str(
        doc.get("sessao") or doc.get("digitalizacao") or doc.get("data") or ""
    )
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", raw_date)
    date_key = (m.group(3), m.group(2), m.group(1)) if m else ("0", "0", "0")
    reg = _digits(_registro_of(doc) or "")
    return (date_key, int(reg) if reg else 0)


def _pick_latest_societario(docs: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Melhor doc constitutivo da JUCESP — sugestão pro analista.

    Prefere o contrato CONSOLIDADO (retrato vigente) mais recente; senão, o ato
    societário (constituição/alteração) mais recente. Retorna None quando NÃO há
    ato constitutivo (só encerramento/procuração/deliberação/etc.) — aí o fluxo
    cai em `found=false` e o analista anexa o documento. SEM fallback "pega
    qualquer doc por data" (era a causa do pick de encerramento de filial).
    """
    societarios = [
        d
        for d in docs
        if _DOC_SOCIETARIO_RE.search(_searchable_text(d)) and _registro_of(d)
    ]
    if not societarios:
        return None
    consolidados = [d for d in societarios if _CONSOLIDA_RE.search(_searchable_text(d))]
    return max(consolidados or societarios, key=_sort_key)


def build_document_options(documentos: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Lista de arquivamentos JUCESP -> opções pro seletor (Fatia 2 / opção B).

    Cada opção: {registro, protocolo, descricao, data, disponivel, suggested}.
    `suggested=True` no doc que o classificador escolheria (consolidação mais
    recente) — só uma sugestão; o analista vê a lista e decide. Sem ato
    constitutivo, nenhum `suggested` (analista escolhe ou anexa manualmente).
    """
    suggested = _pick_latest_societario(documentos)
    suggested_reg = _registro_of(suggested) if suggested is not None else None
    options: list[dict[str, Any]] = []
    for d in documentos:
        reg = _registro_of(d)
        if reg is None:
            continue
        descricao = str(d.get("texto") or d.get("descricao") or "").strip()
        digit = str(d.get("digitalizacao") or "").strip().upper()
        options.append(
            {
                "registro": reg,
                "protocolo": (str(d.get("protocolo") or "").strip() or None),
                "descricao": descricao or "(sem descrição)",
                "data": (str(d.get("sessao") or d.get("data") or "").strip() or None),
                "disponivel": digit == "DISPONÍVEL",
                "suggested": reg == suggested_reg,
            }
        )
    return options


async def _persist_junta_data(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    fields_json: dict[str, Any],
    raw_id: UUID | None,
    adapter_version: str,
) -> None:
    company = (
        await db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == tenant_id,
                CreditDossierCompany.dossier_id == dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()
    if company is None:
        return
    company.junta_data = {
        **fields_json,
        "_meta": {
            "fonte": "junta_comercial_sp",
            "raw_id": str(raw_id) if raw_id else None,
            "adapter_version": adapter_version,
            "fetched_at": datetime.now(UTC).isoformat(),
        },
    }
    await db.flush()


async def fetch_social_contract_from_junta(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    initiated_by: UUID | None,
) -> CreditDossierDocument:
    """Busca o contrato social mais recente na JUCESP e anexa ao dossiê.

    Returns:
        O documento criado, já com a extração multimodal executada.

    Raises:
        JuntaFetchError: empresa sem CNPJ, não encontrada na JUCESP, sem
            documentos societários arquivados, ou falha do provedor.
    """
    from app.modules.credito.services.document import (
        create_document,
        process_document,
    )
    from app.modules.credito.services.dossier import get_dossier
    from app.modules.integracoes.adapters.data.infosimples.errors import (
        InfosimplesAdapterError,
    )

    dossier = await get_dossier(db, tenant_id=tenant_id, dossier_id=dossier_id)
    if dossier is None:
        raise JuntaFetchError("Dossiê não encontrado.")
    cnpj = _digits(dossier.target_cnpj)
    if len(cnpj) != 14:
        raise JuntaFetchError(
            "O dossiê não tem CNPJ da empresa-alvo — preencha a identificação "
            "antes de buscar na JUCESP."
        )

    triggered_by = f"dossie:{dossier_id}"

    try:
        # 1. Ficha completa (QSA oficial + arquivamentos) — também persiste.
        ficha = await fetch_junta_ficha(
            db, tenant_id=tenant_id, cnpj=cnpj, triggered_by=triggered_by
        )
        if not ficha.found or ficha.fields is None:
            raise JuntaFetchError(
                "Empresa não encontrada na JUCESP "
                f"({ficha.message or 'sem resultados'}). A empresa é registrada "
                "em SP?"
            )
        if ficha.fields_json:
            await _persist_junta_data(
                db,
                tenant_id=tenant_id,
                dossier_id=dossier_id,
                fields_json=ficha.fields_json,
                raw_id=ficha.raw_id,
                adapter_version=ficha.adapter_version,
            )

        nire = _digits(ficha.fields.nire)
        if not nire:
            raise JuntaFetchError(
                "A ficha da JUCESP veio sem NIRE — sem como localizar os "
                "documentos arquivados."
            )

        # 2. Documentos digitalizados arquivados.
        lista = await fetch_junta_lista_documentos(
            db, tenant_id=tenant_id, nire=nire, triggered_by=triggered_by
        )
        if not lista.found:
            raise JuntaFetchError(
                "Nenhum documento digitalizado arquivado na JUCESP para o "
                f"NIRE {nire}."
            )
        alvo = _pick_latest_societario(lista.documentos)
        if alvo is None:
            raise JuntaFetchError(
                "A JUCESP listou documentos, mas nenhum com número de registro "
                "utilizável para download."
            )
        registro = _registro_of(alvo) or ""

        # 3. Download da cópia digitalizada.
        download = await fetch_junta_documento(
            db,
            tenant_id=tenant_id,
            nire=nire,
            registro=registro,
            triggered_by=triggered_by,
        )
    except InfosimplesAdapterError as e:
        # Mensagem do adapter já é voltada ao operador (credencial ausente,
        # vendor fora do ar etc.) — repassa sem stack.
        raise JuntaFetchError(str(e)) from e

    descricao = str(alvo.get("descricao") or "documento societario").strip()
    safe_desc = re.sub(r"[^A-Za-z0-9_-]+", "_", descricao)[:60].strip("_")
    filename = f"JUCESP_{nire}_{registro}_{safe_desc or 'documento'}.pdf"

    # 4. Vira documento do dossiê + extração multimodal (mesmo fluxo do upload).
    document = await create_document(
        db,
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        doc_type=DocumentType.SOCIAL_CONTRACT,
        filename=filename,
        mime_type=download.mime_type or "application/pdf",
        body=download.content,
        uploaded_by=initiated_by,
    )
    document = await process_document(
        db,
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        document=document,
        initiated_by=initiated_by,
    )
    return document


# ─── Gate de seleção (opção B) — duas fases ──────────────────────────────────
# A busca em UMA chamada (`fetch_social_contract_from_junta`, auto-pick) continua
# servindo o botão manual "Buscar na JUCESP". O GATE (analista escolhe o doc na
# lista) usa as duas funções abaixo: prepara as opções (sem custo de download)
# e, depois da escolha, baixa só o registro escolhido.


@dataclass(slots=True)
class SocialContractOptions:
    """Resultado da fase de SELEÇÃO (lista-dcs) do gate JUCESP."""

    found_company: bool
    message: str
    nire: str | None
    documentos: list[dict[str, Any]]  # arquivamentos crus (p/ auto-pick legado)
    options: list[dict[str, Any]]  # build_document_options (p/ a lista da UI)


async def prepare_social_contract_options(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
) -> SocialContractOptions:
    """Fase 1 do gate: ficha (persiste QSA + NIRE) + lista de documentos
    arquivados → opções pro analista escolher. NÃO baixa nada (sem custo de
    download-dc). `found_company=False` quando a empresa não está na JUCESP /
    sem NIRE — aí o fluxo cai no upload manual (aresta found==false).
    """
    from app.modules.credito.services.dossier import get_dossier
    from app.modules.integracoes.adapters.data.infosimples.errors import (
        InfosimplesAdapterError,
    )

    dossier = await get_dossier(db, tenant_id=tenant_id, dossier_id=dossier_id)
    if dossier is None:
        raise JuntaFetchError("Dossiê não encontrado.")
    cnpj = _digits(dossier.target_cnpj)
    if len(cnpj) != 14:
        raise JuntaFetchError(
            "O dossiê não tem CNPJ da empresa-alvo — preencha a identificação "
            "antes de buscar na JUCESP."
        )
    triggered_by = f"dossie:{dossier_id}"

    try:
        ficha = await fetch_junta_ficha(
            db, tenant_id=tenant_id, cnpj=cnpj, triggered_by=triggered_by
        )
        if not ficha.found or ficha.fields is None:
            return SocialContractOptions(
                found_company=False,
                message=(
                    "Empresa não encontrada na JUCESP "
                    f"({ficha.message or 'sem resultados'}). A empresa é registrada em SP?"
                ),
                nire=None,
                documentos=[],
                options=[],
            )
        if ficha.fields_json:
            await _persist_junta_data(
                db,
                tenant_id=tenant_id,
                dossier_id=dossier_id,
                fields_json=ficha.fields_json,
                raw_id=ficha.raw_id,
                adapter_version=ficha.adapter_version,
            )
        nire = _digits(ficha.fields.nire)
        if not nire:
            return SocialContractOptions(
                found_company=False,
                message=(
                    "A ficha da JUCESP veio sem NIRE — sem como localizar os "
                    "documentos arquivados."
                ),
                nire=None,
                documentos=[],
                options=[],
            )
        lista = await fetch_junta_lista_documentos(
            db, tenant_id=tenant_id, nire=nire, triggered_by=triggered_by
        )
        documentos = list(lista.documentos) if lista.found else []
    except InfosimplesAdapterError as e:
        # Infra (credencial, vendor fora do ar) → erro de negócio repassado.
        raise JuntaFetchError(str(e)) from e

    return SocialContractOptions(
        found_company=True,
        message=(
            ""
            if documentos
            else f"Nenhum documento digitalizado arquivado na JUCESP para o NIRE {nire}."
        ),
        nire=nire,
        documentos=documentos,
        options=build_document_options(documentos),
    )


async def download_social_contract_by_registro(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    nire: str,
    registro: str,
    descricao: str = "documento societario",
    initiated_by: UUID | None = None,
) -> CreditDossierDocument:
    """Fase 2 do gate: baixa a cópia digitalizada do registro ESCOLHIDO e anexa
    ao dossiê (extração multimodal no mesmo fluxo de conferência do upload).
    """
    from app.modules.credito.services.document import (
        create_document,
        process_document,
    )
    from app.modules.integracoes.adapters.data.infosimples.errors import (
        InfosimplesAdapterError,
    )

    try:
        download = await fetch_junta_documento(
            db,
            tenant_id=tenant_id,
            nire=nire,
            registro=registro,
            triggered_by=f"dossie:{dossier_id}",
        )
    except InfosimplesAdapterError as e:
        raise JuntaFetchError(str(e)) from e

    safe_desc = re.sub(r"[^A-Za-z0-9_-]+", "_", str(descricao))[:60].strip("_")
    filename = f"JUCESP_{nire}_{registro}_{safe_desc or 'documento'}.pdf"

    document = await create_document(
        db,
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        doc_type=DocumentType.SOCIAL_CONTRACT,
        filename=filename,
        mime_type=download.mime_type or "application/pdf",
        body=download.content,
        uploaded_by=initiated_by,
    )
    return await process_document(
        db,
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        document=document,
        initiated_by=initiated_by,
    )
