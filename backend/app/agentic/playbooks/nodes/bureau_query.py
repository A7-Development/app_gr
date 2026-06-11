"""BureauQueryNode — consulta bureau externo (Serasa, BigDataCorp, etc).

Config schema:
    {
        "adapter": "serasa_pj" | "serasa_pf" | "bigdatacorp" | "infosimples",
        "entity_type": "company" | "person",
        "entity_ref": "<doc>" | "{{trigger.cnpj}}" | "{{node.X.output.target_cnpj}}",
        "environment": "production" | "sandbox",   # opcional, default production
    }

Quando o engine instancia o no, `entity_ref` ja vem RESOLVIDO (template
substituido por CNPJ literal). O adapter cuida da normalizacao (mascara
e digitos).

Adapters wired:
    - serasa_pj: consulta Business Information Report (PJ analitico),
      grava raw + silver, e devolve consulta_id pra nodes downstream
      referenciarem (ex.: agentes especialistas que leem do warehouse).

Adapters ainda placeholder:
    - serasa_pf, bigdatacorp, infosimples — retornam status "em breve".

Falha de consulta (auth, rede, contrato) levanta excecao — engine marca
o `workflow_node_run` como FAILED. Operador pode reprocessar ou pular.
"""

from __future__ import annotations

import re
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.playbooks.nodes._base import (
    BaseNode,
    NodeContext,
    NodeOutput,
    Requirement,
    VarType,
)
from app.core.enums import Environment
from app.modules.integracoes.public import execute_serasa_pj_query

