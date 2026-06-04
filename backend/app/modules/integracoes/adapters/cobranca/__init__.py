"""Adapter de cobranca (boletos / CNAB).

Popula o lado COBRANCA da conciliacao: captura arquivos CNAB (via FileSource),
pousa no bronze (`landing`), parseia por banco e mapeia para o canonico
`wh_boleto`. A conciliacao em si (cruzar wh_boleto x wh_titulo) vive no modulo
`controladoria` -- integracoes popula o warehouse, dominio le (CLAUDE.md 11.3).

Estrutura:
    version.py            -- ADAPTER_VERSION
    landing.py            -- RawFile -> wh_cnab_raw_arquivo (bronze, idempotente)
    <banco>/parser.py     -- CNAB -> ocorrencias (futuro, por banco)
    mappers/boleto.py     -- ocorrencias -> wh_boleto (futuro)
"""

from app.modules.integracoes.adapters.cobranca.version import ADAPTER_VERSION

__all__ = ["ADAPTER_VERSION"]
