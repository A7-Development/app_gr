"""Mapper: payload /v2/conta-corrente/bank-account/statement/{ag}/{cc}/{ini}/{fim}
-> dicts canonicos.

Granularidade: 1 chamada -> N linhas em wh_extrato_bancario (1 por lancamento).

source_id por lancamento = `bank_account_statement|{ua}|{ag}|{conta}|{YYYY-MM-DD}|{lancamento_id}`
(quando QiTech expoe o id estavel `lancamento`); fallback `sha16(item)` quando
ausente. Re-fetch do mesmo periodo nao duplica via UQ (business key explicita).

Schema REAL (observado em prod 2026-05, payload_shapes/bank_account.statement.md):

    {
        "extrato": [
            {
                "data": "2026-05-26T00:00:00.000",        # data contabil (crit.)
                "dataHora": "26/05/2026 07:15:08",          # timestamp do evento
                "valor": 1559348.82,                        # SEMPRE positivo
                "tipoLancamento": "C",                      # C=credito D=debito S=saldo
                "documento": 0,
                "lancamento": 50957269,                     # id estavel (int)
                "historico": {                              # objeto, NAO string
                    "codigo": "0497",                       # codigo de historico
                    "descricao": "TED - STR FORNECEDOR X"   # texto do lancamento
                },
                "contraparte": {
                    "nome": "FORNECEDOR X",                 # as vezes literal "null"
                    "inscricao": 42449234000160,            # CPF/CNPJ (int, sem pad)
                    "tipoPessoa": "J",                      # J|F (guia o zero-pad)
                    "indicadorEnviadoRecebido": "R"         # R=recebido E=enviado
                }
            },
            ...
        ]
    }

Pontos criticos do shape real (corrigidos em qitech_adapter_v0.5.0):
- O sinal NAO vem no `valor` (sempre positivo) — vem em `tipoLancamento`.
- `tipoLancamento="S"` sao linhas de SALDO (snapshot de saldo, nao movimento) —
  descartadas aqui; saldo vive em wh_saldo_bancario_diario (bank_account.balance).
- `historico` e um objeto {codigo, descricao}, nao string: `descricao` (texto) vai
  pra coluna `descricao` (faz parte da business key e e o campo pesquisavel);
  `codigo` vai pra coluna `historico` (codigo de historico bancario).
- Doc da contraparte vem em `inscricao` (inteiro) — zero-pad por tipoPessoa.

Lancamentos sem (data_lancamento E valor E tipo C/D) sao descartados — sao campos
criticos. Mapper aceita ainda envelope em lista direta / "lancamentos" / "items"
/ "movimentos" / "relatorios.*" por compatibilidade defensiva.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from app.modules.integracoes.adapters.admin.qitech.hashing import sha256_of_row
from app.modules.integracoes.adapters.admin.qitech.mappers._common import (
    build_provenance,
    normalize_str_or_none,
    parse_iso_or_none,
    to_decimal,
)


def _extract_items(payload: Any) -> list[Any]:
    """Encontra a lista de lancamentos no payload, tolerando varios formatos."""
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("extrato", "lancamentos", "lançamentos", "items", "movimentos"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
        # Forma nested em "relatorios"/"relatórios"
        relatorios = payload.get("relatorios") or payload.get("relatórios")
        if isinstance(relatorios, dict):
            for key in ("statement", "extrato", "lancamentos", "lançamentos"):
                v = relatorios.get(key)
                if isinstance(v, list):
                    return v
    return []


def _clean_null(value: Any) -> str | None:
    """Como `normalize_str_or_none`, mas trata o literal string `"null"`/`"none"`.

    QiTech envia `"null"` (string) em campos de contraparte vazios (ex.: linhas
    de saldo) em vez de `null` JSON. Sem isso, gravariamos a palavra "null".
    """
    s = normalize_str_or_none(value)
    if s is None:
        return None
    if s.strip().lower() in ("null", "none"):
        return None
    return s


def _parse_datahora(value: Any) -> datetime | None:
    """Parse de `dataHora` no formato BR `DD/MM/YYYY HH:MM:SS` (ou so a data)."""
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y"):
        try:
            return datetime.strptime(raw[: len(fmt) + 6], fmt)
        except ValueError:
            continue
    return None


def _format_doc(raw: Any, *, tipo_pessoa: str | None) -> str | None:
    """Formata `inscricao` (CPF/CNPJ) preservando zeros a esquerda.

    QiTech manda `inscricao` como inteiro (ex.: 42449234000160) — converte pra
    string e zero-pad pra 14 digitos (PJ) ou 11 (PF). `tipoPessoa` 'J'/'F' guia
    o pad; sem ele, infere pelo comprimento. Coluna silver e String(14).
    """
    if raw is None:
        return None
    digits = "".join(ch for ch in str(raw) if ch.isdigit())
    if not digits or int(digits) == 0:
        return None
    tp = (tipo_pessoa or "").strip().upper()
    if tp == "J":
        return digits.zfill(14)
    if tp == "F":
        return digits.zfill(11)
    return digits.zfill(11) if len(digits) <= 11 else digits.zfill(14)


def _pick_data_lancamento(item: dict[str, Any]) -> date | None:
    for key in (
        "data",
        "dataLancamento",
        "dataLançamento",
        "dataLiquidacao",
        "dataLiquidação",
    ):
        v = item.get(key)
        if isinstance(v, str) and v:
            parsed = parse_iso_or_none(v)
            if parsed:
                return parsed.date()
            try:
                return date.fromisoformat(v[:10])
            except ValueError:
                continue
    return None


def _pick_data_movimento(item: dict[str, Any]) -> date | None:
    # Campos ISO (compat com outros formatos) primeiro.
    for key in ("dataMovimento", "dataMovimentacao", "dataOperacao"):
        v = item.get(key)
        if isinstance(v, str) and v:
            parsed = parse_iso_or_none(v)
            if parsed:
                return parsed.date()
            try:
                return date.fromisoformat(v[:10])
            except ValueError:
                continue
    # QiTech statement: `dataHora` = "DD/MM/YYYY HH:MM:SS" e o timestamp do evento.
    dh = _parse_datahora(item.get("dataHora"))
    if dh is not None:
        return dh.date()
    # Fallback: mesma data contabil do lancamento.
    return _pick_data_lancamento(item)


def _pick_valor(item: dict[str, Any]) -> Decimal | None:
    for key in ("valor", "valorMovimento", "valorMovimentacao", "amount"):
        if key in item and item[key] is not None:
            try:
                return to_decimal(item[key])
            except Exception:
                continue
    return None


def _pick_tipo(item: dict[str, Any]) -> str | None:
    """Normaliza para 'C' (credito/entrada), 'D' (debito/saida) ou 'S' (saldo).

    QiTech /bank-account/statement usa `tipoLancamento` com valores C/D/S.
    'S' (linha de saldo) e retornado pra que o caller a descarte — nao e
    movimento. Aliases antigos mantidos por seguranca/compat.
    """
    for key in (
        "tipoLancamento",
        "tipo",
        "tipoOperacao",
        "tipoDeOperacao",
        "natureza",
    ):
        v = item.get(key)
        if v is None:
            continue
        s = str(v).strip().upper()
        if not s:
            continue
        if s in ("S", "SALDO"):
            return "S"
        if s.startswith("D") or s in ("DEBIT", "DEBITO", "DÉBITO", "SAIDA", "SAÍDA", "-"):
            return "D"
        if s.startswith("C") or s in ("CREDIT", "CREDITO", "CRÉDITO", "ENTRADA", "+"):
            return "C"
    # Fallback: sinal do valor (raro — QiTech sempre manda tipoLancamento).
    valor = _pick_valor(item)
    if valor is not None and valor < 0:
        return "D"
    if valor is not None and valor > 0:
        return "C"
    return None


def _pick_contrapartida(item: dict[str, Any]) -> tuple[str | None, str | None]:
    """Extrai (nome, doc) da contraparte. Doc vem de `inscricao` (CPF/CNPJ int)."""
    cp = item.get("contraparte") or item.get("contrapartida")
    if not isinstance(cp, dict):
        return None, None
    nome = _clean_null(cp.get("nome") or cp.get("name"))
    raw_doc = cp.get("inscricao")
    if raw_doc is None:
        raw_doc = cp.get("cnpj") or cp.get("cpf") or cp.get("documento") or cp.get("doc")
    doc = _format_doc(raw_doc, tipo_pessoa=_clean_null(cp.get("tipoPessoa")))
    return nome, doc


def _pick_historico(item: dict[str, Any]) -> tuple[str | None, str | None]:
    """Retorna (codigo_historico, descricao_texto).

    QiTech entrega `historico` como objeto {codigo, descricao}. O texto
    (`descricao`) e o campo pesquisavel e parte da business key -> vai pra
    coluna `descricao`. O `codigo` (codigo de historico bancario) -> coluna
    `historico`. Tolera `historico` vindo como string simples (outros formatos).
    """
    hist = item.get("historico") or item.get("histórico")
    if isinstance(hist, dict):
        codigo = normalize_str_or_none(hist.get("codigo") or hist.get("código"))
        descricao = normalize_str_or_none(
            hist.get("descricao") or hist.get("descrição")
        )
    else:
        codigo = None
        descricao = normalize_str_or_none(hist)
    # Fallback de descricao: campo `descricao` solto no item, se existir.
    if descricao is None:
        descricao = normalize_str_or_none(
            item.get("descricao") or item.get("descrição")
        )
    return codigo, descricao


def map_bank_account_statement(
    *,
    payload: Any,
    tenant_id: UUID,
    unidade_administrativa_id: UUID,
    agencia: str,
    conta: str,
) -> list[dict[str, Any]]:
    """Mapeia payload de extrato em N linhas canonicas.

    Descarta:
    - linhas de saldo (`tipoLancamento="S"`) — nao sao movimentos;
    - linhas sem (data_lancamento E valor E tipo C/D) — campos criticos.
    """
    items = _extract_items(payload)
    if not items:
        return []

    ingested_at = datetime.now(UTC)
    rows: list[dict[str, Any]] = []

    for item in items:
        if not isinstance(item, dict):
            continue

        tipo = _pick_tipo(item)
        if tipo == "S":
            continue  # linha de saldo — vai pra wh_saldo_bancario_diario, nao aqui

        data_lanc = _pick_data_lancamento(item)
        valor = _pick_valor(item)

        if data_lanc is None or valor is None or tipo is None:
            continue

        # Valor sempre absoluto no warehouse — sinal vai em `tipo`.
        valor_abs = abs(valor)

        historico_codigo, descricao_texto = _pick_historico(item)
        contraparte_nome, contraparte_doc = _pick_contrapartida(item)

        # id estavel do lancamento quando presente; senao hash do item.
        lanc_id = item.get("lancamento")
        stable = (
            str(lanc_id)
            if lanc_id not in (None, 0, "0", "")
            else sha256_of_row(item)[:16]
        )
        source_id = (
            f"bank_account_statement|{unidade_administrativa_id}|"
            f"{agencia}|{conta}|{data_lanc.isoformat()}|{stable}"
        )

        moeda = normalize_str_or_none(item.get("moeda")) or "BRL"
        datahora = _parse_datahora(item.get("dataHora"))
        src_updated = datahora or parse_iso_or_none(
            item.get("dataAtualizacao") or item.get("updatedAt")
        )

        rows.append(
            {
                "tenant_id": tenant_id,
                "unidade_administrativa_id": unidade_administrativa_id,
                "agencia": agencia,
                "conta": conta,
                "banco_codigo": None,
                "banco_nome": None,
                "moeda": moeda,
                "data_lancamento": data_lanc,
                "data_movimento": _pick_data_movimento(item),
                "valor": valor_abs,
                "tipo": tipo,
                # codigo de historico bancario (ex.: "0497" = TED, "0099" = saldo)
                "historico": historico_codigo,
                # texto do lancamento — pesquisavel + parte da business key
                "descricao": descricao_texto,
                "documento": normalize_str_or_none(
                    item.get("documento") or item.get("nrDocumento")
                ),
                "contrapartida_nome": contraparte_nome,
                "contrapartida_doc": contraparte_doc,
                **build_provenance(
                    source_id=source_id,
                    item=item,
                    ingested_at=ingested_at,
                    source_updated_at=src_updated,
                ),
            }
        )

    return rows
