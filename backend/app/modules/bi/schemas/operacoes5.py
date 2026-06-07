"""BI — schemas da pagina /bi/operacoes5 (espinha de drill por dimensao).

Drill descendente UA -> Produto -> Cedente -> (Sacado, Fase 2) -> Operacao ->
Documento, aplicando o padrao de navegacao (docs/navegacao-aprofundamento.md):
cedente = rota, operacao = drawer, documento = inline.

Regime CAIXA (wh_operacao + wh_titulo), identico a operacoes4. Toda agregacao
reconcilia on-screen (CLAUDE.md §14.6): a soma das linhas exibidas = total
retornado no bundle (vop_total / valor_total).
"""

from datetime import date

from pydantic import BaseModel, Field


class Operacoes5CedenteItem(BaseModel):
    """Linha do ranking de cedentes (nivel Cedente da espinha)."""

    cedente_id: int | None = Field(description="Id Bitfin do cedente. None = '(n/d)'.")
    cedente_nome: str
    cedente_documento: str | None = Field(description="CNPJ/CPF sem mascara.")
    vop: float = Field(description="VOP do cedente (soma total_bruto) no periodo filtrado.")
    n_op: int = Field(description="Numero de operacoes do cedente no periodo.")
    taxa_media: float | None = Field(description="Taxa de juros media ponderada por VOP.")
    prazo_medio: float | None = Field(description="Prazo medio real ponderado por VOP.")
    receita: float = Field(description="Receita total (regime caixa, 4 buckets).")
    yield_pct: float | None = Field(description="receita / vop em %.")
    share_pct: float = Field(description="Participacao % do cedente no VOP total da pagina.")


class Operacoes5CedentesData(BaseModel):
    """Bundle do ranking de cedentes. Reconcilia: sum(cedentes.vop) == vop_total."""

    cedentes: list[Operacoes5CedenteItem]
    total: int = Field(description="Numero de cedentes na lista (todos, sem corte).")
    vop_total: float = Field(description="VOP somado de todos os cedentes (reconciliacao).")
    receita_total: float


class Operacoes5OperacaoItem(BaseModel):
    """Linha da lista de operacoes de um cedente (nivel Operacao = drawer).

    Inclui a COMPOSICAO COMPLETA da receita (regime caixa) — a taxa/desagio e
    so uma parte; cada tarifa entra como campo proprio. Os 8 componentes de
    receita somam `receita` (reconciliacao §14.6). IOF/imposto/descontos sao
    tributos/ajustes — NAO entram em `receita`, vao separados.
    """

    operacao_id: int
    data_de_efetivacao: date | None
    produto: str = Field(description="Sigla do produto (FAT, CMS, ...).")
    modalidade: str
    quantidade_de_titulos: int
    vop: float = Field(description="total_bruto da operacao.")
    total_liquido: float
    taxa_juros: float = Field(description="Taxa de juros da operacao (% a.m.).")
    prazo_medio: float = Field(description="Prazo medio real (dias).")
    receita: float = Field(description="Receita total da operacao = soma dos 8 componentes abaixo.")

    # Composicao da receita (regime caixa) — somam `receita`.
    rec_desagio: float = Field(description="Desagio (total_de_juros).")
    rec_tarifa_cessao: float = Field(description="Tarifa de cessao (comunicados de cessao).")
    rec_consultas_financeiras: float
    rec_consultas_fiscais: float
    rec_registros_bancarios: float
    rec_documentos_digitais: float
    rec_ad_valorem: float
    rec_rebate: float

    # Tributos e ajustes — NAO compoem receita (exibidos a parte).
    trib_iof: float = Field(description="IOF (tributo, nao-receita).")
    trib_imposto: float = Field(description="Imposto (tributo, nao-receita).")
    trib_descontos: float = Field(description="Descontos/abatimentos (ajuste, nao-receita).")


class Operacoes5OperacoesData(BaseModel):
    """Bundle das operacoes de um cedente. Reconcilia: sum(operacoes.vop) == vop_total."""

    cedente_id: int | None
    cedente_nome: str
    cedente_documento: str | None
    operacoes: list[Operacoes5OperacaoItem]
    total: int
    vop_total: float
    receita_total: float


class Operacoes5DocumentoItem(BaseModel):
    """Linha da lista de documentos (titulos) de uma operacao (nivel Documento = inline)."""

    titulo_id: int
    sigla: str = Field(description="Tipo do documento (DUP, NF, CCB, ...).")
    numero: str = Field(description="Numero do documento (duplicata/nota).")
    sacado_id: int = Field(description="Id Bitfin do sacado (nome resolvido na Fase 2).")
    valor: float
    valor_liquido: float
    saldo_devedor: float
    data_de_vencimento_efetiva: date | None
    situacao: int
    status: int | None


class Operacoes5DocumentosData(BaseModel):
    """Bundle dos documentos de uma operacao. Reconcilia: sum(documentos.valor) == valor_total."""

    operacao_id: int
    documentos: list[Operacoes5DocumentoItem]
    total: int
    valor_total: float
