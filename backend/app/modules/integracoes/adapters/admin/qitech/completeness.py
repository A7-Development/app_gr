"""QiTech raw payload — completeness inspector.

Opcao A da resposta-semantica (memoria `project_qitech_response_semantics.md`,
2026-05-13). O pipeline historicamente tratou `http_status=200` como sinonimo
de "dado completo". Casos vistos em 12/05/2026 e 30/04/2026 mostraram que a
administradora pode publicar relatorios parciais pela QiTech (ex.: `market.rf`
sem o `clienteId` principal do fundo), e isso renderiza zero silencioso na UI.

Este modulo expoe `assess_completeness(...)` — funcao pura que olha o payload
bruto + contexto da UA e devolve um dos 3 valores:

- `complete`: subsets esperados todos presentes.
- `partial` : payload chegou mas falta um subset esperado.
- `empty`   : payload sem dado utilizavel (envelope vazio, http 4xx-as-row).

A semantica fica na coluna `wh_qitech_raw_relatorio.completeness` (migration
`e4a7b2c9d031`). O coverage service (`services/coverage.py`) usa essa coluna
para mapear o status do dia em `OK | PARTIAL | NOT_PUBLISHED`, alimentando a
aba Cobertura com a 3a cor.

Perfis cobertos no MVP (Opcao A):

- `mec`: deve ter as 3 classes de cota (Sub Jr / Mezanino / Senior). Faltar
  qualquer uma -> `partial`. Lista vazia -> `empty`.
- `rf` : deve ter ao menos 1 row com `clienteId` casando com o
  `cliente_id_principal` da UA (primeira palavra do nome em UPPER, ex.:
  "REALINVEST FIDC" -> "REALINVEST"). Sem isso -> `partial` (caso 12/05).
- `fidc-estoque` e `fidc-custodia/*`: endpoints CSV (relatorio entregue como
  arquivo externo). O `payload` armazenado e *metadata* do report file —
  nao tem chave `relatórios`, entao o `_default_assess` marcava sempre como
  `empty` (bug observado em 2026-05-18). Perfil novo `_assess_csv_report`
  usa `bytes > 0` ou `rows_estimate > 0` como sinal de conteudo presente.

Outros tipos (`conta-corrente`, `tesouraria`, etc.) hoje retornam `complete`
quando http==200 — perfil pode ser adicionado aqui sob demanda quando
descobrirmos padroes de publicacao parcial neles. Falsos negativos (marcar
parcial onde nao e) sao mais caros que falsos positivos: prefira ser
conservador e expandir a regra so apos confirmar com dado real.
"""

from __future__ import annotations

from typing import Any, Literal

Completeness = Literal["complete", "partial", "empty"]


def _norm(s: str | None) -> str:
    return (s or "").strip().upper()


def _cliente_id_principal(ua_nome: str) -> str:
    """Replica a heuristica de balanco.py:232 — primeira palavra do nome da UA
    em UPPER. Para "REALINVEST FIDC" devolve "REALINVEST"."""
    return _norm(ua_nome).split(" ", 1)[0]


def _is_sub_jr_name(carteira_nome: str, ua_nome: str) -> bool:
    """Replica a heuristica de cota_sub.py — clienteNome do MEC bate com
    o nome cru da UA (ex.: "REALINVEST FIDC" == "REALINVEST FIDC")."""
    return _norm(carteira_nome) == _norm(ua_nome)


def _is_mezanino_name(carteira_nome: str) -> bool:
    return "MEZANINO" in _norm(carteira_nome)


def _is_senior_name(carteira_nome: str) -> bool:
    return "SENIOR" in _norm(carteira_nome)


def _mec_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extrai a lista de relatorios MEC do envelope QiTech, tolerando shape
    ausente. Estrutura tipica: payload['relatórios']['mec'] -> list."""
    if not isinstance(payload, dict):
        return []
    relatorios = payload.get("relatórios")
    if not isinstance(relatorios, dict):
        return []
    mec = relatorios.get("mec")
    if not isinstance(mec, list):
        return []
    return [item for item in mec if isinstance(item, dict)]


def _rf_items(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Extrai a lista de relatorios RF do envelope QiTech."""
    if not isinstance(payload, dict):
        return []
    relatorios = payload.get("relatórios")
    if not isinstance(relatorios, dict):
        return []
    rf = relatorios.get("rf")
    if not isinstance(rf, list):
        return []
    return [item for item in rf if isinstance(item, dict)]


def _assess_mec(payload: dict[str, Any] | None, ua_nome: str) -> Completeness:
    items = _mec_items(payload)
    if not items:
        return "empty"
    has_sub = any(_is_sub_jr_name(i.get("clienteNome") or "", ua_nome) for i in items)
    has_mez = any(_is_mezanino_name(i.get("clienteNome") or "") for i in items)
    has_sen = any(_is_senior_name(i.get("clienteNome") or "") for i in items)
    if has_sub and has_mez and has_sen:
        return "complete"
    return "partial"


def _assess_rf(payload: dict[str, Any] | None, ua_nome: str) -> Completeness:
    items = _rf_items(payload)
    if not items:
        return "empty"
    principal = _cliente_id_principal(ua_nome)
    has_principal = any(_norm(i.get("clienteId") or "") == principal for i in items)
    if has_principal:
        return "complete"
    return "partial"


