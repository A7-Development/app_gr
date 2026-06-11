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
        from app.modules.credito.services.junta import (
            JuntaFetchError,
            fetch_social_contract_from_junta,
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

        return NodeOutput(
            data={
                "found": True,
                "document_id": str(doc.id),
                "filename": doc.original_filename,
                "doc_type": doc.doc_type.value,
                "message": "",
            },
            status_hint=f"documento anexado: {doc.original_filename[:60]}",
        )
