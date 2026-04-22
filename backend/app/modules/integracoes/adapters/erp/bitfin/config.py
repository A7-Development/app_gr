"""BitfinConfig: parametros de conexao lidos de `tenant_source_config.config`.

Recebido como argumento por todo o pipeline — zero leitura de variaveis de ambiente.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BitfinConfig:
    """Config por tenant para o adapter Bitfin.

    Mapeado de `tenant_source_config.config` (JSONB) via `from_dict`.
    Cada tenant com adapter Bitfin habilitado tem seu proprio banco SQL Server
    (ex.: `UNLTD_A7CREDIT` atende exclusivamente o tenant `a7-credit`).
    """

    server: str
    database_bitfin: str
    database_analytics: str
    user: str
    password: str
    driver: str = "ODBC Driver 17 for SQL Server"

    @classmethod
    def from_dict(cls, data: dict) -> BitfinConfig:
        return cls(
            server=data["server"],
            database_bitfin=data["database_bitfin"],
            database_analytics=data["database_analytics"],
            user=data["user"],
            password=data["password"],
            driver=data.get("driver", "ODBC Driver 17 for SQL Server"),
        )
