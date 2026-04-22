"""Service de favoritos por usuario (BI/Benchmark).

- Estado local ao `gr_db` (tabela `user_fund_favorite`), escopo (tenant, user).
- Enriquece `denom_social` via JOIN com `cvm_remote.tab_i` na ultima competencia
  CVM disponivel (dado publico, CLAUDE.md 13.1).
- Todas as operacoes sao **idempotentes**: adicionar duas vezes nao erra,
  remover nao existente tambem nao.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.bi.schemas.favoritos import FavoritoItem, FavoritosLista


async def listar_favoritos(
    db: AsyncSession, *, user_id: UUID, tenant_id: UUID
) -> FavoritosLista:
    """Retorna todos os favoritos do usuario, enriquecidos com `denom_social`
    vindo do snapshot mais recente em `cvm_remote.tab_i`."""
    stmt = text(
        """
        WITH ult AS (
            SELECT MAX(competencia)::date AS competencia FROM cvm_remote.tab_i
        )
        SELECT
            f.cnpj,
            f.created_at,
            ti.denom_social
        FROM user_fund_favorite f
        LEFT JOIN cvm_remote.tab_i ti
            ON ti.cnpj_fundo_classe = f.cnpj
           AND ti.competencia = (SELECT competencia FROM ult)
        WHERE f.user_id = :user_id
          AND f.tenant_id = :tenant_id
        ORDER BY f.created_at DESC
        """
    )
    result = await db.execute(stmt, {"user_id": user_id, "tenant_id": tenant_id})
    rows = result.all()
    favoritos = [
        FavoritoItem(
            cnpj=r.cnpj,
            denom_social=r.denom_social,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return FavoritosLista(favoritos=favoritos, total=len(favoritos))


async def adicionar_favorito(
    db: AsyncSession, *, user_id: UUID, tenant_id: UUID, cnpj: str
) -> None:
    """Insere o favorito (idempotente via ON CONFLICT DO NOTHING)."""
    stmt = text(
        """
        INSERT INTO user_fund_favorite (tenant_id, user_id, cnpj)
        VALUES (:tenant_id, :user_id, :cnpj)
        ON CONFLICT (user_id, cnpj) DO NOTHING
        """
    )
    await db.execute(
        stmt, {"tenant_id": tenant_id, "user_id": user_id, "cnpj": cnpj}
    )
    await db.commit()


async def remover_favorito(
    db: AsyncSession, *, user_id: UUID, tenant_id: UUID, cnpj: str
) -> None:
    """Remove o favorito. Filtro extra por `tenant_id` (defense in depth)."""
    stmt = text(
        """
        DELETE FROM user_fund_favorite
        WHERE user_id = :user_id
          AND tenant_id = :tenant_id
          AND cnpj = :cnpj
        """
    )
    await db.execute(
        stmt, {"user_id": user_id, "tenant_id": tenant_id, "cnpj": cnpj}
    )
    await db.commit()
