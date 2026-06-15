"""Dossier service — CRUD + lifecycle binding to the workflow engine."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.playbooks.models.definition import PlaybookDefinition
from app.agentic.playbooks.models.run import PlaybookRun, PlaybookRunStep
from app.agentic.playbooks.services import engine as workflow_engine
from app.core.database import AsyncSessionLocal
from app.core.enums import (
    CompanyRole,
    DossierStatus,
    NodeRunStatus,
    OpinionRecommendation,
    PersonRole,
    PlaybookRunStatus,
)
from app.modules.credito.models.analysis import CreditDossierAnalysis
from app.modules.credito.models.company import CreditDossierCompany
from app.modules.credito.models.dossier import CreditDossier
from app.modules.credito.models.opinion import CreditDossierOpinion
from app.modules.credito.models.person import CreditDossierPerson
from app.modules.credito.models.red_flag import CreditDossierRedFlag

logger = logging.getLogger(__name__)

# Referencias fortes das tasks de fundo (1b) — sem isto o GC pode coletar uma
# task ainda em execucao. add_done_callback remove ao terminar.
_BG_RESUME_TASKS: set[asyncio.Task[None]] = set()


def spawn_resume_execution(
    *, run_id: UUID, dossier_id: UUID, tenant_id: UUID
) -> None:
    """Dispara a execucao do grafo em BACKGROUND (§1b).

    O submit do dossie chama `prepare_resume` (marca RUNNING) + commit e ENTAO
    isto — retornando na hora, sem bloquear 1-2 min na consulta JUCESP/agente.
    O polling de 3s do cockpit mostra o progresso (node RUNNING -> feedback ao
    vivo). A task usa sessao PROPRIA (a da request fecha ao responder) e tem
    guard que marca FAILED se algo estourar (nunca fica RUNNING pra sempre).
    """
    task = asyncio.create_task(
        _resume_execution_bg(
            run_id=run_id, dossier_id=dossier_id, tenant_id=tenant_id
        )
    )
    _BG_RESUME_TASKS.add(task)
    task.add_done_callback(_BG_RESUME_TASKS.discard)


async def _resume_execution_bg(
    *, run_id: UUID, dossier_id: UUID, tenant_id: UUID
) -> None:
    try:
        async with AsyncSessionLocal() as db:
            # _execute_run nao levanta em falha de node (seta FAILED e retorna);
            # o commit aqui persiste PAUSED/COMPLETED/FAILED + o status do dossie.
            await workflow_engine.execute_paused_run(db, run_id=run_id)
            dossier = await get_dossier(
                db, tenant_id=tenant_id, dossier_id=dossier_id
            )
            if dossier is not None:
                await sync_status_from_workflow(db, dossier=dossier)
            await db.commit()
    except Exception:
        # Erro inesperado (sessao/conexao/bug) — garante que o run nao fica
        # preso em RUNNING. Sessao limpa pra escrever o FAILED.
        logger.exception("resume em background falhou: run=%s", run_id)
        try:
            async with AsyncSessionLocal() as db:
                run = (
                    await db.execute(
                        select(PlaybookRun).where(PlaybookRun.id == run_id)
                    )
                ).scalar_one_or_none()
                if run is not None and run.status == PlaybookRunStatus.RUNNING:
                    run.status = PlaybookRunStatus.FAILED
                    run.error_detail = (
                        "Falha inesperada ao executar a etapa em background."
                    )
                    run.completed_at = datetime.now(UTC)
                    dossier = await get_dossier(
                        db, tenant_id=tenant_id, dossier_id=dossier_id
                    )
                    if dossier is not None:
                        await sync_status_from_workflow(db, dossier=dossier)
                    await db.commit()
        except Exception:
            logger.exception(
                "resume em background: falha ao marcar FAILED run=%s", run_id
            )


class DossierServiceError(RuntimeError):
    """Domain-level dossier error."""


async def create_dossier(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    workflow_definition_id: UUID,
    target_cnpj: str | None = None,
    target_name: str | None = None,
    analyst_id: UUID | None = None,
    operation_type: str | None = None,
    requested_amount: Any | None = None,
    requested_term_days: int | None = None,
    notes: str | None = None,
) -> CreditDossier:
    """Create a dossier and start its workflow run.

    A identidade da entidade analisada (target_cnpj/target_name) e opcional:
    em fluxos PF/PJ que coletam doc via human_input, o motor ira popular
    esses campos retroativamente via `absorb_identity_from_human_input`.
    Em fluxos sem identidade (simulacao, analise de produto), permanecem
    nulos.

    O dossier e o workflow run sao criados na mesma transacao. O caller
    se responsabiliza pelo commit.
    """
    dossier = CreditDossier(
        tenant_id=tenant_id,
        target_cnpj=target_cnpj,
        target_name=target_name,
        workflow_definition_id=workflow_definition_id,
        analyst_id=analyst_id,
        operation_type=operation_type,
        requested_amount=requested_amount,
        requested_term_days=requested_term_days,
        notes=notes,
        status=DossierStatus.DRAFT,
    )
    db.add(dossier)
    await db.flush()

    # Código humano único (DC-AAAA-NNNN) — sequence global, ano da criação.
    seq = await db.scalar(text("SELECT nextval('credit_dossier_code_seq')"))
    dossier.code = f"DC-{datetime.now(UTC).year}-{int(seq):04d}"
    await db.flush()

    # Trigger data minimo (2026-06-12): o CONTRATO do gatilho e so
    # dossier_id + trigger_kind (ver TriggerNode.produces). target_cnpj/
    # target_name seguem aqui como payload INTERNO (cabecalho de contexto
    # dos agentes em runtime) — nao sao variaveis publicadas; CNPJ entra
    # pelo formulario de Identificacao e vive na empresa-alvo do dossie.
    trigger_data: dict[str, Any] = {"dossier_id": str(dossier.id)}
    if target_cnpj:
        trigger_data["target_cnpj"] = target_cnpj
    if target_name:
        trigger_data["target_name"] = target_name

    run = await workflow_engine.start_run(
        db,
        tenant_id=tenant_id,
        definition_id=workflow_definition_id,
        trigger_type="manual",
        trigger_data=trigger_data,
        initiated_by=analyst_id,
    )

    dossier.workflow_run_id = run.id
    dossier.status = _status_from_run(run)
    await db.flush()
    # Refresh to populate server-defaults (`created_at`, `updated_at`) that
    # were generated by Postgres on INSERT but are not yet on the Python
    # object. Without this, accessing `dossier.updated_at` after commit (e.g.
    # via Pydantic `model_validate`) triggers a lazy refresh which fails in
    # async context with MissingGreenlet.
    await db.refresh(dossier)
    return dossier


async def get_dossier(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> CreditDossier | None:
    return (
        await db.execute(
            select(CreditDossier).where(
                CreditDossier.tenant_id == tenant_id,
                CreditDossier.id == dossier_id,
            )
        )
    ).scalar_one_or_none()


async def delete_dossier(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> bool:
    """Hard-delete a dossier and its bound workflow run.

    Cascades:
    - All `credit_dossier_*` child tables (analysis, attachments, notes,
      links, bureau_query, document, financial, opinion, person, pleito,
      red_flag, check) are FK'd with `ondelete=CASCADE` and disappear.
    - The bound `workflow_run` is deleted explicitly here (not FK'd back
      from dossier->run with cascade); its `workflow_node_run` children
      cascade off the run delete.

    Returns True if a dossier was deleted, False if not found (404 in API).
    """
    dossier = await get_dossier(db, tenant_id=tenant_id, dossier_id=dossier_id)
    if dossier is None:
        return False

    workflow_run_id = dossier.workflow_run_id

    await db.delete(dossier)
    await db.flush()

    if workflow_run_id is not None:
        run = (
            await db.execute(
                select(PlaybookRun).where(PlaybookRun.id == workflow_run_id)
            )
        ).scalar_one_or_none()
        if run is not None:
            await db.delete(run)
            await db.flush()

    return True


async def list_dossiers(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    status: DossierStatus | None = None,
    analyst_id: UUID | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[CreditDossier]:
    query = select(CreditDossier).where(CreditDossier.tenant_id == tenant_id)
    if status is not None:
        query = query.where(CreditDossier.status == status)
    if analyst_id is not None:
        query = query.where(CreditDossier.analyst_id == analyst_id)
    query = query.order_by(CreditDossier.created_at.desc()).limit(limit).offset(offset)
    return list((await db.execute(query)).scalars().all())


async def sync_status_from_workflow(
    db: AsyncSession,
    *,
    dossier: CreditDossier,
) -> CreditDossier:
    """Update `dossier.status` based on the bound workflow run.

    Called after every workflow event that may have transitioned the run.
    """
    if dossier.workflow_run_id is None:
        return dossier
    run = (
        await db.execute(
            select(PlaybookRun).where(PlaybookRun.id == dossier.workflow_run_id)
        )
    ).scalar_one_or_none()
    if run is None:
        return dossier
    dossier.status = _status_from_run(run)
    if run.status == PlaybookRunStatus.COMPLETED and dossier.finalized_at is None:
        dossier.finalized_at = run.completed_at
    await db.flush()
    return dossier


_IDENTITY_KEYS_CNPJ = {"cnpj", "target_cnpj"}
_IDENTITY_KEYS_CPF = {"cpf", "target_cpf"}
_IDENTITY_KEYS_NAME = {
    "razao_social",
    "target_name",
    "nome",
    "nome_completo",
    "name",
}


def _digits(s: str) -> str:
    """Strip mask characters from a doc string."""
    return "".join(ch for ch in s if ch.isdigit())


async def absorb_identity_from_human_input(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    submitted: dict[str, Any],
) -> None:
    """Populate target_cnpj/target_name on the dossier when a human_input
    submitted a document (cnpj/cpf) or a label.

    Idempotent: only writes when the dossier still has the field NULL OR
    the submitted value is non-empty and different from the current. This
    lets the analyst correct a previously-typed CNPJ in a later step.

    Called by the resume endpoint right after `engine.resume_run` flushes
    the human_input output.
    """
    if not submitted:
        return

    dossier = await get_dossier(db, tenant_id=tenant_id, dossier_id=dossier_id)
    if dossier is None:
        return

    # Documento — prioriza CNPJ; cai pra CPF.
    new_doc: str | None = None
    for key, value in submitted.items():
        if not isinstance(value, str) or not value.strip():
            continue
        lk = key.lower()
        if lk in _IDENTITY_KEYS_CNPJ:
            digits = _digits(value)
            if len(digits) == 14:
                new_doc = digits
                break
        elif lk in _IDENTITY_KEYS_CPF:
            digits = _digits(value)
            if len(digits) == 11:
                new_doc = digits
                # nao quebra: se vier CNPJ depois, prevalece (cnpj > cpf)

    if new_doc and new_doc != (dossier.target_cnpj or ""):
        dossier.target_cnpj = new_doc

    # Label/nome.
    for key, value in submitted.items():
        if not isinstance(value, str) or not value.strip():
            continue
        if key.lower() in _IDENTITY_KEYS_NAME:
            stripped = value.strip()
            if stripped != (dossier.target_name or ""):
                dossier.target_name = stripped[:255]
            break

    await db.flush()


# ─── Graph persistence (handoff esteira-credito §3) ─────────────────────────
#
# Persiste o "grafo de entrada societario" coletado por nodes human_input:
# empresa-alvo (role TARGET) + coligadas (GROUP_MEMBER) + socios (PARTNER com
# %participacao). Antes desta camada o dado morria no output do node.

_GRAPH_TARGET_CNPJ_KEYS = {"cnpj", "target_cnpj"}
_GRAPH_NAME_KEYS = {"razao_social", "target_name", "nome", "name"}
_GRAPH_FOUNDING_KEYS = {"data_fundacao", "founding_date", "data_constituicao", "fundacao"}
_GRAPH_SOCIOS_KEYS = {"socios", "partners", "quadro_societario"}
_GRAPH_COLIGADAS_KEYS = {"outros_cnpjs", "coligadas", "group_cnpjs"}

_SOCIO_NAME_KEYS = ("nome", "name", "razao_social")
_SOCIO_CPF_KEYS = ("cpf", "documento", "doc")
_SOCIO_PCT_KEYS = ("participacao_pct", "ownership_pct", "participacao", "percentual", "pct")
_COLIGADA_CNPJ_KEYS = ("cnpj", "documento", "doc")
_COLIGADA_NAME_KEYS = ("nome", "name", "razao_social")


def _pick(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Case-insensitive lookup of the first matching key in a dict."""
    lowered = {k.lower(): v for k, v in d.items()}
    for k in keys:
        if k in lowered:
            return lowered[k]
    return None


