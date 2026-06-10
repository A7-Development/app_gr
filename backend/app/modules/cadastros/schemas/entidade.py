"""Cadastros — schemas da Ficha da Entidade (peek/resumo).

Consumido pelo `<EntidadePeek />` (drawer global `?entidade=<documento>`).
Blocos F1 (carteira ativa, limites, performance) NAO estao aqui — entram
quando as posicoes por papel forem ingeridas; o frontend renderiza
placeholder de dominio ate la.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EntidadePapelOut(BaseModel):
    papel: str = Field(description="cedente | sacado | avalista | socio | fornecedor")
    source_id: str = Field(
        description="Id do papel na fonte (Bitfin: ClienteId/SacadoId). "
        "O do papel cedente liga com wh_operacao.cedente_id."
    )
    status_fonte: str | None


class EntidadeEstabelecimentoOut(BaseModel):
    """Estabelecimento da mesma raiz (matriz/filial da mesma PJ)."""

    documento: str
    nome: str
    filial_numero: str | None
    is_matriz: bool | None
    localidade: str | None
    estado: str | None


class GrupoMembroOut(BaseModel):
    documento: str | None = Field(description="None = membro em quarentena.")
    nome: str | None
    vinculo: str | None
    papeis: list[str]


class GrupoEconomicoOut(BaseModel):
    nome: str
    segmento: str | None
    membros: list[GrupoMembroOut]


class BureauResumoOut(BaseModel):
    """Ultima consulta de bureau do documento (hoje: Serasa Relato PJ)."""

    fonte: str
    consultado_em: datetime
    score: int | None
    score_classe: str | None
    protestos_qtd: int | None
    pefin_qtd: int | None
    refin_qtd: int | None
    cheques_qtd: int | None
    acoes_judiciais_qtd: int | None
    falencias_qtd: int | None
    valor_total_restricoes: float | None


class CarteiraAtivaLinhaOut(BaseModel):
    """Linha da mini-matriz Carteira Ativa (escopo CNPJ ou Grupo)."""

    escopo: str = Field(description="cnpj | grupo")
    cedente_valor: float
    sacado_valor: float
    total: float
    cedente_vencido: float
    sacado_vencido: float


class LimiteProdutoOut(BaseModel):
    """Limite aprovado por produto (papel cedente — nao ha limite por sacado)."""

    produto_sigla: str | None
    limite: float
    em_uso: float = Field(description="Risco total em aberto no produto.")
    vencido: float


class PerformanceResumoOut(BaseModel):
    """Snapshot do vencimentario (janela de apuracao do Bitfin).

    Componentes (liquidados + recomprados + vencidos_*) somam
    `vencimentario` (§14.6 — reconciliacao on-screen no peek)."""

    papel: str = Field(description="Lente: cedente | sacado")
    indice_liquidez: float | None
    vencimentario: float | None
    liquidados: float | None
    recomprados: float | None
    vencidos_penalizados: float | None
    vencidos_nao_penalizados: float | None
    janela_dias: int | None
    data_apuracao: datetime | None
    prazo_medio_carteira: float | None = Field(
        description="Prazo medio do ESTOQUE (lente cedente)."
    )
    indice_pontualidade: float | None = Field(
        description="Lente sacado apenas."
    )


class EntidadeResumoOut(BaseModel):
    """Resumo da entidade para o peek — identidade + papeis + grupo + bureau."""

    # Identidade
    documento: str
    tipo_pessoa: str
    nome: str
    documento_raiz: str | None
    filial_numero: str | None
    is_matriz: bool | None

    # Cadastro
    cnae_chave: str | None
    cnae_denominacao: str | None
    porte: str | None
    data_constituicao: datetime | None
    em_recuperacao_judicial: bool | None
    data_recuperacao_judicial: datetime | None
    localidade: str | None
    estado: str | None

    # Papeis (a tese do party model: o mesmo CNPJ em N papeis)
    papeis: list[EntidadePapelOut]
    cedente_id: int | None = Field(
        description="Conveniencia: source_id numerico do papel cedente "
        "(Bitfin ClienteId) — usado pelo peek p/ buscar operacoes via "
        "/bi/operacoes5/operacoes?cedente_id=."
    )

    # Estrutura
    estabelecimentos: list[EntidadeEstabelecimentoOut] = Field(
        description="Todos os estabelecimentos da mesma raiz (inclui o proprio)."
    )
    grupo: GrupoEconomicoOut | None

    # Posicoes por papel (F1)
    carteira_ativa: list[CarteiraAtivaLinhaOut]
    limites: list[LimiteProdutoOut]
    performance: PerformanceResumoOut | None

    # Bureau
    bureau: BureauResumoOut | None

    # Proveniencia (§14.5)
    source_type: str
    ingested_at: datetime
