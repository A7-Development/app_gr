"""Conexao com SQL Server (pyodbc, sync; usado em thread pool pelo ETL async)."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pyodbc

from app.core.config import get_settings

_settings = get_settings()


def _build_connection_string(database: str) -> str:
    return (
        f"DRIVER={{{_settings.BITFIN_DRIVER}}};"
        f"SERVER={_settings.BITFIN_HOST};"
        f"DATABASE={database};"
        f"UID={_settings.BITFIN_USER};"
        f"PWD={_settings.BITFIN_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )


@contextmanager
def open_mssql_connection(database: str) -> Iterator[pyodbc.Connection]:
    """Context manager que abre e fecha conexao MSSQL."""
    conn = pyodbc.connect(_build_connection_string(database), autocommit=False)
    try:
        yield conn
    finally:
        conn.close()


def fetch_rows(
    database: str,
    sql: str,
    params: tuple[Any, ...] | None = None,
) -> list[dict[str, Any]]:
    """Executa SELECT e retorna rows como lista de dicts (colunas como keys)."""
    with open_mssql_connection(database) as conn:
        cursor = conn.cursor()
        cursor.execute(sql, params or ())
        if cursor.description is None:
            return []
        cols = [col[0] for col in cursor.description]
        return [dict(zip(cols, row, strict=True)) for row in cursor.fetchall()]


def ping(database: str) -> dict[str, Any]:
    """Health check: abre conexao e executa SELECT 1."""
    rows = fetch_rows(database, "SELECT DB_NAME() AS db, @@VERSION AS version")
    return rows[0] if rows else {}
