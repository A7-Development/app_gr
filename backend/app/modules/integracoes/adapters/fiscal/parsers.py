"""Extracao curada dos documentos fiscais (dict canonico -> campos silver).

Trabalha sobre o dict produzido por `xml_json.xml_to_dict`. Curadoria da
regra >=95% + normalizacao por conceito (decisao 2026-07-07):
- documento da parte = CNPJ OU CPF (uma coluna);
- autorizacao = protNFe/protCTe (cStat 100 ou 150 = autorizada);
- tolerante a ausencia: campo faltando vira None (nunca explode) -- o raw
  JSONB integral esta sempre ao lado para os casos exoticos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation


def _get(obj: dict | None, *path: str) -> dict | list | str | None:
    cur: dict | list | str | None = obj
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _text(obj: dict | None, *path: str) -> str | None:
    v = _get(obj, *path)
    if isinstance(v, dict):
        v = v.get("#text")
    if isinstance(v, list):
        v = v[0] if v else None
        if isinstance(v, dict):
            v = v.get("#text")
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return None


def _as_list(v: dict | list | None) -> list:
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _decimal(s: str | None) -> Decimal | None:
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _int(s: str | None) -> int | None:
    try:
        return int(s) if s else None
    except ValueError:
        return None


def _dt(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


def _date(s: str | None) -> date | None:
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None


def _parte_documento(parte: dict | None) -> tuple[str | None, str | None]:
    """(documento, tipo_pessoa) a partir de CNPJ|CPF do bloco da parte."""
    doc = _text(parte, "CNPJ")
    if doc:
        return doc, "pj"
    doc = _text(parte, "CPF")
    if doc:
        return doc, "pf"
    return None, None


# cStat de documento utilizavel: 100=autorizado, 150=autorizado fora de prazo.
_CSTAT_AUTORIZADA = {100, 150}


@dataclass
class DuplicataParsed:
    numero: str
    vencimento: date | None
    valor: Decimal | None


@dataclass
class NfeParsed:
    chave_acesso: str
    schema_versao: str | None
    numero: int
    serie: int | None
    modelo: str | None
    natureza_operacao: str | None
    data_emissao: datetime | None
    tipo_operacao: str | None
    finalidade: str | None
    emitente_documento: str
    emitente_nome: str | None
    emitente_uf: str | None
    emitente_municipio: str | None
    destinatario_documento: str | None
    destinatario_tipo_pessoa: str | None
    destinatario_nome: str | None
    destinatario_uf: str | None
    destinatario_municipio: str | None
    valor_produtos: Decimal | None
    valor_frete: Decimal | None
    valor_desconto: Decimal | None
    valor_total: Decimal | None
    valor_tributos: Decimal | None
    modalidade_frete: str | None
    meio_pagamento: str | None
    numero_fatura: str | None
    valor_fatura_liquido: Decimal | None
    cstat: int | None
    autorizada: bool
    protocolo: str | None
    data_autorizacao: datetime | None
    duplicatas: list[DuplicataParsed] = field(default_factory=list)


def parse_nfe(doc: dict) -> NfeParsed | None:
    """Extrai o silver curado de um nfeProc canonico. None = sem chave (lixo)."""
    inf = _get(doc, "NFe", "infNFe")
    if not isinstance(inf, dict):
        return None
    prot = _get(doc, "protNFe", "infProt")
    if isinstance(prot, list):
        prot = prot[0] if prot else None
    chave = _text(prot, "chNFe") if isinstance(prot, dict) else None
    if not chave:
        raw_id = inf.get("@Id") or ""
        chave = raw_id.removeprefix("NFe") or None
    if not chave:
        return None

    ide = _get(inf, "ide") if isinstance(_get(inf, "ide"), dict) else {}
    emit = _get(inf, "emit") if isinstance(_get(inf, "emit"), dict) else {}
    dest = _get(inf, "dest") if isinstance(_get(inf, "dest"), dict) else {}
    tot = _get(inf, "total", "ICMSTot")
    tot = tot if isinstance(tot, dict) else {}
    cobr = _get(inf, "cobr") if isinstance(_get(inf, "cobr"), dict) else {}
    emit_doc, _ = _parte_documento(emit)
    dest_doc, dest_tipo = _parte_documento(dest)
    if not emit_doc:
        return None

    dups: list[DuplicataParsed] = []
    for dup in _as_list(cobr.get("dup")):
        if not isinstance(dup, dict):
            continue
        numero = _text(dup, "nDup")
        if not numero:
            continue
        dups.append(
            DuplicataParsed(
                numero=numero,
                vencimento=_date(_text(dup, "dVenc")),
                valor=_decimal(_text(dup, "vDup")),
            )
        )

    det_pag = _as_list(_get(inf, "pag", "detPag"))
    meio_pag = _text(det_pag[0], "tPag") if det_pag and isinstance(det_pag[0], dict) else None

    cstat = _int(_text(prot, "cStat")) if isinstance(prot, dict) else None
    return NfeParsed(
        chave_acesso=chave,
        schema_versao=(doc.get("@versao") if isinstance(doc.get("@versao"), str) else None),
        numero=_int(_text(ide, "nNF")) or 0,
        serie=_int(_text(ide, "serie")),
        modelo=_text(ide, "mod"),
        natureza_operacao=_text(ide, "natOp"),
        data_emissao=_dt(_text(ide, "dhEmi")),
        tipo_operacao=_text(ide, "tpNF"),
        finalidade=_text(ide, "finNFe"),
        emitente_documento=emit_doc,
        emitente_nome=_text(emit, "xNome"),
        emitente_uf=_text(emit, "enderEmit", "UF"),
        emitente_municipio=_text(emit, "enderEmit", "xMun"),
        destinatario_documento=dest_doc,
        destinatario_tipo_pessoa=dest_tipo,
        destinatario_nome=_text(dest, "xNome"),
        destinatario_uf=_text(dest, "enderDest", "UF"),
        destinatario_municipio=_text(dest, "enderDest", "xMun"),
        valor_produtos=_decimal(_text(tot, "vProd")),
        valor_frete=_decimal(_text(tot, "vFrete")),
        valor_desconto=_decimal(_text(tot, "vDesc")),
        valor_total=_decimal(_text(tot, "vNF")),
        valor_tributos=_decimal(_text(tot, "vTotTrib")),
        modalidade_frete=_text(inf, "transp", "modFrete"),
        meio_pagamento=meio_pag,
        numero_fatura=_text(cobr, "fat", "nFat"),
        valor_fatura_liquido=_decimal(_text(cobr, "fat", "vLiq")),
        cstat=cstat,
        autorizada=cstat in _CSTAT_AUTORIZADA,
        protocolo=_text(prot, "nProt") if isinstance(prot, dict) else None,
        data_autorizacao=_dt(_text(prot, "dhRecbto")) if isinstance(prot, dict) else None,
        duplicatas=dups,
    )


@dataclass
class CteParsed:
    chave_acesso: str
    schema_versao: str | None
    numero: int
    serie: int | None
    cfop: str | None
    natureza_operacao: str | None
    data_emissao: datetime | None
    tipo_cte: str | None
    municipio_inicio: str | None
    uf_inicio: str | None
    municipio_fim: str | None
    uf_fim: str | None
    emitente_documento: str
    emitente_nome: str | None
    remetente_documento: str | None
    remetente_nome: str | None
    destinatario_documento: str | None
    destinatario_nome: str | None
    expedidor_documento: str | None
    recebedor_documento: str | None
    tomador_codigo: str | None
    valor_prestacao: Decimal | None
    valor_receber: Decimal | None
    valor_carga: Decimal | None
    produto_predominante: str | None
    cstat: int | None
    autorizada: bool
    protocolo: str | None
    data_autorizacao: datetime | None
    chaves_nfe: list[str] = field(default_factory=list)


def parse_cte(doc: dict) -> CteParsed | None:
    """Extrai o silver curado de um cteProc canonico."""
    inf = _get(doc, "CTe", "infCte")
    if not isinstance(inf, dict):
        return None
    prot = _get(doc, "protCTe", "infProt")
    if isinstance(prot, list):
        prot = prot[0] if prot else None
    chave = _text(prot, "chCTe") if isinstance(prot, dict) else None
    if not chave:
        raw_id = inf.get("@Id") or ""
        chave = raw_id.removeprefix("CTe") or None
    if not chave:
        return None

    ide = _get(inf, "ide") if isinstance(_get(inf, "ide"), dict) else {}
    emit = _get(inf, "emit") if isinstance(_get(inf, "emit"), dict) else {}
    rem = _get(inf, "rem") if isinstance(_get(inf, "rem"), dict) else {}
    dest = _get(inf, "dest") if isinstance(_get(inf, "dest"), dict) else {}
    exped = _get(inf, "exped") if isinstance(_get(inf, "exped"), dict) else {}
    receb = _get(inf, "receb") if isinstance(_get(inf, "receb"), dict) else {}
    vprest = _get(inf, "vPrest") if isinstance(_get(inf, "vPrest"), dict) else {}
    carga = _get(inf, "infCTeNorm", "infCarga")
    carga = carga if isinstance(carga, dict) else {}
    emit_doc, _ = _parte_documento(emit)
    if not emit_doc:
        return None

    # toma: CT-e 3.x usa ide/toma3/toma ou ide/toma4/toma.
    tomador = _text(ide, "toma3", "toma") or _text(ide, "toma4", "toma") or _text(ide, "toma")

    chaves = []
    for inf_nfe in _as_list(_get(inf, "infCTeNorm", "infDoc", "infNFe")):
        if isinstance(inf_nfe, dict):
            ch = _text(inf_nfe, "chave")
            if ch:
                chaves.append(ch)

    cstat = _int(_text(prot, "cStat")) if isinstance(prot, dict) else None
    return CteParsed(
        chave_acesso=chave,
        schema_versao=(doc.get("@versao") if isinstance(doc.get("@versao"), str) else None),
        numero=_int(_text(ide, "nCT")) or 0,
        serie=_int(_text(ide, "serie")),
        cfop=_text(ide, "CFOP"),
        natureza_operacao=_text(ide, "natOp"),
        data_emissao=_dt(_text(ide, "dhEmi")),
        tipo_cte=_text(ide, "tpCTe"),
        municipio_inicio=_text(ide, "xMunIni"),
        uf_inicio=_text(ide, "UFIni"),
        municipio_fim=_text(ide, "xMunFim"),
        uf_fim=_text(ide, "UFFim"),
        emitente_documento=emit_doc,
        emitente_nome=_text(emit, "xNome"),
        remetente_documento=_parte_documento(rem)[0],
        remetente_nome=_text(rem, "xNome"),
        destinatario_documento=_parte_documento(dest)[0],
        destinatario_nome=_text(dest, "xNome"),
        expedidor_documento=_parte_documento(exped)[0],
        recebedor_documento=_parte_documento(receb)[0],
        tomador_codigo=tomador,
        valor_prestacao=_decimal(_text(vprest, "vTPrest")),
        valor_receber=_decimal(_text(vprest, "vRec")),
        valor_carga=_decimal(_text(carga, "vCarga")),
        produto_predominante=_text(carga, "proPred"),
        cstat=cstat,
        autorizada=cstat in _CSTAT_AUTORIZADA,
        protocolo=_text(prot, "nProt") if isinstance(prot, dict) else None,
        data_autorizacao=_dt(_text(prot, "dhRecbto")) if isinstance(prot, dict) else None,
        chaves_nfe=chaves,
    )
