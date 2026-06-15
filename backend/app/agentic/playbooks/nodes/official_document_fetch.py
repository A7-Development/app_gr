"""OfficialDocumentFetchNode — busca documento oficial direto da fonte publica.

Diferente do `cadastral_enrichment` (output = DADO no silver), o output deste
node e um DOCUMENTO anexado ao dossie + extracao multimodal — mesmo fluxo de
conferencia do upload manual. O analista nao precisa clicar em nada: o grafo
executa a busca sozinho.

Config schema:
    {
        "document": "social_contract_jucesp"   # receita do documento oficial
    }

Cada receita e uma CADEIA curada de 1..N datasets do catalogo de Provedores
de Dados (decisao de produto 2026-06-11): o usuario escolhe o DOCUMENTO, nao
os datasets crus. Receita unica hoje:

    social_contract_jucesp — Contrato social · JUCESP:
        ficha completa (QSA oficial -> junta_data) -> documento societario
        mais recente -> download do PDF -> credit_dossier_document
        (SOCIAL_CONTRACT) -> extracao multimodal.

`found=False` (empresa nao registrada em SP / sem documentos arquivados) NAO
e erro — o node conclui e o downstream ve a ausencia (`message` explica).
Falha de infra (credencial, vendor fora do ar) levanta excecao — engine marca
FAILED e o operador reprocessa.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.playbooks.nodes._base import (
    BaseNode,
    NodeContext,
    NodeOutput,
    VarType,
)

# Receitas disponiveis — chave estavel usada em `config.document`. Adicionar
# receita = entrada aqui + branch em `execute()` (a cadeia em si vive no
# service de dominio, ex.: credito/services/junta.py).
RECIPES: dict[str, str] = {
    "social_contract_jucesp": "Contrato social · JUCESP (Junta Comercial SP)",
}

_DEFAULT_RECIPE = "social_contract_jucesp"


class OfficialDocumentFetchNode(BaseNode):
    """Busca documento oficial na fonte publica e anexa ao dossie."""

    type = "official_document_fetch"

    def validate_config(self) -> None:
        document = self.config.get("document", _DEFAULT_RECIPE)
        if document not in RECIPES:
            raise ValueError(
                f"official_document_fetch: receita desconhecida {document!r}. "
                f"Disponiveis: {sorted(RECIPES)}"
            )
        mode = self.config.get("mode", "auto")
        if mode not in ("auto", "select"):
            raise ValueError(
                f"official_document_fetch: mode {mode!r} invalido "
                "(use 'auto' = auto-pick, ou 'select' = gate de selecao)."
            )

    def produces(self) -> dict[str, VarType]:
        return {
            "found": VarType.BOOLEAN,
            "document_id": VarType.STRING,
            "filename": VarType.STRING,
            "doc_type": VarType.STRING,
            "message": VarType.STRING,
        }

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        # Late imports: evita ciclo (nodes -> credito service -> workflow public).
        from sqlalchemy import desc, select

        from app.core.enums import DocumentType
        from app.modules.credito.models.document import CreditDossierDocument
        from app.modules.credito.services.junta import (
            JuntaFetchError,
            download_social_contract_by_registro,
            fetch_social_contract_from_junta,
            prepare_social_contract_options,
        )
        from app.modules.integracoes.adapters.data.infosimples.errors import (
            InfosimplesAdapterError,
        )

        document = self.config.get("document") or _DEFAULT_RECIPE

        dossier_id_raw = ctx.trigger_data.get("dossier_id")
        if not dossier_id_raw:
            raise RuntimeError(
                "official_document_fetch: trigger_data sem dossier_id — "
                "node so roda dentro de um dossie de credito."
            )

        # GATE DE HOMOLOGACAO (2026-06-12, decisao de produto): a estacao NAO
        # fecha sozinha. Apos anexar+extrair, o node PAUSA ate o analista
        # homologar a conferencia (PATCH extraction -> validated, que tambem
        # retoma o run). Tambem torna o node idempotente: re-execucao no
        # resume NAO re-consulta a JUCESP (custo + 2min) — le o documento que
        # ja esta no dossie (vindo desta busca OU de upload manual paralelo).
        existing = (
            await db.execute(
                select(CreditDossierDocument)
                .where(
                    CreditDossierDocument.tenant_id == ctx.tenant_id,
                    CreditDossierDocument.dossier_id == UUID(str(dossier_id_raw)),
                    CreditDossierDocument.doc_type == DocumentType.SOCIAL_CONTRACT,
                )
                .order_by(desc(CreditDossierDocument.uploaded_at))
                .limit(1)
            )
        ).scalar_one_or_none()
        if existing is not None and existing.extraction_status == "validated":
            return NodeOutput(
                data={
                    "found": True,
                    "document_id": str(existing.id),
                    "filename": existing.original_filename,
                    "doc_type": existing.doc_type.value,
                    "message": "",
                },
                status_hint="conferência homologada pelo analista",
            )
        if existing is not None and existing.extraction_status in (
            "success",
            "processing",
        ):
            return NodeOutput(
                data={
                    "found": True,
                    "document_id": str(existing.id),
                    "filename": existing.original_filename,
                    "doc_type": existing.doc_type.value,
                    "message": "Aguardando o analista homologar a conferência da extração.",
                },
                should_pause=True,
                status_hint="aguardando homologação da conferência",
            )

        # ── GATE DE SELECAO (opcao B, 2026-06-15) ────────────────────────────
        # `mode="select"`: em vez do auto-pick silencioso, o analista escolhe o
        # documento na lista. Fase 1 (pending=None): lista-dcs -> opcoes (PAUSA,
        # sem custo de download). Fase 2 (resume com a escolha): baixa SO o
        # registro escolhido -> cai no mesmo gate de homologacao. `mode="auto"`
        # (default) preserva o auto-pick — o botao manual "Buscar na JUCESP"
        # (api/document.py) continua via fetch_social_contract_from_junta.
        mode = self.config.get("mode", "auto")
        if mode == "select":
            entry = ctx.previous_outputs.get(ctx.node_id, {})
            pending = entry.get("pending_input")
            target = UUID(str(dossier_id_raw))
            if pending is None:
                # FASE 1 — consulta a lista (sem baixar).
                try:
                    prep = await prepare_social_contract_options(
                        db, tenant_id=ctx.tenant_id, dossier_id=target
                    )
                except JuntaFetchError as e:
                    if isinstance(e.__cause__, InfosimplesAdapterError):
                        raise RuntimeError(
                            f"official_document_fetch[{document}]: {e}"
                        ) from e
                    return NodeOutput(
                        data={
                            "found": False,
                            "document_id": "",
                            "filename": "",
                            "doc_type": "",
                            "message": str(e),
                            "options": [],
                        },
                        status_hint="documento nao localizado na fonte",
                    )
                if not prep.found_company or not prep.options:
                    # Sem empresa / sem doc digitalizado -> upload manual
                    # (a aresta found==false roteia pro document_request).
                    return NodeOutput(
                        data={
                            "found": False,
                            "document_id": "",
                            "filename": "",
                            "doc_type": "social_contract",
                            "message": prep.message,
                            "options": [],
                        },
                        status_hint="nada para escolher — anexar manualmente",
                    )
                return NodeOutput(
                    data={
                        "phase": "select",
                        "doc_type": "social_contract",
                        "nire": prep.nire,
                        "options": prep.options,
                    },
                    should_pause=True,
                    status_hint=(
                        f"escolha o documento societario ({len(prep.options)} arquivados)"
                    ),
                )
            # FASE 2 — resume com a escolha.
            action = str(pending.get("action") or "").lower()
            registro = str(pending.get("registro") or "").strip()
            if action == "manual" or not registro:
                return NodeOutput(
                    data={
                        "found": False,
                        "document_id": "",
                        "filename": "",
                        "doc_type": "social_contract",
                        "message": "Analista optou por anexar o documento manualmente.",
                        "options": [],
                    },
                    status_hint="analista vai anexar manualmente",
                )
            nire = str((entry.get("output") or {}).get("nire") or "")
            try:
                doc = await download_social_contract_by_registro(
                    db,
                    tenant_id=ctx.tenant_id,
                    dossier_id=target,
                    nire=nire,
                    registro=registro,
                    descricao=str(pending.get("descricao") or "documento societario"),
                )
            except JuntaFetchError as e:
                if isinstance(e.__cause__, InfosimplesAdapterError):
                    raise RuntimeError(
                        f"official_document_fetch[{document}]: {e}"
                    ) from e
                return NodeOutput(
                    data={
                        "found": False,
                        "document_id": "",
                        "filename": "",
                        "doc_type": "social_contract",
                        "message": str(e),
                        "options": [],
                    },
                    status_hint="falha ao baixar o documento escolhido",
                )
            return NodeOutput(
                data={
                    "found": True,
                    "document_id": str(doc.id),
                    "filename": doc.original_filename,
                    "doc_type": doc.doc_type.value,
                    "message": "Aguardando o analista homologar a conferência da extração.",
                },
                should_pause=True,
                status_hint=(
                    f"documento anexado: {doc.original_filename[:48]} — aguardando homologação"
                ),
            )

        # ── AUTO mode (default/legacy): auto-pick silencioso ─────────────────
        # Receita unica hoje; branch explicito pra proxima receita nao virar if-cego.
        assert document == "social_contract_jucesp"
        try:
            doc = await fetch_social_contract_from_junta(
                db,
                tenant_id=ctx.tenant_id,
                dossier_id=UUID(str(dossier_id_raw)),
                initiated_by=None,
            )
        except JuntaFetchError as e:
            # Infra (credencial ausente, vendor fora do ar) -> FAILED,
            # operador reprocessa. Ausencia de dado (empresa nao registrada
            # em SP, sem documentos arquivados) -> found=False, fluxo segue.
            if isinstance(e.__cause__, InfosimplesAdapterError):
                raise RuntimeError(f"official_document_fetch[{document}]: {e}") from e
            return NodeOutput(
                data={
                    "found": False,
                    "document_id": "",
                    "filename": "",
                    "doc_type": "",
                    "message": str(e),
                },
                status_hint="documento nao localizado na fonte",
            )

        # Documento anexado + extraido — PAUSA pro analista conferir e
        # homologar (gate). A homologacao retoma o run e a re-execucao cai
        # no branch "validated" acima, completando com found=true.
        return NodeOutput(
            data={
                "found": True,
                "document_id": str(doc.id),
                "filename": doc.original_filename,
                "doc_type": doc.doc_type.value,
                "message": "Aguardando o analista homologar a conferência da extração.",
            },
            should_pause=True,
            status_hint=f"documento anexado: {doc.original_filename[:48]} — aguardando homologação",
        )
