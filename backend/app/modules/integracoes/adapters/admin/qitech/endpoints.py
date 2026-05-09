"""Catalogo de endpoints QiTech em uso.

Cada entrada e uma constante com `method` + `path`. O `path` sempre
relativo a `QiTechConfig.base_url` — nunca URL absoluta, para que sandbox
e producao compartilhem o catalogo.

Convencao de nomenclatura:
    E_<AREA>_<ACAO> = (METODO, PATH)

Adicionar endpoint = adicionar linha aqui + seu handler em etl.py.
Nenhum endpoint vive hardcoded dentro do etl.
"""

from __future__ import annotations

from typing import NamedTuple


class Endpoint(NamedTuple):
    method: str
    path: str


# Auth — bearer token (usado implicitamente pelo http_client; documentado
# aqui para manter o catalogo unico).
E_AUTH_TOKEN = Endpoint(method="POST", path="/v2/painel/token/api")

# Relatorios — "Mercado".
# Path template com placeholders nomeados para `str.format(**kwargs)`:
#   tipo_de_mercado: ex. "outros-fundos", "renda-fixa" (str, hifen no valor).
#   data:            aaaa-mm-dd (date.isoformat()).
# Retorna todos os ativos com quebra por carteira, filtrado pelo perfil
# de acesso do client_id.
E_REPORT_MARKET = Endpoint(
    method="GET",
    path="/v2/netreport/report/market/{tipo_de_mercado}/{data}",
)

# Bank account — Saldo (snapshot de fechamento do dia).
# Path template:
#   agencia: codigo da agencia da Singulare zero-padded a 4 digitos (ex.: "0001").
#            String literal — viaja exatamente como cadastrado em
#            QiTechBankAccount.agencia.
#   conta:   numero da conta sem digito verificador (ex.: "4532551").
#   data:    aaaa-mm-dd (date.isoformat()).
# Retorna saldo da conta-corrente na data.
#
# NOTA: balance herdado por simetria do statement (confirmado em 2026-05-01
# que statement vive sob /v2/conta-corrente/bank-account/...). Validar
# diretamente em ambiente real antes de iterar em volume.
E_BANK_ACCOUNT_BALANCE = Endpoint(
    method="GET",
    path="/v2/conta-corrente/bank-account/balance/{agencia}/{conta}/{data}",
)

# Bank account — Extrato (lancamentos do periodo).
# Path template:
#   agencia: codigo da agencia zero-padded a 4 digitos (ex.: "0001").
#   conta:   numero da conta sem digito verificador (ex.: "4532551").
#   inicio:  aaaa-mm-dd (data inicial inclusiva).
#   fim:     aaaa-mm-dd (data final inclusiva).
# Retorna lancamentos da conta-corrente no periodo.
#
# CONFIRMADO 2026-05-01 em teste real — endereco antigo `/v2/bank-account/...`
# (sem o prefixo /conta-corrente/) NAO existe.
E_BANK_ACCOUNT_STATEMENT = Endpoint(
    method="GET",
    path="/v2/conta-corrente/bank-account/statement/{agencia}/{conta}/{inicio}/{fim}",
)
