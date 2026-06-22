"""Mapper de protestos CENPROT-SP (Infosimples `cenprot-sp/protestos`) -> canonico.

Fonte: protestosp.com.br (Central de Protesto do Estado de SP) via Infosimples.
UMA chamada (token + cnpj/cpf, SEM login gov.br). Retorna, por cartorio de SP,
os titulos protestados com valor + cancelamento + quitacao.

LIMITES desta fonte (tratados com honestidade — §14.6):
- NAO traz o credor (cedente/apresentante). Esse so existe na consulta
  `ieptb/protestos/detalhes-sp` (login gov.br), fora de escopo nesta versao.
  Por isso `credor` fica sempre None aqui.
- NAO traz DATA por titulo (so valor/cancelamento/quitacao).
- Retorna so a PRIMEIRA PAGINA do site (`retornou_todos_os_protestos_do_site`).
  Quando false, os titulos listados sao incompletos vs `quantidade_titulos` — a
  flag `completo` propaga isso pra view.

Mapper tolerante a nomes de campo (candidatos) + fallback generico (`_walk`)
para shapes inesperados. Bronze e a verdade; re-map idempotente.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# ─── Chaves candidatas (toleram variacao de layout do vendor) ────────────────
_K_QTD = ("quantidade_titulos", "qtd_titulos", "quantidade_protestos",
          "numero_total_protestos", "total")
_K_COMPLETO = ("retornou_todos_os_protestos_do_site", "retornou_todos",
               "completo")

_K_CARTORIO = ("nome", "cartorio", "nome_cartorio", "tabelionato")
_K_CART_NUM = ("codigo", "numero_cartorio", "cartorio_numero", "numero")
_K_CIDADE = ("cidade", "municipio")
_K_UF = ("uf", "estado", "sigla_uf")

_K_VALOR = ("valor", "valor_protestado", "valor_titulo")
_K_VALOR_CANCEL = ("valor_cancelamento", "valor_cancelado")
_K_VALOR_QUITACAO = ("valor_quitacao", "valor_quitado")
# Credor — NAO existe no cenprot-sp; mantido p/ fallback caso a fonte mude.
_K_CREDOR = ("nome_cedente", "cedente", "nome_apresentante", "apresentante",
             "credor", "sacador", "portador", "nome_credor")
_K_DOC_CREDOR = ("documento_credor", "cnpj_credor", "cnpj_credor_afetado")
_K_DATA = ("data_protesto", "data", "data_titulo")
_K_VENC = ("data_vencimento", "vencimento")
_K_ESPECIE = ("especie", "tipo_titulo")


@dataclass(slots=True)
class ProtestoTitulo:
    cartorio: str | None = None
    cartorio_numero: str | None = None
    cidade: str | None = None
    uf: str | None = None
    data_protesto: date | None = None
    data_vencimento: date | None = None
    valor: Decimal | None = None
    valor_cancelamento: Decimal | None = None
    valor_quitacao: Decimal | None = None
    credor: str | None = None
    documento_credor: str | None = None
    especie: str | None = None
    detalhe: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProtestoFields:
    constam_protestos: bool = False
    qtd_total: int = 0
    valor_total: Decimal | None = None
    # True quando a fonte garantiu ter retornado TODOS os protestos (vs so a 1a
    # pagina). False/None -> a tabela e parcial; a view avisa.
    completo: bool = True
    com_credor: bool = False
    observacoes: str | None = None
    titulos: list[ProtestoTitulo] = field(default_factory=list)


def _g(d: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Primeiro valor nao-vazio dentre as chaves candidatas (case-insensitive)."""
    lower = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        v = lower.get(k.lower())
        if v not in (None, "", [], {}):
            return v
    return None


def _to_decimal(raw: Any) -> Decimal | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, (int, float)):
        return Decimal(str(raw))
    s = re.sub(r"[^\d,.\-]", "", str(raw))
    if not s or s in ("-", "."):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except (InvalidOperation, ValueError):
        return None


