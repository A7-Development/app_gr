"""System-maintainer health view of every data source / job / model.

The maintainer's single pane of glass (feedback Ricardo 2026-07-08 — "estou
sem visao da CVM"): one row per monitored item with LAST RUN + status +
FRESHNESS (is the data stale?). The freshness rule is what catches a source
that silently stopped — monitoring "ran?" is weak, "is it overdue?" is what
a maintainer needs.

Spine = `decision_log` (most jobs already write SYNC / SCORE / CALCULATION).
Items the log cannot see (federated ETL like CVM) declare a FRESHNESS PROBE
— a SQL that returns the max reference date of the ingested data — so we
detect staleness without the external ETL cooperating.

Adding a monitored item = one entry in _MONITORADOS. No schema.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class Monitorado:
    """One monitored source/job/model."""

    chave: str
    label: str
    categoria: str  # fonte_externa | job_interno | modelo | federado
    cadencia_horas: float  # frescor esperado; acima disso = atrasado
    # Ou casa por rule_or_model no decision_log...
    rule_or_model: str | None = None
    # ...ou uma sonda de frescor (SQL -> 1 coluna com a data/timestamp mais
    # recente do dado ingerido). Usado por fontes que nao logam (CVM/FDW).
    freshness_sql: str | None = None
    descricao: str = ""


# Registro declarativo — a fonte da verdade do que o mantenedor monitora.
_MONITORADOS: tuple[Monitorado, ...] = (
    Monitorado(
        "bitfin", "ERP Bitfin (sync)", "fonte_externa", 26,
        rule_or_model="bitfin_adapter",
        descricao="Espelho do ERP — cessoes, titulos, liquidacoes.",
    ),
    Monitorado(
        "bitfin_reconcile", "Bitfin — reconciler", "job_interno", 26,
        rule_or_model="bitfin_reconcile",
    ),
    Monitorado(
        "qitech", "Admin QiTech (sync)", "fonte_externa", 26,
        rule_or_model="qitech_adapter",
        descricao="Relatorios do administrador fiduciario.",
    ),
    Monitorado(
        "landing_gateway", "Landing zone — recepcao de arquivos", "fonte_externa", 26,
        rule_or_model="file_gateway",
        descricao="Gateway que recebe uploads do Strata Collector (CNAB/fiscal).",
    ),
    Monitorado(
        "cobranca_drain", "Cobranca — ingestao CNAB (drain)", "job_interno", 26,
        freshness_sql="SELECT max(started_at) FROM wh_cobranca_sync_run",
        descricao="Drena arquivos de retorno CNAB p/ o silver (event-driven).",
    ),
    Monitorado(
        "fiscal_landing", "Fiscal — ingestao NFe/CTe (drain)", "job_interno", 26,
        rule_or_model="fiscal_landing",
        descricao="Drena NFe/CTe da landing p/ o warehouse (event-driven).",
    ),
    Monitorado(
        "deteccao_scoring", "Risco — scoring de liquidacao", "modelo", 8,
        rule_or_model="liquidacao_boleto",
        descricao="Pontua as liquidacoes e consolida o risco por cedente.",
    ),
    Monitorado(
        "cedente_risco", "Risco — consolidacao de cedentes", "modelo", 8,
        rule_or_model="cedente_risco",
    ),
    Monitorado(
        "ref_bacen", "Referencia Bacen (agencias/IFs)", "fonte_externa", 24 * 40,
        rule_or_model="ref_bacen_adapter",
        descricao="Cadastro publico de agencias/instituicoes (Olinda). "
        "Mensal — HOJE MANUAL (agendamento pendente).",
    ),
    # CVM: ETL externo (repo etl-cvm, VM 26) via postgres_fdw — nao escreve no
    # nosso decision_log. Sonda de frescor sobre a competencia mais recente.
    Monitorado(
        "cvm_fidc", "CVM FIDC (federado)", "federado", 24 * 45,
        # processada_em = quando o ETL externo (repo etl-cvm, VM 26) rodou.
        freshness_sql="SELECT max(processada_em) FROM cvm_remote.competencias",
        descricao="Informes mensais CVM (dados publicos) via FDW. Ingestao "
        "por repo externo — monitorado por frescor da ultima competencia.",
    ),
)


def _status_frescor(ultima: datetime | None, cadencia_horas: float) -> str:
    if ultima is None:
        return "nunca_rodou"
    if ultima.tzinfo is None:
        ultima = ultima.replace(tzinfo=UTC)
    horas = (datetime.now(UTC) - ultima).total_seconds() / 3600
    return "atrasado" if horas > cadencia_horas else "ok"


_SEVERIDADE = {"erro": 0, "atrasado": 1, "nunca_rodou": 2, "ok": 3}


async def _ultima_do_log(db: AsyncSession, rule: str) -> dict[str, Any] | None:
    row = (
        await db.execute(
            text(
                "SELECT occurred_at, decision_type, output, explanation, triggered_by "
                "FROM decision_log WHERE rule_or_model = :rule "
                "ORDER BY occurred_at DESC LIMIT 1"
            ),
            {"rule": rule},
        )
    ).mappings().first()
    return dict(row) if row else None


def _erro_no_output(output: Any) -> bool:
    if not isinstance(output, dict):
        return False
    errs = output.get("errors")
    if errs:
        return True
    return output.get("ok") is False


def _volume(output: Any) -> int | None:
    if not isinstance(output, dict):
        return None
    for k in ("rows_ingested", "rows", "scores_gravados", "cedentes", "linhas"):
        v = output.get(k)
        if isinstance(v, int):
            return v
    return None


async def painel_saude(db: AsyncSession) -> list[dict[str, Any]]:
    """One row per monitored item, most-severe first."""
    saida: list[dict[str, Any]] = []
    for m in _MONITORADOS:
        item: dict[str, Any] = {
            "chave": m.chave,
            "label": m.label,
            "categoria": m.categoria,
            "descricao": m.descricao,
            "cadencia_horas": m.cadencia_horas,
            "ultima_execucao": None,
            "status": "nunca_rodou",
            "detalhe": None,
            "volume": None,
            "disparado_por": None,
        }
        if m.rule_or_model:
            log = await _ultima_do_log(db, m.rule_or_model)
            if log:
                ultima = log["occurred_at"]
                erro = _erro_no_output(log["output"])
                item.update(
                    ultima_execucao=ultima.isoformat() if ultima else None,
                    status="erro" if erro else _status_frescor(ultima, m.cadencia_horas),
                    detalhe=log.get("explanation"),
                    volume=_volume(log["output"]),
                    disparado_por=log.get("triggered_by"),
                )
        elif m.freshness_sql:
            try:
                ref = (await db.execute(text(m.freshness_sql))).scalar_one_or_none()
                # A sonda pode devolver date ou datetime.
                if isinstance(ref, datetime):
                    ref_dt: datetime | None = (
                        ref if ref.tzinfo else ref.replace(tzinfo=UTC)
                    )
                elif ref is not None:
                    ref_dt = datetime(ref.year, ref.month, ref.day, tzinfo=UTC)
                else:
                    ref_dt = None
                item.update(
                    ultima_execucao=ref.isoformat() if ref is not None else None,
                    status=_status_frescor(ref_dt, m.cadencia_horas),
                    detalhe=f"dado mais recente: {ref}" if ref else "sonda sem retorno",
                )
            except Exception as exc:
                item.update(status="erro", detalhe=f"sonda falhou: {exc}")

        saida.append(item)

    saida.sort(key=lambda x: (_SEVERIDADE.get(x["status"], 9), x["label"]))
    return saida
