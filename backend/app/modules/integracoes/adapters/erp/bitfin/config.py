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
    user: str
    password: str
    driver: str = "ODBC Driver 17 for SQL Server"
    # ANALYTICS e database A7-especifico (construido pela A7 em cima de UNLTD_A7CREDIT).
    # Clientes Bitfin novos NAO terao um ANALYTICS provisionado -- so o UNLTD_<X>
    # que o Bitfin entrega por padrao. A partir do adapter v2.0.0 o caminho critico
    # do DRE deixou de depender deste banco; resta apenas `sync_titulo_snapshot`
    # (elig_snapshot_titulo) que ainda le dele -- followup separado pra eliminar.
    # Quando None, syncs que dependem de ANALYTICS sao skipadas com warning.
    database_analytics: str | None = None

    @classmethod
    def from_dict(cls, data: dict) -> BitfinConfig:
        return cls(
            server=data["server"],
            database_bitfin=data["database_bitfin"],
            database_analytics=data.get("database_analytics"),
            user=data["user"],
            password=data["password"],
            driver=data.get("driver", "ODBC Driver 17 for SQL Server"),
        )
