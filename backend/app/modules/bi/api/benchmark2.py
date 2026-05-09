"""BI -> L2 Benchmark2 (lista de fundos CVM com PL + cotistas).

Endpoint experimental — entrega complementar ao Benchmark canonico, com
foco em listagem completa para o pattern <DataTableShell>.

Fonte: schema federado `cvm_remote.*` (postgres_fdw, dado publico CVM FIDC).
Sem escopo de tenant (CLAUDE.md sec 13.1). Source type = 'public:cvm_fidc'.
"""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.modules.bi.schemas.benchmark2 import (
    Benchmark2FundoRow,
    Benchmark2FundosLista,
)

router = APIRouter(prefix="/benchmark2", tags=["bi:benchmark2"])

_Guard = Depends(require_module(Module.BI, Permission.READ))


_FUNDOS_QUERY = text(
    """
    WITH ult AS (
        SELECT MAX(competencia) AS comp FROM cvm_remote.tab_iv
    ),
    pl_3m AS (
        SELECT
            cnpj_fundo_classe,
            AVG(tab_iv_a_vl_pl) AS pl_medio_3m
        FROM cvm_remote.tab_iv
        WHERE competencia >= ((SELECT comp FROM ult) - INTERVAL '2 months')::date
          AND competencia <= (SELECT comp FROM ult)
        GROUP BY cnpj_fundo_classe
    ),
    cotistas_agg AS (
        SELECT
            cnpj_fundo_classe,
            SUM(tab_x_nr_cotst) AS cotistas
        FROM cvm_remote.tab_x_1
        WHERE competencia = (SELECT comp FROM ult)
        GROUP BY cnpj_fundo_classe
    )
    SELECT
        i.cnpj_fundo_classe                          AS cnpj,
        i.denom_social                               AS fundo,
        LOWER(NULLIF(TRIM(i.condom), ''))            AS condom,
        c.cotistas::int                              AS cotistas,
        pl3.pl_medio_3m::float                       AS pl_medio_3m,
        iv.tab_iv_a_vl_pl::float                     AS pl_ult_mes,
        TO_CHAR((SELECT comp FROM ult), 'YYYY-MM')   AS competencia
    FROM cvm_remote.tab_i i
    JOIN cvm_remote.tab_iv iv
        ON iv.cnpj_fundo_classe = i.cnpj_fundo_classe
       AND iv.competencia       = i.competencia
    LEFT JOIN pl_3m         pl3 ON pl3.cnpj_fundo_classe = i.cnpj_fundo_classe
    LEFT JOIN cotistas_agg  c   ON c.cnpj_fundo_classe   = i.cnpj_fundo_classe
    WHERE i.competencia = (SELECT comp FROM ult)
    ORDER BY iv.tab_iv_a_vl_pl DESC NULLS LAST;
    """
)


@router.get(
    "/fundos",
    response_model=Benchmark2FundosLista,
    dependencies=[_Guard],
)
async def fundos(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Benchmark2FundosLista:
    """Lista todos os fundos CVM com PL + PL medio 3M + cotistas."""
    result = await db.execute(_FUNDOS_QUERY)
    rows = result.mappings().all()
    if not rows:
        return Benchmark2FundosLista(competencia="", fundos=[], total=0)

    competencia = str(rows[0]["competencia"])
    fundos_list = [
        Benchmark2FundoRow(
            cnpj=str(r["cnpj"]),
            fundo=str(r["fundo"]),
            condom=r["condom"],
            cotistas=int(r["cotistas"]) if r["cotistas"] is not None else None,
            pl_medio_3m=float(r["pl_medio_3m"]) if r["pl_medio_3m"] is not None else None,
            pl_ult_mes=float(r["pl_ult_mes"]) if r["pl_ult_mes"] is not None else None,
        )
        for r in rows
    ]
    return Benchmark2FundosLista(
        competencia=competencia,
        fundos=fundos_list,
        total=len(fundos_list),
    )
