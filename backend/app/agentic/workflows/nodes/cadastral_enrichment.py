"""CadastralEnrichmentNode — enriquece a empresa-alvo via public_code (white-label).

Diferente do `bureau_query` (que e VENDOR-keyed via `adapter`), este node e
TENANT-FACING e referencia um `public_code` NEUTRO (ex.: "CAD-PJ"). A
resolucao public_code -> vendor + dataset + credencial acontece em runtime,
dentro de `integracoes` — o vendor NUNCA aparece na config nem no output
(decisao white-label 2026-06-04, §13/§19).

Config schema:
    {
        "public_code": "CAD-PJ"   # codigo neutro do dataset cadastral (default CAD-PJ)
    }

Fluxo: le `dossier_id` do trigger_data, chama
`credito.cadastral.enrich_target_cadastral(public_code=...)`, que consulta a
fonte, grava BRONZE + SILVER (tax_status/cnaes/capital_social/founding_date em
credit_dossier_company) e devolve o outcome. Os checks do gate A2
(company_status_active, cnae_permitido, company_founding_age) leem esse silver
depois (silver-only, §13.2.1).

found=False (CNPJ sem dados) NAO e erro — o node conclui e os checks
downstream veem "data ausente" e reprovam (conservador). Falha de
resolucao/credencial/rede levanta excecao (engine marca FAILED, operador
reprocessa).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.workflows.nodes._base import (
    BaseNode,
    NodeContext,
    NodeOutput,
    VarType,
)

_DEFAULT_PUBLIC_CODE = "CAD-PJ"


class CadastralEnrichmentNode(BaseNode):
    """Enriquecimento cadastral da empresa-alvo via public_code neutro."""

    type = "cadastral_enrichment"

    def validate_config(self) -> None:
        public_code = self.config.get("public_code", _DEFAULT_PUBLIC_CODE)
        if not isinstance(public_code, str) or not public_code.strip():
            raise ValueError(
                "cadastral_enrichment: 'public_code' deve ser uma string nao-vazia "
                f"(ex.: '{_DEFAULT_PUBLIC_CODE}')."
            )

    def produces(self) -> dict[str, VarType]:
        return {
            "status": VarType.STRING,
            "found": VarType.BOOLEAN,
            "cnpj": VarType.CNPJ,
            "public_code": VarType.STRING,
            "applied": VarType.LIST,
        }

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        # Late import: evita ciclo no import tree (nodes -> credito service).
        from app.modules.credito.services.cadastral import enrich_target_cadastral

        public_code = (
            self.config.get("public_code") or _DEFAULT_PUBLIC_CODE
        ).strip()

        dossier_id_raw = ctx.trigger_data.get("dossier_id")
        if not dossier_id_raw:
            raise RuntimeError(
                "cadastral_enrichment: trigger_data sem dossier_id — "
                "node so roda dentro de um dossie de credito."
            )

        outcome = await enrich_target_cadastral(
            db,
            tenant_id=ctx.tenant_id,
            dossier_id=UUID(str(dossier_id_raw)),
            public_code=public_code,
        )

        if not outcome.ok:
            errors = "; ".join(outcome.errors) or "erro desconhecido"
            raise RuntimeError(f"cadastral_enrichment[{public_code}]: {errors}")

        status_hint = (
            f"enriquecido ({len(outcome.applied)} campos)"
            if outcome.found
            else "CNPJ sem dados na fonte"
        )

        return NodeOutput(
            data={
                "status": "ok",
                "found": outcome.found,
                "cnpj": outcome.cnpj,
                "public_code": public_code,
                "applied": outcome.applied,
            },
            status_hint=status_hint,
        )
