"""Catalogo de endpoints Serasa PJ em uso.

Cada entrada e uma constante com `method` + `path` relativo a
`SerasaPjConfig.base_url` — nunca URL absoluta, para que UAT e producao
compartilhem o catalogo.

Convencao:
    E_<AREA>_<ACAO> = (METODO, PATH)
"""

from __future__ import annotations

from typing import NamedTuple


class Endpoint(NamedTuple):
    method: str
    path: str


# Auth — login via Basic Auth (clientID:clientSecret) emite Access Token.
# Resposta tem typo da Serasa: "AcessToken" em vez de "AccessToken".
E_AUTH_LOGIN = Endpoint(
    method="POST",
    path="/security/iam/v1/client-identities/login",
)

# Business Information Report — endpoint canonico do PJ.
#
# Validado contra prod 2026-05-01 via probe: `OPTIONS /reports` retorna
# `Allow: GET,HEAD,OPTIONS` — o metodo correto e GET (nao POST). Todos os
# parametros (reportName, documentId, scoreModelId) vao em QUERY PARAM,
# sem body. POST devolve 404 silencioso (Istio bloqueia em vez de 405).
#
# Headers: Authorization Bearer + X-Retailer-Document-Id (obrigatorio).
E_BUSINESS_INFORMATION_REPORT = Endpoint(
    method="GET",
    path="/credit-services/business-information-report/v1/reports",
)
