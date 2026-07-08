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
    SEGMENTO_BANCO,
    SEGMENTO_BANCO_COOPERATIVO,
    SEGMENTO_COOPERATIVA,
    SEGMENTO_IP,
    RefBacenAgencia,
    RefBacenInstituicao,
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
_AGENCIA_MATRIZ = "00001"


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
    # Fonte da resolucao da praca (escada): "bacen" | "cadastro_erp" |
    # "nao_resolvida". Vira feature do modelo e aparece na memoria de calculo.
    praca_fonte: str = "nao_resolvida"


def _norm_banco(banco: str | None) -> str | None:
    b = (banco or "").strip()
    return b.zfill(3) if b.isdigit() and int(b) > 0 else None


def _norm_agencia(agencia: str | None) -> str | None:
    a = (agencia or "").strip()
    return a.zfill(5) if a.isdigit() and int(a) > 0 else None


class RefBacenResolver:
    """Resolver em memoria (carrega a ref inteira: ~1k instituicoes + ~18k
    agencias). Use `carregar` uma vez por job; `resolver` e puro e barato --
    o formato certo para o motor de sinais varrer milhares de eventos."""

    def __init__(
        self,
        instituicoes: dict[str, RefBacenInstituicao],
        agencias: dict[tuple[str, str], RefBacenAgencia],
        erp_agencias: dict[tuple[str, str], tuple[str, str]] | None = None,
    ) -> None:
        self._inst = instituicoes
        self._ag = agencias
        # 2o degrau: (banco_compe, agencia_5) -> (municipio, uf) do cadastro
        # ERP. Cobre agencias que a referencia Bacen (snapshot atual) perdeu.
        self._erp = erp_agencias or {}

    @classmethod
    async def carregar(cls, db: AsyncSession) -> RefBacenResolver:
        inst = {
            row.codigo_compe: row
            for row in (await db.execute(select(RefBacenInstituicao))).scalars()
        }
        ag = {
            (row.banco_compe, row.agencia_codigo): row
            for row in (await db.execute(select(RefBacenAgencia))).scalars()
        }
        # Cadastro ERP: dedup por (banco, agencia) — linha COM cidade vence
        # (multiplas AgenciaId podem apontar o mesmo par; queremos a util).
        erp: dict[tuple[str, str], tuple[str, str]] = {}
        for row in (await db.execute(select(WhBancoAgencia))).scalars():
            b = _norm_banco(row.banco_codigo)
            a = _norm_agencia(row.agencia_codigo)
            if not b or not a or not row.localidade:
                continue
            key = (b, a)
            if key not in erp:
                erp[key] = (row.localidade, (row.estado or "").strip() or "")
        return cls(inst, ag, erp)

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
        if a == _AGENCIA_MATRIZ:
            return PracaLiquidacao(
                CANAL_BANCO_SEM_PRACA, b, inst.nome_reduzido, inst.segmento, a,
                row.municipio if row else None,
                row.municipio_ibge if row else None,
                row.uf if row else None,
                False, "agencia-matriz (0001): liquidacao eletronica, cidade nao e praca",
            )
        if row is None or row.municipio is None:
            # 2o degrau da escada: cadastro ERP recupera agencia fisica que a
            # referencia Bacen (snapshot atual) nao lista (extinta/renumerada).
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
                "agencia fora da referencia Bacen e do cadastro (interna/extinta)"
                if a else "evento sem agencia pagadora",
            )
        return PracaLiquidacao(
            CANAL_BANCO_PRACA, b, inst.nome_reduzido, inst.segmento, a,
            row.municipio, row.municipio_ibge, row.uf, True,
            f"agencia {a} resolvida: {row.municipio}/{row.uf}",
            praca_fonte="bacen",
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
