"""Classificador de canal de liquidacao (Sentinela CNAB F2).

Traduz o par (banco_pagador, agencia_pagadora) de `wh_boleto_evento` em um
CANAL canonico + praca (municipio/UF), usando a referencia publica Bacen
(`ref_bacen_*`). Regra de ouro (licao do caso MFL): AUSENCIA de resolucao e um
estado explicito -- nunca herda a classificacao mais conveniente.

Canais:
  banco_praca      banco com agencia fisica resolvida -> praca real (S1 opera)
  banco_sem_praca  banco conhecido, mas agencia-matriz (0001) ou fora da ref
                   (numeracao interna/extinta -- ex. Itau 8544)
  cooperativa      redes cooperativas (756 Sicoob, 748 Sicredi, 085 Ailos...):
                   o campo "agencia" e o codigo da singular, sem praca publica.
                   Por decisao de escopo (2026-07-07), cooperativa e sinal de
                   atencao por si -- sem sintonia fina de singular.
  ip               instituicao de pagamento (conta eletronica)
  outras_if        SCD / financeira / demais IFs
  nao_resolvido    codigo de banco fora da referencia Bacen

Baixa manual e recompra NAO passam por aqui -- nao tem evento bancario; sao
canais proprios derivados de `wh_titulo` (motor de sinais, F3/F4).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.warehouse.banco_agencia import WhBancoAgencia
from app.warehouse.ref_bacen import (
    FONTE_OLINDA,
    SEGMENTO_BANCO,
    SEGMENTO_BANCO_COOPERATIVO,
    SEGMENTO_COOPERATIVA,
    SEGMENTO_IP,
    RefBacenAgencia,
    RefBacenInstituicao,
    RefBacenPosto,
)

CANAL_BANCO_PRACA = "banco_praca"
CANAL_BANCO_SEM_PRACA = "banco_sem_praca"
CANAL_COOPERATIVA = "cooperativa"
CANAL_IP = "ip"
CANAL_OUTRAS_IF = "outras_if"
CANAL_NAO_RESOLVIDO = "nao_resolvido"

# Agencia 0001 e sede/matriz: em bancos digitais e de atacado ela concentra a
# liquidacao ELETRONICA do pais inteiro -- tratar a cidade da matriz como
# "praca do pagamento" geraria S1 falso (ex.: ABC 246/0001 Sao Paulo). A
# cidade resolvida e preservada no resultado, mas o canal fica sem_praca.
# DEFAULT de nascenca — o valor vigente vem do parametro versionado
# `agencia_matriz` (deteccao_parametro), passado pelo caller em `carregar`
# (zero hardcode, decisao 2026-07-10).
_AGENCIA_MATRIZ_DEFAULT = "00001"


@dataclass(frozen=True)
class PracaLiquidacao:
    """Resultado da classificacao de um par (banco, agencia)."""

    canal: str
    banco_compe: str | None
    instituicao: str | None
    segmento: str | None
    agencia_codigo: str | None
    municipio: str | None
    municipio_ibge: int | None
    uf: str | None
    # True apenas quando o canal e banco_praca (municipio confiavel p/ S1).
    praca_resolvida: bool
    # Racional legivel ("agencia fora da referencia Bacen", ...) p/ auditoria.
    detalhe: str
    # Fonte da resolucao da praca (escada): "bacen" | "bcb_historico" |
    # "bcb_posto" | "cadastro_erp" | "nao_resolvida". Vira feature do modelo e
    # aparece na memoria de calculo.
    praca_fonte: str = "nao_resolvida"
    # Tipo do posto Bacen (PAB/PAE/AG Empresarial/...) quando a praca veio do
    # degrau de postos; None nos demais degraus.
    tipo_posto: str | None = None
    # Janela de vigencia da agencia na serie historica BCB (YYYYMM). NULL =
    # desconhecida (linha so-Olinda ou posto/ERP) — tratar como vigente.
    # Consumidor futuro: sinal PRC-04 (pagamento fora de vigencia, as-of).
    primeira_competencia: int | None = None
    ultima_competencia: int | None = None


def _norm_banco(banco: str | None) -> str | None:
    b = (banco or "").strip()
    return b.zfill(3) if b.isdigit() and int(b) > 0 else None


def _norm_agencia(agencia: str | None) -> str | None:
    a = (agencia or "").strip()
    return a.zfill(5) if a.isdigit() and int(a) > 0 else None


class RefBacenResolver:
    """Resolver em memoria (carrega a ref inteira: ~1k instituicoes + ~30k
    agencias consolidadas + postos). Use `carregar` uma vez por job;
    `resolver` e puro e barato -- o formato certo para o motor de sinais
    varrer milhares de eventos."""

    def __init__(
        self,
        instituicoes: dict[str, RefBacenInstituicao],
        agencias: dict[tuple[str, str], RefBacenAgencia],
        erp_agencias: dict[tuple[str, str], tuple[str, str]] | None = None,
        postos: dict[tuple[str, str], tuple[str, str, str | None]] | None = None,
        agencia_matriz: str = _AGENCIA_MATRIZ_DEFAULT,
    ) -> None:
        self._matriz = agencia_matriz
        self._inst = instituicoes
        self._ag = agencias
        # Escada de resolucao (consolidacao 2026-07-10; ex-4 degraus):
        #   1. ref_bacen_agencia CONSOLIDADA (Olinda vivo + serie historica BCB
        #      com extintas — coluna `fonte` distingue; ex-wh_bcb_agencia)
        #   2. ref_bacen_posto (postos de atendimento — PAB/PAC/AG Empresarial)
        #   3. cadastro ERP (fallback factual)
        self._posto = postos or {}
        self._erp = erp_agencias or {}

    @classmethod
    async def carregar(
        cls, db: AsyncSession, *, agencia_matriz: str = _AGENCIA_MATRIZ_DEFAULT
    ) -> RefBacenResolver:
        inst = {
            row.codigo_compe: row
            for row in (await db.execute(select(RefBacenInstituicao))).scalars()
        }
        ag = {
            (row.banco_compe, row.agencia_codigo): row
            for row in (await db.execute(select(RefBacenAgencia))).scalars()
        }
        # Postos de atendimento Bacen (2o degrau): (banco_compe, posto_codigo)
        # -> (municipio, uf, tipo_posto). Cobre unidades com codigo proprio no
        # CNAB que na taxonomia Bacen sao postos (AG Empresarial/PAB da CEF).
        posto: dict[tuple[str, str], tuple[str, str, str | None]] = {}
        posto_rows = await db.execute(
            select(
                RefBacenPosto.banco_compe,
                RefBacenPosto.posto_codigo,
                RefBacenPosto.municipio,
                RefBacenPosto.uf,
                RefBacenPosto.tipo_posto,
            ).where(
                RefBacenPosto.banco_compe.isnot(None),
                RefBacenPosto.posto_codigo.isnot(None),
                RefBacenPosto.municipio.isnot(None),
            )
        )
        for banco_c, codigo, municipio, uf, tipo in posto_rows:
            b = _norm_banco(banco_c)
            a = _norm_agencia(codigo)
            if b and a and municipio:
                key = (b, a)
                if key not in posto:  # 1a ocorrencia vence (dups raros)
                    posto[key] = (municipio, (uf or "").strip() or "", tipo)
        # Cadastro ERP (3o degrau): dedup por (banco, agencia).
        erp: dict[tuple[str, str], tuple[str, str]] = {}
        for row in (await db.execute(select(WhBancoAgencia))).scalars():
            b = _norm_banco(row.banco_codigo)
            a = _norm_agencia(row.agencia_codigo)
            if not b or not a or not row.localidade:
                continue
            key = (b, a)
            if key not in erp:
                erp[key] = (row.localidade, (row.estado or "").strip() or "")
        return cls(inst, ag, erp, posto, agencia_matriz=agencia_matriz)

    def resolver(self, banco: str | None, agencia: str | None) -> PracaLiquidacao:
        b = _norm_banco(banco)
        a = _norm_agencia(agencia)
        if b is None:
            return PracaLiquidacao(
                CANAL_NAO_RESOLVIDO, None, None, None, a, None, None, None,
                False, "evento sem banco pagador",
            )
        inst = self._inst.get(b)
        if inst is None:
            return PracaLiquidacao(
                CANAL_NAO_RESOLVIDO, b, None, None, a, None, None, None,
                False, "codigo de banco fora da referencia Bacen (STR)",
            )
        if inst.segmento in (SEGMENTO_BANCO_COOPERATIVO, SEGMENTO_COOPERATIVA):
            return PracaLiquidacao(
                CANAL_COOPERATIVA, b, inst.nome_reduzido, inst.segmento, a,
                None, None, None, False,
                "rede cooperativa: 'agencia' e o codigo da singular (sem praca publica)",
            )
        if inst.segmento == SEGMENTO_IP:
            return PracaLiquidacao(
                CANAL_IP, b, inst.nome_reduzido, inst.segmento, a,
                None, None, None, False, "instituicao de pagamento (conta eletronica)",
            )
        if inst.segmento != SEGMENTO_BANCO:
            return PracaLiquidacao(
                CANAL_OUTRAS_IF, b, inst.nome_reduzido, inst.segmento, a,
                None, None, None, False, f"segmento {inst.segmento}",
            )
        # Banco: tenta resolver a agencia fisica.
        row = self._ag.get((b, a)) if a else None
        if a == self._matriz:
            return PracaLiquidacao(
                CANAL_BANCO_SEM_PRACA, b, inst.nome_reduzido, inst.segmento, a,
                row.municipio if row else None,
                row.municipio_ibge if row else None,
                row.uf if row else None,
                False, "agencia-matriz (0001): liquidacao eletronica, cidade nao e praca",
            )
        if row is None or row.municipio is None:
            # 2o degrau: postos de atendimento Bacen (AG Empresarial/PAB/PAE).
            posto = self._posto.get((b, a)) if a else None
            if posto is not None:
                return PracaLiquidacao(
                    CANAL_BANCO_PRACA, b, inst.nome_reduzido, inst.segmento, a,
                    posto[0], None, posto[1] or None, True,
                    f"agencia {a} resolvida via posto de atendimento Bacen"
                    f" ({posto[2] or 'posto'}): {posto[0]}/{posto[1]}",
                    praca_fonte="bcb_posto",
                    tipo_posto=posto[2],
                )
            # 3o degrau: cadastro ERP (fallback factual).
            erp = self._erp.get((b, a)) if a else None
            if erp is not None:
                return PracaLiquidacao(
                    CANAL_BANCO_PRACA, b, inst.nome_reduzido, inst.segmento, a,
                    erp[0], None, erp[1] or None, True,
                    f"agencia {a} resolvida pelo cadastro do ERP: {erp[0]}/{erp[1]}",
                    praca_fonte="cadastro_erp",
                )
            return PracaLiquidacao(
                CANAL_BANCO_SEM_PRACA, b, inst.nome_reduzido, inst.segmento, a,
                None, None, None, False,
                "agencia fora de todas as fontes (interna/extinta desconhecida)"
                if a else "evento sem agencia pagadora",
            )
        # 1o degrau (consolidado): a coluna `fonte` diz se a linha veio do
        # snapshot vivo Olinda ("bacen") ou da serie historica BCB
        # ("bcb_historico" — inclui extintas, ex.: 1417/Mercado Sao Sebastiao).
        fonte_row = getattr(row, "fonte", FONTE_OLINDA)
        praca_fonte = "bacen" if fonte_row == FONTE_OLINDA else "bcb_historico"
        origem = (
            "resolvida"
            if praca_fonte == "bacen"
            else "resolvida pela serie historica BCB"
        )
        return PracaLiquidacao(
            CANAL_BANCO_PRACA, b, inst.nome_reduzido, inst.segmento, a,
            row.municipio, row.municipio_ibge, row.uf, True,
            f"agencia {a} {origem}: {row.municipio}/{row.uf}",
            praca_fonte=praca_fonte,
            primeira_competencia=getattr(row, "primeira_competencia", None),
            ultima_competencia=getattr(row, "ultima_competencia", None),
        )


async def resolver_praca(
    db: AsyncSession, banco: str | None, agencia: str | None
) -> PracaLiquidacao:
    """Resolucao pontual (1 par, 2 selects). Para varreduras, use
    `RefBacenResolver.carregar` uma vez e resolva em memoria."""
    b = _norm_banco(banco)
    a = _norm_agencia(agencia)
    inst_map: dict[str, RefBacenInstituicao] = {}
    ag_map: dict[tuple[str, str], RefBacenAgencia] = {}
    if b is not None:
        inst = (
            await db.execute(
                select(RefBacenInstituicao).where(
                    RefBacenInstituicao.codigo_compe == b
                )
            )
        ).scalar_one_or_none()
        if inst is not None:
            inst_map[b] = inst
        if a is not None:
            row = (
                await db.execute(
                    select(RefBacenAgencia).where(
                        RefBacenAgencia.banco_compe == b,
                        RefBacenAgencia.agencia_codigo == a,
                    )
                )
            ).scalar_one_or_none()
            if row is not None:
                ag_map[(b, a)] = row
    return RefBacenResolver(inst_map, ag_map).resolver(banco, agencia)
