"""Curadoria de Contratos de Dados (nível MANTENEDOR) — Fase 5.

Serviço por trás da UI de gestão (`/admin/data-contracts`). Lista contratos,
abre o detalhe (campos do contrato + valor de exemplo de uma consulta real +
campos NOVOS detectados 🆕) e salva edições como NOVA VERSÃO (imutável) +
ativa (decisão UX 2026-06-06: salvar = nova versão + ativa; rollback = reativar).

A amostra/detecção de campo novo é, na Fase 5, específica do BDC (lê o último
payload em `wh_bdc_raw_consulta`). Generalização por fonte = Fase 6.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.data_providers.contract_resolver import resolve_contract
from app.shared.data_providers.field_paths import extract_by_path, flatten_paths
from app.shared.data_providers.models.contract import (
    DatasetContract,
    DatasetContractActive,
)
from app.shared.data_providers.models.field import DatasetField


@dataclass(frozen=True)
class FieldRow:
    """Um campo no detalhe da curadoria (do contrato OU novo detectado)."""

    field_path: str
    public_label: str | None
    description: str | None
    semantic_type: str
    categoria_ui: str | None
    sensibilidade: str
    eh_fato: str
    to_silver: bool
    silver_target: str | None
    on_screen: bool
    screen_order: int | None
    to_tool: bool
    to_agent: bool
    to_check: bool
    status: str
    novo: bool
    valor_exemplo: str | None


def _pretty(path: str) -> str:
    seg = path.replace("[]", "").split(".")[-1]
    s = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", seg).replace("_", " ").strip()
    return (s[:1].upper() + s[1:]) if s else path


def _sample_str(v: Any) -> str | None:
    if v is None:
        return None
    if isinstance(v, list):
        parts = [_sample_str(x) for x in v]
        parts = [p for p in parts if p]
        return ", ".join(parts[:5]) or None
    if isinstance(v, dict):
        for k in ("Activity", "Description", "Name", "Value"):
            if isinstance(v.get(k), str) and v[k].strip():
                return v[k].strip()
        return None
    return str(v)[:120]


async def _latest_bdc_basic_data(db: AsyncSession, public_code: str) -> dict:
    """Último `basic_data` real consultado para este public_code (amostra)."""
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
    if isinstance(results, list) and results and isinstance(results[0], dict):
        basic = results[0].get("BasicData")
        if isinstance(basic, dict):
            return basic
    return {}


@dataclass(frozen=True)
class ContractListItem:
    contract_id: UUID
    provider: str
    api_endpoint: str
    dataset_code: str
    public_code: str | None
    version: int
    status: str
    n_campos: int


async def list_contracts(db: AsyncSession) -> list[ContractListItem]:
    """Lista os contratos ATIVOS (1 por identidade global)."""
    rows = (
        await db.execute(
            select(DatasetContract, DatasetContractActive)
            .join(
                DatasetContractActive,
                DatasetContractActive.active_contract_id == DatasetContract.id,
            )
            .where(DatasetContractActive.tenant_id.is_(None))
            .order_by(DatasetContract.provider, DatasetContract.api_endpoint)
        )
    ).all()
    out: list[ContractListItem] = []
    for contract, _active in rows:
        n = (
            await db.execute(
                select(DatasetField).where(DatasetField.contract_id == contract.id)
            )
        ).scalars().all()
        out.append(
            ContractListItem(
                contract_id=contract.id,
                provider=contract.provider,
                api_endpoint=contract.api_endpoint,
                dataset_code=contract.dataset_code,
                public_code=contract.public_code,
                version=contract.version,
                status=contract.status,
                n_campos=len(n),
            )
        )
    return out


@dataclass(frozen=True)
class ContractDetail:
    contract_id: UUID
    provider: str
    api_endpoint: str
    dataset_code: str
    public_code: str | None
    version: int
    status: str
    campos: list[FieldRow]
    n_novos: int


async def get_contract_detail(
    db: AsyncSession, *, provider: str, api_endpoint: str, dataset_code: str
) -> ContractDetail | None:
    """Detalhe do contrato ativo: campos + valor de exemplo + novos detectados."""
    rc = await resolve_contract(
        db, provider=provider, api_endpoint=api_endpoint, dataset_code=dataset_code
    )
    if rc is None:
        return None

    sample: dict = {}
    if provider == "bdc" and rc.contract.public_code:
        sample = await _latest_bdc_basic_data(db, rc.contract.public_code)

    campos: list[FieldRow] = []
    for f in rc.fields:
        campos.append(
            FieldRow(
                field_path=f.field_path,
                public_label=f.public_label,
                description=f.description,
                semantic_type=f.semantic_type,
                categoria_ui=f.categoria_ui,
                sensibilidade=f.sensibilidade,
                eh_fato=f.eh_fato,
                to_silver=f.to_silver,
                silver_target=f.silver_target,
                on_screen=f.on_screen,
                screen_order=f.screen_order,
                to_tool=f.to_tool,
                to_agent=f.to_agent,
                to_check=f.to_check,
                status=f.status,
                novo=False,
                valor_exemplo=_sample_str(extract_by_path(sample, f.field_path)) if sample else None,
            )
        )

    novos = sorted(flatten_paths(sample) - rc.field_paths()) if sample else []
    for path in novos:
        campos.append(
            FieldRow(
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
                novo=True,
                valor_exemplo=_sample_str(extract_by_path(sample, path)),
            )
        )

    return ContractDetail(
        contract_id=rc.contract.id,
        provider=rc.contract.provider,
        api_endpoint=rc.contract.api_endpoint,
        dataset_code=rc.contract.dataset_code,
        public_code=rc.contract.public_code,
        version=rc.contract.version,
        status=rc.contract.status,
        campos=campos,
        n_novos=len(novos),
    )


async def save_new_version(
    db: AsyncSession,
    *,
    provider: str,
    api_endpoint: str,
    dataset_code: str,
    fields: list[dict],
    owner: str | None,
) -> DatasetContract:
    """Cria NOVA versão (imutável) com o conjunto de campos dado + ativa.

    `fields` = estado desejado completo (a UI manda todos os campos). A versão
    anterior vira `archived`; o ponteiro ativo passa a apontar a nova. Rollback
    = reativar a versão anterior (endpoint separado).
    """
    current = (
        await db.execute(
            select(DatasetContract)
            .where(
                DatasetContract.provider == provider,
                DatasetContract.api_endpoint == api_endpoint,
                DatasetContract.dataset_code == dataset_code,
            )
            .order_by(desc(DatasetContract.version))
            .limit(1)
        )
    ).scalar_one_or_none()
    if current is None:
        raise ValueError(
            f"Contrato inexistente: {provider}/{api_endpoint}/{dataset_code}"
        )

    new_version = current.version + 1
    new_contract = DatasetContract(
        id=uuid4(),
        provider=provider,
        api_endpoint=api_endpoint,
        dataset_code=dataset_code,
        public_code=current.public_code,
        version=new_version,
        status="active",
        owner=owner or current.owner,
        description=current.description,
        tenant_id=None,
    )
    db.add(new_contract)
    await db.flush()

    for f in fields:
        db.add(
            DatasetField(
                id=uuid4(),
                contract_id=new_contract.id,
                field_path=f["field_path"],
                public_label=f.get("public_label"),
                description=f.get("description"),
                semantic_type=f.get("semantic_type") or "text",
                categoria_ui=f.get("categoria_ui"),
                sensibilidade=f.get("sensibilidade") or "publico",
                eh_fato=f.get("eh_fato") or "contexto",
                to_silver=bool(f.get("to_silver")),
                silver_target=f.get("silver_target"),
                on_screen=bool(f.get("on_screen", True)),
                screen_order=f.get("screen_order"),
                to_tool=bool(f.get("to_tool")),
                to_agent=bool(f.get("to_agent")),
                to_check=bool(f.get("to_check")),
                status="curado",
                classified_by=owner,
            )
        )

    # Arquiva a anterior + move o ponteiro ativo.
    current.status = "archived"
    active = (
        await db.execute(
            select(DatasetContractActive).where(
                DatasetContractActive.provider == provider,
                DatasetContractActive.api_endpoint == api_endpoint,
                DatasetContractActive.dataset_code == dataset_code,
                DatasetContractActive.tenant_id.is_(None),
            )
        )
    ).scalar_one_or_none()
    if active is None:
        db.add(
            DatasetContractActive(
                id=uuid4(),
                provider=provider,
                api_endpoint=api_endpoint,
                dataset_code=dataset_code,
                tenant_id=None,
                active_contract_id=new_contract.id,
            )
        )
    else:
        active.active_contract_id = new_contract.id

    await db.flush()
    return new_contract
