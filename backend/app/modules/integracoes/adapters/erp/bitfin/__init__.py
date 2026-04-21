"""Adapter Bitfin.

Conecta em dois databases MSSQL na mesma instancia:
- `UNLTD_A7CREDIT` (Bitfin ERP nativo)
- `ANALYTICS` (views pre-computadas usadas pelo BI)

Popula as 7 tabelas `wh_*` em `gr_db` com proveniencia completa.
"""

from app.modules.integracoes.adapters.erp.bitfin.version import ADAPTER_VERSION

__all__ = ["ADAPTER_VERSION"]
