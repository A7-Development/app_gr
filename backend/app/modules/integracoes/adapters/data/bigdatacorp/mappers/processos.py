"""Mapper (BDC processes) -> structs do silver de processos judiciais PJ.

Le `Result[0].Lawsuits` (lista de processos + agregados da entidade) e produz:
- por processo: cabecalho + partes + andamentos (com flag de evento patrimonial)
- resumo da entidade: contadores por status/area/polo, execucoes contra a
  empresa + credores, recencia.

Decisoes:
- `Value == -1` (ou <= 0) -> None (no Juizado quase sempre vem -1 = nao informado).
- polaridade da EMPRESA-ALVO = Polarity da parte cujo Doc == cnpj consultado.
- `encerrado` = status na familia de encerrados (arquivado/baixado/extinto/...).
- andamento dedup key = sha256 do conteudo normalizado (BDC repete o mesmo
  andamento com CaptureDate diferente).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# Status que significam "morto" (lente de risco exclui; lente de bens nao).
_CLOSED = {
    "ARQUIVADO",
    "BAIXADO",
    "EXTINTO",
    "ENCERRADO",
    "TRANSITADO EM JULGADO",
    "CANCELADO",
    "FINALIZADO",
}

# Eventos que citam bem/garantia — pro garimpo (full-text + flag).
_PATRIMONIAL_RE = re.compile(
    r"\b(PENHOR|ARRESTO|ARRESTAD|BLOQUEIO|INDISPONIBILIDADE\s+DE\s+BENS|"
    r"ADJUDIC|LEIL|HASTA\s+PUBLICA|SEQUESTRO|BACENJUD|SISBAJUD|RENAJUD|"
    r"INFOJUD|MATRICULA|MATRÍCULA|PLACA|BEM\s+IMOVEL|BENS\s+IMOVEIS|"
    r"AVALIACAO\s+DE\s+BENS|REMOCAO\s+DE\s+BENS|CONSTRICAO)\b",
    re.IGNORECASE,
)


def _digits(value: str | None) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def _parse_dt(raw: Any) -> datetime | None:
    if not raw:
        return None
    s = str(raw).strip().replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.year in (1, 1900):
        return None
    return dt


def _parse_date(raw: Any) -> date | None:
    dt = _parse_dt(raw)
    return dt.date() if dt is not None else None


def _norm_value(raw: Any) -> Decimal | None:
    if raw is None:
        return None
    try:
        v = Decimal(str(raw))
    except (InvalidOperation, ValueError):
        return None
    return v if v > 0 else None


def _is_closed(status: str | None) -> bool:
    return (status or "").strip().upper() in _CLOSED


def _area(court_type: str | None) -> str:
    t = (court_type or "").strip().upper()
    if "TRABALH" in t:
        return "trabalhista"
    if "CRIMINAL" in t:
        return "criminal"
    if "TRIBUTAR" in t or "FAZENDA" in t:
        return "tributaria"
    if "CIVEL" in t or "CÍVEL" in t:
        return "civel"
    return "outros"


def _is_execucao(tipo: str | None, assunto: str | None) -> bool:
    blob = f"{tipo or ''} {assunto or ''}".upper()
    return "EXECU" in blob


def _is_recuperacao_falencia(tipo: str | None, assunto: str | None) -> bool:
    blob = f"{tipo or ''} {assunto or ''}".upper()
    return "FALENCIA" in blob or "FALÊNCIA" in blob or "RECUPERACAO JUDICIAL" in blob


def _sha(text: str) -> str:
    return hashlib.sha256(text.strip().upper().encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ProcessoParteFields:
    polaridade: str | None
    tipo_parte: str | None
    ativa: bool | None
    nome: str | None
    doc: str | None


@dataclass(frozen=True)
class ProcessoAndamentoFields:
    data: datetime | None
    conteudo: str
    conteudo_hash: str
    evento_patrimonial: bool


@dataclass(frozen=True)
class ProcessoFields:
    numero: str
    tipo: str | None
    assunto: str | None
    assunto_cnj: str | None
    assunto_cnj_amplo: str | None
    tribunal: str | None
    instancia: str | None
    area: str | None
    comarca: str | None
    orgao_julgador: str | None
    uf: str | None
    status: str | None
    encerrado: bool
    valor: Decimal | None
    polaridade_alvo: str | None
    is_execucao: bool
    num_partes: int | None
    num_atualizacoes: int | None
    idade_dias: int | None
    data_redistribuicao: date | None
    data_notice: date | None
    data_last_movement: date | None
    data_last_update: datetime | None
    source_updated_at: datetime | None
    partes: list[ProcessoParteFields] = field(default_factory=list)
    andamentos: list[ProcessoAndamentoFields] = field(default_factory=list)


@dataclass(frozen=True)
class ProcessoResumoFields:
    qtd_total: int
    qtd_ativos: int
    qtd_encerrados: int
    por_area: dict[str, dict[str, Any]]
    qtd_como_reu: int
    qtd_como_autor: int
    qtd_execucoes_contra: int
    credores_executando: list[dict[str, str | None]]
    qtd_recuperacao_falencia: int
    valor_total_informado: Decimal | None
    last_30d: int | None
    last_90d: int | None
    last_365d: int | None
    primeira_data: date | None
    ultima_data: date | None


@dataclass(frozen=True)
class ProcessosMapResult:
    found: bool
    dataset_status_code: int | None
    query_id: str | None
    processos: list[ProcessoFields]
    resumo: ProcessoResumoFields | None


def _first_result_block(payload: dict, dataset: str) -> dict | None:
    results = payload.get("Result") or []
    if not results:
        return None
    block = results[0].get("Lawsuits")
    return block if isinstance(block, dict) else None


def _map_partes(raw_parties: list, cnpj: str) -> tuple[list[ProcessoParteFields], str | None]:
    partes: list[ProcessoParteFields] = []
    polaridade_alvo: str | None = None
    for p in raw_parties or []:
        doc = _digits(p.get("Doc"))
        pol = p.get("Polarity")
        partes.append(
            ProcessoParteFields(
                polaridade=pol,
                tipo_parte=p.get("Type"),
                ativa=p.get("IsPartyActive"),
                nome=p.get("Name"),
                doc=doc or None,
            )
        )
        # Polaridade da empresa-alvo: a parte cujo doc bate com o cnpj. Prefere
        # um polo nao-neutro; cai no que vier se ainda nao tiver nada.
        if doc == cnpj and (polaridade_alvo is None or (pol and pol != "NEUTRAL")):
            polaridade_alvo = pol
    return partes, polaridade_alvo


def _map_andamentos(raw_updates: list) -> list[ProcessoAndamentoFields]:
    seen: set[tuple[str, str]] = set()
    out: list[ProcessoAndamentoFields] = []
    for u in raw_updates or []:
        conteudo = (u.get("Content") or "").strip()
        if not conteudo:
            continue
        h = _sha(conteudo)
        dt = _parse_dt(u.get("PublishDate"))
        key = (dt.isoformat() if dt else "", h)
        if key in seen:  # dedupe dentro da mesma resposta (BDC repete)
            continue
        seen.add(key)
        out.append(
            ProcessoAndamentoFields(
                data=dt,
                conteudo=conteudo,
                conteudo_hash=h,
                evento_patrimonial=bool(_PATRIMONIAL_RE.search(conteudo)),
            )
        )
    return out


def map_processos(payload: dict, *, cnpj: str, dataset: str = "processes") -> ProcessosMapResult:
    """Parseia o envelope `processes` -> processos + resumo."""
    cnpj_digits = _digits(cnpj)
    status_block = (payload.get("Status") or {}).get(dataset) or []
    dataset_status_code = (
        status_block[0].get("Code") if isinstance(status_block, list) and status_block else None
    )
    query_id = payload.get("QueryId")
    block = _first_result_block(payload, dataset)
    if block is None:
        return ProcessosMapResult(
            found=False, dataset_status_code=dataset_status_code,
            query_id=query_id, processos=[], resumo=None,
        )

    raw_list = block.get("Lawsuits") or []
    processos: list[ProcessoFields] = []
    por_area: dict[str, dict[str, Any]] = {}
    qtd_ativos = qtd_encerrados = qtd_reu = qtd_autor = 0
    qtd_exec_contra = qtd_rec_fal = 0
    valor_total = Decimal("0")
    valor_visto = False
    credores: dict[str, dict[str, str | None]] = {}
    seen_num: set[str] = set()  # BDC repete numeros entre paginas/instancias

    for lw in raw_list:
        numero = (lw.get("Number") or "").strip()
        if not numero or numero in seen_num:
            continue
        seen_num.add(numero)
        tipo = lw.get("Type")
        assunto = lw.get("MainSubject")
        status = lw.get("Status")
        encerrado = _is_closed(status)
        area = _area(lw.get("CourtType"))
        valor = _norm_value(lw.get("Value"))
        partes, pol_alvo = _map_partes(lw.get("Parties") or [], cnpj_digits)
        is_exec = _is_execucao(tipo, assunto)
        last_update = _parse_dt(lw.get("LastUpdate"))

        processos.append(
            ProcessoFields(
                numero=numero, tipo=tipo, assunto=assunto,
                assunto_cnj=lw.get("InferredCNJSubjectName"),
                assunto_cnj_amplo=lw.get("InferredBroadCNJSubjectName"),
                tribunal=lw.get("CourtName"),
                instancia=str(lw.get("CourtLevel")) if lw.get("CourtLevel") is not None else None,
                area=lw.get("CourtType"), comarca=lw.get("CourtDistrict"),
                orgao_julgador=lw.get("JudgingBody"), uf=lw.get("State"),
                status=status, encerrado=encerrado, valor=valor,
                polaridade_alvo=pol_alvo, is_execucao=is_exec,
                num_partes=lw.get("NumberOfParties"),
                num_atualizacoes=lw.get("NumberOfUpdates"),
                idade_dias=lw.get("LawSuitAge"),
                data_redistribuicao=_parse_date(lw.get("RedistributionDate")),
                data_notice=_parse_date(lw.get("NoticeDate")),
                data_last_movement=_parse_date(lw.get("LastMovementDate")),
                data_last_update=last_update,
                source_updated_at=last_update,
                partes=partes,
                andamentos=_map_andamentos(lw.get("Updates") or []),
            )
        )

        # ── agregados (so dos VIVOS p/ as lentes de risco) ──
        if encerrado:
            qtd_encerrados += 1
            continue
        qtd_ativos += 1
        slot = por_area.setdefault(area, {"qtd": 0, "valor": 0.0})
        slot["qtd"] += 1
        if valor is not None:
            slot["valor"] = float(Decimal(str(slot["valor"])) + valor)
            valor_total += valor
            valor_visto = True
        if pol_alvo == "PASSIVE":
            qtd_reu += 1
        elif pol_alvo == "ACTIVE":
            qtd_autor += 1
        if _is_recuperacao_falencia(tipo, assunto):
            qtd_rec_fal += 1
        # Execucao onde a empresa e EXECUTADA -> outro credor cobrando.
        if is_exec and pol_alvo == "PASSIVE":
            qtd_exec_contra += 1
            for pt in partes:
                if pt.polaridade == "ACTIVE" and pt.doc != cnpj_digits and pt.nome:
                    credores.setdefault(
                        pt.doc or pt.nome, {"nome": pt.nome, "doc": pt.doc}
                    )

    resumo = ProcessoResumoFields(
        qtd_total=len(processos), qtd_ativos=qtd_ativos, qtd_encerrados=qtd_encerrados,
        por_area=por_area, qtd_como_reu=qtd_reu, qtd_como_autor=qtd_autor,
        qtd_execucoes_contra=qtd_exec_contra,
        credores_executando=list(credores.values()),
        qtd_recuperacao_falencia=qtd_rec_fal,
        valor_total_informado=valor_total if valor_visto else None,
        last_30d=block.get("Last30DaysLawsuits"),
        last_90d=block.get("Last90DaysLawsuits"),
        last_365d=block.get("Last365DaysLawsuits"),
        primeira_data=_parse_date(block.get("FirstLawsuitDate")),
        ultima_data=_parse_date(block.get("LastLawsuitDate")),
    )

    return ProcessosMapResult(
        found=bool(raw_list), dataset_status_code=dataset_status_code,
        query_id=query_id, processos=processos, resumo=resumo,
    )
