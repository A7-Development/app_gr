"""Service layer para metadados auxiliares do BI.

Consultas simples de taxonomia (UAs, produtos, modalidades) que alimentam
dropdowns do frontend. Filtradas por tenant (CLAUDE.md 10.2).
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from sqlalchemy import Date, cast, exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.warehouse.dim import DimProduto, DimUnidadeAdministrativa
from app.warehouse.operacao import Operacao


async def listar_uas(db: AsyncSession, tenant_id: UUID) -> list[DimUnidadeAdministrativa]:
    """Lista UAs do tenant, ordenadas por `ua_id`.

    Filtros aplicados:
    - `ativa = true` na dim (Bitfin pode ter UAs desativadas historicas).
    - **EXISTS em wh_operacao** do mesmo tenant/ua: so retorna UAs com
      ao menos 1 operacao efetivada — remove UAs "fantasma" (configuradas
      no ERP mas sem movimentacao) do filtro de UI.

    Semantica: nao-contextual. Nao considera filtros atuais do usuario
    (periodo, produto). Para filtro contextual avancado, adicionar
    parametros opcionais e aplicar no EXISTS.
    """
    has_operacao = exists().where(
        Operacao.tenant_id == tenant_id,
        Operacao.unidade_administrativa_id == DimUnidadeAdministrativa.ua_id,
        Operacao.efetivada.is_(True),
    )

    stmt = (
        select(DimUnidadeAdministrativa)
        .where(
            DimUnidadeAdministrativa.tenant_id == tenant_id,
            DimUnidadeAdministrativa.ativa.is_(True),
            has_operacao,
        )
        .order_by(DimUnidadeAdministrativa.ua_id)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def listar_produtos(db: AsyncSession, tenant_id: UUID) -> list[DimProduto]:
    """Lista produtos do tenant que tem ao menos 1 operacao efetivada.

    Mesma filosofia do `listar_uas`: taxonomia crua do Bitfin tem 20 produtos,
    mas muitos sem volume. O filtro `EXISTS` reduz o combo para as siglas
    que fazem sentido selecionar hoje — evita "FAT (0 ops), CBS (0 ops)..."
    no popover.

    Ordenacao: pelo nome (alfabetico). Mais previsivel que `produto_id`
    para o usuario final.
    """
    # O produto e identificado em wh_operacao pelo prefixo da coluna
    # `modalidade` antes do hifen. Juntamos pela `sigla` da dim.
    sigla_expr = func.split_part(Operacao.modalidade, "-", 1)

    has_operacao = exists().where(
        Operacao.tenant_id == tenant_id,
        Operacao.efetivada.is_(True),
        sigla_expr == DimProduto.sigla,
    )

    stmt = (
        select(DimProduto)
        .where(DimProduto.tenant_id == tenant_id, has_operacao)
        .order_by(DimProduto.nome)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def data_minima_operacao(db: AsyncSession, tenant_id: UUID) -> date | None:
    """Data da operacao efetivada mais antiga do tenant.

    Usado pelo preset 'ALL' do seletor de periodo no frontend: em vez de
    mandar um range fixo e amplo (ex.: 2000-01-01), o picker ja abre com
    o intervalo real de dados disponiveis — o que da feedback claro ao
    usuario (ex.: "ALL = 15/03/2024 → hoje, ~2 anos de historico").

    Retorna None quando o tenant nao tem nenhuma operacao efetivada
    (tenant novo/vazio). Frontend pode cair em fallback (hoje - 24M).
    """
    stmt = (
        select(func.min(cast(Operacao.data_de_efetivacao, Date)))
        .where(
            Operacao.tenant_id == tenant_id,
            Operacao.efetivada.is_(True),
            Operacao.data_de_efetivacao.is_not(None),
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
