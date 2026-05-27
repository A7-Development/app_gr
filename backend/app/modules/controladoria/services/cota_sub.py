"""Controladoria · Cota Sub — service de Variacao Diaria.

Computa a decomposicao da variacao do PL da cota subordinada junior entre
D-1 e D0, espelhando a logica da planilha
`VariacaoDeCota_Preenchida.xlsx` (aba Analise).

Origem dos dados — apenas tabelas canonicas (silver) do warehouse:

    - PL Sub Jr           ← wh_mec_evolucao_cotas (`patrimonio` da classe Sub Jr)
    - Compromissada       ← wh_posicao_compromissada (sum `valor_bruto`)
    - Mezanino/Senior     ← wh_mec_evolucao_cotas (`patrimonio` da classe Mez/Sr x -1)
    - Titulos Publicos    ← wh_posicao_outros_ativos (filtro TPF em `descricao_tipo_de_ativo`)
    - Fundos DI           ← wh_posicao_cota_fundo (filtro DI em `ativo_nome`)
    - DC                  ← wh_estoque_recebivel (`valor_presente`, ja liquido de PDD)
    - Op Estruturadas /   ← wh_posicao_outros_ativos (demais tipos — segregacao
      Outros Ativos          fica para o frontend via `descricao_tipo_de_ativo`)
    - PDD                 ← wh_estoque_recebivel (sum `valor_pdd`, valor absoluto)
    - CPR                 ← wh_cpr_movimento (sum `valor` agregado)
    - Tesouraria          ← wh_saldo_tesouraria + wh_saldo_conta_corrente
    - Apropriacao DC      ← derivado: G - (D + E + F) sobre wh_estoque_recebivel
                              + wh_aquisicao_recebivel + wh_liquidacao_recebivel
    - Apropriacao despesas ← derivado de wh_cpr_movimento (delta total liquido)

Identificacao da classe de cota (Sub Jr / Mezanino / Senior) e feita por
heuristica sobre `carteira_cliente_nome`. Se um fundo nao seguir essa
convencao de naming, a heuristica precisa ser estendida.

Filtro de UA: usado quando a tabela tem `unidade_administrativa_id`. Para
EstoqueRecebivel/AquisicaoRecebivel/LiquidacaoRecebivel (que tambem expoem
`fundo_doc`), preferimos `unidade_administrativa_id` quando presente.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub import (
    ApropriacaoDc,
    ApropriacaoDcEvidencia,
    ApropriacaoDcLinha,
    CprDetalhado,
    CprMovimentoItem,
    DecomposicaoItem,
    PlCategoria,
    SaldoTesourariaEvidencia,
    VariacaoDiariaResponse,
)
from app.modules.controladoria.services.cosif.classifier import (
    classify,
    load_overrides,
    load_rules_cache,
)
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.aquisicao_recebivel import AquisicaoRecebivel
from app.warehouse.cpr_movimento import CprMovimento
from app.warehouse.estoque_recebivel import EstoqueRecebivel
from app.warehouse.liquidacao_recebivel import LiquidacaoRecebivel
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas
from app.warehouse.movimento_caixa import MovimentoCaixa
from app.warehouse.posicao_compromissada import PosicaoCompromissada
from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo
from app.warehouse.posicao_outros_ativos import PosicaoOutrosAtivos
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa
from app.warehouse.saldo_tesouraria import SaldoTesouraria

ZERO = Decimal("0")


# ─────────────────────────────────────────────────────────────────────────────
# Heuristicas de classificacao
# ─────────────────────────────────────────────────────────────────────────────


def _norm(s: str | None) -> str:
    return (s or "").strip().upper()


def _is_mezanino(carteira_nome: str) -> bool:
    """Classe Mezanino: o `clienteNome` da QiTech contem 'MEZANINO'."""
    return "MEZANINO" in _norm(carteira_nome)


def _is_senior(carteira_nome: str) -> bool:
    """Classe Senior: o `clienteNome` da QiTech contem 'SENIOR'."""
    return "SENIOR" in _norm(carteira_nome)


def _is_sub_jr(carteira_nome: str, ua_nome: str) -> bool:
    """Classe Sub Jr (subordinada junior).

    Convencao QiTech (validada com REALINVEST FIDC, 2026-04-23):
        - Sub Jr:    `clienteNome` == nome do fundo cru (ex.: "REALINVEST FIDC")
        - Mezanino:  `clienteNome` == nome + " MEZANINO N" (ex.: "REALINVEST FIDC MEZANINO 1")
        - Senior:    `clienteNome` == nome + " SENIOR N"
    Identificacao POSITIVA: nome normalizado bate com o nome da UA.
    """
    return _norm(carteira_nome) == _norm(ua_nome)


def _is_titulo_publico(descricao_tipo: str) -> bool:
    n = (descricao_tipo or "").lower()
    # TPF / LFT / LTN / NTN / Tesouro
    return any(k in n for k in ("titulo publico", "tpf", "lft", "ltn", "ntn", "tesouro"))


def _is_fundo_externo(ativo_nome: str, ua_nome: str) -> bool:
    """Fundo EXTERNO = nao bate com o PREFIXO do nome da UA do fundo.

    Mudanca 2026-05-18 (Fase 3c-pre): antes existia `_is_fundo_di` com
    regex por nome ('DI', 'soberano', 'selic', etc.) — fragil porque
    cada novo fundo (ex.: ITAU SOBERANO REF SI) exigia atualizacao da
    lista. Filosofia nova: confiar no endpoint da QiTech (todo papel
    em `wh_posicao_cota_fundo` e cota de fundo). Filtro residual: so
    EXCLUIR fundos internos (representacao alternativa da carteira DC
    do proprio FIDC — ex.: 'REALINVEST A VENCER', 'REALINVEST VENCIDOS'),
    pra nao duplicar contagem com o driver Apropriacao DC.

    Identificacao do interno: primeira palavra do nome da UA aparece no
    nome do papel. `REALINVEST FIDC` -> prefixo `REALINVEST` -> casa com
    `REALINVEST A VENCER` e `REALINVEST VENCIDOS`. Funciona porque o
    nome do FIDC sempre comeca pelo nome unico do fundo (sem coincidir
    com nome de fundo externo).
    """
    a = _norm(ativo_nome or "")
    ua_tokens = _norm(ua_nome or "").split()
    if not ua_tokens:
        return True
    prefix = ua_tokens[0]
    return prefix not in a


def _dia_util_anterior(d: date) -> date:
    """D-1 simples: dia util anterior considerando apenas finais de semana.

    TODO: usar calendario B3/Anbima quando integrarmos `holidays_br`.
    """
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:  # 5=sab, 6=dom
        prev -= timedelta(days=1)
    return prev


# ─────────────────────────────────────────────────────────────────────────────
# Query helpers — cada um devolve Decimal
# ─────────────────────────────────────────────────────────────────────────────


async def _sum_compromissada(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(PosicaoCompromissada.valor_bruto), ZERO))
        .where(PosicaoCompromissada.tenant_id == tenant_id)
        .where(PosicaoCompromissada.unidade_administrativa_id == ua_id)
        .where(PosicaoCompromissada.data_posicao == data)
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _mec_classes(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    data: date,
) -> dict[str, Decimal]:
    """Devolve {sub_jr, mezanino, senior} → patrimonio classificando pela `carteira_cliente_nome`."""
    stmt = (
        select(MecEvolucaoCotas.carteira_cliente_nome, MecEvolucaoCotas.patrimonio)
        .where(MecEvolucaoCotas.tenant_id == tenant_id)
        .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
        .where(MecEvolucaoCotas.data_posicao == data)
    )
    rows = (await db.execute(stmt)).all()
    out: dict[str, Decimal] = {"sub_jr": ZERO, "mezanino": ZERO, "senior": ZERO}
    for nome, patrimonio in rows:
        v = Decimal(patrimonio or 0)
        if _is_sub_jr(nome, ua_nome):
            out["sub_jr"] += v
        elif _is_mezanino(nome):
            out["mezanino"] += v
        elif _is_senior(nome):
            out["senior"] += v
    return out


async def _sum_mov_caixa_fundo_externo(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    data: date,
) -> Decimal:
    """Net cash flow do dia relacionado a fundos EXTERNOS (entradas + saidas).

    Filtro: `descricao ILIKE '%fundo%'` AND (`aplicacao` OR `resgate`)
    AND nao casa com o nome da UA (exclui fundos internos REALINVEST
    A VENCER / VENCIDOS, que sao DC contabilizada em outro driver).

    Dedup defensivo: agrupa por (entradas, saidas) DISTINCT. QiTech publica
    varias rows pro mesmo evento — com/sem 'a receber em DD/MM' no fim da
    descricao, com/sem `[CODIGO]`, sufixos variados. Em REALINVEST 13/05
    o resgate ITAU SOBERANO aparece com 3 descricoes distintas mas todas
    com mesma entrada R$ 318.166,73 — chave so por valores absorve as 3.

    Convencao de sinal:
      - Aplicacao no fundo: caixa SAI (saida < 0). Soma E+S < 0.
      - Resgate do fundo:   caixa ENTRA (entrada > 0). Soma E+S > 0.

    Filtro de fundos internos (carteira DC propria, ex.: REALINVEST A VENCER):
    busca por `prefixo` do nome da UA na descricao. `REALINVEST FIDC` ->
    prefixo `REALINVEST` -> casa com "Aplicacao no Fundo REALINVEST A VENCER".

    Usado em `compute_fundos_di` (Fase 3c-C) para isolar rendimento:
      rendimento_fundo = ΔPos + net_caixa.
    """
    stmt = (
        select(
            MovimentoCaixa.descricao,
            MovimentoCaixa.entradas,
            MovimentoCaixa.saidas,
        )
        .where(MovimentoCaixa.tenant_id == tenant_id)
        .where(MovimentoCaixa.unidade_administrativa_id == ua_id)
        .where(MovimentoCaixa.data_liquidacao == data)
    )
    rows = (await db.execute(stmt)).all()

    # Prefixo do nome da UA para detectar fundos internos.
    # "REALINVEST FIDC" -> "REALINVEST"; fundos internos da carteira propria
    # aparecem como "REALINVEST A VENCER", "REALINVEST VENCIDOS", etc.
    ua_tokens = _norm(ua_nome or "").split()
    ua_prefix = ua_tokens[0] if ua_tokens else ""

    seen: set[tuple[str, str]] = set()
    total = ZERO
    for desc, ent, sai in rows:
        d = (desc or "")
        d_lower = d.lower()
        if "fundo" not in d_lower:
            continue
        # Excluir aplicacao/resgate em fundos internos (carteira DC propria)
        if ua_prefix and ua_prefix in _norm(d):
            continue
        if ("aplicação" not in d_lower
                and "aplicacao" not in d_lower
                and "resgate" not in d_lower):
            continue
        # Dedup por (ent, sai) so — descricoes variam com sufixos a receber/pagar.
        key = (str(ent or 0), str(sai or 0))
        if key in seen:
            continue
        seen.add(key)
        total += Decimal(ent or 0) + Decimal(sai or 0)
    return total


async def _mec_classes_fluxo_caixa(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    data: date,
) -> dict[str, Decimal]:
    """Devolve {sub_jr, mezanino, senior} -> fluxo liquido de caixa do dia.

    fluxo = entradas - saidas + aporte - retirada (defensivo: QiTech popula
    so um dos pares — REALINVEST usa entradas/saidas; outros fundos podem
    usar aporte/retirada). Soma os 4 cobre ambos os casos sem dupla
    contagem desde que QiTech nao popule ambos.

    Usado por `compute_senior`/`compute_mezanino` (Fase 3c-A) para subtrair
    cash flow do ΔPL da classe e isolar APENAS a remuneracao (rendimento).
    """
    stmt = (
        select(
            MecEvolucaoCotas.carteira_cliente_nome,
            MecEvolucaoCotas.entradas,
            MecEvolucaoCotas.saidas,
            MecEvolucaoCotas.aporte,
            MecEvolucaoCotas.retirada,
        )
        .where(MecEvolucaoCotas.tenant_id == tenant_id)
        .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
        .where(MecEvolucaoCotas.data_posicao == data)
    )
    rows = (await db.execute(stmt)).all()
    out: dict[str, Decimal] = {"sub_jr": ZERO, "mezanino": ZERO, "senior": ZERO}
    for nome, entradas, saidas, aporte, retirada in rows:
        fluxo = (
            Decimal(entradas or 0)
            - Decimal(saidas or 0)
            + Decimal(aporte or 0)
            - Decimal(retirada or 0)
        )
        if _is_sub_jr(nome, ua_nome):
            out["sub_jr"] += fluxo
        elif _is_mezanino(nome):
            out["mezanino"] += fluxo
        elif _is_senior(nome):
            out["senior"] += fluxo
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Renda fixa: classificacao via COSIF para roteamento por driver gestor
# ─────────────────────────────────────────────────────────────────────────────

# Mapping COSIF (prefixo) -> driver do metodo gestor. COSIF e padrao
# CVM/BACEN global e estavel — justifica constante em codigo. Curadoria
# acontece em `cosif_rule` (regras de papel -> cosif) e
# `tenant_papel_classificacao` (overrides por tenant) — esses sim DB-backed.
#
# Valor `None` = driver implicito (excluir do somatorio):
#   - 3.9.9.* (compensacao interna) = cotas internas do proprio fundo,
#     pareadas positivo+negativo somando zero
#   - 6.1.* (cotas emitidas) = passivo da subordinacao, ja captado via MEC
#     nos drivers Senior / Mezanino
COSIF_TO_DRIVER_GESTOR: dict[str, str | None] = {
    # TPF (Notas e Letras do Tesouro Nacional)
    "1.3.1.10.07": "titulos_publicos",  # NTN
    "1.2.1.10.05": "titulos_publicos",  # LTN
    # Notas Comerciais = Op Estruturadas (metodo gestor REALINVEST)
    "1.3.1.10.16": "op_estruturadas",
    # Cotas de fundo RF (raro vir aqui — geralmente vai em wh_posicao_cota_fundo)
    "1.3.1.15.30": "fundos_di",
    # Compensacao interna (cotas internas pareadas) — exclui
    "3.9.9.30.50": None,
    # Cotas emitidas (passivo, capturado via MEC nos drivers Sr/Mez) — exclui
    "6.1.1.70.30": None,
}


def _driver_gestor_for_cosif(cosif: str | None) -> str | None:
    """Mapeia codigo COSIF -> driver gestor por prefixo (match mais especifico).

    Retorna None quando COSIF e classificado como excluivel (compensacao
    interna ou cota emitida) OU quando nao bate com nenhum prefixo
    conhecido. Quando o classifier devolve `cosif=None` (papel pendente),
    tambem retorna None — papel pendente nao contribui pra nenhum driver
    ate ser classificado.
    """
    if not cosif:
        return None
    # Match pelo prefixo mais longo (caso adicionem hierarquias futuramente).
    best: tuple[int, str | None] = (0, None)
    for prefix, driver in COSIF_TO_DRIVER_GESTOR.items():
        if cosif.startswith(prefix) and len(prefix) > best[0]:
            best = (len(prefix), driver)
    return best[1]


async def _sum_renda_fixa_por_driver(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date,
) -> dict[str, Decimal]:
    """Soma wh_posicao_renda_fixa agrupado por driver gestor.

    Aplica classificacao COSIF (cosif_rule + tenant_papel_classificacao) em
    cada papel, mapeia COSIF -> driver via `COSIF_TO_DRIVER_GESTOR`, e
    acumula `valor_bruto` por driver. Papeis nao classificados ou em
    categorias excluidas (compensacao/cota emitida) NAO entram em nenhum
    driver — ficam invisiveis do somatorio (residuo do metodo).

    Returns:
        dict[driver_name, Decimal] — drivers sem papel ficam ausentes.
    """
    rules_cache = await load_rules_cache(db)
    overrides = await load_overrides(db, tenant_id=tenant_id, fundo_id=ua_id)

    stmt = (
        select(
            PosicaoRendaFixa.codigo,
            PosicaoRendaFixa.nome_do_papel,
            PosicaoRendaFixa.codigo_lastro,
            PosicaoRendaFixa.quantidade,
            PosicaoRendaFixa.valor_bruto,
        )
        .where(PosicaoRendaFixa.tenant_id == tenant_id)
        .where(PosicaoRendaFixa.unidade_administrativa_id == ua_id)
        .where(PosicaoRendaFixa.data_posicao == data)
    )
    rows = (await db.execute(stmt)).all()

    totais: dict[str, Decimal] = {}
    for codigo, nome_do_papel, codigo_lastro, quantidade, valor_bruto in rows:
        row_dict: dict[str, Any] = {
            "codigo": codigo,
            "nome_do_papel": nome_do_papel,
            "codigo_lastro": codigo_lastro,
            "quantidade": quantidade,
        }
        resolution = classify(
            silver_origin="wh_posicao_renda_fixa",
            row=row_dict,
            rules_cache=rules_cache,
            overrides=overrides,
        )
        driver = _driver_gestor_for_cosif(resolution.cosif)
        if driver is None:
            continue
        totais[driver] = totais.get(driver, ZERO) + Decimal(valor_bruto or 0)
    return totais


async def _sum_titulos_publicos(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> Decimal:
    """Titulos Publicos = Σ wh_posicao_renda_fixa classificado como TPF via COSIF.

    Refactor 2026-05-19: antes lia de `wh_posicao_outros_ativos` filtrando
    por `descricao_tipo_de_ativo` (que nao trazia TPF na pratica). Agora
    le de `wh_posicao_renda_fixa` e usa a classificacao COSIF para
    identificar TPF (NTN, LTN) — agnostico, sem hardcode de siglas.
    """
    totais = await _sum_renda_fixa_por_driver(db, tenant_id, ua_id, data)
    return totais.get("titulos_publicos", ZERO)


async def _sum_op_estruturadas(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> Decimal:
    """Op Estruturadas = Σ wh_posicao_renda_fixa classificado como Nota Comercial via COSIF.

    Vocabulario gestor REALINVEST: "Op Estruturadas" = Notas Comerciais
    (NCPX, NC*, etc.). Identificacao agnostica via cosif_rule (regra
    `rf.nota_comercial` -> cosif 1.3.1.10.16.*).
    """
    totais = await _sum_renda_fixa_por_driver(db, tenant_id, ua_id, data)
    return totais.get("op_estruturadas", ZERO)


async def _sum_outros_ativos_nao_tpf(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> Decimal:
    """Outros ativos + Op Estruturadas (planilha trata juntos no MVP).

    Exclusoes:
      - TPF (`_is_titulo_publico` no `descricao_tipo_de_ativo`) — pertence
        ao driver Titulos Publicos.
      - PDD (`codigo='PDD'`) — bug double-counting (2026-05-19): a QiTech
        reporta PDD em DUAS fontes — `wh_estoque_recebivel.valor_pdd`
        (granular) e `wh_posicao_outros_ativos` (consolidado, 1 linha
        com codigo='PDD'). O driver PDD ja consome a fonte granular;
        se nao excluir aqui, PDD vai pra dois drivers (PDD + Outros Ativos).
    """
    stmt = (
        select(
            PosicaoOutrosAtivos.descricao_tipo_de_ativo,
            PosicaoOutrosAtivos.valor_total,
        )
        .where(PosicaoOutrosAtivos.tenant_id == tenant_id)
        .where(PosicaoOutrosAtivos.unidade_administrativa_id == ua_id)
        .where(PosicaoOutrosAtivos.data_posicao == data)
        .where(PosicaoOutrosAtivos.codigo != "PDD")
    )
    rows = (await db.execute(stmt)).all()
    total = ZERO
    for tipo, valor in rows:
        if not _is_titulo_publico(tipo or ""):
            total += Decimal(valor or 0)
    return total


async def _sum_fundos_di(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, ua_nome: str, data: date
) -> Decimal:
    """Soma posicoes em fundos EXTERNOS (qualquer fundo em
    `wh_posicao_cota_fundo` cujo nome nao bata com o da UA).

    Fundos internos (`REALINVEST A VENCER` / `REALINVEST VENCIDOS`) sao
    excluidos — representam a carteira DC do proprio FIDC, contabilizada
    no driver Apropriacao DC.
    """
    stmt = (
        select(
            PosicaoCotaFundo.ativo_nome,
            PosicaoCotaFundo.valor_liquido,
        )
        .where(PosicaoCotaFundo.tenant_id == tenant_id)
        .where(PosicaoCotaFundo.unidade_administrativa_id == ua_id)
        .where(PosicaoCotaFundo.data_posicao == data)
    )
    rows = (await db.execute(stmt)).all()
    total = ZERO
    for nome, valor in rows:
        if _is_fundo_externo(nome or "", ua_nome):
            total += Decimal(valor or 0)
    return total


async def _sum_dc(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, ua_nome: str, data: date,
) -> Decimal:
    """DC = Σ wh_estoque_recebivel.valor_presente, excluindo WOP.

    Refactor 2026-05-24 (metodo granular, Fase 1A do redesign cota-sub):
    voltamos a ler granular ex-WOP, abandonando o consolidado
    `wh_posicao_cota_fundo` que era a fonte desde 2026-05-19 (metodo gestor).

    Razao da volta ao granular: o consolidado QiTech (`valor_liquido` das
    cotas internas tipo "REALINVEST A VENCER" / "REALINVEST VENCIDOS") tem
    opacidade — qualquer ajuste interno (PDD, WOP, mutacao silenciosa) entra
    no saldo sem trilha auditavel, e a Apropriacao deduzida por residual no
    drill DC virava balde de ruido. O granular permite decompor o ΔDC em
    5 buckets com fonte propria (aquisicao, liquidacao, migracao WOP,
    apropriacao de juros, mutacao silenciosa).

    WOP (write-off pendente) e excluido porque:
      - PDD em 100% do VP → contribuicao liquida ao PL Sub Jr e zero
      - QiTech segrega WOP da cota interna do estoque consolidado (offset
        de R$ 118.046 que aparecia entre granular e A VENCER+VENCIDOS no
        REALINVEST 11-12/05 e exatamente o saldo WOP)
      - Excluindo de ambos os lados (DC e PDD) mantemos coerencia

    Assinatura mantida — `ua_nome` continua no parametro por compatibilidade
    com os callers existentes (nao usado mais nesta versao). O CNPJ do fundo
    e resolvido via subquery a partir do `ua_id`.

    Reconciliacao com consolidado MEC vira linha separada de auditoria
    (Fase 4 do redesign), nao mais fonte de calculo.
    """
    fundo_doc_subq = (
        select(UnidadeAdministrativa.cnpj)
        .where(UnidadeAdministrativa.id == ua_id)
        .scalar_subquery()
    )
    stmt = (
        select(func.coalesce(func.sum(EstoqueRecebivel.valor_presente), ZERO))
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc_subq)
        .where(EstoqueRecebivel.data_referencia == data)
        .where(EstoqueRecebivel.faixa_pdd != "WOP")
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _sum_pdd(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date,
) -> Decimal:
    """PDD = Σ wh_estoque_recebivel.valor_pdd, excluindo WOP.

    Refactor 2026-05-24 (metodo granular, Fase 1B do redesign cota-sub):
    pareada com `_sum_dc` (Fase 1A) — mesma fonte granular ex-WOP. Antes lia
    `wh_posicao_outros_ativos.valor_total` filtrado por codigo='PDD'
    (consolidado QiTech, vinha negativo).

    Granular retorna SEMPRE positivo (sem inversao). O consumer
    (`balanco_patrimonial._snapshot_categorias`) ja faz `abs(pdd_raw)`
    — segue no-op com valor positivo.

    WOP excluido pelo mesmo motivo de `_sum_dc`: titulos em WOP estao 100%
    provisionados, mas QiTech segrega tanto na DC quanto na PDD consolidada.
    Excluindo de ambos os lados, mantemos a coerencia (efeito liquido zero
    no PL Sub Jr).

    Reconciliacao com PDD consolidado (`wh_posicao_outros_ativos`) vira
    auditoria separada na Fase 4.
    """
    fundo_doc_subq = (
        select(UnidadeAdministrativa.cnpj)
        .where(UnidadeAdministrativa.id == ua_id)
        .scalar_subquery()
    )
    stmt = (
        select(func.coalesce(func.sum(EstoqueRecebivel.valor_pdd), ZERO))
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc_subq)
        .where(EstoqueRecebivel.data_referencia == data)
        .where(EstoqueRecebivel.faixa_pdd != "WOP")
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _sum_cpr_snapshot(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(CprMovimento.valor), ZERO))
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao == data)
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _sum_cpr_por_sinal(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> tuple[Decimal, Decimal]:
    """CPR segregado por sinal de `valor` (mesma heuristica de `_cpr_lista`).

    Retorna (a_receber, a_pagar):
      - a_receber = Σ(valor > 0) -> natureza ATIVA. Diferimentos de despesa +
        "LIQUIDADOS TOTAL - PROV" (recebivel em transito retido pelo floating
        bancario). Sempre >= 0.
      - a_pagar   = Σ(valor < 0) -> natureza PASSIVA (despesas/taxas/IOF a
        recolher). Mantem o sinal NEGATIVO (<= 0).

    Por construcao `a_receber + a_pagar == _sum_cpr_snapshot` (o net do dia).
    Snapshot de UM dia (1 linha por item): somar e correto. A armadilha do
    "saldo acumulado por lote" so morde em serie temporal/multi-lote.
    """
    stmt = (
        select(
            func.coalesce(
                func.sum(case((CprMovimento.valor > 0, CprMovimento.valor), else_=ZERO)),
                ZERO,
            ),
            func.coalesce(
                func.sum(case((CprMovimento.valor < 0, CprMovimento.valor), else_=ZERO)),
                ZERO,
            ),
        )
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao == data)
    )
    receber, pagar = (await db.execute(stmt)).one()
    return Decimal(receber or 0), Decimal(pagar or 0)


async def _sum_tesouraria(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date
) -> Decimal:
    """Tesouraria do driver Sub = `wh_saldo_tesouraria` classe Sub apenas.

    Refactor 2026-05-19 (metodo gestor REALINVEST, ΔSaldo simples): antes
    somava `wh_saldo_tesouraria` + `wh_saldo_conta_corrente`, mas o gestor
    publica "Tesouraria" como uma unica linha consolidada em
    `market.tesouraria`. SaldoContaCorrente cobre o mesmo dinheiro de outro
    angulo (visao da conta, nao do fundo) — duplica contagem na otica do
    PL Sub. Mantemos apenas `wh_saldo_tesouraria` da classe Sub (exclui
    MEZANINO/SENIOR — cada classe reporta seu saldo separadamente).
    """
    s_tes = (
        select(func.coalesce(func.sum(SaldoTesouraria.valor), ZERO))
        .where(SaldoTesouraria.tenant_id == tenant_id)
        .where(SaldoTesouraria.unidade_administrativa_id == ua_id)
        .where(SaldoTesouraria.data_posicao == data)
        .where(SaldoTesouraria.carteira_cliente_nome.notilike("%MEZANINO%"))
        .where(SaldoTesouraria.carteira_cliente_nome.notilike("%SENIOR%"))
    )
    return Decimal((await db.execute(s_tes)).scalar() or 0)


async def _saldo_tesouraria_evidencias(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, d_prev: date, d0: date,
) -> tuple[SaldoTesourariaEvidencia, ...]:
    """Composicao do saldo de tesouraria por descricao (D-1 → D0).

    Refactor 2026-05-19: pareada com `_sum_tesouraria`, le APENAS
    `wh_saldo_tesouraria` da classe Sub. Σ deltas = valor_brl do driver
    Tesouraria.
    """
    stmt_tes = (
        select(
            SaldoTesouraria.descricao,
            SaldoTesouraria.data_posicao,
            func.coalesce(func.sum(SaldoTesouraria.valor), ZERO).label("valor"),
        )
        .where(SaldoTesouraria.tenant_id == tenant_id)
        .where(SaldoTesouraria.unidade_administrativa_id == ua_id)
        .where(SaldoTesouraria.data_posicao.in_([d_prev, d0]))
        .where(SaldoTesouraria.carteira_cliente_nome.notilike("%MEZANINO%"))
        .where(SaldoTesouraria.carteira_cliente_nome.notilike("%SENIOR%"))
        .group_by(SaldoTesouraria.descricao, SaldoTesouraria.data_posicao)
    )
    rows_tes = (await db.execute(stmt_tes)).all()
    tes_pivot: dict[tuple[str, date], Decimal] = {}
    tes_descricoes: set[str] = set()
    for desc, dpos, val in rows_tes:
        desc = desc or "Saldo em Tesouraria"
        tes_pivot[(desc, dpos)] = Decimal(val or 0)
        tes_descricoes.add(desc)

    evid: list[SaldoTesourariaEvidencia] = []
    for desc in sorted(tes_descricoes):
        v_prev = tes_pivot.get((desc, d_prev), ZERO)
        v_d0 = tes_pivot.get((desc, d0), ZERO)
        evid.append(
            SaldoTesourariaEvidencia(
                fonte="wh_saldo_tesouraria",
                descricao=desc,
                codigo=None,
                valor_d_prev=v_prev,
                valor_d0=v_d0,
                delta=v_d0 - v_prev,
            )
        )
    return tuple(evid)


async def _composicao_compromissada_evidencias(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    d_prev: date,
    d0: date,
) -> tuple[SaldoTesourariaEvidencia, ...]:
    """Composicao do saldo de Compromissadas por operacao (D-1 → D0).

    1 evidencia por `codigo` (= 1 operacao compromissada) presente em D-1
    OU D0. Σ deltas = valor_brl do driver. Descricao traz papel + taxa +
    janela (aquisicao → resgate) pra dar contexto.

    Reaproveita `SaldoTesourariaEvidencia` (shape generico).
    """
    stmt = (
        select(
            PosicaoCompromissada.codigo,
            PosicaoCompromissada.papel,
            PosicaoCompromissada.taxa_ano,
            PosicaoCompromissada.data_aquisicao,
            PosicaoCompromissada.data_resgate,
            PosicaoCompromissada.data_posicao,
            func.coalesce(
                func.sum(PosicaoCompromissada.valor_bruto), ZERO,
            ).label("valor"),
        )
        .where(PosicaoCompromissada.tenant_id == tenant_id)
        .where(PosicaoCompromissada.unidade_administrativa_id == ua_id)
        .where(PosicaoCompromissada.data_posicao.in_([d_prev, d0]))
        .group_by(
            PosicaoCompromissada.codigo,
            PosicaoCompromissada.papel,
            PosicaoCompromissada.taxa_ano,
            PosicaoCompromissada.data_aquisicao,
            PosicaoCompromissada.data_resgate,
            PosicaoCompromissada.data_posicao,
        )
    )
    rows = (await db.execute(stmt)).all()

    pivot: dict[tuple[str, date], Decimal] = {}
    # Metadata da operacao (papel/taxa/datas) — preferencia D0; fallback D-1.
    meta: dict[str, dict[str, object]] = {}
    for codigo, papel, taxa, dt_aq, dt_rg, dpos, val in rows:
        codigo = codigo or "(sem codigo)"
        pivot[(codigo, dpos)] = Decimal(val or 0)
        # Atualiza metadata: D0 sobrescreve D-1 (mais recente).
        if codigo not in meta or dpos == d0:
            meta[codigo] = {
                "papel":         papel or "",
                "taxa_ano":      taxa,
                "data_aquisicao": dt_aq,
                "data_resgate":  dt_rg,
            }

    evid: list[SaldoTesourariaEvidencia] = []
    for codigo, m in meta.items():
        v_prev = pivot.get((codigo, d_prev), ZERO)
        v_d0 = pivot.get((codigo, d0), ZERO)
        # Filtro: ignora operacoes zeradas nos 2 dias.
        if v_prev == ZERO and v_d0 == ZERO:
            continue
        # Monta descricao: "LTNO @ 13,80%aa · 11/05→12/05".
        parts: list[str] = []
        if m["papel"]:
            parts.append(str(m["papel"]))
        if m["taxa_ano"] is not None:
            taxa_str = f"{float(m['taxa_ano']):.2f}".replace(".", ",")  # type: ignore[arg-type]
            parts.append(f"@ {taxa_str}%aa")
        if m["data_aquisicao"] and m["data_resgate"]:
            dt_aq = m["data_aquisicao"]
            dt_rg = m["data_resgate"]
            parts.append(
                f"{dt_aq.strftime('%d/%m')}→{dt_rg.strftime('%d/%m')}",  # type: ignore[union-attr]
            )
        descricao = " · ".join(parts) if parts else codigo

        evid.append(
            SaldoTesourariaEvidencia(
                fonte="wh_posicao_compromissada",
                descricao=descricao,
                codigo=codigo,
                valor_d_prev=v_prev,
                valor_d0=v_d0,
                delta=v_d0 - v_prev,
            )
        )
    evid.sort(key=lambda e: abs(e.delta), reverse=True)
    return tuple(evid)


async def _composicao_fundos_di_evidencias(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    d_prev: date,
    d0: date,
) -> tuple[SaldoTesourariaEvidencia, ...]:
    """Composicao do saldo de Fundos DI por fundo externo (D-1 → D0).

    1 evidencia por fundo externo presente em D-1 OU D0 (FULL JOIN). Σ
    deltas = valor_brl do driver. Pareada com `_sum_fundos_di` (exclui
    fundos internos REALINVEST A VENCER / VENCIDOS).

    Reaproveita `SaldoTesourariaEvidencia` — shape generico (descricao +
    saldos D-1/D0 + delta). Nome do tipo e historico (criado pro driver
    Tesouraria); pode acabar renomeado pra `ComposicaoSaldoEvidencia` em
    refactor futuro.
    """
    stmt = (
        select(
            PosicaoCotaFundo.ativo_nome,
            PosicaoCotaFundo.data_posicao,
            func.coalesce(
                func.sum(PosicaoCotaFundo.valor_liquido), ZERO,
            ).label("valor"),
        )
        .where(PosicaoCotaFundo.tenant_id == tenant_id)
        .where(PosicaoCotaFundo.unidade_administrativa_id == ua_id)
        .where(PosicaoCotaFundo.data_posicao.in_([d_prev, d0]))
        .group_by(PosicaoCotaFundo.ativo_nome, PosicaoCotaFundo.data_posicao)
    )
    rows = (await db.execute(stmt)).all()

    pivot: dict[tuple[str, date], Decimal] = {}
    nomes_externos: set[str] = set()
    for nome, dpos, val in rows:
        nome = nome or "(sem nome)"
        if not _is_fundo_externo(nome, ua_nome):
            continue
        pivot[(nome, dpos)] = Decimal(val or 0)
        nomes_externos.add(nome)

    evid: list[SaldoTesourariaEvidencia] = []
    for nome in sorted(nomes_externos):
        v_prev = pivot.get((nome, d_prev), ZERO)
        v_d0 = pivot.get((nome, d0), ZERO)
        # Filtro: ignora fundos que ficaram zerados nos 2 dias (poluiria UI).
        if v_prev == ZERO and v_d0 == ZERO:
            continue
        evid.append(
            SaldoTesourariaEvidencia(
                fonte="wh_posicao_cota_fundo",
                descricao=nome,
                codigo=None,
                valor_d_prev=v_prev,
                valor_d0=v_d0,
                delta=v_d0 - v_prev,
            )
        )
    # Ordena por |delta| desc — destaque pra fundos que mexeram mais.
    evid.sort(key=lambda e: abs(e.delta), reverse=True)
    return tuple(evid)


async def _pl_sub_jr(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, ua_nome: str, data: date
) -> Decimal:
    classes = await _mec_classes(db, tenant_id, ua_id, ua_nome, data)
    return classes["sub_jr"]


# ─────────────────────────────────────────────────────────────────────────────
# Apropriacao DC — bloco a vencer e bloco vencidos
# ─────────────────────────────────────────────────────────────────────────────


async def _estoque_a_vencer(
    db: AsyncSession, tenant_id: UUID, fundo_doc: str, data: date
) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(EstoqueRecebivel.valor_presente), ZERO))
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data)
        .where(EstoqueRecebivel.data_vencimento_ajustada >= data)
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _estoque_vencidos(
    db: AsyncSession, tenant_id: UUID, fundo_doc: str, data: date
) -> Decimal:
    stmt = (
        select(func.coalesce(func.sum(EstoqueRecebivel.valor_presente), ZERO))
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data)
        .where(EstoqueRecebivel.data_vencimento_ajustada < data)
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _aquisicoes(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    d1: date,
    d0: date,
    a_vencer_ref_data: date | None = None,
) -> Decimal:
    """Aquisicoes consolidadas no periodo (d1, d0].

    Se `a_vencer_ref_data` e dado, filtra aquisicoes com vencimento > a_vencer_ref_data
    (subset 'a vencer no momento de referencia').
    Se None, retorna todas (subset 'vencidos' = total - a_vencer; aqui retorna 0
    pois aquisicoes a vencer nao se sobrepoem com vencidos no mesmo periodo).
    """
    stmt = (
        select(func.coalesce(func.sum(AquisicaoRecebivel.valor_compra), ZERO))
        .where(AquisicaoRecebivel.tenant_id == tenant_id)
        .where(AquisicaoRecebivel.unidade_administrativa_id == ua_id)
        .where(AquisicaoRecebivel.data_aquisicao > d1)
        .where(AquisicaoRecebivel.data_aquisicao <= d0)
    )
    if a_vencer_ref_data is not None:
        stmt = stmt.where(AquisicaoRecebivel.data_vencimento > a_vencer_ref_data)
    else:
        # bloco "vencidos" — aquisicoes ja vencidas no momento da aquisicao
        stmt = stmt.where(AquisicaoRecebivel.data_vencimento <= d0)
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _liquidados(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    d1: date,
    d0: date,
    *,
    apenas_vencidos: bool,
) -> Decimal:
    """Liquidados no periodo (d1, d0]. Sinal: NEGATIVO (saida do estoque).

    Heuristica: se `apenas_vencidos`, filtra `data_vencimento < data_posicao`
    (titulo ja estava vencido quando foi liquidado). Caso contrario, o restante
    (a vencer no momento da liquidacao).
    """
    stmt = (
        select(func.coalesce(func.sum(LiquidacaoRecebivel.valor_pago), ZERO))
        .where(LiquidacaoRecebivel.tenant_id == tenant_id)
        .where(LiquidacaoRecebivel.unidade_administrativa_id == ua_id)
        .where(LiquidacaoRecebivel.data_posicao > d1)
        .where(LiquidacaoRecebivel.data_posicao <= d0)
    )
    if apenas_vencidos:
        stmt = stmt.where(
            LiquidacaoRecebivel.data_vencimento < LiquidacaoRecebivel.data_posicao,
        )
    else:
        stmt = stmt.where(
            LiquidacaoRecebivel.data_vencimento >= LiquidacaoRecebivel.data_posicao,
        )
    raw = Decimal((await db.execute(stmt)).scalar() or 0)
    return -raw  # negativo = saida


async def _apropriacao_dc(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, fundo_doc: str, d1: date, d0: date
) -> ApropriacaoDc:
    # A vencer
    av_d1 = await _estoque_a_vencer(db, tenant_id, fundo_doc, d1)
    av_d0 = await _estoque_a_vencer(db, tenant_id, fundo_doc, d0)
    av_aq = await _aquisicoes(db, tenant_id, ua_id, d1, d0, a_vencer_ref_data=d0)
    av_li = await _liquidados(db, tenant_id, ua_id, d1, d0, apenas_vencidos=False)
    av_apr = av_d0 - (av_d1 + av_aq + av_li)

    # Vencidos
    ve_d1 = await _estoque_vencidos(db, tenant_id, fundo_doc, d1)
    ve_d0 = await _estoque_vencidos(db, tenant_id, fundo_doc, d0)
    ve_aq = await _aquisicoes(db, tenant_id, ua_id, d1, d0, a_vencer_ref_data=None)
    ve_li = await _liquidados(db, tenant_id, ua_id, d1, d0, apenas_vencidos=True)
    ve_apr = ve_d0 - (ve_d1 + ve_aq + ve_li)

    return ApropriacaoDc(
        a_vencer=ApropriacaoDcLinha(
            estoque_d1=av_d1, aquisicoes=av_aq, liquidados=av_li,
            estoque_d0=av_d0, apropriacao=av_apr,
        ),
        vencidos=ApropriacaoDcLinha(
            estoque_d1=ve_d1, aquisicoes=ve_aq, liquidados=ve_li,
            estoque_d0=ve_d0, apropriacao=ve_apr,
        ),
        total=av_apr + ve_apr,
    )


def _apropriacao_dc_evidencias(
    apr: ApropriacaoDc, d_prev: date, d0: date,
) -> tuple[ApropriacaoDcEvidencia, ...]:
    """4 inputs do calculo `Apropriacao = ΔEstoque - Aq + Liq` (consolidados).

    Cada evidencia traz o valor com sinal coerente com a formula — Σ
    valor_brl das 4 evidencias = `apr.total` do driver.

    Labels carregam as datas dinamicamente pra evitar ambiguidade ("do dia"
    nao deixa claro qual dia). Aquisicoes/liquidacoes acontecem em D0
    (intervalo (d_prev, d0] em `_aquisicoes` / `_liquidados`).

    Convencao do source (em `_liquidados`): valor_pago retorna NEGATIVO
    (saida do estoque). Logo, `-Liq` no codigo equivale a `+|Liq|`
    conceitualmente — caixa retorna ao fundo, apropriacao positiva
    quando o estoque caiu por liquidacao.
    """
    delta_a_vencer = apr.a_vencer.estoque_d0 - apr.a_vencer.estoque_d1
    delta_vencidos = apr.vencidos.estoque_d0 - apr.vencidos.estoque_d1
    aquisicoes_total = apr.a_vencer.aquisicoes + apr.vencidos.aquisicoes
    liquidados_total = apr.a_vencer.liquidados + apr.vencidos.liquidados

    fmt_prev = d_prev.strftime("%d/%m")
    fmt_d0 = d0.strftime("%d/%m")

    return (
        ApropriacaoDcEvidencia(
            label=f"Estoque a vencer · {fmt_prev} → {fmt_d0}",
            fonte="wh_estoque_recebivel",
            bloco="a_vencer",
            valor_d_prev=apr.a_vencer.estoque_d1,
            valor_d0=apr.a_vencer.estoque_d0,
            valor_brl=delta_a_vencer,
        ),
        ApropriacaoDcEvidencia(
            label=f"Estoque vencidos · {fmt_prev} → {fmt_d0}",
            fonte="wh_estoque_recebivel",
            bloco="vencidos",
            valor_d_prev=apr.vencidos.estoque_d1,
            valor_d0=apr.vencidos.estoque_d0,
            valor_brl=delta_vencidos,
        ),
        ApropriacaoDcEvidencia(
            label=f"Aquisições em {fmt_d0}",
            fonte="wh_aquisicao_recebivel",
            bloco="aquisicoes",
            valor_brl=-aquisicoes_total,
        ),
        ApropriacaoDcEvidencia(
            label=f"Liquidações em {fmt_d0}",
            fonte="wh_liquidacao_recebivel",
            bloco="liquidados",
            valor_brl=-liquidados_total,
        ),
    )


# ─────────────────────────────────────────────────────────────────────────────
# CPR detalhado
# ─────────────────────────────────────────────────────────────────────────────


async def _cpr_lista(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, data: date, *, receber: bool
) -> list[CprMovimentoItem]:
    """Lista de itens CPR por sinal de `valor` (receber=positivo, pagar=negativo).

    Heuristica de segregacao: pelo sinal numerico do `valor`. Se o adapter grava
    todos os valores como positivos e usa `historico_traduzido` para indicar
    direcao, este filtro precisa ser estendido para olhar o historico.
    """
    cond = CprMovimento.valor > 0 if receber else CprMovimento.valor < 0
    stmt = (
        select(CprMovimento.descricao, CprMovimento.valor)
        .where(CprMovimento.tenant_id == tenant_id)
        .where(CprMovimento.unidade_administrativa_id == ua_id)
        .where(CprMovimento.data_posicao == data)
        .where(cond)
        .order_by(CprMovimento.valor.desc() if receber else CprMovimento.valor.asc())
    )
    rows = (await db.execute(stmt)).all()
    return [
        CprMovimentoItem(descricao=desc or "", valor=Decimal(val or 0))
        for desc, val in rows
    ]


async def _cpr_detalhado(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, d1: date, d0: date
) -> CprDetalhado:
    receber_d1 = await _cpr_lista(db, tenant_id, ua_id, d1, receber=True)
    receber_d0 = await _cpr_lista(db, tenant_id, ua_id, d0, receber=True)
    pagar_d1   = await _cpr_lista(db, tenant_id, ua_id, d1, receber=False)
    pagar_d0   = await _cpr_lista(db, tenant_id, ua_id, d0, receber=False)

    total_d1 = sum((m.valor for m in receber_d1), ZERO) + sum((m.valor for m in pagar_d1), ZERO)
    total_d0 = sum((m.valor for m in receber_d0), ZERO) + sum((m.valor for m in pagar_d0), ZERO)

    return CprDetalhado(
        receber_d1=receber_d1,
        receber_d0=receber_d0,
        pagar_d1=pagar_d1,
        pagar_d0=pagar_d0,
        total_d1=total_d1,
        total_d0=total_d0,
        variacao=total_d0 - total_d1,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Orquestracao principal
# ─────────────────────────────────────────────────────────────────────────────


def _categoria(
    key: str, label: str, d1: Decimal, d0: Decimal, source: str
) -> PlCategoria:
    return PlCategoria(
        key=key, label=label, d1=d1, d0=d0, delta=d0 - d1, source=source,
    )


def _signal(valor: Decimal) -> str:
    if valor > 0:
        return "ganho"
    if valor < 0:
        return "prejuizo"
    return "neutro"


async def compute_variacao_diaria(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    *,
    data_d1: date | None = None,
) -> VariacaoDiariaResponse:
    """Computa a resposta completa do endpoint."""

    # Resolve UA + dia anterior
    ua = (
        await db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise ValueError(f"Unidade Administrativa {ua_id} nao encontrada no tenant")

    fundo_doc = ua.cnpj or ""
    # D-1: fonte de verdade = wh_dia_util_qitech (mesma do Calendar). Trata
    # feriados e falhas de ETL uniformemente — `_dia_util_anterior` local
    # so recua sab/dom, deprecated via essa substituicao.
    d1 = data_d1 or await dia_util_anterior_qitech(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )

    # Categorias D-1 e D0
    compromissada_d1 = await _sum_compromissada(db, tenant_id, ua_id, d1)
    compromissada_d0 = await _sum_compromissada(db, tenant_id, ua_id, data_d0)
    classes_d1 = await _mec_classes(db, tenant_id, ua_id, ua.nome, d1)
    classes_d0 = await _mec_classes(db, tenant_id, ua_id, ua.nome, data_d0)
    titulos_d1 = await _sum_titulos_publicos(db, tenant_id, ua_id, d1)
    titulos_d0 = await _sum_titulos_publicos(db, tenant_id, ua_id, data_d0)
    outros_d1 = await _sum_outros_ativos_nao_tpf(db, tenant_id, ua_id, d1)
    outros_d0 = await _sum_outros_ativos_nao_tpf(db, tenant_id, ua_id, data_d0)
    fundos_di_d1 = await _sum_fundos_di(db, tenant_id, ua_id, ua.nome, d1)
    fundos_di_d0 = await _sum_fundos_di(db, tenant_id, ua_id, ua.nome, data_d0)
    op_estr_d1 = await _sum_op_estruturadas(db, tenant_id, ua_id, d1)
    op_estr_d0 = await _sum_op_estruturadas(db, tenant_id, ua_id, data_d0)
    dc_d1 = await _sum_dc(db, tenant_id, ua_id, ua.nome, d1)
    dc_d0 = await _sum_dc(db, tenant_id, ua_id, ua.nome, data_d0)
    pdd_d1 = await _sum_pdd(db, tenant_id, ua_id, d1)
    pdd_d0 = await _sum_pdd(db, tenant_id, ua_id, data_d0)
    cpr_snap_d1 = await _sum_cpr_snapshot(db, tenant_id, ua_id, d1)
    cpr_snap_d0 = await _sum_cpr_snapshot(db, tenant_id, ua_id, data_d0)
    teso_d1 = await _sum_tesouraria(db, tenant_id, ua_id, d1)
    teso_d0 = await _sum_tesouraria(db, tenant_id, ua_id, data_d0)

    # Mezanino e Senior — sinal invertido (passivo do Sub Jr)
    mezanino_d1 = -classes_d1["mezanino"]
    mezanino_d0 = -classes_d0["mezanino"]
    senior_d1 = -classes_d1["senior"]
    senior_d0 = -classes_d0["senior"]

    pl_d1 = classes_d1["sub_jr"]
    pl_d0 = classes_d0["sub_jr"]
    pl_delta = pl_d0 - pl_d1
    pl_delta_pct = (pl_delta / pl_d1) if pl_d1 != 0 else ZERO

    categorias = [
        _categoria("compromissada",    "Compromissada",    compromissada_d1, compromissada_d0, "wh_posicao_compromissada"),
        _categoria("mezanino",         "Mezanino",         mezanino_d1,      mezanino_d0,      "wh_mec_evolucao_cotas (classe Mez x -1)"),
        _categoria("senior",           "Senior",           senior_d1,        senior_d0,        "wh_mec_evolucao_cotas (classe Sr x -1)"),
        _categoria("titulos_publicos", "Titulos Publicos", titulos_d1,       titulos_d0,       "wh_posicao_renda_fixa (COSIF TPF)"),
        _categoria("fundos_di",        "Fundos DI",        fundos_di_d1,     fundos_di_d0,     "wh_posicao_cota_fundo (externos)"),
        _categoria("dc",               "DC",               dc_d1,            dc_d0,            "wh_posicao_cota_fundo (internos REALINVEST)"),
        _categoria("op_estruturadas",  "Op Estruturadas",  op_estr_d1,       op_estr_d0,       "wh_posicao_renda_fixa (COSIF Nota Comercial)"),
        _categoria("outros_ativos",    "Outros Ativos",    outros_d1,        outros_d0,        "wh_posicao_outros_ativos (exclui PDD + TPF)"),
        _categoria("pdd",              "PDD",              pdd_d1,           pdd_d0,           "wh_posicao_outros_ativos (codigo='PDD')"),
        _categoria("cpr",              "CPR",              cpr_snap_d1,      cpr_snap_d0,      "wh_cpr_movimento (sum valor)"),
        _categoria("tesouraria",       "Tesouraria",       teso_d1,          teso_d0,          "wh_saldo_tesouraria (classe Sub)"),
    ]

    # Apropriacao DC + CPR detalhado
    apr_dc = await _apropriacao_dc(db, tenant_id, ua_id, fundo_doc, d1, data_d0)
    cpr_det = await _cpr_detalhado(db, tenant_id, ua_id, d1, data_d0)

    # Drivers canonicos (Fase 3b do refactor, 2026-05-18). Lazy import pra
    # evitar circular: compute.py importa helpers daqui (`_sum_*`); inverter
    # o sentido aqui exigiria mover helpers pra modulo neutro — refactor
    # registrado como tech debt da Fase 4.
    from app.modules.controladoria.schemas.cota_sub import DriverResultOut
    from app.modules.controladoria.services.cota_sub_drivers import (
        compute_drivers,
    )

    driver_computation = await compute_drivers(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0, data_d_prev=d1,
    )
    drivers_out = [
        DriverResultOut(
            metric_global_id=d.metric_global_id,
            label=d.label,
            formula_description=d.formula_description,
            valor_brl=d.valor_brl,
            valor_d_prev=d.valor_d_prev,
            valor_d0=d.valor_d0,
            endpoints_required=list(d.endpoints_required),
            indeterminado_por_dado=d.indeterminado_por_dado,
            motivo_indeterminado=d.motivo_indeterminado,
            endpoints_unavailable=list(d.endpoints_unavailable),
            # Evidencias especializadas por driver (Fase 4b, 2026-05-18).
            # Cada driver popula 0-1 campo; demais ficam vazios.
            pdd_evidencias=list(d.pdd_evidencias),
            mtm_evidencias=list(d.mtm_evidencias),
            cpr_evidencias=list(d.cpr_evidencias),
            remuneracao_evidencias=list(d.remuneracao_evidencias),
            movimento_carteira_evidencias=list(d.movimento_carteira_evidencias),
            saldo_tesouraria_evidencias=list(d.saldo_tesouraria_evidencias),
            apropriacao_dc_evidencias=list(d.apropriacao_dc_evidencias),
        )
        for d in driver_computation.drivers
    ]

    # Decomposicao (painel C27:D35 da planilha)
    delta_pdd = pdd_d0 - pdd_d1
    delta_compromissada = compromissada_d0 - compromissada_d1
    delta_senior = senior_d0 - senior_d1
    delta_mezanino = mezanino_d0 - mezanino_d1
    delta_titulos = titulos_d0 - titulos_d1
    delta_fundos_di = fundos_di_d0 - fundos_di_d1

    decomposicao = [
        DecomposicaoItem(key="pdd",              label="PDD",                  valor=delta_pdd,        sinal=_signal(delta_pdd)),
        DecomposicaoItem(key="apropriacao_dc",   label="Apropriacao de DC",    valor=apr_dc.total,     sinal=_signal(apr_dc.total)),
        DecomposicaoItem(key="fundos_di",        label="Fundos DI",            valor=delta_fundos_di,  sinal=_signal(delta_fundos_di)),
        DecomposicaoItem(key="apropriacao_dsp",  label="Apropriacao despesas", valor=cpr_det.variacao, sinal=_signal(cpr_det.variacao)),
        DecomposicaoItem(key="compromissada",    label="Compromissada",        valor=delta_compromissada, sinal=_signal(delta_compromissada)),
        DecomposicaoItem(key="senior",           label="Senior",               valor=delta_senior,     sinal=_signal(delta_senior)),
        DecomposicaoItem(key="mezanino",         label="Mezanino",             valor=delta_mezanino,   sinal=_signal(delta_mezanino)),
        DecomposicaoItem(key="titulos",          label="Titulos Publicos",     valor=delta_titulos,    sinal=_signal(delta_titulos)),
        DecomposicaoItem(key="tarifas",          label="Tarifas",              valor=ZERO,             sinal="neutro"),
    ]
    decomposicao_total = sum((d.valor for d in decomposicao), ZERO)

    return VariacaoDiariaResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior=d1,
        pl_d1=pl_d1,
        pl_d0=pl_d0,
        pl_delta=pl_delta,
        pl_delta_pct=pl_delta_pct,
        categorias=categorias,
        decomposicao=decomposicao,
        decomposicao_total=decomposicao_total,
        divergencia=decomposicao_total - pl_delta,
        apropriacao_dc=apr_dc,
        cpr_detalhado=cpr_det,
        drivers=drivers_out,
        soma_drivers=driver_computation.soma_drivers,
        residuo_modelo=driver_computation.residuo,
    )
