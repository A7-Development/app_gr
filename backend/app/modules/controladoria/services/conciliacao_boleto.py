"""Controladoria · Conciliacao de boletos (carteira Bitfin x banco cobrador).

Item 2 da Entrega 3 ("Recebivel de cobranca"). Cruza, titulo a titulo:

  - lado carteira: `wh_titulo` em aberto (situacao=0) cujo produto e elegivel
    a boleto (FAT/CBV/DMS/CBS, prefixo de `wh_operacao.modalidade`)
  - lado banco:    `wh_boleto` ativo na data-base (estado=ativo)

Classifica cada titulo/boleto em: Conciliado / Divergencia de valor /
Divergencia de vencimento / So em BITFIN / So em banco.

Fonte canonica dos dois lados (silver). Le warehouse -- nao chama integracoes
(CLAUDE.md 11.3). Valor comparado = `wh_titulo.valor_liquido` (face que o
sacado paga) vs `wh_boleto.valor_boleto`.

GOTCHA de fuso (critico): `wh_titulo.data_de_vencimento` e guardado como
meia-noite de Sao Paulo (03:00Z). Para casar com a data do boleto (date puro),
compara-se `(data_de_vencimento AT TIME ZONE 'America/Sao_Paulo')::date`.
Comparar o timestamp cru geraria divergencia de vencimento FALSA em todo
titulo.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Date, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.warehouse.boleto import ESTADO_ATIVO, Boleto
from app.warehouse.operacao import Operacao
from app.warehouse.titulo import Titulo

# Produtos (prefixo de Operacao.modalidade) que possuem boleto como recebivel.
# Fato estrutural do Bitfin (quais produtos geram boleto), nao quirk de tenant.
PRODUTOS_COM_BOLETO = ("FAT", "CBV", "DMS", "CBS")

# Situacao do titulo "Em aberto" (Bitfin). Confirmado via wh_titulo_snapshot.
SITUACAO_EM_ABERTO = 0

# NOTA multitenant: exclusoes especificas de um tenant (ex.: na A7, os cedentes
# Pedreira operam FAT+CBV sobre o mesmo grupo e so o CBV gera boleto) NAO vivem
# aqui -- sao regra de FILTRO no front (ou config de tenant), nunca no motor.
# Por isso cada linha expoe `cedente_documento` + `produto`: o front filtra.

# Tipos de divergencia.
STATUS_CONCILIADO = "conciliado"
STATUS_DIV_VALOR = "divergencia_valor"
STATUS_DIV_VENCIMENTO = "divergencia_vencimento"
STATUS_SO_BITFIN = "so_em_bitfin"
STATUS_SO_BANCO = "so_em_banco"


@dataclass
class _TituloLado:
    numero: str
    valor_liquido: Decimal
    vencimento: date | None
    produto: str
    cedente_documento: str | None
    sacado_id: int | None


@dataclass
class _BoletoLado:
    numero_documento: str
    valor_boleto: Decimal
    data_vencimento: date
    banco_origem: str
    sacado_documento: str | None


@dataclass
class LinhaConciliacao:
    status: str
    numero: str
    valor_bitfin: Decimal | None = None
    valor_banco: Decimal | None = None
    venc_bitfin: date | None = None
    venc_banco: date | None = None
    produto: str | None = None
    banco: str | None = None
    # Exposto para o front aplicar filtros especificos do tenant (ex.: excluir
    # FAT de cedentes Pedreira na A7). O motor nao filtra por isso.
    cedente_documento: str | None = None


@dataclass
class ConciliacaoBoletoResult:
    data_ref: date
    titulos_abertos: int = 0
    boletos_ativos: int = 0
    conciliados: int = 0
    linhas: list[LinhaConciliacao] = field(default_factory=list)

    def por_status(self, status: str) -> list[LinhaConciliacao]:
        return [linha for linha in self.linhas if linha.status == status]


def _normalizar_numero(numero: str | None) -> str:
    """Chave de cruzamento. Por ora so trim; normalizacao mais agressiva
    (mascaras/parcela) entra se o cruzamento real exigir."""
    return (numero or "").strip()


async def _carregar_titulos(
    db: AsyncSession, tenant_id: UUID
) -> list[_TituloLado]:
    produto = func.split_part(Operacao.modalidade, "-", 1)
    venc_sp = func.timezone(
        "America/Sao_Paulo", Titulo.data_de_vencimento
    ).cast(Date)
    stmt = (
        select(
            Titulo.numero,
            Titulo.valor_liquido,
            venc_sp.label("vencimento"),
            produto.label("produto"),
            Operacao.cedente_documento,
            Titulo.sacado_id,
        )
        .join(
            Operacao,
            (Operacao.operacao_id == Titulo.operacao_id)
            & (Operacao.tenant_id == Titulo.tenant_id),
        )
        .where(
            Titulo.tenant_id == tenant_id,
            Titulo.situacao == SITUACAO_EM_ABERTO,
            produto.in_(PRODUTOS_COM_BOLETO),
        )
    )
    rows = (await db.execute(stmt)).all()
    return [
        _TituloLado(
            numero=numero,
            valor_liquido=valor,
            vencimento=venc,
            produto=prod,
            cedente_documento=cedente_doc,
            sacado_id=sacado_id,
        )
        for numero, valor, venc, prod, cedente_doc, sacado_id in rows
    ]


async def _carregar_boletos(
    db: AsyncSession, tenant_id: UUID, data_ref: date
) -> list[_BoletoLado]:
    stmt = select(
        Boleto.numero_documento,
        Boleto.valor_boleto,
        Boleto.data_vencimento,
        Boleto.banco_origem,
        Boleto.sacado_documento,
    ).where(
        Boleto.tenant_id == tenant_id,
        Boleto.data_ref == data_ref,
        Boleto.estado == ESTADO_ATIVO,
    )
    rows = (await db.execute(stmt)).all()
    return [
        _BoletoLado(
            numero_documento=numero,
            valor_boleto=valor,
            data_vencimento=venc,
            banco_origem=banco,
            sacado_documento=sacado_doc,
        )
        for numero, valor, venc, banco, sacado_doc in rows
    ]


async def conciliar_boletos(
    db: AsyncSession, *, tenant_id: UUID, data_ref: date
) -> ConciliacaoBoletoResult:
    """Concilia titulos abertos x boletos ativos na data-base. Title a title."""
    titulos = await _carregar_titulos(db, tenant_id)
    boletos = await _carregar_boletos(db, tenant_id, data_ref)

    titulos_por_numero: dict[str, _TituloLado] = {}
    for t in titulos:
        titulos_por_numero.setdefault(_normalizar_numero(t.numero), t)
    boletos_por_numero: dict[str, _BoletoLado] = {}
    for b in boletos:
        boletos_por_numero.setdefault(_normalizar_numero(b.numero_documento), b)

    result = ConciliacaoBoletoResult(
        data_ref=data_ref,
        titulos_abertos=len(titulos),
        boletos_ativos=len(boletos),
    )

    for numero in titulos_por_numero.keys() | boletos_por_numero.keys():
        t = titulos_por_numero.get(numero)
        b = boletos_por_numero.get(numero)

        if t is not None and b is None:
            result.linhas.append(
                LinhaConciliacao(
                    status=STATUS_SO_BITFIN,
                    numero=numero,
                    valor_bitfin=t.valor_liquido,
                    venc_bitfin=t.vencimento,
                    produto=t.produto,
                    cedente_documento=t.cedente_documento,
                )
            )
        elif t is None and b is not None:
            result.linhas.append(
                LinhaConciliacao(
                    status=STATUS_SO_BANCO,
                    numero=numero,
                    valor_banco=b.valor_boleto,
                    venc_banco=b.data_vencimento,
                    banco=b.banco_origem,
                )
            )
        elif t is not None and b is not None:
            linha = LinhaConciliacao(
                status=STATUS_CONCILIADO,
                numero=numero,
                valor_bitfin=t.valor_liquido,
                valor_banco=b.valor_boleto,
                venc_bitfin=t.vencimento,
                venc_banco=b.data_vencimento,
                produto=t.produto,
                banco=b.banco_origem,
                cedente_documento=t.cedente_documento,
            )
            if t.valor_liquido != b.valor_boleto:
                linha.status = STATUS_DIV_VALOR
            elif t.vencimento != b.data_vencimento:
                linha.status = STATUS_DIV_VENCIMENTO
            else:
                result.conciliados += 1
            result.linhas.append(linha)

    return result