def _first_str(submitted: dict[str, Any], keys: set[str]) -> str | None:
    for k, v in submitted.items():
        if k.lower() in keys and isinstance(v, str) and v.strip():
            return v.strip()
    return None


def _first_list(submitted: dict[str, Any], keys: set[str]) -> list | None:
    for k, v in submitted.items():
        if k.lower() in keys and isinstance(v, list):
            return v
    return None


def _parse_date_loose(value: str | None) -> date | None:
    """Parse YYYY-MM-DD (ISO) or DD/MM/YYYY into a date; None if unparseable."""
    if not isinstance(value, str) or not value.strip():
        return None
    s = value.strip()
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        pass
    parts = s.replace("-", "/").split("/")
    if len(parts) == 3 and 1 <= len(parts[0]) <= 2:
        try:
            d_, m_, y_ = int(parts[0]), int(parts[1]), int(parts[2])
            return date(y_, m_, d_)
        except ValueError:
            return None
    return None


def _parse_pct(value: Any) -> Decimal | None:
    """Parse an ownership percentage: accepts 40, 40.5, '40,5', '40%'."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return None
    if isinstance(value, str):
        s = value.strip().rstrip("%").strip().replace(",", ".")
        if not s:
            return None
        try:
            return Decimal(s)
        except (InvalidOperation, ValueError):
            return None
    return None


async def absorb_graph_from_human_input(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    submitted: dict[str, Any],
) -> None:
    """Persist the entry societary graph (target company + group + partners).

    Scans the human_input `submitted` dict for company / partner keys and
    writes `credit_dossier_company` (TARGET + GROUP_MEMBER) and
    `credit_dossier_person` (PARTNER with ownership_pct). No-op when the form
    carried no graph-related fields, so it can run on every submit (like
    `absorb_identity_from_human_input`).

    Idempotent: re-submitting re-syncs — the partner set for the target is
    replaced, the target company is updated in place.
    """
    if not submitted:
        return

    raw_cnpj = _first_str(submitted, _GRAPH_TARGET_CNPJ_KEYS)
    target_cnpj: str | None = None
    if raw_cnpj:
        digits = _digits(raw_cnpj)
        if len(digits) == 14:
            target_cnpj = digits
    name = _first_str(submitted, _GRAPH_NAME_KEYS)
    founding = _parse_date_loose(_first_str(submitted, _GRAPH_FOUNDING_KEYS))
    socios = _first_list(submitted, _GRAPH_SOCIOS_KEYS)
    coligadas = _first_list(submitted, _GRAPH_COLIGADAS_KEYS)

    if not (target_cnpj or name or founding or socios or coligadas):
        return

    # ── Empresa-alvo (TARGET) — upsert (1 por dossie) ───────────────────
    target = (
        await db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == tenant_id,
                CreditDossierCompany.dossier_id == dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()

    if target is None and target_cnpj:
        dossier = await get_dossier(db, tenant_id=tenant_id, dossier_id=dossier_id)
        fallback_name = name or (dossier.target_name if dossier else None) or target_cnpj
        target = CreditDossierCompany(
            tenant_id=tenant_id,
            dossier_id=dossier_id,
            cnpj=target_cnpj,
            name=fallback_name[:255],
            role=CompanyRole.TARGET,
            founding_date=founding,
        )
        db.add(target)
    elif target is not None:
        if target_cnpj:
            target.cnpj = target_cnpj
        if name:
            target.name = name[:255]
        if founding is not None:
            target.founding_date = founding
    await db.flush()

    company_cnpj = target.cnpj if target is not None else target_cnpj

    # ── Socios (PARTNER) — replace set p/ idempotencia ──────────────────
    if socios is not None and company_cnpj is not None:
        await db.execute(
            delete(CreditDossierPerson).where(
                CreditDossierPerson.tenant_id == tenant_id,
                CreditDossierPerson.dossier_id == dossier_id,
                CreditDossierPerson.role == PersonRole.PARTNER,
                CreditDossierPerson.company_cnpj == company_cnpj,
            )
        )
        for item in socios:
            if not isinstance(item, dict):
                continue
            snome = _pick(item, _SOCIO_NAME_KEYS)
            if not isinstance(snome, str) or not snome.strip():
                continue
            cpf_red: str | None = None
            scpf = _pick(item, _SOCIO_CPF_KEYS)
            if isinstance(scpf, str):
                cd = _digits(scpf)
                if cd:
                    cpf_red = cd[-4:]
            db.add(
                CreditDossierPerson(
                    tenant_id=tenant_id,
                    dossier_id=dossier_id,
                    name=snome.strip()[:255],
                    role=PersonRole.PARTNER,
                    company_cnpj=company_cnpj,
                    cpf_redacted=cpf_red,
                    ownership_pct=_parse_pct(_pick(item, _SOCIO_PCT_KEYS)),
                )
            )
        await db.flush()

    # ── Coligadas (GROUP_MEMBER) — upsert (sem docs, lente de risco) ────
    if coligadas:
        for item in coligadas:
            ccnpj: str | None = None
            cname: str | None = None
            if isinstance(item, str):
                cd = _digits(item)
                if len(cd) == 14:
                    ccnpj = cd
            elif isinstance(item, dict):
                rawc = _pick(item, _COLIGADA_CNPJ_KEYS)
                if isinstance(rawc, str):
                    cd = _digits(rawc)
                    if len(cd) == 14:
                        ccnpj = cd
                cn = _pick(item, _COLIGADA_NAME_KEYS)
                if isinstance(cn, str) and cn.strip():
                    cname = cn.strip()
            if ccnpj is None:
                continue
            exists = (
                await db.execute(
                    select(CreditDossierCompany).where(
                        CreditDossierCompany.tenant_id == tenant_id,
                        CreditDossierCompany.dossier_id == dossier_id,
                        CreditDossierCompany.cnpj == ccnpj,
                        CreditDossierCompany.role == CompanyRole.GROUP_MEMBER,
                    )
                )
            ).scalar_one_or_none()
            if exists is None:
                db.add(
                    CreditDossierCompany(
                        tenant_id=tenant_id,
                        dossier_id=dossier_id,
                        cnpj=ccnpj,
                        name=(cname or ccnpj)[:255],
                        role=CompanyRole.GROUP_MEMBER,
                    )
                )
        await db.flush()


async def save_bureau_analysis(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    subsection: str,
    summary: str,
    indicators: dict[str, Any],
    raw_data: dict[str, Any],
    source_meta: dict[str, Any],
) -> CreditDossierAnalysis:
    """Persist a bureau query result into the dossier so agents can read it.

    Writes one `CreditDossierAnalysis` row with section='bureau_queries'. The
    payload follows the same shape that `read_dossier_section` exposes back to
    agent tools, plus a `raw_data` block with a trimmed dump of the silver
    tables (top sócios / restrições / etc.) and a `source_meta` block carrying
    provenance (consulta_id, raw_id, adapter version).

    `subsection` distinguishes multiple bureaus saved into the same section
    ('serasa_pj', 'bigdatacorp', 'infosimples', ...). Stored inside
    `ai_analysis.subsection` since the table has no native column for it.
    """
    analysis = CreditDossierAnalysis(
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        section="bureau_queries",
        ai_analysis={
            "subsection": subsection,
            "summary": summary,
            "indicators": indicators,
            "raw_data": raw_data,
            "source_meta": source_meta,
        },
    )
    db.add(analysis)
    await db.flush()
    return analysis


async def create_opinion(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    executive_summary: str,
    recommendation: OpinionRecommendation,
    strengths: list[str],
    concerns: list[str],
    conditions: list[str],
    ai_draft: str | None,
    analyst_id: UUID | None,
) -> CreditDossierOpinion:
    """Create a new (current) opinion version for the dossier.

    Demotes any previous current opinion and bumps the version. The analyst's
    edited text lands in `analyst_final` + `executive_summary`; `ai_draft`
    keeps the deterministic draft assembled from flags/gate (audit trail).
    """
    await db.execute(
        update(CreditDossierOpinion)
        .where(
            CreditDossierOpinion.tenant_id == tenant_id,
            CreditDossierOpinion.dossier_id == dossier_id,
            CreditDossierOpinion.is_current.is_(True),
        )
        .values(is_current=False)
    )
    max_version = (
        await db.execute(
            select(func.max(CreditDossierOpinion.version)).where(
                CreditDossierOpinion.tenant_id == tenant_id,
                CreditDossierOpinion.dossier_id == dossier_id,
            )
        )
    ).scalar()
    opinion = CreditDossierOpinion(
        tenant_id=tenant_id,
        dossier_id=dossier_id,
        version=(max_version or 0) + 1,
        is_current=True,
        executive_summary=executive_summary,
        strengths=strengths,
        concerns=concerns,
        recommendation=recommendation,
        conditions=conditions,
        ai_draft=ai_draft,
        analyst_final=executive_summary,
        signed_by=analyst_id,
        signed_at=datetime.now(UTC),
    )
    db.add(opinion)
    await db.flush()
    return opinion


def _downstream_nodes(graph: dict[str, Any], node_id: str) -> set[str]:
    """All nodes reachable downstream of `node_id` via edges (exclusive)."""
    edges = (graph or {}).get("edges") or []
    adjacency: dict[str, list[str]] = {}
    for e in edges:
        src = e.get("source")
        tgt = e.get("target")
        if src and tgt:
            adjacency.setdefault(src, []).append(tgt)
    seen: set[str] = set()
    stack: list[str] = list(adjacency.get(node_id, []))
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(adjacency.get(n, []))
    return seen


async def rerun_node(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    node_id: str,
) -> None:
    """Re-execute a node (and everything downstream of it).

    Deletes the target node's run + all downstream node runs (so they are no
    longer "settled" and re-execute), removes the red_flags those runs raised
    (avoid duplicates), resets the run to RUNNING, and resumes. Decision_log
    entries are append-only and preserved (audit trail). Used after the
    analyst edits inputs / re-attaches a document.
    """
    dossier = await get_dossier(db, tenant_id=tenant_id, dossier_id=dossier_id)
    if dossier is None or dossier.workflow_run_id is None:
        raise DossierServiceError("Dossie sem workflow run para reprocessar.")

    wf_def = (
        await db.execute(
            select(PlaybookDefinition).where(
                PlaybookDefinition.id == dossier.workflow_definition_id
            )
        )
    ).scalar_one_or_none()
    graph = wf_def.graph if wf_def is not None else {}
    targets = _downstream_nodes(graph, node_id) | {node_id}

    run_steps = (
        await db.execute(
            select(PlaybookRunStep).where(
                PlaybookRunStep.run_id == dossier.workflow_run_id,
                PlaybookRunStep.node_id.in_(targets),
            )
        )
    ).scalars().all()

    flag_ids: list[UUID] = []
    for step in run_steps:
        for fid in (step.output_data or {}).get("flag_ids") or []:
            try:
                flag_ids.append(UUID(str(fid)))
            except (ValueError, TypeError):
                continue
    if flag_ids:
        await db.execute(
            delete(CreditDossierRedFlag).where(
                CreditDossierRedFlag.tenant_id == tenant_id,
                CreditDossierRedFlag.dossier_id == dossier_id,
                CreditDossierRedFlag.id.in_(flag_ids),
            )
        )
    for step in run_steps:
        await db.delete(step)
    await db.flush()

    run = (
        await db.execute(
            select(PlaybookRun).where(PlaybookRun.id == dossier.workflow_run_id)
        )
    ).scalar_one_or_none()
    if run is not None:
        run.status = PlaybookRunStatus.RUNNING
        run.completed_at = None
        await db.flush()

    await workflow_engine.resume_run(
        db, run_id=dossier.workflow_run_id, pending_inputs={}
    )


def _status_from_run(run: PlaybookRun) -> DossierStatus:
    """Derive DossierStatus from PlaybookRunStatus + node-level signals."""
    rs = run.status
    if rs == PlaybookRunStatus.PENDING:
        return DossierStatus.DRAFT
    if rs == PlaybookRunStatus.RUNNING:
        # Heuristic: if we're past document_request, we're analyzing; else collecting.
        return DossierStatus.ANALYZING
    if rs == PlaybookRunStatus.PAUSED:
        return DossierStatus.REVIEW
    if rs == PlaybookRunStatus.COMPLETED:
        return DossierStatus.FINALIZED
    if rs == PlaybookRunStatus.CANCELLED:
        return DossierStatus.CANCELLED
    if rs == PlaybookRunStatus.FAILED:
        return DossierStatus.REVIEW  # surfaces in UI as needing analyst intervention
    return DossierStatus.DRAFT


# ─── Listing progress enrichment ────────────────────────────────────────────


_RUNNING_NODE_TYPES = {"specialist_agent", "bureau_query", "document_extractor", "http_request"}


def _next_action_for_dossier(
    *,
    dossier: CreditDossier,
    run: PlaybookRun | None,
    node_runs: list[PlaybookRunStep],
) -> tuple[str, str, str | None]:
    """Compute (kind, label, next_node_id) for the dossier listing.

    See `NextActionKind` in schemas.dossier for the kind taxonomy.
    """
    if dossier.status == DossierStatus.FINALIZED:
        return ("finalized", "Finalizado", None)

    # Find a node currently waiting for human input.
    waiting = next(
        (nr for nr in node_runs if nr.status == NodeRunStatus.WAITING_INPUT),
        None,
    )
    if waiting is not None:
        return ("human_input", "Aguardando voce", waiting.node_id)

    # Find a node currently running.
    running = next(
        (nr for nr in node_runs if nr.status == NodeRunStatus.RUNNING),
        None,
    )
    if running is not None:
        if running.node_type in _RUNNING_NODE_TYPES:
            return ("agent_running", "Analise IA em curso", running.node_id)
        return ("agent_running", "Em execucao", running.node_id)

    # Run is paused/blocked but no waiting_input — likely transitioning.
    if run is not None and run.status == PlaybookRunStatus.PAUSED:
        return ("blocked", "Bloqueado", None)

    # All nodes completed but dossier still not finalized — needs analyst review.
    if run is not None and run.status == PlaybookRunStatus.COMPLETED:
        return ("ready_to_finalize", "Pronto para finalizar", None)

    if run is None or run.status == PlaybookRunStatus.PENDING:
        return ("blocked", "Aguardando inicio", None)

    if run.status == PlaybookRunStatus.FAILED:
        return ("blocked", "Falha — revisar", None)

    return ("blocked", "Bloqueado", None)


async def compute_progress_map(
    db: AsyncSession,
    *,
    dossiers: list[CreditDossier],
) -> dict[UUID, dict[str, Any]]:
    """Bulk-compute (completed_steps, total_steps, next_action) for many dossiers.

    Two queries regardless of N:
    - One SELECT on workflow_definition for the unique definition ids
    - One SELECT on workflow_run + workflow_node_run for the unique run ids

    Returns a dict keyed by dossier.id with the progress fields ready to be
    spread into DossierListItem.
    """
    if not dossiers:
        return {}

    def_ids = {d.workflow_definition_id for d in dossiers}
    run_ids = {d.workflow_run_id for d in dossiers if d.workflow_run_id is not None}

    # Bulk-fetch definitions (for total_steps).
    defs_by_id: dict[UUID, PlaybookDefinition] = {}
    if def_ids:
        defs_rows = (
            await db.execute(
                select(PlaybookDefinition).where(PlaybookDefinition.id.in_(def_ids))
            )
        ).scalars().all()
        defs_by_id = {d.id: d for d in defs_rows}

    # Bulk-fetch runs.
    runs_by_id: dict[UUID, PlaybookRun] = {}
    if run_ids:
        runs_rows = (
            await db.execute(
                select(PlaybookRun).where(PlaybookRun.id.in_(run_ids))
            )
        ).scalars().all()
        runs_by_id = {r.id: r for r in runs_rows}

    # Bulk-fetch node_runs grouped by run_id.
    node_runs_by_run: dict[UUID, list[PlaybookRunStep]] = {}
    if run_ids:
        nr_rows = (
            await db.execute(
                select(PlaybookRunStep)
                .where(PlaybookRunStep.run_id.in_(run_ids))
                .order_by(PlaybookRunStep.started_at.asc().nulls_last())
            )
        ).scalars().all()
        for nr in nr_rows:
            node_runs_by_run.setdefault(nr.run_id, []).append(nr)

    # Compute progress per dossier.
    out: dict[UUID, dict[str, Any]] = {}
    for d in dossiers:
        wf_def = defs_by_id.get(d.workflow_definition_id)
        total_steps = 0
        if wf_def is not None and isinstance(wf_def.graph, dict):
            nodes = wf_def.graph.get("nodes") or []
            total_steps = len(nodes)

        run = runs_by_id.get(d.workflow_run_id) if d.workflow_run_id else None
        nrs = node_runs_by_run.get(d.workflow_run_id, []) if d.workflow_run_id else []
        completed_steps = sum(1 for nr in nrs if nr.status == NodeRunStatus.COMPLETED)

        kind, label, next_node = _next_action_for_dossier(
            dossier=d, run=run, node_runs=nrs
        )

        out[d.id] = {
            "completed_steps": completed_steps,
            "total_steps": total_steps,
            "next_action_kind": kind,
            "next_action_label": label,
            "next_node_id": next_node,
        }
    return out


async def absorb_partners_from_social_contract(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    fields: dict[str, Any],
) -> None:
    """Materializa o QSA extraído do CONTRATO SOCIAL em `credit_dossier_person`.

    Chamada quando a extração do `social_contract` é HOMOLOGADA pelo analista
    (update_extraction → validated): os sócios homologados viram a verdade do
    grafo societário do dossiê (role=PARTNER, replace-set idempotente — mesma
    semântica de `absorb_graph_from_human_input`). CPF é reduzido aos 4
    últimos dígitos (LGPD); o documento original continua sendo a fonte.
    Alimenta os checks determinísticos (`ownership_sum`) e o parecer.
    """
    socios = fields.get("socios") if isinstance(fields, dict) else None
    if not isinstance(socios, list) or not socios:
        return

    # Dialeto tipado (2026-06-11): a extração traz quotas/capital por sócio,
    # não percentual — o % é aritmética DERIVADA EM CÓDIGO (nunca pelo LLM),
    # e só quando o denominador veio escrito no documento.
    capital = fields.get("capital_social")
    capital = capital if isinstance(capital, dict) else {}
    total_quotas = capital.get("total_quotas")
    capital_subscrito = capital.get("subscrito")

    def _pct_of(item: dict[str, Any]) -> Decimal | None:
        pct = _parse_pct(item.get("participacao_pct"))
        if pct is not None:
            return pct
        quotas = item.get("quotas")
        if isinstance(total_quotas, int) and total_quotas > 0 and isinstance(quotas, int):
            return Decimal(str(round(quotas / total_quotas * 100.0, 2)))
        sub_socio = item.get("capital_subscrito_socio")
        if (
            isinstance(capital_subscrito, (int, float))
            and capital_subscrito > 0
            and isinstance(sub_socio, (int, float))
        ):
            return Decimal(str(round(sub_socio / capital_subscrito * 100.0, 2)))
        return None

    target = (
        await db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == tenant_id,
                CreditDossierCompany.dossier_id == dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()
    company_cnpj = target.cnpj if target is not None else None
    if company_cnpj is None:
        dossier = await get_dossier(db, tenant_id=tenant_id, dossier_id=dossier_id)
        raw = dossier.target_cnpj if dossier else None
        digits = _digits(raw) if raw else ""
        company_cnpj = digits if len(digits) == 14 else None
    if company_cnpj is None:
        return

    await db.execute(
        delete(CreditDossierPerson).where(
            CreditDossierPerson.tenant_id == tenant_id,
            CreditDossierPerson.dossier_id == dossier_id,
            CreditDossierPerson.role == PersonRole.PARTNER,
            CreditDossierPerson.company_cnpj == company_cnpj,
        )
    )
    for item in socios:
        if not isinstance(item, dict):
            continue
        nome = item.get("nome")
        if not isinstance(nome, str) or not nome.strip():
            continue
        cpf_red: str | None = None
        # Dialeto v2 usa `cpf`; o tipado (2026-06-11) usa `cpf_cnpj`.
        raw_cpf = item.get("cpf") or item.get("cpf_cnpj")
        if isinstance(raw_cpf, str):
            cpf_digits = _digits(raw_cpf)
            if cpf_digits:
                cpf_red = cpf_digits[-4:]
        db.add(
            CreditDossierPerson(
                tenant_id=tenant_id,
                dossier_id=dossier_id,
                name=nome.strip()[:255],
                role=PersonRole.PARTNER,
                company_cnpj=company_cnpj,
                cpf_redacted=cpf_red,
                ownership_pct=_pct_of(item),
            )
        )
    await db.flush()


__all__ = [
    "DossierServiceError",
    "NodeRunStatus",
    "absorb_graph_from_human_input",
    "absorb_identity_from_human_input",
    "absorb_partners_from_social_contract",
    "compute_progress_map",
    "create_dossier",
    "create_opinion",
    "delete_dossier",
    "get_dossier",
    "list_dossiers",
    "rerun_node",
    "save_bureau_analysis",
    "sync_status_from_workflow",
]
