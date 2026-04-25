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