_SUPPORTED_ADAPTERS = {"serasa_pj", "serasa_pf", "bigdatacorp", "infosimples"}
_WIRED_ADAPTERS = {"serasa_pj"}  # outros caem no placeholder

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
                    "(string com documento ou template `{{trigger.cnpj}}`)."
                )
            env = self.config.get("environment", "production")
            if env not in {"production", "sandbox"}:
                raise ValueError(
                    f"bureau_query[{adapter}]: 'environment' invalido "
                    f"(='{env}'). Use 'production' ou 'sandbox'."
                )

    def produces(self) -> dict[str, VarType]:
        """Outputs disponíveis pra nós downstream após bureau_query OK."""
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

        Output expoe `consulta_id` — nodes seguintes (agentes
        especialistas, regras de risco) leem do warehouse via esse id.

        Apos a query Serasa OK, persiste um resumo estruturado em
        `CreditDossierAnalysis(section='bureau_queries')` se houver
        dossier_id no trigger_data, para que os agentes especialistas
        possam ler via tool `read_dossier_section('bureau_queries')`
        sem tocar silver direto (silver-only por design — CLAUDE.md
        §13.2.1).
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

        consulta_id = UUID(str(summary["consulta_id"]))
        dossier_id_raw = ctx.trigger_data.get("dossier_id")
        if dossier_id_raw:
            await _persist_serasa_to_dossier(
                db,
                tenant_id=ctx.tenant_id,
                dossier_id=UUID(str(dossier_id_raw)),
                consulta_id=consulta_id,
                raw_id=UUID(str(summary["raw_id"])),
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


def _money(d: Decimal | None) -> float | None:
    """Decimal → float pra serializar em JSONB (Postgres aceita ambos, mas
    JSONB nativo nao tem Decimal — float e mais transparente pro agente)."""
    if d is None:
        return None
    return float(d)


async def _persist_serasa_to_dossier(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    consulta_id: UUID,
    raw_id: UUID,
) -> None:
    """Read silver and persist a structured summary into CreditDossierAnalysis.

    Reads `wh_serasa_pj_consulta` (header — score, contadores, cadastrais),
    top 5 sócios e top 10 restrições, e escreve em
    `CreditDossierAnalysis(section='bureau_queries', subsection='serasa_pj')`.
    """
    # Late imports para evitar ciclos no import tree do app.
    from app.modules.credito.services.dossier import save_bureau_analysis
    from app.warehouse.serasa_pj_consulta import SerasaPjConsulta
    from app.warehouse.serasa_pj_restricao import SerasaPjRestricao
    from app.warehouse.serasa_pj_socio import SerasaPjSocio

    consulta = (
        await db.execute(
            select(SerasaPjConsulta).where(
                SerasaPjConsulta.tenant_id == tenant_id,
                SerasaPjConsulta.id == consulta_id,
            )
        )
    ).scalar_one_or_none()
    if consulta is None:
        # Silver ainda nao gravado (race ou erro de mapper). Nao quebra
        # o workflow — agentes leem o que houver e seguem.
        return

    # Zero ocultacao (§14.6): dossie de credito mostra TODOS os socios e
    # restricoes — sem `.limit`. `qtd_socios` abaixo reflete a lista completa
    # (antes era len() de uma lista capada em 5 -> mentia quando havia mais).
    # `order_by` so define a ORDEM de apresentacao, nao corta.
    socios_rows = (
        await db.execute(
            select(SerasaPjSocio)
            .where(
                SerasaPjSocio.tenant_id == tenant_id,
                SerasaPjSocio.consulta_id == consulta_id,
            )
            .order_by(SerasaPjSocio.percentual.desc().nullslast())
        )
    ).scalars().all()

    restricoes_rows = (
        await db.execute(
            select(SerasaPjRestricao)
            .where(
                SerasaPjRestricao.tenant_id == tenant_id,
                SerasaPjRestricao.consulta_id == consulta_id,
            )
            .order_by(SerasaPjRestricao.valor.desc().nullslast())
        )
    ).scalars().all()

    indicators: dict[str, Any] = {
        "score_pj": _money(consulta.score_h4pj),
        "score_classe": consulta.score_classe,
        "score_descricao": consulta.score_descricao,
        "tem_restricao": bool(
            consulta.has_refin or consulta.has_pefin
            or consulta.has_protesto or consulta.has_cheque
        ),
        "qtd_refin": consulta.count_refin,
        "qtd_pefin": consulta.count_pefin,
        "qtd_protesto": consulta.count_protesto,
        "qtd_cheque": consulta.count_cheque,
        "valor_total_restricoes_brl": _money(consulta.valor_total_restricoes),
        "tem_falencia": consulta.has_falencias,
        "qtd_falencias": consulta.count_falencias,
        "valor_falencias_brl": _money(consulta.valor_falencias),
        "tem_acao_judicial": consulta.has_acoes_judiciais,
        "qtd_acoes_judiciais": consulta.count_acoes_judiciais,
        "valor_acoes_judiciais_brl": _money(consulta.valor_acoes_judiciais),
        "qtd_socios": len(socios_rows),
        "capital_social_brl": _money(consulta.capital_social),
        "faturamento_presumido_brl": _money(consulta.faturamento_presumido),
        "situacao_cadastral": consulta.situacao_cadastral,
        "data_constituicao": (
            consulta.data_constituicao.isoformat()
            if consulta.data_constituicao else None
        ),
        "atividade_principal_cnae": consulta.atividade_principal_cnae,
        "regime_tributario": consulta.tax_option,
        "numero_funcionarios": consulta.number_employees,
        # Conclusao DERIVADA pelo Strata (regra serasa_liminar_v1): "NADA
        # CONSTA" explicito = padrao de supressao judicial de apontamentos.
        # Quando true, os zeros acima NAO significam ficha limpa.
        "suspeita_liminar": bool(consulta.suspeita_liminar),
        "negative_summary_message": consulta.negative_summary_message,
    }

    raw_data: dict[str, Any] = {
        "cadastrais": {
            "razao_social": consulta.razao_social,
            "nome_fantasia": consulta.nome_fantasia,
            "cnpj": consulta.cnpj,
            "atividade_principal": consulta.atividade_principal_descricao,
        },
        "socios": [
            {
                "documento": s.documento,
                "documento_tipo": s.documento_tipo,
                "nome": s.nome,
                "qualificacao": s.qualificacao,
                "percentual": _money(s.percentual),
                "data_entrada": s.data_entrada.isoformat() if s.data_entrada else None,
            }
            for s in socios_rows
        ],
        "restricoes": [
            {
                "tipo": r.tipo,
                "valor_brl": _money(r.valor),
                "credor": r.credor,
                "data_ocorrencia": (
                    r.data_ocorrencia.isoformat() if r.data_ocorrencia else None
                ),
                "data_baixa": r.data_baixa.isoformat() if r.data_baixa else None,
                "detalhe": r.detalhe,
            }
            for r in restricoes_rows
        ],
    }

    summary_lines: list[str] = []
    summary_lines.append(
        f"Consulta Serasa PJ para {consulta.razao_social or consulta.cnpj} "
        f"(CNPJ {consulta.cnpj}) em "
        f"{consulta.consulted_at.strftime('%Y-%m-%d')}."
    )
    if consulta.score_h4pj is not None:
        summary_lines.append(
            f"Score H4PJ: {consulta.score_h4pj} "
            f"(classe {consulta.score_classe or 'N/A'})."
        )
    qtd_total = (
        consulta.count_refin + consulta.count_pefin
        + consulta.count_protesto + consulta.count_cheque
    )
    if qtd_total:
        summary_lines.append(
            f"{qtd_total} restricao(oes) ativa(s); valor total "
            f"R$ {_money(consulta.valor_total_restricoes) or 0:,.2f}."
        )
    elif consulta.suspeita_liminar:
        summary_lines.append(
            "ATENCAO — POSSIVEL LIMINAR (conclusao Strata, regra "
            "serasa_liminar_v1): a Serasa retornou 'NADA CONSTA' explicito, "
            "padrao de supressao JUDICIAL de apontamentos. Os zeros de "
            "restricao NAO significam ficha limpa — a empresa provavelmente "
            "obteve liminar para esconder negativos relevantes. Trate como "
            "sinal de risco elevado, nao como ausencia de risco."
        )
    else:
        summary_lines.append("Sem restricoes ativas (refin/pefin/protesto/cheque).")
    if consulta.has_acoes_judiciais:
        summary_lines.append(
            f"{consulta.count_acoes_judiciais} acao(oes) judicial(is) — "
            f"R$ {_money(consulta.valor_acoes_judiciais) or 0:,.2f}."
        )
    if consulta.has_falencias:
        summary_lines.append(
            f"{consulta.count_falencias} ocorrencia(s) de falencia/recuperacao."
        )

    source_meta: dict[str, Any] = {
        "fonte": "serasa_pj",
        "consulta_id": str(consulta_id),
        "raw_id": str(raw_id),
        "consulted_at": consulta.consulted_at.isoformat(),
        "requested_report": consulta.requested_report,
        "actual_report_returned": consulta.actual_report_returned,
        "reciprocity_downgrade": consulta.reciprocity_downgrade,
    }

    await save_bureau_analysis(
        db,
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        subsection="serasa_pj",
        summary=" ".join(summary_lines),
        indicators=indicators,
        raw_data=raw_data,
        source_meta=source_meta,
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
