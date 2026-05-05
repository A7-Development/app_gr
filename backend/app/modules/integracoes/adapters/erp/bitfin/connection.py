"""Conexao com SQL Server (pyodbc, sync; usado em thread pool pelo ETL async).

Credenciais vem da `BitfinConfig` recebida por argumento (populada pelo
`tenant_source_config` do tenant em execucao). Zero leitura de env.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pyodbc

from app.modules.integracoes.adapters.erp.bitfin.config import BitfinConfig

# Timeouts (segundos). Sem isso, `cursor.execute` / `fetchall` bloqueiam
# indefinidamente — o que trava o `executor.shutdown(wait=True)` do asyncio
# durante reload/SIGTERM e deixa o servidor zumbi (porta aberta, worker preso
# em join). Valores conservadores para um SLA realista do Bitfin: queries
# analiticas grandes (Operacao, Titulo) podem levar minutos legitimamente.
_LOGIN_TIMEOUT_S = 10  # tempo maximo pra autenticar (servidor down -> falha rapida)
_QUERY_TIMEOUT_S = 300  # tempo maximo por query (5 min — ETL grande encaixa, deadlock nao)


def _build_connection_string(config: BitfinConfig, database: str) -> str:
    return (
        f"DRIVER={{{config.driver}}};"
        f"SERVER={config.server};"
        f"DATABASE={database};"
        f"UID={config.user};"
        f"PWD={config.password};"
        f"TrustServerCertificate=yes;"
        # Timeouts da camada TDS/ODBC. Connect = handshake; Login = auth pos-handshake.
        f"Connect Timeout={_LOGIN_TIMEOUT_S};"
        f"Login Timeout={_LOGIN_TIMEOUT_S};"
    )


@contextmanager
def open_mssql_connection(
    config: BitfinConfig, database: str
) -> Iterator[pyodbc.Connection]:
    """Context manager que abre e fecha conexao MSSQL."""
    conn = pyodbc.connect(_build_connection_string(config, database), autocommit=False)
    # Timeout aplicado a todas as queries desta conexao. Atributo da Connection
    # no pyodbc — propaga pra cursores. 0 = sem timeout (default); evite.
    conn.timeout = _QUERY_TIMEOUT_S
    try:
        yield conn
    finally:
        conn.close()


def fetch_rows(
    config: BitfinConfig,
    database: str,
    sql: str,
    params: tuple[Any, ...] | None = None,
) -> list[dict[str, Any]]:
    """Executa SELECT e retorna rows como lista de dicts (colunas como keys)."""
    with open_mssql_connection(config, database) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params or ())
        if cursor.description is None:
            return []
        cols = [col[0] for col in cursor.description]
        return [dict(zip(cols, row, strict=True)) for row in cursor.fetchall()]


def ping(config: BitfinConfig, database: str) -> dict[str, Any]:
    """Health check: abre conexao e executa SELECT 1."""
    rows = fetch_rows(config, database, "SELECT DB_NAME() AS db, @@VERSION AS version")
    return rows[0] if rows else {}
