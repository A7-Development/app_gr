"""Controladoria · Cota Sub — detector de itens NAO RECONHECIDOS.

Problema que resolve (2026-05-27, caso VCNC): cada driver da pagina Cota Sub
classifica/filtra suas fontes por heuristica. Quando a QiTech publica um valor
NOVO num campo de classificacao (uma sigla de papel nova, uma classe de cota
renomeada, uma faixa de PDD inedita), a heuristica nao casa e o item:

  - SOME da particao patrimonial -> vaza pro residuo, em silencio (modo
    `vaza_residuo`); ou
  - ENTRA num driver indevidamente / em dobro (modo `entra_indevido`).

O caso VCNC (nota comercial vencida nao reconhecida pela regra COSIF) ficou
+44k invisivel por 93 dias ate ser pego no olho (+37k MEC vs ~0 modelo).

Este modulo varre TODAS as fontes da pagina e reporta o que cada driver NAO
conseguiu reconhecer — usando a MESMA logica de reconhecimento que o driver
usa (reaproveita `_is_sub_jr`/`_is_mezanino`/`_is_senior`, `classify` + COSIF
map, `_is_fundo_externo`, constante WOP). Reusar a logica do driver (em vez de
declarar um vocabulario paralelo) garante que o detector nunca saia de sincronia
com o que o driver de fato conta.

Invariante de reconciliacao: Σ(valor dos itens `vaza_residuo`) deve explicar uma
parcela do `residuo_modelo` da variacao diaria. O que sobra e ruido real
(timing de caixa/floating), nao drop cego.

Consumo: endpoint da pagina expoe o relatorio (painel "Itens nao reconhecidos")
e o smoke `smoke_cota_sub_completude.py` faz guard de CI (zero `vaza_residuo`
acima de threshold em datas-controle).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.controladoria.services.cota_sub import (
    ZERO,
    _driver_for_nome_papel,
    _is_fundo_externo,
    _is_mezanino,
    _is_senior,
    _is_sub_jr,
    _is_titulo_publico,
)
from app.warehouse.estoque_recebivel import EstoqueRecebivel
from app.warehouse.mec_evolucao_cotas import MecEvolucaoCotas
from app.warehouse.posicao_cota_fundo import PosicaoCotaFundo
from app.warehouse.posicao_outros_ativos import PosicaoOutrosAtivos
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa
from app.warehouse.saldo_tesouraria import SaldoTesouraria

# Modo de impacto de um item nao reconhecido.
#   vaza_residuo  -> some da particao, infla o residuo (o caso grave: VCNC)
#   entra_indevido-> entra num driver indevidamente / em dobro
#   vigia         -> reconhecido hoje, mas em campo heuristico — exposto pra
#                    auditoria (valor novo aparecendo num filtro que so inclui)
Modo = Literal["vaza_residuo", "entra_indevido", "vigia"]

# Faixas de rating PDD conhecidas (escala CVM AA..H) + write-off pendente.
# Usada so como vocabulario de VIGIA do campo `faixa_pdd`: uma faixa fora deste
# conjunto esta sendo silenciosamente tratada como performada (incluida em
# DC/PDD) — pode ser um novo rotulo de baixa que deveria ser excluido como WOP.
_FAIXAS_PDD_CONHECIDAS = {"AA", "A", "B", "C", "D", "E", "F", "G", "H", "WOP"}
_FAIXA_WOP = "WOP"

# Threshold de relevancia: itens com |valor| abaixo disso nao viram alerta
# (ruido de centavos). Configuravel pelo caller.
_THRESHOLD_DEFAULT = Decimal("1")

# Janela (dias corridos) p/ a vigia de fundo externo decidir se um fundo e "novo".
# So vira vigia se NAO foi visto (>= threshold) em nenhum dia desta janela antes
# de D0. Evita que um fundo DI de varredura (caixa ocioso que zera e recarrega,
# ex.: ITAU SOBERANO REF SI) reacenda o alerta a cada recarga. ~30 dias uteis.
_FUNDO_NOVO_LOOKBACK_DIAS = 45


@dataclass(frozen=True)
class ItemNaoReconhecido:
    """Um valor que uma fonte da pagina Cota Sub nao soube classificar."""

    fonte: str            # silver table (ex.: "wh_posicao_renda_fixa")
    endpoint: str         # endpoint QiTech de origem (ex.: "qitech.market.rf")
    campo: str            # campo de classificacao (ex.: "nome_do_papel")
    identificador: str    # valor cru (codigo do papel, nome da classe, faixa)
    label: str            # rotulo humano pra UI
    valor_d0: Decimal     # peso R$ em D0 (0 se ausente em D0)
    valor_d_prev: Decimal # peso R$ em D-1 (0 se ausente em D-1)
    modo: Modo
    driver_afetado: str   # qual driver/alvo sofre (ex.: "Op Estruturadas", "ALVO PL Sub")
    motivo: str           # explicacao curta pt-BR


@dataclass(frozen=True)
class CompletudeReport:
    """Resultado da varredura — itens + agregados pra guard e UI."""

    data_d0: date
    data_d_prev: date
    itens: tuple[ItemNaoReconhecido, ...] = ()

    @property
    def vaza_residuo(self) -> tuple[ItemNaoReconhecido, ...]:
        return tuple(i for i in self.itens if i.modo == "vaza_residuo")

    @property
    def entra_indevido(self) -> tuple[ItemNaoReconhecido, ...]:
        return tuple(i for i in self.itens if i.modo == "entra_indevido")

    @property
    def total_vaza_residuo_d0(self) -> Decimal:
        """Σ |valor D0| dos itens que vazam pro residuo — deve explicar parte
        do residuo_modelo da variacao diaria."""
        return sum((abs(i.valor_d0) for i in self.vaza_residuo), ZERO)

    @property
    def tem_alerta(self) -> bool:
        """Ha item em modo drop/false-include (exclui vigia informacional)."""
        return any(i.modo in ("vaza_residuo", "entra_indevido") for i in self.itens)


# Exclusoes conhecidas da RF (reconhecidas, fora das 2 linhas): SRP
# (compromissada/repo, pareada ~0) e MEZAN (mezanino, passivo via MEC).
_RF_EXCLUSOES_CONHECIDAS: frozenset[str] = frozenset({"SRP", "MEZAN"})


# ─────────────────────────────────────────────────────────────────────────────
# Scanners por fonte (cada um devolve list[ItemNaoReconhecido])
# ─────────────────────────────────────────────────────────────────────────────


async def _scan_mec_classes(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, ua_nome: str,
    d_prev: date, d0: date, threshold: Decimal,
) -> list[ItemNaoReconhecido]:
    """MEC: classe cujo `carteira_cliente_nome` nao casa Sub/Mez/Senior.

    O MAIS GRAVE: `_mec_classes` distribui patrimonio em {sub_jr, mez, senior};
    uma classe que nao casa nenhum dos 3 some — corrompe o ALVO (PL Sub) ou um
    driver. `_is_sub_jr` usa match EXATO com o nome da UA, entao uma 2a classe
    subordinada ou um rename do fundo derruba o alvo silenciosamente.
    """
    saldos: dict[str, dict[str, Decimal]] = {}  # nome -> {d_prev, d0}
    for d, slot in ((d_prev, "d_prev"), (d0, "d0")):
        rows = (
            await db.execute(
                select(MecEvolucaoCotas.carteira_cliente_nome, MecEvolucaoCotas.patrimonio)
                .where(MecEvolucaoCotas.tenant_id == tenant_id)
                .where(MecEvolucaoCotas.unidade_administrativa_id == ua_id)
                .where(MecEvolucaoCotas.data_posicao == d)
            )
        ).all()
        for nome, patrimonio in rows:
            saldos.setdefault(nome or "", {"d_prev": ZERO, "d0": ZERO})[slot] += Decimal(patrimonio or 0)

    out: list[ItemNaoReconhecido] = []
    for nome, vals in saldos.items():
        if _is_sub_jr(nome, ua_nome) or _is_mezanino(nome) or _is_senior(nome):
            continue
        if abs(vals["d0"]) < threshold and abs(vals["d_prev"]) < threshold:
            continue
        out.append(ItemNaoReconhecido(
            fonte="wh_mec_evolucao_cotas", endpoint="qitech.market.mec",
            campo="carteira_cliente_nome", identificador=nome,
            label=f"Classe nao reconhecida: {nome}",
            valor_d0=vals["d0"], valor_d_prev=vals["d_prev"],
            modo="vaza_residuo", driver_afetado="ALVO PL Sub / Senior / Mezanino",
            motivo=(
                "carteira_cliente_nome nao casa Sub Jr (match exato do nome da UA), "
                "Mezanino nem Senior. Patrimonio desta classe sai da decomposicao."
            ),
        ))
    return out


async def _scan_renda_fixa(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    d_prev: date, d0: date, threshold: Decimal,
) -> list[ItemNaoReconhecido]:
    """Renda fixa: papel cujo `nome_do_papel` NAO e reconhecido — nem cai numa
    linha (Titulos Publicos / Op. Estruturadas via `_driver_for_nome_papel`) nem
    e exclusao conhecida (SRP/MEZAN). Tipo novo que a QiTech trouxer VAZA ->
    flag pra cadastrar. Considera ambas as datas (papel pode entrar so em D0)."""
    acc: dict[str, dict[str, Any]] = {}
    for d, slot in ((d_prev, "d_prev"), (d0, "d0")):
        rows = (
            await db.execute(
                select(
                    PosicaoRendaFixa.codigo, PosicaoRendaFixa.nome_do_papel,
                    PosicaoRendaFixa.codigo_lastro, PosicaoRendaFixa.valor_bruto,
                )
                .where(PosicaoRendaFixa.tenant_id == tenant_id)
                .where(PosicaoRendaFixa.unidade_administrativa_id == ua_id)
                .where(PosicaoRendaFixa.data_posicao == d)
            )
        ).all()
        for codigo, nome, codigo_lastro, valor_bruto in rows:
            entry = acc.setdefault(codigo or nome or "?", {
                "nome": nome or "", "lastro": codigo_lastro or "",
                "d_prev": ZERO, "d0": ZERO,
            })
            entry[slot] = Decimal(valor_bruto or 0)
            entry["nome"] = nome or entry["nome"]
            entry["lastro"] = codigo_lastro or entry["lastro"]

    out: list[ItemNaoReconhecido] = []
    for codigo, e in acc.items():
        nome = e["nome"]
        # Reconhecido (cai numa linha) ou exclusao intencional conhecida -> ok.
        if _driver_for_nome_papel(nome, e["lastro"]) is not None:
            continue
        if (nome or "").strip().upper() in _RF_EXCLUSOES_CONHECIDAS:
            continue
        # Tesouro -OVE = exclusao intencional (garantia/over), nao vaza.
        if nome.strip().upper().startswith(("NTN", "LTN", "LFT")) \
                and (e["lastro"] or "").strip().upper().endswith("OVE"):
            continue
        vd0 = e.get("d0", ZERO)
        vdp = e.get("d_prev", ZERO)
        if abs(vd0) < threshold and abs(vdp) < threshold:
            continue
        out.append(ItemNaoReconhecido(
            fonte="wh_posicao_renda_fixa", endpoint="qitech.market.rf",
            campo="nome_do_papel", identificador=str(codigo),
            label=f"{nome} ({codigo})",
            valor_d0=vd0, valor_d_prev=vdp,
            modo="vaza_residuo",
            driver_afetado="Titulos Publicos / Op Estruturadas",
            motivo=(
                f"Tipo de papel '{nome}' nao reconhecido (nem Tesouro NTN/LTN/LFT, "
                f"nem Nota Comercial NCPX/VCNC/PDDNC, nem exclusao SRP/MEZAN) — "
                f"cadastrar a classificacao em _driver_for_nome_papel."
            ),
        ))
    return out


async def _scan_tesouraria(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, ua_nome: str,
    d_prev: date, d0: date, threshold: Decimal,
) -> list[ItemNaoReconhecido]:
    """Tesouraria: `_sum_tesouraria` mantem tudo que NAO e Mez/Sr como Sub.

    Uma classe nova (nem Mez, nem Sr, nem Sub Jr reconhecida) seria CONTADA
    como Sub indevidamente. Detecta linhas que entram no somatorio Sub mas
    nao batem `_is_sub_jr`.
    """
    acc: dict[str, dict[str, Decimal]] = {}
    for d, slot in ((d_prev, "d_prev"), (d0, "d0")):
        rows = (
            await db.execute(
                select(SaldoTesouraria.carteira_cliente_nome, SaldoTesouraria.valor)
                .where(SaldoTesouraria.tenant_id == tenant_id)
                .where(SaldoTesouraria.unidade_administrativa_id == ua_id)
                .where(SaldoTesouraria.data_posicao == d)
            )
        ).all()
        for nome, valor in rows:
            acc.setdefault(nome or "", {"d_prev": ZERO, "d0": ZERO})[slot] += Decimal(valor or 0)

    out: list[ItemNaoReconhecido] = []
    for nome, vals in acc.items():
        n = (nome or "").upper()
        if "MEZANINO" in n or "SENIOR" in n:
            continue  # excluido do somatorio Sub — ok
        if _is_sub_jr(nome, ua_nome):
            continue  # reconhecido como Sub — ok
        if abs(vals["d0"]) < threshold and abs(vals["d_prev"]) < threshold:
            continue
        out.append(ItemNaoReconhecido(
            fonte="wh_saldo_tesouraria", endpoint="qitech.market.tesouraria",
            campo="carteira_cliente_nome", identificador=nome,
            label=f"Tesouraria de classe nao-Sub contada como Sub: {nome}",
            valor_d0=vals["d0"], valor_d_prev=vals["d_prev"],
            modo="entra_indevido", driver_afetado="Tesouraria",
            motivo=(
                "Linha nao e Mez/Sr e nao casa Sub Jr, mas o filtro 'notlike MEZ/SR' "
                "a inclui no saldo Sub — possivel over-count."
            ),
        ))
    return out


async def _scan_faixa_pdd(
    db: AsyncSession, tenant_id: UUID, fundo_doc: str,
    d_prev: date, d0: date, threshold: Decimal,
) -> list[ItemNaoReconhecido]:
    """Estoque: faixa_pdd fora da escala CVM conhecida + WOP.

    DC/PDD excluem WOP e incluem o resto. Uma faixa inedita esta sendo tratada
    como performada (incluida) — se for um novo rotulo de baixa, deveria sair
    como WOP. VIGIA (a inclusao em si nao some; mas o tratamento pode estar
    errado).
    """
    out: list[ItemNaoReconhecido] = []
    for d, slot in ((d_prev, "d_prev"), (d0, "d0")):
        rows = (
            await db.execute(
                select(
                    EstoqueRecebivel.faixa_pdd,
                    EstoqueRecebivel.valor_presente,
                )
                .where(EstoqueRecebivel.tenant_id == tenant_id)
                .where(EstoqueRecebivel.fundo_doc == fundo_doc)
                .where(EstoqueRecebivel.data_referencia == d)
            )
        ).all()
        agg: dict[str, Decimal] = {}
        for faixa, vp in rows:
            f = (faixa or "(null)").strip().upper()
            if f in _FAIXAS_PDD_CONHECIDAS:
                continue
            agg[f] = agg.get(f, ZERO) + Decimal(vp or 0)
        for f, vp in agg.items():
            if abs(vp) < threshold:
                continue
            out.append(ItemNaoReconhecido(
                fonte="wh_estoque_recebivel", endpoint="qitech.market.fidc_estoque",
                campo="faixa_pdd", identificador=f,
                label=f"Faixa PDD desconhecida: {f} ({slot})",
                valor_d0=vp if slot == "d0" else ZERO,
                valor_d_prev=vp if slot == "d_prev" else ZERO,
                modo="vigia", driver_afetado="DC / PDD",
                motivo=(
                    "faixa_pdd fora da escala CVM (AA..H) e nao e WOP. Esta sendo "
                    "incluida em DC/PDD como performada — confirmar se nao deveria "
                    "ser tratada como write-off."
                ),
            ))
    return out


async def _scan_cota_fundo(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID, ua_nome: str,
    d_prev: date, d0: date, threshold: Decimal,
) -> list[ItemNaoReconhecido]:
    """Cota fundo: lista fundos EXTERNOS GENUINAMENTE NOVOS em Fundos DI (vigia).

    `_is_fundo_externo` e prefixo-based: um fundo externo entra direto em Fundos
    DI. Vale expor um fundo NOVO no dia 1 — mas so quando e de fato novo.

    "Novo" = tem saldo em D0 e NAO foi visto (>= threshold) em nenhum dia da
    janela `_FUNDO_NOVO_LOOKBACK_DIAS` antes de D0. Olhar so D-1 reacendia o
    alerta a cada recarga de um fundo de varredura (ITAU SOBERANO REF SI, que
    zera e recarrega) — ruido, nao novidade.
    """
    janela_inicio = d0 - timedelta(days=_FUNDO_NOVO_LOOKBACK_DIAS)
    rows = (
        await db.execute(
            select(
                PosicaoCotaFundo.ativo_nome,
                PosicaoCotaFundo.data_posicao,
                PosicaoCotaFundo.valor_liquido,
            )
            .where(PosicaoCotaFundo.tenant_id == tenant_id)
            .where(PosicaoCotaFundo.unidade_administrativa_id == ua_id)
            .where(PosicaoCotaFundo.data_posicao >= janela_inicio)
            .where(PosicaoCotaFundo.data_posicao <= d0)
        )
    ).all()

    saldo_d0: dict[str, Decimal] = {}
    visto_antes: dict[str, Decimal] = {}  # maior |saldo| em datas < D0 na janela
    for nome, d, valor in rows:
        if not _is_fundo_externo(nome or "", ua_nome):
            continue  # fundo interno (DC) — nao conta aqui
        key = nome or ""
        v = Decimal(valor or 0)
        d_norm = d.date() if hasattr(d, "date") else d
        if d_norm == d0:
            saldo_d0[key] = saldo_d0.get(key, ZERO) + v
        else:
            visto_antes[key] = max(visto_antes.get(key, ZERO), abs(v))

    out: list[ItemNaoReconhecido] = []
    for nome, v0 in saldo_d0.items():
        # Novo de verdade: tem saldo agora E nao apareceu em nenhum dia da janela.
        novo = abs(v0) >= threshold and visto_antes.get(nome, ZERO) < threshold
        if not novo:
            continue
        out.append(ItemNaoReconhecido(
            fonte="wh_posicao_cota_fundo", endpoint="qitech.market.outros_fundos",
            campo="ativo_nome", identificador=nome,
            label=f"Fundo externo novo em Fundos DI: {nome}",
            valor_d0=v0, valor_d_prev=ZERO,
            modo="vigia", driver_afetado="Fundos DI",
            motivo=(
                f"Fundo externo sem saldo nos ultimos {_FUNDO_NOVO_LOOKBACK_DIAS} "
                "dias passou a ter saldo em D0 — entra em Fundos DI. Conferir se a "
                "contraparte de caixa foi capturada."
            ),
        ))
    return out


async def _scan_outros_ativos(
    db: AsyncSession, tenant_id: UUID, ua_id: UUID,
    d_prev: date, d0: date, threshold: Decimal,
) -> list[ItemNaoReconhecido]:
    """Outros ativos: codigo novo (≠ PDD) ou tipo TPF ambiguo (vigia).

    O driver Outros Ativos inclui tudo que nao e PDD nem TPF (blanket). Um
    codigo novo entra direto; um tipo que casa `_is_titulo_publico` sai pro
    driver TPF. Expoe codigos novos pra revisao.
    """
    out: list[ItemNaoReconhecido] = []
    seen_d0: dict[str, Decimal] = {}
    rows = (
        await db.execute(
            select(
                PosicaoOutrosAtivos.codigo,
                PosicaoOutrosAtivos.descricao_tipo_de_ativo,
                PosicaoOutrosAtivos.valor_total,
            )
            .where(PosicaoOutrosAtivos.tenant_id == tenant_id)
            .where(PosicaoOutrosAtivos.unidade_administrativa_id == ua_id)
            .where(PosicaoOutrosAtivos.data_posicao == d0)
        )
    ).all()
    for codigo, tipo, valor in rows:
        c = (codigo or "").strip().upper()
        if c == "PDD" or _is_titulo_publico(tipo or ""):
            continue  # PDD tem driver proprio; TPF vai pro driver TPF
        seen_d0[f"{codigo}/{tipo}"] = seen_d0.get(f"{codigo}/{tipo}", ZERO) + Decimal(valor or 0)
    for ident, valor in seen_d0.items():
        if abs(valor) < threshold:
            continue
        out.append(ItemNaoReconhecido(
            fonte="wh_posicao_outros_ativos", endpoint="qitech.market.outros_ativos",
            campo="codigo/descricao_tipo_de_ativo", identificador=ident,
            label=f"Outro ativo incluido (blanket): {ident}",
            valor_d0=valor, valor_d_prev=ZERO,
            modo="vigia", driver_afetado="Outros Ativos",
            motivo=(
                "Item entra no driver Outros Ativos por exclusao (nao e PDD nem TPF). "
                "Conferir se a classificacao residual esta correta."
            ),
        ))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Orquestrador
# ─────────────────────────────────────────────────────────────────────────────


async def scan_nao_reconhecidos(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    ua_nome: str,
    fundo_doc: str,
    data_d0: date,
    data_d_prev: date,
    threshold: Decimal = _THRESHOLD_DEFAULT,
) -> CompletudeReport:
    """Varre TODAS as fontes da pagina Cota Sub por itens nao reconhecidos.

    Ordem por gravidade: leak-mode (MEC classes, RF COSIF) primeiro, depois
    false-include (tesouraria), depois vigia (faixa_pdd, cota_fundo, outros).
    """
    itens: list[ItemNaoReconhecido] = []
    itens += await _scan_mec_classes(db, tenant_id, ua_id, ua_nome, data_d_prev, data_d0, threshold)
    itens += await _scan_renda_fixa(db, tenant_id, ua_id, data_d_prev, data_d0, threshold)
    itens += await _scan_tesouraria(db, tenant_id, ua_id, ua_nome, data_d_prev, data_d0, threshold)
    itens += await _scan_faixa_pdd(db, tenant_id, fundo_doc, data_d_prev, data_d0, threshold)
    itens += await _scan_cota_fundo(db, tenant_id, ua_id, ua_nome, data_d_prev, data_d0, threshold)
    itens += await _scan_outros_ativos(db, tenant_id, ua_id, data_d_prev, data_d0, threshold)

    # Ordena: vaza_residuo > entra_indevido > vigia, depois por |valor D0| desc.
    _ordem = {"vaza_residuo": 0, "entra_indevido": 1, "vigia": 2}
    itens.sort(key=lambda i: (_ordem[i.modo], -abs(i.valor_d0)))

    return CompletudeReport(
        data_d0=data_d0, data_d_prev=data_d_prev, itens=tuple(itens),
    )