def _assess_csv_report(payload: dict[str, Any] | None, ua_nome: str) -> Completeness:
    """Para endpoints CSV (fidc-estoque, fidc-custodia/*), o `payload` no raw e
    *metadata* do report file gerado pela QiTech — nao o conteudo bruto. O CSV
    propriamente dito mora em storage externo apontado por `qitech_job_id`.

    Shape tipico do payload (visto em 2026-05-18 com report cheio):
        {"bytes": 1148660, "format": "csv", "delimiter": ";",
         "qitech_job_id": "...", "rows_estimate": 2888, "qitech_webhook_id": 835558}

    E quando o report e gerado mas sem conteudo (dia sem operacoes ou fundo
    ainda nao constituido):
        {"bytes": 0, ..., "rows_estimate": 0, ...}

    Sinal de complete: existe `qitech_job_id` E (bytes > 0 OU rows_estimate > 0).
    Sem job_id -> envelope corrompido, marca empty. Job presente mas tamanho
    zerado -> dia legitimamente vazio, marca empty.

    `ua_nome` aceito por compatibilidade de assinatura — completeness aqui e
    propriedade do report inteiro, nao depende da UA.
    """
    del ua_nome  # nao usado, mas assinatura padrao de _ASSESSORS
    if not isinstance(payload, dict):
        return "empty"
    if not payload.get("qitech_job_id"):
        return "empty"
    bytes_ = payload.get("bytes")
    rows_estimate = payload.get("rows_estimate")
    has_bytes = isinstance(bytes_, int) and bytes_ > 0
    has_rows = isinstance(rows_estimate, int) and rows_estimate > 0
    if has_bytes or has_rows:
        return "complete"
    return "empty"


def _assess_window_json_report(payload: dict[str, Any] | None, ua_nome: str) -> Completeness:
    """Para endpoints `/fidc-custodia/report/*` SINCRONOS (JSON inline, nao CSV
    async): `aquisicao-consolidada` e `liquidados-baixados`. Payload tipico:

        {"aquisicaoConsolidada": [...]} ou {"liquidadosBaixados": [...]}

    Apos split por `dataDaPosicao` (custodia.py::_persist_raw_split_by_window),
    cada raw cobre 1 dia: array pode estar cheio (operacoes naquele dia) ou
    vazio (dia sem movimento — fim de semana, feriado, ou simplesmente sem
    aquisicoes/liquidacoes).

    Sinal:
      - payload sem dict ou sem key esperada -> empty (envelope corrompido)
      - array non-empty -> complete (dia teve operacao)
      - array vazio mas http=200 -> empty (dia legitimamente sem mov;
        cobertura UI deve diferenciar de "fetch falhou")
    """
    del ua_nome  # nao usado — completeness e propriedade do payload
    if not isinstance(payload, dict):
        return "empty"
    # Aceita aquisicaoConsolidada OU liquidadosBaixados (uma key por endpoint).
    for v in payload.values():
        if isinstance(v, list) and v:
            return "complete"
    return "empty"


# Map tipo_de_mercado -> assessor especifico. Tipos ausentes do mapa caem
# no default permissivo (`_default_assess`) — `complete` quando http==200.
_ASSESSORS = {
    "mec": _assess_mec,
    "rf": _assess_rf,
    # Endpoint CSV assincrono — payload e metadata do report file.
    "fidc-estoque": _assess_csv_report,
    # Endpoints JSON sincronos (split por dia em custodia.py). Payload e
    # array de items inline, nao metadata de CSV.
    "fidc-custodia/aquisicao-consolidada": _assess_window_json_report,
    "fidc-custodia/liquidados-baixados": _assess_window_json_report,
    # TODO: definir assessor especifico pros 2 abaixo quando aparecerem em
    # producao — provavelmente _assess_window_json_report se for json, ou
    # _assess_csv_report se virar CSV async.
    "fidc-custodia/movimento-aberto": _assess_csv_report,
    "fidc-custodia/detalhes-operacoes": _assess_csv_report,
}


def _default_assess(payload: dict[str, Any] | None, ua_nome: str) -> Completeness:
    """Sem perfil especifico: se ha qualquer payload nao-vazio, marca complete.
    Envelope vazio (lista de relatorios None ou len==0) marca empty."""
    if not isinstance(payload, dict):
        return "empty"
    relatorios = payload.get("relatórios")
    if not isinstance(relatorios, dict):
        return "empty"
    has_any_data = any(
        isinstance(v, list) and len(v) > 0
        for v in relatorios.values()
    )
    if has_any_data:
        return "complete"
    return "empty"


def assess_completeness(
    *,
    tipo_de_mercado: str,
    payload: dict[str, Any] | None,
    http_status: int,
    ua_nome: str | None,
) -> Completeness | None:
    """Classifica o payload em `complete | partial | empty`.

    Retorna `None` quando faltar contexto (`ua_nome=None`) E o tipo exigir
    contexto pra avaliar (mec/rf usam o nome da UA). Para tipos default, a
    avaliacao acontece sem UA.

    Args:
        tipo_de_mercado: chave canonica do raw (ex.: 'mec', 'rf',
            'conta-corrente'). Ver `_ASSESSORS`.
        payload: body JSON cru da QiTech (pode ser None se a fonte e CSV).
        http_status: status HTTP do fetch. != 200 sempre conta como `empty`.
        ua_nome: nome cru da UA (ex.: 'REALINVEST FIDC') quando relevante.

    Returns:
        'complete' | 'partial' | 'empty' | None (None = nao avaliado).
    """
    # 4xx/5xx: a fonte explicitamente nao publicou — empty cobre o caso.
    if http_status != 200:
        return "empty"

    assessor = _ASSESSORS.get(tipo_de_mercado)
    if assessor is not None:
        if not ua_nome:
            # Tipo exige contexto da UA pra avaliar e nao temos — nao chuta.
            return None
        return assessor(payload, ua_nome)

    # Tipo sem perfil — usa default permissivo.
    return _default_assess(payload, ua_nome or "")
