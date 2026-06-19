"""BureauQueryNode — consulta bureau externo (Serasa, BigDataCorp, etc).

Config schema:
    {
        "adapter": "serasa_pj" | "serasa_pf" | "bigdatacorp" | "infosimples",
        "entity_type": "company" | "person",
        "entity_ref": "<doc>" | "{{node.identificacao.output.cnpj}}",
        "environment": "production" | "sandbox",   # opcional, default production
    }

Quando o engine instancia o no, `entity_ref` ja vem RESOLVIDO (template
substituido por CNPJ literal). O adapter cuida da normalizacao (mascara
e digitos).

Adapters wired:
    - serasa_pj: Business Information Report (PJ analitico) -> raw + silver.
    - bigdatacorp: consulta multi-dataset (cadastral + societario + KYC +
      evolucao) -> raw + silver. Ambos devolvem metadados; nodes/agentes
      downstream leem o silver via read-tools (get_serasa_pj /
      get_quadro_societario / get_kyc_pj / get_evolucao_pj), nao por secao
      persistida no dossie.

Adapters ainda placeholder:
    - serasa_pf, infosimples — retornam status "em breve".

Falha de consulta (auth, rede, contrato) levanta excecao — engine marca
o `workflow_node_run` como FAILED. Operador pode reprocessar ou pular.
"""

from __future__ import annotations

import logging
import re
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.playbooks.nodes._base import (
    BaseNode,
    NodeContext,
    NodeOutput,
    Requirement,
    VarType,
)
from app.core.enums import Environment
from app.modules.integracoes.public import (
    execute_serasa_pj_query,
    fetch_bdc_dossie_pj,
)

logger = logging.getLogger(__name__)

_SUPPORTED_ADAPTERS = {"serasa_pj", "serasa_pf", "bigdatacorp", "infosimples"}
_WIRED_ADAPTERS = {"serasa_pj", "bigdatacorp"}  # demais caem no placeholder

# Mapa adapter -> tipo do documento principal de entrada.
# Usado por `requires()` para validar que o entity_ref resolve para
# um campo upstream do tipo correto.
_ADAPTER_INPUT_TYPE: dict[str, VarType] = {
    "serasa_pj": VarType.CNPJ,
    "serasa_pf": VarType.CPF,
    "bigdatacorp": VarType.CNPJ,  # usa CNPJ no MVP
    "infosimples": VarType.CNPJ,
}


