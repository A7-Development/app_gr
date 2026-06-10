"""Controladoria · Conciliacao de boletos (carteira Bitfin x banco cobrador).

Item 2 da Entrega 3 ("Recebivel de cobranca"). Cruza, titulo a titulo:

  - lado carteira: `wh_titulo` em aberto (situacao=0) de operacao EFETIVADA
    (cessao real) -- TODOS os produtos. O escopo por produto NAO e gateado
    aqui: cada linha expoe `produto` (prefixo de `wh_operacao.modalidade`) e o
    filtro de Produto da pagina decide o que mostrar. Nao ha lista hardcoded de
    "produtos com boleto" (premissa removida 2026-06-06 -- escondia CMS/
    Comissaria, que tem boleto real registrado no banco).
  - lado banco:    `wh_boleto_vigente` ativo (estado=ativo) -- a carteira de
    cobranca ATUAL, projetada do fold da timeline (sem data-base)

A conciliacao e estado-vs-estado ("carteira agora x cobranca atual"), nao uma
analise por dia. A defasagem do lado banco (ate o ultimo retorno processado) e
exposta como FRESCOR (`cobranca_atualizada_ate`), nao como filtro.

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

from app.warehouse.boleto_evento import ORIGEM_RETORNO, BoletoEvento
from app.warehouse.boleto_vigente import (
    ESTADO_ATIVO,
    ESTADO_ENVIADO,
    BoletoVigente,
)
from app.warehouse.cnab_raw_arquivo import TIPO_ARQUIVO_RETORNO, CnabRawArquivo
from app.warehouse.dim import DimUnidadeAdministrativa
from app.warehouse.operacao import Operacao
from app.warehouse.titulo import Titulo

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
# Decomposicao do "So BITFIN": o titulo tem remessa de registro ENVIADA ao
# banco, mas o banco ainda NAO confirmou a entrada (sem retorno cod 02). E o
# furo operacional acionavel -- instruimos o banco e ele nao acusou. O resto do
# "So BITFIN" (sem remessa) e titulo que nunca foi enviado para cobranca bancaria.
STATUS_ENVIADO_NAO_CONFIRMADO = "enviado_nao_confirmado"

# Pipeline de protesto/cartorio na timeline (wh_boleto_evento.tipo_evento).
# Strings da taxonomia canonica do decoder de cobranca -- duplicadas aqui de
# proposito: importar de modules/integracoes/adapters seria cross-import de
# internals (CLAUDE.md 11.3); o contrato estavel e o valor gravado no silver.
_PROTESTO_TIPOS = (
    "protesto_instruido",
    "encaminhado_cartorio",
    "protesto_sustado",
    "retirado_cartorio",
)


@dataclass
class _TituloLado:
    numero: str
    valor_liquido: Decimal
    vencimento: date | None
    data_operacao: date | None
    produto: str
    cedente_documento: str | None
    cedente_nome: str | None
    sacado_id: int | None
    ua_id: int
    ua_nome: str | None


@dataclass
class _BoletoLado:
    numero_documento: str
    nosso_numero: str
    valor_boleto: Decimal
    data_vencimento: date | None
    banco_origem: str
    sacado_documento: str | None
    ua_id: int | None
    ua_nome: str | None
    # Data do evento que definiu o estado vigente. Para estado=enviado e a data
    # de geracao da remessa de registro -> base do aging "aguardando ha N dias".
    estado_em: date | None = None


@dataclass
class LinhaConciliacao:
    status: str
    numero: str
    # Nosso numero do banco (lado boleto) — ajuda a achar divergencia.
    nosso_numero: str | None = None
    valor_bitfin: Decimal | None = None
    valor_banco: Decimal | None = None
    venc_bitfin: date | None = None
    venc_banco: date | None = None
    data_operacao: date | None = None
    produto: str | None = None
    banco: str | None = None
    # Exposto para o front aplicar filtros especificos do tenant (ex.: excluir
    # FAT de cedentes Pedreira na A7). O motor nao filtra por isso.
    cedente_documento: str | None = None
    cedente_nome: str | None = None
    # UA (Unidade Administrativa) do titulo — escopo da analise. Vem do lado
    # Bitfin (wh_titulo). Linhas "so em banco" (boleto sem titulo) ficam sem UA
    # ate o boleto carregar UA do header CNAB (rebuild da carteira de cobranca).
    ua_id: int | None = None
    ua_nome: str | None = None
    # Situacao do titulo no wh_titulo (codigo Bitfin), preenchida APENAS em
    # linhas "so em banco": o titulo pode estar liquidado (1) ou recomprado (5)
    # no sistema com o boleto ainda ativo no banco — pendencia de pedido de
    # baixa. None em "so em banco" = numero sem titulo no warehouse. Nas demais
    # linhas e None por construcao (lado Bitfin so entra com situacao=0).
    situacao_titulo: int | None = None
    # Aging do "enviado, aguardando confirmacao": data de geracao da remessa de
    # registro (estado vigente=enviado). None nas demais linhas.
    enviado_em: date | None = None
    # Ultimo evento do pipeline de protesto/cartorio do boleto (timeline,
    # origem=retorno): protesto_instruido / encaminhado_cartorio /
    # protesto_sustado / retirado_cartorio. None = sem protesto.
    protesto_tipo: str | None = None
    protesto_em: date | None = None


@dataclass
class ConciliacaoBoletoResult:
    titulos_abertos: int = 0
    boletos_ativos: int = 0
    conciliados: int = 0
    # Frescor do lado banco: data do ultimo evento de cobranca processado
    # (a carteira BITFIN e "agora"; o banco reflete ate aqui).
    cobranca_atualizada_ate: date | None = None
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
    # Data da operacao (cessao) — efetivacao, normalizada para data de Sao Paulo.
    data_op_sp = func.timezone(
        "America/Sao_Paulo", Operacao.data_de_efetivacao
    ).cast(Date)
    stmt = (
        select(
            Titulo.numero,
            Titulo.valor_liquido,
            venc_sp.label("vencimento"),
            data_op_sp.label("data_operacao"),
            produto.label("produto"),
            Operacao.cedente_documento,
            Operacao.cedente_nome,
            Titulo.sacado_id,
            Titulo.unidade_administrativa_id,
            DimUnidadeAdministrativa.nome.label("ua_nome"),
        )
        .join(
            Operacao,
            (Operacao.operacao_id == Titulo.operacao_id)
            & (Operacao.tenant_id == Titulo.tenant_id),
        )
        .outerjoin(
            DimUnidadeAdministrativa,
            (DimUnidadeAdministrativa.ua_id == Titulo.unidade_administrativa_id)
            & (DimUnidadeAdministrativa.tenant_id == Titulo.tenant_id),
        )
        .where(
            Titulo.tenant_id == tenant_id,
            Titulo.situacao == SITUACAO_EM_ABERTO,
            # Sem gate de produto: TODOS os produtos entram; o filtro de Produto
            # da pagina (front) decide o escopo. `produto` segue selecionado como
            # coluna para alimentar o filtro + display.
            # So cessao REAL entra na conciliacao. Operacao nao-efetivada e
            # rascunho/pendente (sem cedente, removida do Bitfin depois) — seus
            # titulos virariam "Só BITFIN" fantasma. Alinha com o BI
            # (_apply_filters sempre exige efetivada=true).
            Operacao.efetivada.is_(True),
        )
    )
    rows = (await db.execute(stmt)).all()
    return [
        _TituloLado(
            numero=numero,
            valor_liquido=valor,
            vencimento=venc,
            data_operacao=data_op,
            produto=prod,
            cedente_documento=cedente_doc,
            cedente_nome=cedente_nome,
            sacado_id=sacado_id,
            ua_id=ua_id,
            ua_nome=ua_nome,
        )
        for numero, valor, venc, data_op, prod, cedente_doc, cedente_nome, sacado_id, ua_id, ua_nome in rows
    ]


async def _carregar_boletos(
    db: AsyncSession, tenant_id: UUID, *, estado: str = ESTADO_ATIVO
) -> list[_BoletoLado]:
    """Boletos vigentes do tenant num `estado` (sem data-base).

    `estado=ativo` -> carteira de cobranca confirmada pelo banco; `estado=enviado`
    -> remessas de registro enviadas que o banco ainda nao confirmou.
    """
    stmt = select(
        BoletoVigente.numero_documento,
        BoletoVigente.nosso_numero,
        BoletoVigente.valor_atual,
        BoletoVigente.data_vencimento,
        BoletoVigente.banco_origem,
        BoletoVigente.sacado_documento,
        BoletoVigente.ua_id,
        BoletoVigente.ua_nome,
        BoletoVigente.data_ocorrencia_vigente,
    ).where(
        BoletoVigente.tenant_id == tenant_id,
        BoletoVigente.estado == estado,
    )
    rows = (await db.execute(stmt)).all()
    return [
        _BoletoLado(
            numero_documento=numero,
            nosso_numero=nosso,
            valor_boleto=valor,
            data_vencimento=venc,
            banco_origem=banco,
            sacado_documento=sacado_doc,
            ua_id=ua_id,
            ua_nome=ua_nome,
            estado_em=estado_em,
        )
        for numero, nosso, valor, venc, banco, sacado_doc, ua_id, ua_nome, estado_em in rows
    ]


async def _situacao_titulos(
    db: AsyncSession, tenant_id: UUID, numeros: set[str]
) -> dict[str, int]:
    """Situacao mais recente (por `data_da_situacao`) de cada numero em
    `wh_titulo`, em QUALQUER situacao — usada para explicar o "so em banco".

    O boleto ativo sem titulo ABERTO quase sempre tem titulo ENCERRADO no
    sistema (liquidado/recomprado) cujo pedido de baixa nunca foi efetivado no
    banco. Expor a situacao transforma a linha em acao ("instruir baixa").
    """
    if not numeros:
        return {}
    stmt = (
        select(Titulo.numero, Titulo.situacao)
        .where(
            Titulo.tenant_id == tenant_id,
            func.btrim(Titulo.numero).in_(numeros),
        )
        .order_by(Titulo.numero, Titulo.data_da_situacao.desc())
    )
    situacoes: dict[str, int] = {}
    for numero, situacao in (await db.execute(stmt)).all():
        situacoes.setdefault(_normalizar_numero(numero), situacao)
    return situacoes


async def _protestos_por_boleto(
    db: AsyncSession, tenant_id: UUID
) -> dict[tuple[str, str], tuple[str, date]]:
    """Ultimo evento do pipeline de protesto/cartorio por boleto, chaveado por
    `(banco_origem, numero_documento normalizado)`.

    Le a timeline (`wh_boleto_evento`, origem=retorno). Eventos de protesto sao
    `efeito_estado=info` — nao mudam o estado vigente — entao a conciliacao e o
    unico lugar que os expoe ao usuario. Conjunto pequeno (centenas).
    """
    stmt = (
        select(
            BoletoEvento.banco_origem,
            BoletoEvento.numero_documento,
            BoletoEvento.tipo_evento,
            BoletoEvento.data_ocorrencia,
        )
        .where(
            BoletoEvento.tenant_id == tenant_id,
            BoletoEvento.origem == ORIGEM_RETORNO,
            BoletoEvento.tipo_evento.in_(_PROTESTO_TIPOS),
        )
        .order_by(BoletoEvento.data_ocorrencia.desc())
    )
    protestos: dict[tuple[str, str], tuple[str, date]] = {}
    for banco, numero, tipo, data in (await db.execute(stmt)).all():
        protestos.setdefault((banco, _normalizar_numero(numero)), (tipo, data))
    return protestos


async def _cobranca_atualizada_ate(
    db: AsyncSession, tenant_id: UUID
) -> date | None:
    """Frescor do lado banco = data do ULTIMO ARQUIVO de retorno processado
    (data de gravacao no header CNAB), nao a ultima ocorrencia. "Cobranca ate
    DD/MM" = ate quando temos retornos do banco -- mais intuitivo que a data do
    ultimo evento (que pode ser mais antiga que o arquivo mais recente)."""
    stmt = select(func.max(CnabRawArquivo.data_ref)).where(
        CnabRawArquivo.tenant_id == tenant_id,
        CnabRawArquivo.tipo_arquivo == TIPO_ARQUIVO_RETORNO,
    )
    return (await db.execute(stmt)).scalar_one_or_none()


async def conciliar_boletos(
    db: AsyncSession, *, tenant_id: UUID
) -> ConciliacaoBoletoResult:
    """Concilia a carteira BITFIN atual x cobranca vigente. Titulo a titulo."""
    titulos = await _carregar_titulos(db, tenant_id)
    boletos = await _carregar_boletos(db, tenant_id)
    # Remessas enviadas que o banco ainda nao confirmou (estado=enviado).
    # Consultadas so para DECOMPOR o "So BITFIN" -- nao entram na contagem de
    # boletos ativos nem viram "so em banco". A soma (So BITFIN + Enviado nao
    # confirmado) = o "So BITFIN" antigo (reconcilia, §14.6).
    enviados = await _carregar_boletos(db, tenant_id, estado=ESTADO_ENVIADO)

    titulos_por_numero: dict[str, _TituloLado] = {}
    for t in titulos:
        titulos_por_numero.setdefault(_normalizar_numero(t.numero), t)
    boletos_por_numero: dict[str, _BoletoLado] = {}
    for b in boletos:
        boletos_por_numero.setdefault(_normalizar_numero(b.numero_documento), b)
    enviados_por_numero: dict[str, _BoletoLado] = {}
    for e in enviados:
        enviados_por_numero.setdefault(_normalizar_numero(e.numero_documento), e)

    result = ConciliacaoBoletoResult(
        titulos_abertos=len(titulos),
        boletos_ativos=len(boletos),
        cobranca_atualizada_ate=await _cobranca_atualizada_ate(db, tenant_id),
    )

    for numero in titulos_por_numero.keys() | boletos_por_numero.keys():
        t = titulos_por_numero.get(numero)
        b = boletos_por_numero.get(numero)

        if t is not None and b is None:
            # Titulo BITFIN sem boleto ATIVO no banco. Decompoe: se ha remessa
            # de registro enviada (sem confirmacao) -> "enviado, aguardando
            # confirmacao"; senao -> nunca enviado para cobranca bancaria.
            e = enviados_por_numero.get(numero)
            if e is not None:
                result.linhas.append(
                    LinhaConciliacao(
                        status=STATUS_ENVIADO_NAO_CONFIRMADO,
                        numero=numero,
                        nosso_numero=e.nosso_numero,
                        valor_bitfin=t.valor_liquido,
                        valor_banco=e.valor_boleto,
                        venc_bitfin=t.vencimento,
                        venc_banco=e.data_vencimento,
                        data_operacao=t.data_operacao,
                        produto=t.produto,
                        banco=e.banco_origem,
                        cedente_documento=t.cedente_documento,
                        cedente_nome=t.cedente_nome,
                        ua_id=t.ua_id,
                        ua_nome=t.ua_nome,
                        enviado_em=e.estado_em,
                    )
                )
            else:
                result.linhas.append(
                    LinhaConciliacao(
                        status=STATUS_SO_BITFIN,
                        numero=numero,
                        valor_bitfin=t.valor_liquido,
                        venc_bitfin=t.vencimento,
                        data_operacao=t.data_operacao,
                        produto=t.produto,
                        cedente_documento=t.cedente_documento,
                        cedente_nome=t.cedente_nome,
                        ua_id=t.ua_id,
                        ua_nome=t.ua_nome,
                    )
                )
        elif t is None and b is not None:
            result.linhas.append(
                LinhaConciliacao(
                    status=STATUS_SO_BANCO,
                    numero=numero,
                    nosso_numero=b.nosso_numero,
                    valor_banco=b.valor_boleto,
                    venc_banco=b.data_vencimento,
                    banco=b.banco_origem,
                    ua_id=b.ua_id,
                    ua_nome=b.ua_nome,
                )
            )
        elif t is not None and b is not None:
            linha = LinhaConciliacao(
                status=STATUS_CONCILIADO,
                numero=numero,
                nosso_numero=b.nosso_numero,
                valor_bitfin=t.valor_liquido,
                valor_banco=b.valor_boleto,
                venc_bitfin=t.vencimento,
                venc_banco=b.data_vencimento,
                data_operacao=t.data_operacao,
                produto=t.produto,
                banco=b.banco_origem,
                cedente_documento=t.cedente_documento,
                cedente_nome=t.cedente_nome,
                ua_id=t.ua_id,
                ua_nome=t.ua_nome,
            )
            if t.valor_liquido != b.valor_boleto:
                linha.status = STATUS_DIV_VALOR
            elif t.vencimento != b.data_vencimento:
                linha.status = STATUS_DIV_VENCIMENTO
            else:
                result.conciliados += 1
            result.linhas.append(linha)

    # Enriquece o "so em banco" com a situacao do titulo no warehouse (qualquer
    # situacao): liquidado/recomprado no sistema com boleto ativo = pendencia de
    # pedido de baixa no banco.
    so_banco = [linha for linha in result.linhas if linha.status == STATUS_SO_BANCO]
    situacoes = await _situacao_titulos(
        db, tenant_id, {linha.numero for linha in so_banco}
    )
    for linha in so_banco:
        linha.situacao_titulo = situacoes.get(linha.numero)

    # Anota o pipeline de protesto/cartorio nas linhas com lado banco (boleto
    # ativo ou enviado). Eventos de protesto sao info no fold — so aparecem aqui.
    protestos = await _protestos_por_boleto(db, tenant_id)
    for linha in result.linhas:
        if linha.banco is None:
            continue
        protesto = protestos.get((linha.banco, linha.numero))
        if protesto is not None:
            linha.protesto_tipo, linha.protesto_em = protesto

    return result
