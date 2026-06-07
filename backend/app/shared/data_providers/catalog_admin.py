"""Catálogo de datasets (nível MANTENEDOR) — Fase F (a fundação / tronco).

Navega `provedor_dados_dataset` (o que cada provedor oferece: API/endpoint →
dataset) e expõe a curadoria no nível do DATASET — antes de descer pros campos
(que é o Contrato, Fase 5).

O que esta camada faz:

    - `list_catalog`: árvore Provedor → API/endpoint → Dataset, com o estado do
      Contrato de cada dataset (ligado por `public_code`) + sugestões de nome.
    - `suggest_naming`: deriva um rascunho de `public_code` + nome pt-BR do
      código do vendor (decisão 14.8 — auto-sugere, mantenedor aprova).
    - `update_dataset_curation`: grava a camada A7 de `provedor_dados_dataset`
      (public_code, nome, categoria, habilitar, markup) — preservada entre syncs.
    - `create_contract_for_dataset`: cria a 1ª versão do Contrato de um dataset,
      pré-populada por `flatten_paths()` sobre um payload real quando houver
      (decisão 14.9). Idempotente: se já existe contrato pro `public_code`,
      devolve a referência em vez de duplicar.

Ponte Catálogo ↔ Contrato = `public_code` (decisão 1). A tupla de identidade do
contrato (provider/api_endpoint/dataset_code) é bookkeeping interno; o catálogo
nunca a reconstrói das próprias colunas — ele linka por `public_code` e, ao abrir
um contrato, usa a tupla guardada na linha do contrato.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.data_providers.field_paths import flatten_paths
from app.shared.data_providers.models.contract import (
    DatasetContract,
    DatasetContractActive,
)
from app.shared.data_providers.models.dataset import DataProviderDataset
from app.shared.data_providers.models.field import DatasetField

# Wrapper keys do payload BDC que não são dados do dataset em si.
_BDC_WRAPPER_KEYS = {"MatchKeys", "Datasets", "QueryId", "ElapsedMilliseconds"}

_VERSION_SUFFIX = re.compile(r"_v\d+$", re.IGNORECASE)


# ─── Sugestão de nome (decisão 14.8) ─────────────────────────────────────────


def suggest_naming(
    *, provider_dataset_code: str, provider_query_name: str | None
) -> tuple[str, str]:
    """Rascunho mecânico de (public_code, display_name) a partir do vendor.

    Best-effort — o mantenedor refina. Ex.: `ondemand_rf_qsa` →
    (`ONDEMAND-RF-QSA`, "Ondemand Rf Qsa").
    """
    base = (provider_query_name or provider_dataset_code or "").strip()
    base = _VERSION_SUFFIX.sub("", base)
    tokens = re.split(r"[_\s\-]+", base) if base else []
    tokens = [t for t in tokens if t]
    public_code = "-".join(t.upper() for t in tokens) if tokens else "DATASET"
    display_name = " ".join(t[:1].upper() + t[1:].lower() for t in tokens) if tokens else base
    return public_code, display_name


# ─── Árvore do catálogo ──────────────────────────────────────────────────────


@dataclass(frozen=True)
class CatalogContractRef:
    """Estado do Contrato de campos de um dataset (ligado por public_code)."""

    status: str  # "active" | "none"
    version: int | None
    provider: str | None
    api_endpoint: str | None
    dataset_code: str | None
    n_campos: int | None
    n_novos: int | None  # reservado p/ futuro; None por ora


@dataclass(frozen=True)
class CatalogDatasetRow:
    dataset_id: UUID
    provider_slug: str
    provider_api: str
    provider_dataset_code: str
    provider_query_name: str | None
    public_code: str | None
    display_name_pt_br: str | None
    categoria_ui: str | None
    enabled_for_sale: bool
    current_cost_brl: float | None
    markup_pct: float | None
    mode: str  # "marketplace" | "adapter" (global = revenda; ver §15.1)
    suggested_public_code: str
    suggested_name: str
    contract: CatalogContractRef


@dataclass(frozen=True)
class CatalogApiGroup:
    api: str
    total: int
    datasets: list[CatalogDatasetRow]


@dataclass(frozen=True)
class CatalogProviderGroup:
    provider_slug: str
    provider_name: str
    total: int
    enabled_count: int
    with_contract_count: int
    apis: list[CatalogApiGroup]


def _as_float(v: Decimal | None) -> float | None:
    return float(v) if v is not None else None


def _provider_mode(slug: str) -> str:
    """Modo de revenda global do provedor (§15.1). BYOC por tenant é futuro."""
    # BDC = sempre marketplace. Adapters (QiTech/Bitfin) entram na Fase 6 como
    # 'adapter'. Default conservador: marketplace (mostra custo/markup).
    return "adapter" if slug.upper() in {"QITECH", "BITFIN"} else "marketplace"


async def _active_contracts_by_public_code(
    db: AsyncSession,
) -> dict[str, tuple[DatasetContract, int]]:
    """Mapa public_code → (contrato ativo global, n_campos)."""
    rows = (
        await db.execute(
            select(DatasetContract)
            .join(
                DatasetContractActive,
                DatasetContractActive.active_contract_id == DatasetContract.id,
            )
            .where(DatasetContractActive.tenant_id.is_(None))
        )
    ).scalars().all()
    out: dict[str, tuple[DatasetContract, int]] = {}
    for c in rows:
        if not c.public_code:
            continue
        n = len(
            (
                await db.execute(
                    select(DatasetField.id).where(DatasetField.contract_id == c.id)
                )
            ).all()
        )
        out[c.public_code] = (c, n)
    return out


async def list_catalog(
    db: AsyncSession,
    *,
    provider_slug: str | None = None,
    search: str | None = None,
    only_enabled: bool = False,
    only_without_contract: bool = False,
) -> list[CatalogProviderGroup]:
    """Árvore Provedor → API → Dataset com estado de contrato + sugestões."""
    contracts = await _active_contracts_by_public_code(db)

    # Mapa provider_id → (slug, name) — evita join frágil por string.
    prov_rows = (
        await db.execute(text("SELECT id, slug, name FROM provedor_dados"))
    ).all()
    providers: dict[Any, tuple[str, str]] = {
        r[0]: (r[1], r[2] or r[1]) for r in prov_rows
    }

    datasets = (
        await db.execute(select(DataProviderDataset))
    ).scalars().all()

    needle = (search or "").strip().lower()

    # Agrupa por provedor → api.
    by_provider: dict[str, dict[str, Any]] = {}
    for ds in datasets:
        slug, name = providers.get(ds.provider_id, ("UNKNOWN", "UNKNOWN"))
        if provider_slug and slug != provider_slug:
            continue
        if only_enabled and not ds.enabled_for_sale:
            continue

        pc = ds.public_code
        cref_data = contracts.get(pc) if pc else None
        has_contract = cref_data is not None
        if only_without_contract and has_contract:
            continue

        if needle:
            hay = " ".join(
                str(x or "").lower()
                for x in (
                    ds.provider_dataset_code,
                    ds.provider_query_name,
                    ds.public_code,
                    ds.display_name_pt_br,
                    ds.categoria_ui,
                )
            )
            if needle not in hay:
                continue

        sug_pc, sug_name = suggest_naming(
            provider_dataset_code=ds.provider_dataset_code,
            provider_query_name=ds.provider_query_name,
        )

        if has_contract:
            c, n_campos = cref_data
            cref = CatalogContractRef(
                status="active",
                version=c.version,
                provider=c.provider,
                api_endpoint=c.api_endpoint,
                dataset_code=c.dataset_code,
                n_campos=n_campos,
                n_novos=None,
            )
        else:
            cref = CatalogContractRef(
                status="none",
                version=None,
                provider=None,
                api_endpoint=None,
                dataset_code=None,
                n_campos=None,
                n_novos=None,
            )

        row = CatalogDatasetRow(
            dataset_id=ds.id,
            provider_slug=slug,
            provider_api=ds.provider_api,
            provider_dataset_code=ds.provider_dataset_code,
            provider_query_name=ds.provider_query_name,
            public_code=ds.public_code,
            display_name_pt_br=ds.display_name_pt_br,
            categoria_ui=ds.categoria_ui,
            enabled_for_sale=ds.enabled_for_sale,
            current_cost_brl=_as_float(ds.current_cost_brl),
            markup_pct=_as_float(ds.markup_pct),
            mode=_provider_mode(slug),
            suggested_public_code=sug_pc,
            suggested_name=sug_name,
            contract=cref,
        )

        prov = by_provider.setdefault(
            slug, {"name": name or slug, "apis": {}, "enabled": 0, "with_contract": 0}
        )
        prov["apis"].setdefault(ds.provider_api, []).append(row)
        if ds.enabled_for_sale:
            prov["enabled"] += 1
        if has_contract:
            prov["with_contract"] += 1

    out: list[CatalogProviderGroup] = []
    for slug, data in sorted(by_provider.items()):
        apis = [
            CatalogApiGroup(
                api=api,
                total=len(rows_),
                datasets=sorted(
                    rows_,
                    key=lambda r: (
                        not r.enabled_for_sale,  # habilitados primeiro
                        r.public_code or "~",
                        r.provider_dataset_code,
                    ),
                ),
            )
            for api, rows_ in sorted(data["apis"].items())
        ]
        out.append(
            CatalogProviderGroup(
                provider_slug=slug,
                provider_name=data["name"],
                total=sum(a.total for a in apis),
                enabled_count=data["enabled"],
                with_contract_count=data["with_contract"],
                apis=apis,
            )
        )
    return out


# ─── Curadoria no nível do dataset ───────────────────────────────────────────


async def update_dataset_curation(
    db: AsyncSession,
    *,
    dataset_id: UUID,
    public_code: str | None,
    display_name_pt_br: str | None,
    categoria_ui: str | None,
    enabled_for_sale: bool | None,
    markup_pct: float | None,
) -> DataProviderDataset:
    """Grava a camada A7 do dataset (preservada entre syncs do vendor).

    Passar `None` num campo = não mexer nele. `enabled_for_sale` é bool, então
    sempre escreve quando vier não-nulo.
    """
    ds = (
        await db.execute(
            select(DataProviderDataset).where(DataProviderDataset.id == dataset_id)
        )
    ).scalar_one_or_none()
    if ds is None:
        raise ValueError("Dataset não encontrado.")

    if public_code is not None:
        new_pc = public_code.strip() or None
        if new_pc and new_pc != ds.public_code:
            clash = (
                await db.execute(
                    select(DataProviderDataset.id).where(
                        DataProviderDataset.public_code == new_pc,
                        DataProviderDataset.id != dataset_id,
                    )
                )
            ).first()
            if clash:
                raise ValueError(f"public_code '{new_pc}' já está em uso.")
        ds.public_code = new_pc
    if display_name_pt_br is not None:
        ds.display_name_pt_br = display_name_pt_br.strip() or None
    if categoria_ui is not None:
        ds.categoria_ui = categoria_ui.strip() or None
    if enabled_for_sale is not None:
        ds.enabled_for_sale = enabled_for_sale
    if markup_pct is not None:
        ds.markup_pct = Decimal(str(markup_pct))

    await db.flush()
    return ds


# ─── Criar contrato a partir de um dataset (decisão 14.9) ────────────────────


async def _latest_raw_sample(db: AsyncSession, public_code: str) -> dict:
    """Melhor-esforço: bloco de dados do último payload real (BDC) p/ pré-popular.

    Estrutura BDC: payload.Result[0] = bloco de datasets; removemos wrappers e,
    se sobrar exatamente 1 dict, usamos ele (o dataset em si); senão o Result[0]
    inteiro. Genérico o suficiente pro descobre-e-mostra; o mantenedor classifica.
    """
    row = (
        await db.execute(
            text(
                "SELECT payload FROM wh_bdc_raw_consulta "
                "WHERE public_code = :pc AND found = true "
                "ORDER BY fetched_at DESC LIMIT 1"
            ).bindparams(pc=public_code)
        )
    ).first()
    if not row or not isinstance(row[0], dict):
        return {}
    results = row[0].get("Result")
    if not (isinstance(results, list) and results and isinstance(results[0], dict)):
        return {}
    block = {
        k: v for k, v in results[0].items() if k not in _BDC_WRAPPER_KEYS
    }
    inner = [v for v in block.values() if isinstance(v, dict)]
    if len(block) == 1 and inner:
        return inner[0]
    return block


@dataclass(frozen=True)
class CreatedContract:
    provider: str
    api_endpoint: str
    dataset_code: str
    public_code: str
    version: int
    n_campos: int
    already_existed: bool


async def create_contract_for_dataset(
    db: AsyncSession, *, dataset_id: UUID, owner: str | None
) -> CreatedContract:
    """Cria a 1ª versão do contrato do dataset (ou devolve o existente).

    Requer `public_code` no dataset (nomeie antes). Pré-popula campos via
    flatten do último payload real, status `novo_nao_classificado`.
    """
    ds = (
        await db.execute(
            select(DataProviderDataset).where(DataProviderDataset.id == dataset_id)
        )
    ).scalar_one_or_none()
    if ds is None:
        raise ValueError("Dataset não encontrado.")
    if not ds.public_code:
        raise ValueError("Defina o nome/public_code do dataset antes de criar o contrato.")

    public_code = ds.public_code

    # Idempotência: já existe contrato (qualquer versão) pra este public_code?
    existing = (
        await db.execute(
            select(DatasetContract)
            .where(DatasetContract.public_code == public_code)
            .order_by(DatasetContract.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        n = len(
            (
                await db.execute(
                    select(DatasetField.id).where(
                        DatasetField.contract_id == existing.id
                    )
                )
            ).all()
        )
        return CreatedContract(
            provider=existing.provider,
            api_endpoint=existing.api_endpoint,
            dataset_code=existing.dataset_code,
            public_code=public_code,
            version=existing.version,
            n_campos=n,
            already_existed=True,
        )

    # Tupla de identidade do novo contrato = colunas do vendor (verbatim).
    slug_row = (
        await db.execute(
            text("SELECT slug FROM provedor_dados WHERE id = :pid").bindparams(
                pid=ds.provider_id
            )
        )
    ).first()
    provider = slug_row[0] if slug_row else "UNKNOWN"
    api_endpoint = ds.provider_api
    dataset_code = ds.provider_query_name or ds.provider_dataset_code

    contract = DatasetContract(
        id=uuid4(),
        provider=provider,
        api_endpoint=api_endpoint,
        dataset_code=dataset_code,
        public_code=public_code,
        version=1,
        status="active",
        owner=owner,
        description=ds.description_pt_br,
        tenant_id=None,
    )
    db.add(contract)
    await db.flush()

    # Pré-popula campos do payload real (descobre-e-mostra).
    sample = await _latest_raw_sample(db, public_code)
    paths = sorted(flatten_paths(sample)) if sample else []
    for path in paths:
        db.add(
            DatasetField(
                id=uuid4(),
                contract_id=contract.id,
                field_path=path,
                public_label=None,
                description=None,
                semantic_type="text",
                categoria_ui="novos",
                sensibilidade="publico",
                eh_fato="contexto",
                to_silver=False,
                silver_target=None,
                on_screen=True,
                screen_order=None,
                to_tool=False,
                to_agent=False,
                to_check=False,
                status="novo_nao_classificado",
                classified_by=None,
            )
        )

    db.add(
        DatasetContractActive(
            id=uuid4(),
            provider=provider,
            api_endpoint=api_endpoint,
            dataset_code=dataset_code,
            tenant_id=None,
            active_contract_id=contract.id,
        )
    )
    await db.flush()

    return CreatedContract(
        provider=provider,
        api_endpoint=api_endpoint,
        dataset_code=dataset_code,
        public_code=public_code,
        version=1,
        n_campos=len(paths),
        already_existed=False,
    )