class BureauQueryNode(BaseNode):
    """Bureau query — Serasa PJ wired; demais adapters placeholder."""

    type = "bureau_query"

    def validate_config(self) -> None:
        adapter = self.config.get("adapter")
        if adapter not in _SUPPORTED_ADAPTERS:
            raise ValueError(
                f"bureau_query: adapter '{adapter}' nao suportado. "
                f"Aceitos: {sorted(_SUPPORTED_ADAPTERS)}."
            )

        if adapter in _WIRED_ADAPTERS:
            entity_ref = self.config.get("entity_ref")
            if not isinstance(entity_ref, str) or not entity_ref.strip():
                raise ValueError(
                    f"bureau_query[{adapter}]: 'entity_ref' obrigatorio "
                    "(string com documento ou template `{{node.<etapa>.output.cnpj}}`)."
                )
            env = self.config.get("environment", "production")
            if env not in {"production", "sandbox"}:
                raise ValueError(
                    f"bureau_query[{adapter}]: 'environment' invalido "
                    f"(='{env}'). Use 'production' ou 'sandbox'."
                )

    def produces(self) -> dict[str, VarType]:
        """Outputs disponíveis pra nós downstream após bureau_query OK."""
        if self.config.get("adapter") == "bigdatacorp":
            return {
                "adapter": VarType.STRING,
                "status": VarType.STRING,
                "raw_id": VarType.UUID_T,
                "cnpj": VarType.CNPJ,
                "cadastral_found": VarType.BOOLEAN,
                "vinculos_count": VarType.NUMBER,
                "grupo_found": VarType.BOOLEAN,
                "kyc_subjects": VarType.NUMBER,
                "kyc_ocorrencias": VarType.NUMBER,
                "evolucao_found": VarType.BOOLEAN,
                "evolucao_meses": VarType.NUMBER,
            }
        return {
            "adapter": VarType.STRING,
            "status": VarType.STRING,
            "raw_id": VarType.UUID_T,
            "consulta_id": VarType.UUID_T,
            "cnpj": VarType.CNPJ,
            "requested_report": VarType.STRING,
            "actual_report_returned": VarType.STRING,
            "reciprocity_downgrade": VarType.BOOLEAN,
            "latency_ms": VarType.NUMBER,
            "counts": VarType.OBJECT,
        }

    def requires(self) -> list[Requirement]:
        """O entity_ref tem que resolver pra um doc do tipo certo upstream.

        Quando `entity_ref` for literal (não-template), retorna lista vazia
        — o validador entende que o doc veio hardcoded. Quando for template
        (`{{...}}`), extrai a expressão e exige tipo CNPJ/CPF conforme adapter.
        """
        adapter = self.config.get("adapter")
        if adapter not in _WIRED_ADAPTERS:
            return []
        entity_ref = self.config.get("entity_ref")
        if not isinstance(entity_ref, str):
            return []
        expected = _ADAPTER_INPUT_TYPE.get(adapter, VarType.STRING)
        # Extract the inner expression of `{{...}}` if it's a single template.
        inner = _extract_single_template(entity_ref)
        if inner is None:
            # Hardcoded value — engine accepts; nothing to validate semantically.
            return []
        label = "CPF" if expected == VarType.CPF else "CNPJ"
        return [
            Requirement(
                name=f"{label} (entity_ref)",
                type=expected,
                expr=inner,
                optional=False,
            )
        ]

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        adapter = self.config["adapter"]

        if adapter == "serasa_pj":
            return await self._execute_serasa_pj(ctx, db)

        if adapter == "bigdatacorp":
            return await self._execute_bigdatacorp(ctx, db)

        # Adapters ainda nao wired.
        return NodeOutput(
            data={
                "adapter": adapter,
                "status": "not_implemented",
                "message": (
                    f"Adapter '{adapter}' ainda nao implementado. "
                    "Sera ligado em onda futura."
                ),
            },
            status_hint="em breve",
        )

    async def _execute_serasa_pj(
        self, ctx: NodeContext, db: AsyncSession
    ) -> NodeOutput:
        """Dispara consulta Serasa PJ e devolve metadados pra downstream.

        Output expoe `consulta_id`/`cnpj` — nodes seguintes (agentes
        especialistas, regras de risco) leem o silver via a read-tool
        `get_serasa_pj` (silver-first, §13.2.1). A consulta ja materializou
        o silver (`wh_serasa_pj_*`); nao persistimos resumo no dossie.
        """
        cnpj = self.config["entity_ref"]
        environment = Environment(self.config.get("environment", "production"))

        summary = await execute_serasa_pj_query(
            tenant_id=ctx.tenant_id,
            cnpj=cnpj,
            triggered_by=f"workflow_run:{ctx.run_id}",
            environment=environment,
        )

        if not summary["ok"]:
            errors = "; ".join(summary.get("errors", []))
            raise RuntimeError(
                f"bureau_query[serasa_pj]: consulta nao concluiu — {errors}"
            )

        return NodeOutput(
            data={
                "adapter": "serasa_pj",
                "status": "ok",
                "raw_id": str(summary["raw_id"]),
                "consulta_id": str(summary["consulta_id"]),
                "cnpj": summary["cnpj"],
                "requested_report": summary["requested_report"],
                "actual_report_returned": summary["actual_report_returned"],
                "reciprocity_downgrade": summary["reciprocity_downgrade"],
                "latency_ms": summary["latency_ms"],
                "counts": summary["counts"],
            },
        )

    async def _execute_bigdatacorp(
        self, ctx: NodeContext, db: AsyncSession
    ) -> NodeOutput:
        """Consulta multi-dataset BDC (cadastral + societario + KYC).

        Uma chamada -> popula wh_pj_cadastro + wh_pj_vinculo +
        wh_pj_grupo_indicador + wh_pj_kyc(+_ocorrencia). Os outputs expoem os
        contadores; nodes/agentes downstream leem o silver via tool/secao.
        """
        cnpj = self.config["entity_ref"]
        result = await fetch_bdc_dossie_pj(
            tenant_id=ctx.tenant_id,
            cnpj=cnpj,
            triggered_by=f"workflow_run:{ctx.run_id}",
        )
        if not result.ok:
            raise RuntimeError(
                "bureau_query[bigdatacorp]: consulta nao concluiu — "
                + "; ".join(result.errors)
            )

        # Ponte cadastral: a consulta ja materializou o silver (wh_pj_cadastro),
        # mas o card + a read-tool do agente leem `credit_dossier_company`. Sem o
        # node `cadastral_enrichment` no grafo, a empresa-alvo ficava vazia e a
        # analise cadastral via nulo. Enriquece a partir do silver/raw JA buscado
        # (sem nova consulta paga). Best-effort: nao falha a consulta se nao aplicar.
        dossier_id_raw = ctx.trigger_data.get("dossier_id")
        if result.found and result.cadastral_found and dossier_id_raw:
            try:
                from app.modules.credito.services.cadastral import (
                    enrich_target_from_pj_silver,
                )

                await enrich_target_from_pj_silver(
                    db,
                    tenant_id=ctx.tenant_id,
                    dossier_id=UUID(str(dossier_id_raw)),
                )
            except Exception:
                logger.warning(
                    "bureau_query[bigdatacorp]: enrich_target_from_pj_silver falhou "
                    "(consulta OK, segue sem bloquear)",
                    exc_info=True,
                )

        return NodeOutput(
            data={
                "adapter": "bigdatacorp",
                "status": "ok" if result.found else "not_found",
                "raw_id": str(result.raw_id) if result.raw_id else None,
                "cnpj": result.cnpj,
                "cadastral_found": result.cadastral_found,
                "vinculos_count": result.vinculos_count,
                "grupo_found": result.grupo_found,
                "kyc_subjects": result.kyc_subjects,
                "kyc_ocorrencias": result.kyc_ocorrencias,
                "evolucao_found": result.evolucao_found,
                "evolucao_meses": result.evolucao_meses,
            },
        )


_TEMPLATE_FULL_RE = re.compile(r"^\s*\{\{\s*([^}]+?)\s*\}\}\s*$")


def _extract_single_template(value: str) -> str | None:
    """If `value` is exactly `{{path}}` (one template, nothing else), return
    the inner path. Otherwise None.

    Used by `requires()` to know when an entity_ref points to upstream data
    vs being a hardcoded literal. Mixed content (`prefix {{x}}`) is NOT
    treated as a single template — falls back to None and we don't try to
    statically validate.
    """
    m = _TEMPLATE_FULL_RE.match(value)
    return m.group(1).strip() if m else None
