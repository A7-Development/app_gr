"""resolve_contract — lê o Contrato de Dados ATIVO de um dataset + projeções.

Fonte única que as 5 superfícies consultam (ver
`docs/contratos-de-dados-fontes-externas.md`). Resolve a versão ativa via
`dataset_contract_active` e devolve os campos com helpers de projeção por
superfície (silver / tela / tool / agente / check).

Começa global (tenant_id NULL). Quando o override por tenant entrar, a busca
tentará o contrato do tenant antes do global.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.data_providers.models.contract import (
    DatasetContract,
    DatasetContractActive,
)
from app.shared.data_providers.models.field import DatasetField


@dataclass(frozen=True)
class ResolvedContract:
    """Contrato ativo + seus campos, com projeções por superfície."""

    contract: DatasetContract
    fields: list[DatasetField]

    # ─── Projeções por superfície ────────────────────────────────────────────
    def for_screen(self) -> list[DatasetField]:
        """Campos exibíveis, ordenados (screen_order, depois field_path)."""
        vis = [f for f in self.fields if f.on_screen]
        return sorted(
            vis, key=lambda f: (f.screen_order if f.screen_order is not None else 10_000, f.field_path)
        )

    def for_tool(self) -> list[DatasetField]:
        return [f for f in self.fields if f.to_tool]

    def for_agent(self) -> list[DatasetField]:
        return [f for f in self.fields if f.to_agent]

    def for_silver(self) -> list[DatasetField]:
        return [f for f in self.fields if f.to_silver]

    def for_check(self) -> list[DatasetField]:
        return [f for f in self.fields if f.to_check]

    def field_paths(self) -> set[str]:
        """Caminhos já catalogados — base para o detector de campo novo."""
        return {f.field_path for f in self.fields}


async def resolve_contract(
    db: AsyncSession,
    *,
    provider: str,
    api_endpoint: str,
    dataset_code: str,
    tenant_id: UUID | None = None,
) -> ResolvedContract | None:
    """Resolve o contrato ativo do dataset. None se não houver contrato ativo.

    `tenant_id` é aceito para o futuro override por tenant; hoje resolve o
    contrato GLOBAL (tenant_id IS NULL).
    """
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
        return None

    contract = (
        await db.execute(
            select(DatasetContract).where(
                DatasetContract.id == active.active_contract_id
            )
        )
    ).scalar_one_or_none()
    if contract is None:
        return None

    fields = list(
        (
            await db.execute(
                select(DatasetField).where(
                    DatasetField.contract_id == contract.id
                )
            )
        )
        .scalars()
        .all()
    )
    return ResolvedContract(contract=contract, fields=fields)