def _to_date(raw: Any) -> date | None:
    if not raw:
        return None
    s = str(raw).strip()
    m = re.match(r"^(\d{2})/(\d{2})/(\d{4})", s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        return None


def _norm_uf(raw: Any) -> str | None:
    s = str(raw or "").strip().upper()
    return s if len(s) == 2 and s.isalpha() else None


def _as_bool(raw: Any, default: bool) -> bool:
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.strip().lower() in ("true", "sim", "1", "s", "yes")
    if raw is None:
        return default
    return bool(raw)


def _make_titulo(node: dict[str, Any], ctx: dict[str, str | None]) -> ProtestoTitulo:
    credor = _g(node, _K_CREDOR)
    doc_credor = _g(node, _K_DOC_CREDOR)
    detalhe = {k: v for k, v in node.items() if not isinstance(v, (list, dict))}
    if ctx.get("comarca"):
        detalhe.setdefault("comarca", ctx["comarca"])
    return ProtestoTitulo(
        cartorio=(str(_g(node, _K_CARTORIO)) if _g(node, _K_CARTORIO) else ctx.get("cartorio")),
        cartorio_numero=(
            str(_g(node, _K_CART_NUM)) if _g(node, _K_CART_NUM) else ctx.get("cartorio_numero")
        ),
        cidade=(str(_g(node, _K_CIDADE)) if _g(node, _K_CIDADE) else ctx.get("cidade")),
        uf=(_norm_uf(_g(node, _K_UF)) or ctx.get("uf")),
        data_protesto=_to_date(_g(node, _K_DATA)),
        data_vencimento=_to_date(_g(node, _K_VENC)),
        valor=_to_decimal(_g(node, _K_VALOR)),
        valor_cancelamento=_to_decimal(_g(node, _K_VALOR_CANCEL)),
        valor_quitacao=_to_decimal(_g(node, _K_VALOR_QUITACAO)),
        credor=(str(credor).strip() if credor else None),
        documento_credor=(re.sub(r"\D", "", str(doc_credor)) or None if doc_credor else None),
        especie=(str(_g(node, _K_ESPECIE)) if _g(node, _K_ESPECIE) else None),
        detalhe=detalhe,
    )


def _has_title_signal(d: dict[str, Any]) -> bool:
    return _g(d, _K_VALOR) is not None or _g(d, _K_DATA) is not None


def _walk(node: Any, ctx: dict[str, str | None], out: list[ProtestoTitulo]) -> None:
    """Fallback generico: desce listas/dicts coletando titulos-folha (carrega
    contexto de cartorio/cidade/uf). Usado quando o shape `cartorios` esperado
    nao aparece."""
    if isinstance(node, list):
        for it in node:
            _walk(it, ctx, out)
        return
    if not isinstance(node, dict):
        return
    ctx2 = dict(ctx)
    for slot, keys in (("cartorio", _K_CARTORIO), ("cartorio_numero", _K_CART_NUM),
                       ("cidade", _K_CIDADE), ("uf", _K_UF)):
        v = _g(node, keys)
        if v not in (None, ""):
            ctx2[slot] = _norm_uf(v) if slot == "uf" else str(v)
    children = [
        v for v in node.values()
        if (isinstance(v, list) and v and any(isinstance(i, dict) for i in v))
        or isinstance(v, dict)
    ]
    if children:
        for cv in children:
            _walk(cv, ctx2, out)
        return
    if _has_title_signal(node):
        out.append(_make_titulo(node, ctx2))


def map_protesto(first: dict[str, Any]) -> ProtestoFields:
    """Mapeia o data[0] de uma consulta `cenprot-sp/protestos` para o canonico.

    Estrutura esperada: `cartorios: {"<UF>": [ {<cartorio>, protestos:[...]} ]}`.
    Cai no `_walk` generico se o shape vier diferente.
    """
    titulos: list[ProtestoTitulo] = []
    cartorios = first.get("cartorios")
    if isinstance(cartorios, dict):
        for uf_key, lista in cartorios.items():
            if not isinstance(lista, list):
                continue
            uf = _norm_uf(uf_key)
            for cart in lista:
                if not isinstance(cart, dict):
                    continue
                ctx: dict[str, str | None] = {
                    "cartorio": (str(_g(cart, _K_CARTORIO)) if _g(cart, _K_CARTORIO) else None),
                    "cartorio_numero": (str(_g(cart, _K_CART_NUM)) if _g(cart, _K_CART_NUM) else None),
                    "cidade": (str(_g(cart, _K_CIDADE)) if _g(cart, _K_CIDADE) else None),
                    "uf": uf or _norm_uf(_g(cart, _K_UF)),
                    "comarca": (str(cart.get("comarca")) if cart.get("comarca") else None),
                }
                prot = cart.get("protestos")
                if isinstance(prot, list) and prot:
                    for p in prot:
                        if isinstance(p, dict):
                            titulos.append(_make_titulo(p, ctx))
                else:
                    # Cartorio sem detalhe por titulo -> 1 linha sintetica do
                    # cartorio (valor agregado), pra nao esconder o cartorio.
                    titulos.append(_make_titulo(cart, ctx))
    else:
        _walk(first, {}, titulos)

    qtd_explicit = _g(first, _K_QTD)
    qtd_total = (
        int(re.sub(r"\D", "", str(qtd_explicit)) or 0)
        if qtd_explicit is not None
        else len(titulos)
    )
    soma = sum((t.valor for t in titulos if t.valor is not None), Decimal(0))
    valor_total = soma if soma else None

    obs = _g(first, ("observacoes", "observacao", "mensagem"))
    return ProtestoFields(
        constam_protestos=qtd_total > 0 or bool(titulos),
        qtd_total=qtd_total,
        valor_total=valor_total,
        completo=_as_bool(_g(first, _K_COMPLETO), default=True),
        com_credor=any(t.credor for t in titulos),
        observacoes=(str(obs).strip() if obs else None),
        titulos=titulos,
    )


# ─── Cadeia IEPTB (consulta COM credor — submenu "Protestos · Credor SP") ─────
# A consulta nacional `ieptb/protestos` devolve, por cartorio de SP, um token
# `obter_detalhes` que alimenta `ieptb/protestos/detalhes-sp` (onde vem o credor
# nome_cedente/nome_apresentante). O mapper de titulos e o mesmo `map_protesto`
# (o detalhe-sp e uma lista flat `protestos[]`, coberta pelo fallback `_walk`,
# e `_make_titulo` ja extrai o credor via _K_CREDOR).

_K_OBTER_DETALHES = ("obter_detalhes", "detalhes", "token_detalhes")


@dataclass(slots=True)
class SpDetailRequest:
    """Pedido de detalhe SP derivado da consulta nacional IEPTB (carrega o token
    `obter_detalhes` + o contexto de cartorio/cidade/uf de origem)."""

    obter_detalhes: str
    cartorio: str | None = None
    cidade: str | None = None
    uf: str | None = None


def extract_sp_detail_requests(first: dict[str, Any]) -> list[SpDetailRequest]:
    """Varre o response NACIONAL (ieptb/protestos) e coleta os tokens
    `obter_detalhes` (SP), com de-dup e contexto de cartorio. Cada token vira uma
    chamada ao detalhe SP (onde o credor aparece)."""
    out: list[SpDetailRequest] = []
    seen: set[str] = set()

    def _walk_tokens(node: Any, ctx: dict[str, str | None]) -> None:
        if isinstance(node, list):
            for it in node:
                _walk_tokens(it, ctx)
            return
        if not isinstance(node, dict):
            return
        ctx2 = dict(ctx)
        for slot, keys in (("cartorio", _K_CARTORIO), ("cidade", _K_CIDADE), ("uf", _K_UF)):
            v = _g(node, keys)
            if v not in (None, ""):
                ctx2[slot] = _norm_uf(v) if slot == "uf" else str(v)
        token = _g(node, _K_OBTER_DETALHES)
        if token and isinstance(token, (str, int)):
            tok = str(token)
            if tok not in seen:
                seen.add(tok)
                out.append(SpDetailRequest(
                    obter_detalhes=tok, cartorio=ctx2.get("cartorio"),
                    cidade=ctx2.get("cidade"), uf=ctx2.get("uf"),
                ))
        for v in node.values():
            if isinstance(v, (list, dict)):
                _walk_tokens(v, ctx2)

    _walk_tokens(first, {})
    return out
