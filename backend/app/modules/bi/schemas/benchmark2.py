"""Schemas do BI -> Benchmark2 (lista de fundos CVM com PL + cotistas)."""

from pydantic import BaseModel


class Benchmark2FundoRow(BaseModel):
    """Linha da listagem de fundos CVM no Benchmark2.

    Espelha o resultado da query agregada em `services/benchmark2.py` que junta:
      - `cvm_remote.tab_i`   (denom_social, condom)
      - `cvm_remote.tab_iv`  (PL do mes / PL do mes anterior)
      - `cvm_remote.tab_x_1` (cotistas — somados por classe)
    """

    cnpj: str
    fundo: str
    condom: str | None  # 'aberto' | 'fechado' (normalizado lower-case)
    admin: str | None  # razao social da administradora (cvm_remote.tab_i.admin)
    cotistas: int | None
    pl_medio_3m: float | None
    pl_ult_mes: float | None


class Benchmark2FundosLista(BaseModel):
    """Resposta da listagem completa."""

    competencia: str  # 'YYYY-MM' da ultima disponivel
    fundos: list[Benchmark2FundoRow]
    total: int
