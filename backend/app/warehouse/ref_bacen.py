"""ref_bacen_* -- referencia publica de instituicoes e agencias bancarias (Bacen).

Dicionario geografico/institucional do Sentinela CNAB (F2): traduz o par
(banco, agencia) que vem no retorno CNAB (posicoes 166-173) em instituicao,
segmento e praca (municipio/UF) -- INDEPENDENTE do cadastro de agencias do ERP
(que descarta a agencia quando nao a conhece; caso MFL 2026-07-07).

Fontes (dados abertos do Bacen, sem tenant/credencial):
  - Participantes do STR (CSV diario): ISPB, nome, codigo Compe do banco.
  - Informes_Agencias (API Olinda, mensal): agencias de bancos com municipio.

Tabelas GLOBAIS -- sem tenant_id (excecao da regra multi-tenant, CLAUDE.md
sec 10: dado publico de referencia, como `source_catalog`). NAO usam
`Auditable` (sao a propria fonte de referencia): proveniencia em colunas
proprias (fetched_at, fetched_by_version).

Politica de refresh: UPSERT sem delete -- agencia que sai do snapshot do Bacen
(fechada/renumerada) PERMANECE aqui, porque o acervo CNAB historico ainda
referencia agencias extintas. `posicao` marca o snapshot em que a linha foi
vista pela ultima vez.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Segmentos canonicos (heuristica sobre o nome extenso do STR; refinamento via
# BcBase/EntidadesSupervisionadas e follow-up). Dirigem o classificador de
# canal em `adapters/cobranca/canal.py`.
SEGMENTO_BANCO = "banco"
SEGMENTO_BANCO_COOPERATIVO = "banco_cooperativo"  # Bancoob 756, Sicredi 748, Ailos 085
SEGMENTO_COOPERATIVA = "cooperativa"
SEGMENTO_IP = "ip"  # instituicao de pagamento
SEGMENTO_SCD = "scd"  # sociedade de credito direto
SEGMENTO_FINANCEIRA = "financeira"
SEGMENTO_OUTROS = "outros"

# Fonte cadastral da linha de agencia (consolidacao 2026-07-10):
#   olinda         snapshot vivo Informes_Agencias (sync mensal atualiza)
#   bcb_historico  serie historica BCB 2007-2026 (estatica; inclui extintas —
#                  ex. Bradesco 1417 "Mercado Sao Sebastiao") — absorvida da
#                  antiga wh_bcb_agencia (tabela dropada)
FONTE_OLINDA = "olinda"
FONTE_BCB_HISTORICO = "bcb_historico"


class RefBacenInstituicao(Base):
    """Instituicao participante do STR, chaveada pelo codigo Compe (o codigo
    de banco que trafega no CNAB)."""

    __tablename__ = "ref_bacen_instituicao"

    # Codigo Compe do banco ("237", "756", "323"). PK: e a chave de join com o
    # CNAB. Instituicoes sem codigo ("n/a" no STR) nao entram -- inalcancaveis
    # via CNAB.
    codigo_compe: Mapped[str] = mapped_column(String(3), primary_key=True)
    ispb: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    nome_reduzido: Mapped[str] = mapped_column(String(120), nullable=False)
    nome_extenso: Mapped[str | None] = mapped_column(String(255), nullable=True)
    participa_compe: Mapped[bool] = mapped_column(Boolean, nullable=False)
    segmento: Mapped[str] = mapped_column(String(30), nullable=False)
    # De onde veio o segmento ("oficial_bacen" | "heuristica_nome" | "manual").
    segmento_fonte: Mapped[str] = mapped_column(String(20), nullable=False)
    # Rotulo OFICIAL do Bacen (ex.: "Banco Multiplo", "Instituicao de
    # Pagamento") quando resolvido pela Relacao de Instituicoes; NULL se so
    # heuristica. Preserva a granularidade oficial alem do canonico.
    segmento_oficial: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Banco digital = banco (segmento oficial) SEM rede fisica (<=1 agencia).
    # UNICA inferencia: "digital" nao e categoria regulatoria (Inter/C6 sao
    # "Banco Multiplo" oficial). Derivado da contagem de agencias (Bacen).
    is_banco_digital: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    inicio_operacao: Mapped[date | None] = mapped_column(Date, nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_by_version: Mapped[str] = mapped_column(String(64), nullable=False)


class RefBacenPosto(Base):
    """Posto de atendimento (PAB/PAE) do Bacen — a OUTRA metade da rede fisica.

    Dado publico sem tenant_id (excecao §10, como as demais ref_*). Cobre
    unidades que operam com codigo proprio de agencia no CNAB mas na taxonomia
    Bacen sao postos (AG Empresarial/Plataforma Empresas da CEF, PABs em orgaos
    publicos). 3o degrau da escada de praca (antes do ERP). Fonte: Olinda
    Informes_PostosDeAtendimento (snapshot corrente; upsert-sem-delete acumula
    a historia via primeira/ultima posicao).

    Chave natural: (cnpj_base, nome_posto) — o NomePosto identifica o posto na
    instituicao. Lookup do resolver: (banco_compe, posto_codigo) — o codigo vem
    embutido no NomePosto ("6425 - PLATAFORMA EMPRESAS..."); postos sem codigo
    no nome ficam com posto_codigo NULL (fora do lookup, mas na tabela p/ audit).
    """

    __tablename__ = "ref_bacen_posto"
    __table_args__ = (
        UniqueConstraint("cnpj_base", "nome_posto", name="uq_ref_bacen_posto"),
        Index("ix_ref_bacen_posto_lookup", "banco_compe", "posto_codigo"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    cnpj_base: Mapped[str] = mapped_column(String(8), nullable=False)
    # Compe do banco dono (derivado ISPB=CnpjBase); NULL se sem Compe.
    banco_compe: Mapped[str | None] = mapped_column(String(3), nullable=True)
    nome_if: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nome_posto: Mapped[str] = mapped_column(String(255), nullable=False)
    # Codigo do posto (5 digitos zero-padded) extraido do prefixo do NomePosto.
    posto_codigo: Mapped[str | None] = mapped_column(String(5), nullable=True)
    tipo_posto: Mapped[str | None] = mapped_column(String(80), nullable=True)
    endereco: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(9), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(120), nullable=True)
    municipio_ibge: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    # Historia acumulada (upsert-sem-delete): 1a e ultima posicao vista.
    primeira_posicao: Mapped[date | None] = mapped_column(Date, nullable=True)
    ultima_posicao: Mapped[date | None] = mapped_column(Date, nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_by_version: Mapped[str] = mapped_column(String(64), nullable=False)


class RefBacenAgencia(Base):
    """Agencia bancaria com praca (municipio/UF), chaveada por (banco, agencia)
    no formato do CNAB (agencia com 5 digitos, zeros a esquerda)."""

    __tablename__ = "ref_bacen_agencia"
    __table_args__ = (
        UniqueConstraint(
            "banco_compe", "agencia_codigo", name="uq_ref_bacen_agencia_banco_ag"
        ),
        Index("ix_ref_bacen_agencia_municipio", "municipio_ibge"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # Codigo Compe do banco dono da agencia (join CNAB). Derivado no ETL:
    # Informes_Agencias da o CnpjBase; o STR liga CnpjBase(=ISPB) -> compe.
    banco_compe: Mapped[str] = mapped_column(String(3), nullable=False)
    cnpj_base: Mapped[str] = mapped_column(String(8), nullable=False)
    nome_if: Mapped[str] = mapped_column(String(255), nullable=False)
    # Codigo da agencia normalizado a 5 digitos zero-padded ("03372"), como o
    # CNAB entrega nas posicoes 169-173.
    agencia_codigo: Mapped[str] = mapped_column(String(5), nullable=False)
    nome_agencia: Mapped[str | None] = mapped_column(String(255), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(120), nullable=True)
    municipio_ibge: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Data-posicao do snapshot Bacen em que a linha foi vista pela ultima vez.
    # Linha ausente de snapshots novos NAO e apagada (CNAB historico).
    posicao: Mapped[date | None] = mapped_column(Date, nullable=True)
    # --- Consolidacao da serie historica BCB (2026-07-10; ex-wh_bcb_agencia) ---
    # Endereco fisico (so a serie historica traz; Olinda nao tem).
    endereco: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(9), nullable=True)
    # Janela de VIGENCIA observada na serie historica BCB (YYYYMM). Habilita
    # resolucao as-of (pagamento numa agencia fora de vigencia = anomalia
    # temporal — sinal PRC-04 do catalogo). NULL = vigencia desconhecida
    # (linha so-Olinda): tratar como vigente, nunca como anomalia.
    primeira_competencia: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ultima_competencia: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Flag "ativa" do ultimo snapshot da serie historica; NULL = so-Olinda.
    # NUNCA sobrescrita por ausencia em snapshot (extincao se le pela
    # ultima_competencia envelhecida, nao por delete).
    ativa: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Fonte cadastral da linha: FONTE_OLINDA | FONTE_BCB_HISTORICO. Linha
    # bcb_historico que reaparecer no Informes_Agencias e promovida a olinda
    # pelo upsert do sync (cadastro mais fresco vence).
    fonte: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=FONTE_OLINDA
    )

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_by_version: Mapped[str] = mapped_column(String(64), nullable=False)
