"""Mapper de protestos (IEPTB/CENPROT via Infosimples) -- bronze -> canonico.

TOLERANTE a layout: a Infosimples nao publica schema estavel e os nomes de
campo variam entre a consulta nacional e o detalhe SP. Como o bronze guarda o
RESPONSE cru (verdade), este mapper le chaves CANDIDATAS e degrada para None
quando ausentes -- corrigir = ajustar as listas de candidatos + re-rodar o
mapper (sem round-trip pago). GOTCHA: os nomes exatos sao confirmados/ajustados
no primeiro smoke real (espelha a descoberta `texto`/`descricao` do JUCESP).

Provimento CNJ 225/2026: a consulta NACIONAL NAO traz credor; o detalhe SP
pode. Os candidatos de credor (credor/cedente/apresentante/sacador/portador)
ficam aqui para capturar o dado onde a fonte ainda devolver.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# ─── Chaves candidatas (toleram variacao de layout do vendor) ────────────────
_K_QTD = ("quantidade_titulos", "qtd_titulos", "numero_total_protestos",
          "total_protestos", "quantidade_protestos", "qtd_protestos", "total")
_K_VALOR_TOTAL = ("valor_total", "valor_total_protestos", "valor_protestado_total",
                  "valor_protestos", "valor")
_K_CONSTAM = ("constam_protestos", "consta_protesto", "possui_protestos",
              "tem_protesto", "constam")
_K_OBS = ("observacoes", "observacao", "mensagem", "obs")

_K_CARTORIO = ("cartorio", "nome_cartorio", "tabelionato", "nome")
_K_CART_NUM = ("numero_cartorio", "cartorio_numero", "codigo_cartorio", "numero")
_K_CIDADE = ("cidade", "municipio")
_K_UF = ("uf", "estado", "sigla_uf")

_K_DATA = ("data_protesto", "data", "data_titulo", "data_apontamento",
           "data_registro")
_K_VENC = ("data_vencimento", "vencimento")
_K_VALOR = ("valor", "valor_protestado", "valor_titulo")
# Credor do titulo -- so popula onde a fonte devolver (tipicamente o detalhe SP).
# Confirmado no doc Infosimples ieptb/protestos/detalhes-sp (v2.2.37): cada
# protesto traz `nome_cedente` (credor original) e `nome_apresentante` (quem
# apresentou o titulo, em geral banco/cobrador). Cedente e o melhor "credor".
_K_CREDOR = ("nome_cedente", "cedente", "nome_apresentante", "apresentante",
             "credor", "sacador", "portador", "nome_credor", "favorecido")
# Documento do CREDOR -- NAO confundir com `cpf_cnpj` do protesto (= o SACADO/
# devedor consultado). Por isso `cpf_cnpj` fica de fora desta lista.
_K_DOC_CREDOR = ("documento_credor", "cnpj_credor", "cpf_cnpj_credor",
                 "cnpj_credor_afetado", "doc_credor")
_K_ESPECIE = ("especie", "tipo_titulo", "especie_titulo")

# Token opaco que a consulta NACIONAL (ieptb/protestos) devolve por cartorio de
# SP e que alimenta o `obter_detalhes` do detalhe SP (ieptb/protestos/
# detalhes-sp). E o elo do fluxo 2-passos nacional -> detalhe.
_K_OBTER_DETALHES = ("obter_detalhes", "detalhes", "token_detalhes")


@dataclass(slots=True)
class ProtestoTitulo:
    cartorio: str | None = None
    cartorio_numero: str | None = None
    cidade: str | None = None
    uf: str | None = None
    data_protesto: date | None = None
    data_vencimento: date | None = None
    valor: Decimal | None = None
    credor: str | None = None
    documento_credor: str | None = None
    especie: str | None = None
    detalhe: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProtestoFields:
    constam_protestos: bool = False
    qtd_total: int = 0
    valor_total: Decimal | None = None
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
    if not s:
        return None
    # pt-BR "1.234,56" -> "1234.56"; "1234,56" -> "1234.56"; "1234.56" mantem.
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
    return s[:2] if len(s) >= 2 and s.isalpha() else (s if len(s) == 2 else None)


def _has_title_signal(d: dict[str, Any]) -> bool:
    return _g(d, _K_DATA) is not None or _g(d, _K_VALOR) is not None


def _make_titulo(node: dict[str, Any], ctx: dict[str, str | None]) -> ProtestoTitulo:
    credor = _g(node, _K_CREDOR)
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
        credor=(str(credor).strip() if credor else None),
        documento_credor=(
            re.sub(r"\D", "", str(_g(node, _K_DOC_CREDOR))) or None
            if _g(node, _K_DOC_CREDOR)
            else None
        ),
        especie=(str(_g(node, _K_ESPECIE)) if _g(node, _K_ESPECIE) else None),
        detalhe={k: v for k, v in node.items() if not isinstance(v, (list, dict))},
    )


def _walk(node: Any, ctx: dict[str, str | None], out: list[ProtestoTitulo]) -> None:
    """Desce a arvore (estado -> cartorio -> titulo) coletando titulos-folha.

    Carrega o contexto (cartorio/cidade/uf) dos niveis ancestrais. Um dict que
    contem lista(s) de filhos e tratado como AGREGADO (desce, nao emite); um
    dict-folha com sinal de titulo (data/valor) vira um ProtestoTitulo.
    """
    if isinstance(node, list):
        for it in node:
            _walk(it, ctx, out)
        return
    if not isinstance(node, dict):
        return

    ctx2 = dict(ctx)
    for slot, keys in (
        ("cartorio", _K_CARTORIO),
        ("cartorio_numero", _K_CART_NUM),
        ("cidade", _K_CIDADE),
        ("uf", _K_UF),
    ):
        v = _g(node, keys)
        if v not in (None, ""):
            ctx2[slot] = _norm_uf(v) if slot == "uf" else str(v)

    child_lists = [
        v for v in node.values()
        if isinstance(v, list) and v and any(isinstance(i, dict) for i in v)
    ]
    if child_lists:
        for cl in child_lists:
            _walk(cl, ctx2, out)
        return
    if _has_title_signal(node):
        out.append(_make_titulo(node, ctx2))


def map_protesto(
    first: dict[str, Any], ctx: dict[str, str | None] | None = None
) -> ProtestoFields:
    """Mapeia o data[0] de uma consulta de protesto para o canonico.

    Robusto a layout: extrai contadores do header e desce a arvore coletando
    titulos. Quando a fonte so devolve agregados (sem linha por titulo), os
    titulos ficam vazios e o header ainda carrega qtd/valor.

    `ctx` semeia o contexto de cartorio/cidade/uf -- usado no detalhe SP, cujo
    response nao repete o cartorio (ele veio do token `obter_detalhes` da
    consulta nacional). O caller passa o cartorio/cidade/uf de origem.
    """
    titulos: list[ProtestoTitulo] = []
    _walk(first, dict(ctx or {}), titulos)

    qtd_explicit = _g(first, _K_QTD)
    valor_explicit = _to_decimal(_g(first, _K_VALOR_TOTAL))
    constam_explicit = _g(first, _K_CONSTAM)

    qtd_total = (
        int(re.sub(r"\D", "", str(qtd_explicit)) or 0)
        if qtd_explicit is not None
        else len(titulos)
    )
    valor_total = valor_explicit
    if valor_total is None and titulos:
        soma = sum((t.valor for t in titulos if t.valor is not None), Decimal(0))
        valor_total = soma if soma else None

    if isinstance(constam_explicit, bool):
        constam = constam_explicit
    elif isinstance(constam_explicit, str):
        constam = constam_explicit.strip().lower() in ("true", "sim", "1", "s")
    else:
        constam = qtd_total > 0 or bool(titulos)

    obs = _g(first, _K_OBS)
    return ProtestoFields(
        constam_protestos=constam,
        qtd_total=qtd_total,
        valor_total=valor_total,
        com_credor=any(t.credor for t in titulos),
        observacoes=(str(obs).strip() if obs else None),
        titulos=titulos,
    )


@dataclass(slots=True)
class SpDetailRequest:
    """Um pedido de detalhe SP derivado da consulta nacional.

    `obter_detalhes` e o token opaco a passar para ieptb/protestos/detalhes-sp;
    cartorio/cidade/uf sao o contexto de origem (o response do detalhe nao
    repete o cartorio).
    """

    obter_detalhes: str
    cartorio: str | None = None
    cidade: str | None = None
    uf: str | None = None


def extract_sp_detail_requests(first: dict[str, Any]) -> list[SpDetailRequest]:
    """Varre o response NACIONAL e coleta os tokens `obter_detalhes` (SP).

    Cada token alimenta uma chamada ao detalhe SP (onde o credor aparece).
    Carrega o cartorio/cidade/uf do no que produziu o token. De-duplica por
    token. GOTCHA: confirmar a chave exata no primeiro smoke da consulta
    nacional -- candidatos em _K_OBTER_DETALHES.
    """
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
        for slot, keys in (
            ("cartorio", _K_CARTORIO),
            ("cidade", _K_CIDADE),
            ("uf", _K_UF),
        ):
            v = _g(node, keys)
            if v not in (None, ""):
                ctx2[slot] = _norm_uf(v) if slot == "uf" else str(v)
        token = _g(node, _K_OBTER_DETALHES)
        if token and isinstance(token, (str, int)):
            tok = str(token)
            if tok not in seen:
                seen.add(tok)
                out.append(
                    SpDetailRequest(
                        obter_detalhes=tok,
                        cartorio=ctx2.get("cartorio"),
                        cidade=ctx2.get("cidade"),
                        uf=ctx2.get("uf"),
                    )
                )
        for v in node.values():
            if isinstance(v, (list, dict)):
                _walk_tokens(v, ctx2)

    _walk_tokens(first, {})
    return out
