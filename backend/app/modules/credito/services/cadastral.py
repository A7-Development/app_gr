"""Enriquecimento cadastral da empresa-alvo do dossie (silver).

Orquestra o caminho A2 do gate de elegibilidade: pega a empresa-alvo
(TARGET) do dossie, dispara a consulta cadastral externa via o contrato
publico de `integracoes` (white-label — public_code neutro, vendor nunca
exposto) e materializa o resultado nas colunas SILVER de
`credit_dossier_company`. Os checks do gate (`company_status_active`,
`cnae_permitido`, `company_founding_age`) leem essas colunas — nunca o
raw (§13.2.1).

Boundary §11.3: o modulo credito chama integracoes APENAS por `public.py`
(`fetch_cadastral_pj`). A bronze (wh_bdc_raw_consulta) e escrita la dentro;
aqui so escrevemos o silver canonico do dominio credito.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import CompanyRole
from app.modules.credito.models.company import CreditDossierCompany
from app.modules.integracoes.public import (
    CadastralQueryResult,
    fetch_cadastral_pj,
)

logger = logging.getLogger("gr.credito.cadastral")


@dataclass(frozen=True)
class CadastralEnrichmentOutcome:
    """Resultado do enriquecimento — alimenta o trace do node + UI."""

    ok: bool
    found: bool
    cnpj: str | None
    company_id: UUID | None
    raw_id: UUID | None
    # Campos silver efetivamente aplicados (nomes da coluna). Vazio quando
    # found=False ou erro.
    applied: list[str]
    errors: list[str]


def _bdc_text(value: Any) -> str | None:
    """Normaliza campo BDC para string.

    O BDC as vezes devolve um campo como OBJETO em vez de string — ex.:
    `LegalNature` = {"Code": "2062", "Activity": "SOCIEDADE EMPRESARIA LIMITADA"}.
    Renderizar esse objeto cru na UI quebra o React (#31 — objeto como filho).
    Extrai a descricao textual; None quando vazio/ausente.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        for key in ("Activity", "Description", "Name", "Text", "Value", "Label"):
            v = value.get(key)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None
    return str(value)


async def load_cadastral_silver_view(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> dict | None:
    """Monta a visão tenant-facing dos dados cadastrais coletados (WHITE-LABEL).

    Lê o silver da empresa-alvo (`credit_dossier_company`) e serializa SEM
    qualquer identidade de vendor — nenhum `provider_*`, nenhum `_public_code`/
    `_adapter_version` de `receita_data`. Os valores cadastrais são dado da
    própria empresa do tenant; o que nunca vaza é QUEM forneceu. Fonte única do
    card da tela E da read-tool do agente cadastral.

    Princípio (governança 2026-06-06, Ricardo): o dev/agente NUNCA decide quais
    campos do dataset importam. `dados_completos` carrega o `basic_data` INTEIRO
    (nada descartado). O resumo no topo é só conveniência de leitura (campos
    silver validados); todo o resto vai em `dados_completos` pra render genérico.
    A curadoria de relevância (rótulos/ordem/visibilidade) é do usuário, via
    catálogo (fase seguinte).

    Returns:
        Dict tenant-facing, ou None quando não há empresa-alvo no dossie.
    """
    target = (
        await db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == tenant_id,
                CreditDossierCompany.dossier_id == dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()

    if target is None:
        return None

    basic = {}
    if isinstance(target.receita_data, dict):
        b = target.receita_data.get("basic_data")
        if isinstance(b, dict):
            basic = b

    # `enriquecido` = a fonte externa já populou o silver (não só o cadastro).
    enriquecido = bool(
        target.tax_status or target.cnaes or target.capital_social is not None
    )

    return {
        "encontrado": True,
        "enriquecido": enriquecido,
        # ── Resumo (campos silver validados — só conveniência de leitura) ──
        "cnpj": target.cnpj,
        "razao_social": _bdc_text(basic.get("OfficialName")) or target.name,
        "situacao_cadastral": target.tax_status,
        "data_fundacao": (
            target.founding_date.isoformat() if target.founding_date else None
        ),
        "capital_social": (
            float(target.capital_social)
            if target.capital_social is not None
            else None
        ),
        # ── TUDO: o basic_data inteiro, sem o dev escolher (render genérico) ──
        # Nada é descartado. Curadoria de rótulo/ordem/visibilidade = usuário,
        # via catálogo (fase seguinte). White-label preservado: só o basic_data
        # (dado da empresa), nunca o wrapper com _public_code/_adapter_version.
        "dados_completos": basic,
    }


def _pretty_label(path: str) -> str:
    """Rótulo neutro a partir do field_path (último segmento humanizado)."""
    import re

    seg = path.replace("[]", "").split(".")[-1]
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", seg).replace("_", " ").strip()
    return spaced[:1].upper() + spaced[1:] if spaced else path


def _display_value(v: Any) -> Any:
    """Coage valor para display-safe (objeto->texto; lista->lista coerida)."""
    if v is None:
        return None
    if isinstance(v, list):
        out = [_display_value(x) for x in v]
        out = [x for x in out if x is not None and x != ""]
        return out or None
    if isinstance(v, dict):
        return _bdc_text(v)
    return v


async def build_cadastral_card_projection(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> dict | None:
    """Projeção do card cadastral DIRIGIDA PELO CONTRATO (Fase 2).

    Lê o contrato ativo (bdc/empresas/basic_data) e projeta o `basic_data` da
    empresa-alvo em `campos` (só os `on_screen`, com rótulo pt-BR, categoria e
    ordem do contrato) + detecta CAMPOS NOVOS (presentes no payload mas fora do
    contrato) marcados `novo=True` (🆕) — alimentam a curadoria. Sem contrato
    ativo: cai no genérico (todos os campos como novos, rótulo prettificado).

    Returns None quando não há empresa-alvo no dossie.
    """
    from app.shared.data_providers.contract_resolver import resolve_contract
    from app.shared.data_providers.field_paths import (
        extract_by_path,
        flatten_paths,
    )

    target = (
        await db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == tenant_id,
                CreditDossierCompany.dossier_id == dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()
    if target is None:
        return None

    basic: dict = {}
    if isinstance(target.receita_data, dict):
        b = target.receita_data.get("basic_data")
        if isinstance(b, dict):
            basic = b

    enriquecido = bool(
        target.tax_status or target.cnaes or target.capital_social is not None
    )
    summary = {
        "encontrado": True,
        "enriquecido": enriquecido,
        "cnpj": target.cnpj,
        "razao_social": _bdc_text(basic.get("OfficialName")) or target.name,
        "situacao_cadastral": target.tax_status,
        "data_fundacao": (
            target.founding_date.isoformat() if target.founding_date else None
        ),
        "capital_social": (
            float(target.capital_social)
            if target.capital_social is not None
            else None
        ),
    }

    rc = await resolve_contract(
        db, provider="bdc", api_endpoint="empresas", dataset_code="basic_data"
    )

    campos: list[dict] = []
    presentes = flatten_paths(basic)

    if rc is not None:
        catalogados: set[str] = set()
        for f in rc.for_screen():
            catalogados.add(f.field_path)
            campos.append(
                {
                    "field_path": f.field_path,
                    "label": f.public_label or _pretty_label(f.field_path),
                    "categoria": f.categoria_ui or "outros",
                    "ordem": f.screen_order if f.screen_order is not None else 1000,
                    "tipo": f.semantic_type,
                    "valor": _display_value(extract_by_path(basic, f.field_path)),
                    "novo": False,
                }
            )
        # os campos do contrato (mesmo os não-on_screen) já são "conhecidos"
        catalogados |= rc.field_paths()
        novos = sorted(presentes - catalogados)
    else:
        # Sem contrato: tudo é novo (comportamento genérico, prettificado).
        novos = sorted(presentes)

    for path in novos:
        campos.append(
            {
                "field_path": path,
                "label": _pretty_label(path),
                "categoria": "novos",
                "ordem": 9000,
                "tipo": "text",
                "valor": _display_value(extract_by_path(basic, path)),
                "novo": True,
            }
        )

    return {
        **summary,
        "campos": campos,
        "campos_novos_count": len(novos),
        "tem_contrato": rc is not None,
    }


async def build_cadastral_agent_view(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> dict | None:
    """Visão cadastral PARA O AGENTE, dirigida pelo contrato (Fase 3).

    Em vez de despejar o `basic_data` cru (`dados_completos`), entrega só os
    campos marcados `to_agent` no contrato, cada um com **termo canônico** +
    rótulo pt-BR + **descrição** (glossário) + valor. É o que desacopla o agente
    do vendor: ele raciocina em conceitos canônicos (CNPJ, Situação cadastral),
    não em `TaxIdNumber`. Ver central-de-dados-arquitetura.md §4/§5.

    Sem contrato ativo: cai no resumo silver mínimo (conservador).
    Returns None quando não há empresa-alvo no dossie.
    """
    from app.shared.data_providers.contract_resolver import resolve_contract
    from app.shared.data_providers.field_paths import extract_by_path
    from app.shared.data_providers.models.termo_canonico import TermoCanonico

    target = (
        await db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == tenant_id,
                CreditDossierCompany.dossier_id == dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()
    if target is None:
        return None

    basic: dict = {}
    if isinstance(target.receita_data, dict):
        b = target.receita_data.get("basic_data")
        if isinstance(b, dict):
            basic = b

    base = {
        "encontrado": True,
        "cnpj": target.cnpj,
        "razao_social": _bdc_text(basic.get("OfficialName")) or target.name,
    }

    rc = await resolve_contract(
        db, provider="bdc", api_endpoint="empresas", dataset_code="basic_data"
    )
    if rc is None:
        # Sem contrato: resumo silver mínimo.
        base["campos"] = []
        base["tem_contrato"] = False
        return base

    # Mapa termo_id -> (codigo, descricao) para enriquecer cada campo.
    termo_ids = [f.termo_canonico_id for f in rc.fields if f.termo_canonico_id]
    termo_map: dict[UUID, tuple[str, str | None]] = {}
    if termo_ids:
        rows = (
            await db.execute(
                select(
                    TermoCanonico.id,
                    TermoCanonico.codigo,
                    TermoCanonico.descricao,
                ).where(TermoCanonico.id.in_(termo_ids))
            )
        ).all()
        termo_map = {tid: (cod, desc) for tid, cod, desc in rows}

    campos: list[dict] = []
    for f in rc.for_agent():
        termo_cod, termo_desc = termo_map.get(f.termo_canonico_id, (None, None))
        campos.append(
            {
                "termo": termo_cod,
                "campo": f.public_label or _pretty_label(f.field_path),
                "descricao": f.description or termo_desc,
                "valor": _display_value(extract_by_path(basic, f.field_path)),
            }
        )

    base["campos"] = campos
    base["tem_contrato"] = True
    return base


async def enrich_target_cadastral(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    dossier_id: UUID,
    public_code: str = "CAD-PJ",
) -> CadastralEnrichmentOutcome:
    """Enriquece a empresa-alvo do dossie com dados cadastrais externos.

    Encontra a empresa TARGET do dossie, consulta a fonte externa e grava
    o silver (`tax_status`, `cnaes`, `capital_social`, `founding_date`,
    `receita_data`).

    `founding_date` so e sobrescrito quando estava NULL — o valor
    auto-declarado no cadastro e preservado para o cross-check
    declarado x oficial (familia 2, fatia futura). O valor oficial fica
    sempre disponivel em `receita_data.basic_data.FoundedDate`.

    NAO commita — o caller (node/endpoint) controla a transacao. Faz
    `flush()` para materializar antes dos checks lerem.

    Args:
        db: sessao do caller (mesma transacao dos checks downstream).
        tenant_id: escopo (isolamento §10).
        dossier_id: dossie cuja empresa-alvo sera enriquecida.
        public_code: codigo neutro do dataset cadastral (default "CAD-PJ").

    Returns:
        `CadastralEnrichmentOutcome`.
    """
    target = (
        await db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == tenant_id,
                CreditDossierCompany.dossier_id == dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()

    if target is None:
        # Fallback find-or-create: a empresa-alvo (TARGET) normalmente nasce em
        # absorb_graph_from_human_input no submit do cadastro. Mas o node de
        # enriquecimento NAO pode depender dessa ordem/forma — playbook custom
        # pode nao ter um cadastro com as chaves de grafo, ou o node pode rodar
        # antes. Como o dossie ja conhece o alvo (target_cnpj/target_name
        # setados na criacao OU por absorb_identity), criamos a TARGET aqui.
        # absorb_graph depois faz upsert na mesma linha (role=TARGET), sem
        # duplicar.
        from app.modules.credito.services.dossier import get_dossier

        dossier = await get_dossier(
            db, tenant_id=tenant_id, dossier_id=dossier_id
        )
        dossier_cnpj = (
            "".join(ch for ch in (dossier.target_cnpj or "") if ch.isdigit())
            if dossier
            else ""
        )
        if len(dossier_cnpj) != 14:
            return CadastralEnrichmentOutcome(
                ok=False,
                found=False,
                cnpj=(dossier.target_cnpj if dossier else None),
                company_id=None,
                raw_id=None,
                applied=[],
                errors=[
                    "dossie sem empresa-alvo: nao ha TARGET persistido nem "
                    "target_cnpj valido (14 digitos) no dossie"
                ],
            )
        target = CreditDossierCompany(
            tenant_id=tenant_id,
            dossier_id=dossier_id,
            cnpj=dossier_cnpj,
            name=(dossier.target_name or dossier_cnpj)[:255]
            if dossier
            else dossier_cnpj,
            role=CompanyRole.TARGET,
        )
        db.add(target)
        await db.flush()

    cnpj_digits = "".join(ch for ch in (target.cnpj or "") if ch.isdigit())
    if len(cnpj_digits) != 14:
        return CadastralEnrichmentOutcome(
            ok=False,
            found=False,
            cnpj=target.cnpj,
            company_id=target.id,
            raw_id=None,
            applied=[],
            errors=[f"CNPJ da empresa-alvo invalido: {target.cnpj!r}"],
        )

    result: CadastralQueryResult = await fetch_cadastral_pj(
        tenant_id=tenant_id,
        cnpj=cnpj_digits,
        triggered_by=f"dossie:{dossier_id}",
        public_code=public_code,
    )

    if not result.ok:
        return CadastralEnrichmentOutcome(
            ok=False,
            found=False,
            cnpj=cnpj_digits,
            company_id=target.id,
            raw_id=result.raw_id,
            applied=[],
            errors=list(result.errors),
        )

    if not result.found or result.fields is None:
        # CNPJ nao retornou dados — checks downstream veem "data ausente"
        # e reprovam o gate (comportamento conservador correto).
        return CadastralEnrichmentOutcome(
            ok=True,
            found=False,
            cnpj=cnpj_digits,
            company_id=target.id,
            raw_id=result.raw_id,
            applied=[],
            errors=[],
        )

    fields = result.fields
    applied: list[str] = []

    target.tax_status = fields.tax_status
    applied.append("tax_status")
    target.cnaes = fields.cnaes
    applied.append("cnaes")
    target.capital_social = fields.capital_social
    applied.append("capital_social")

    if target.founding_date is None and fields.founding_date is not None:
        target.founding_date = fields.founding_date
        applied.append("founding_date")

    # receita_data = silver bruto preservado (TaxRegime, LegalNature,
    # HistoricalData, ...) + proveniencia interna. Codigo NEUTRO (public_code)
    # — sem slug de vendor, coerente com o white-label (4c o serializer
    # tenant-facing nunca expoe provider_*).
    target.receita_data = {
        "_public_code": result.public_code,
        "_adapter_version": result.adapter_version,
        "_raw_id": str(result.raw_id) if result.raw_id else None,
        "_query_id": result.query_id,
        "basic_data": fields.basic_data,
    }
    applied.append("receita_data")

    await db.flush()

    logger.info(
        "Enriquecimento cadastral aplicado (dossie=%s, cnpj=%s, campos=%s)",
        dossier_id,
        cnpj_digits,
        applied,
    )

    return CadastralEnrichmentOutcome(
        ok=True,
        found=True,
        cnpj=cnpj_digits,
        company_id=target.id,
        raw_id=result.raw_id,
        applied=applied,
        errors=[],
    )


async def enrich_target_from_pj_silver(
    db: AsyncSession, *, tenant_id: UUID, dossier_id: UUID
) -> bool:
    """Enriquece a empresa-alvo a partir do silver `wh_pj_cadastro` JA materializado
    pelo node `bureau_query` (BDC multi-dataset) — SEM nova consulta paga.

    Existem dois pipelines cadastrais: `cadastral_enrichment` faz um fetch CAD-PJ e
    grava em `credit_dossier_company` (que o card + a read-tool do agente leem);
    `bureau_query` faz UMA consulta multi-dataset e grava o cadastral no silver
    (`wh_pj_cadastro` + raw), mas NAO toca em `credit_dossier_company`. Um playbook
    que usa `bureau_query` (sem o node `cadastral_enrichment`) ficava com a tela e o
    agente vendo nulo. Esta ponte aplica o MESMO mapeamento de
    `enrich_target_cadastral` reusando `map_basic_data` sobre o raw que ja existe,
    de modo que a unica consulta do `bureau_query` alimente tambem a leitura.

    Best-effort: o caller (bureau_query) NAO deve falhar se isto nao aplicar — a
    consulta em si ja foi bem-sucedida. Returns True quando aplicou.
    """
    from app.modules.integracoes.adapters.data.bigdatacorp.mappers.cadastral import (
        map_basic_data,
    )
    from app.warehouse.bdc_raw_consulta import BdcRawConsulta
    from app.warehouse.pj_cadastro import PjCadastro

    target = (
        await db.execute(
            select(CreditDossierCompany).where(
                CreditDossierCompany.tenant_id == tenant_id,
                CreditDossierCompany.dossier_id == dossier_id,
                CreditDossierCompany.role == CompanyRole.TARGET,
            )
        )
    ).scalar_one_or_none()
    if target is None:
        return False

    cnpj_digits = "".join(ch for ch in (target.cnpj or "") if ch.isdigit())
    if len(cnpj_digits) != 14:
        return False

    cad = (
        (
            await db.execute(
                select(PjCadastro)
                .where(
                    PjCadastro.tenant_id == tenant_id,
                    PjCadastro.cnpj == cnpj_digits,
                )
                .order_by(PjCadastro.ingested_at.desc())
            )
        )
        .scalars()
        .first()
    )
    if cad is None or cad.raw_id is None:
        return False

    raw = (
        await db.execute(
            select(BdcRawConsulta).where(BdcRawConsulta.id == cad.raw_id)
        )
    ).scalar_one_or_none()
    if raw is None or not isinstance(raw.payload, dict):
        return False

    result = map_basic_data(raw.payload)
    if not result.found or result.fields is None:
        return False

    fields = result.fields
    target.tax_status = fields.tax_status
    target.cnaes = fields.cnaes
    target.capital_social = fields.capital_social
    # founding_date só sobrescreve quando NULL — preserva o auto-declarado para o
    # cross-check declarado x oficial (espelha enrich_target_cadastral).
    if target.founding_date is None and fields.founding_date is not None:
        target.founding_date = fields.founding_date
    target.receita_data = {
        "_raw_id": str(cad.raw_id),
        "_public_code": raw.public_code,
        "basic_data": fields.basic_data,
    }
    await db.flush()
    logger.info(
        "Enriquecimento cadastral via silver BDC aplicado (dossie=%s, cnpj=%s)",
        dossier_id,
        cnpj_digits,
    )
    return True
