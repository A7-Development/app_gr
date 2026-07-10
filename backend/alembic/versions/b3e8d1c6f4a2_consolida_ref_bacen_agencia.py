"""consolida_ref_bacen_agencia

Revision ID: b3e8d1c6f4a2
Revises: a9d1c7e4f2b8
Create Date: 2026-07-10

Consolidacao da referencia de agencias Bacen (decisao Ricardo 2026-07-10):

1. `ref_bacen_agencia` absorve a serie historica BCB (`wh_bcb_agencia`,
   estatica, nunca mais atualizada): colunas de endereco + janela de VIGENCIA
   (primeira/ultima_competencia, habilita resolucao as-of e o sinal PRC-04)
   + `ativa` + `fonte` (olinda | bcb_historico).
2. Backfill: linhas ja existentes (Olinda) sao ENRIQUECIDAS com endereco/
   vigencia do historico; agencias so-do-historico (inclui EXTINTAS, ex.
   Bradesco 1417 "Mercado Sao Sebastiao") sao INSERIDAS com fonte
   bcb_historico.
3. View `ref_bacen_ponto`: superficie unica de lookup da escada de praca
   (agencias consolidadas + postos), com vigencia.
4. Drop de `wh_bcb_agencia` — corrige tambem o naming (era referencia publica
   com prefixo wh_ e tenant_id indevidos).

Downgrade recria `wh_bcb_agencia` VAZIA (dado estatico; recarga via
scripts/backfill_bcb_agencia.py no historico do git) e remove colunas/linhas
consolidadas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b3e8d1c6f4a2"
down_revision: str | Sequence[str] | None = "a9d1c7e4f2b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VIEW = "ref_bacen_ponto"


def upgrade() -> None:
    # 1. Colunas novas (serie historica BCB + fonte cadastral).
    op.add_column("ref_bacen_agencia", sa.Column("endereco", sa.String(255), nullable=True))
    op.add_column("ref_bacen_agencia", sa.Column("bairro", sa.String(255), nullable=True))
    op.add_column("ref_bacen_agencia", sa.Column("cep", sa.String(9), nullable=True))
    op.add_column(
        "ref_bacen_agencia",
        sa.Column("primeira_competencia", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ref_bacen_agencia",
        sa.Column("ultima_competencia", sa.Integer(), nullable=True),
    )
    op.add_column("ref_bacen_agencia", sa.Column("ativa", sa.Boolean(), nullable=True))
    op.add_column(
        "ref_bacen_agencia",
        sa.Column("fonte", sa.String(20), nullable=False, server_default="olinda"),
    )

    # 2a. Enriquece linhas Olinda existentes com endereco/vigencia do historico.
    #     Match pela chave CNAB (banco 3 digitos, agencia 5 digitos zero-padded
    #     — ambos os lados ja armazenam nesse formato).
    op.execute(
        """
        UPDATE ref_bacen_agencia r
        SET endereco = b.endereco,
            bairro = b.bairro,
            cep = b.cep,
            primeira_competencia = b.primeira_competencia,
            ultima_competencia = b.ultima_competencia,
            ativa = b.ativa
        FROM (
            SELECT DISTINCT ON (banco_compe, agencia_codigo)
                   banco_compe, agencia_codigo, endereco, bairro, cep,
                   primeira_competencia, ultima_competencia, ativa
            FROM wh_bcb_agencia
            WHERE banco_compe IS NOT NULL
            ORDER BY banco_compe, agencia_codigo,
                     ultima_competencia DESC NULLS LAST
        ) b
        WHERE r.banco_compe = b.banco_compe
          AND r.agencia_codigo = b.agencia_codigo
        """
    )

    # 2b. Insere agencias que SO existem na serie historica (extintas ou fora
    #     do snapshot Olinda) com fonte='bcb_historico'.
    op.execute(
        """
        INSERT INTO ref_bacen_agencia (
            id, banco_compe, cnpj_base, nome_if, agencia_codigo, nome_agencia,
            municipio, municipio_ibge, uf, data_inicio, posicao,
            endereco, bairro, cep, primeira_competencia, ultima_competencia,
            ativa, fonte, fetched_at, fetched_by_version
        )
        SELECT gen_random_uuid(),
               b.banco_compe,
               COALESCE(substr(b.cnpj, 1, 8), ''),
               COALESCE(b.instituicao, ''),
               b.agencia_codigo,
               b.nome_agencia,
               b.municipio,
               b.municipio_ibge,
               b.uf,
               b.data_inicio,
               NULL,
               b.endereco, b.bairro, b.cep,
               b.primeira_competencia, b.ultima_competencia, b.ativa,
               'bcb_historico', now(), 'consolidacao_b3e8d1c6f4a2'
        FROM (
            SELECT DISTINCT ON (banco_compe, agencia_codigo) *
            FROM wh_bcb_agencia
            WHERE banco_compe IS NOT NULL
            ORDER BY banco_compe, agencia_codigo,
                     ultima_competencia DESC NULLS LAST
        ) b
        WHERE NOT EXISTS (
            SELECT 1 FROM ref_bacen_agencia r
            WHERE r.banco_compe = b.banco_compe
              AND r.agencia_codigo = b.agencia_codigo
        )
        """
    )

    # 3. Superficie unica de lookup da escada (agencias + postos), com
    #    vigencia. Consumo: resolver de praca / consultas ad-hoc.
    op.execute(
        f"""
        CREATE VIEW {_VIEW} AS
        SELECT banco_compe,
               agencia_codigo AS codigo,
               'agencia'::text AS tipo,
               nome_agencia AS nome,
               municipio, municipio_ibge, uf,
               primeira_competencia, ultima_competencia, ativa, fonte
        FROM ref_bacen_agencia
        UNION ALL
        SELECT banco_compe,
               posto_codigo AS codigo,
               COALESCE(tipo_posto, 'posto') AS tipo,
               nome_posto AS nome,
               municipio, municipio_ibge, uf,
               CAST(to_char(primeira_posicao, 'YYYYMM') AS integer),
               CAST(to_char(ultima_posicao, 'YYYYMM') AS integer),
               NULL::boolean AS ativa,
               'bcb_posto'::text AS fonte
        FROM ref_bacen_posto
        WHERE banco_compe IS NOT NULL AND posto_codigo IS NOT NULL
        """
    )

    # 4. A serie historica agora vive consolidada — a tabela (mal-nomeada
    #    wh_ + tenant_id p/ dado publico) sai.
    op.drop_index("ix_wh_bcb_agencia_lookup", table_name="wh_bcb_agencia")
    op.drop_index("ix_wh_bcb_agencia_tenant_id", table_name="wh_bcb_agencia")
    op.drop_table("wh_bcb_agencia")


def downgrade() -> None:
    op.execute(f"DROP VIEW IF EXISTS {_VIEW}")
    # Recria a tabela VAZIA (schema original f8c3a1e6d4b9); recarga do dado
    # estatico via scripts/backfill_bcb_agencia.py (historico do git).
    op.create_table(
        "wh_bcb_agencia",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("banco_compe", sa.String(3), nullable=True),
        sa.Column("agencia_codigo", sa.String(5), nullable=False),
        sa.Column("cnpj", sa.String(14), nullable=True),
        sa.Column("instituicao", sa.String(255), nullable=True),
        sa.Column("nome_agencia", sa.String(255), nullable=True),
        sa.Column("endereco", sa.String(255), nullable=True),
        sa.Column("complemento", sa.String(255), nullable=True),
        sa.Column("bairro", sa.String(255), nullable=True),
        sa.Column("cep", sa.String(9), nullable=True),
        sa.Column("municipio", sa.String(255), nullable=True),
        sa.Column("municipio_ibge", sa.Integer(), nullable=True),
        sa.Column("uf", sa.String(2), nullable=True),
        sa.Column("ddd", sa.String(3), nullable=True),
        sa.Column("fone", sa.String(20), nullable=True),
        sa.Column("segmento", sa.String(64), nullable=True),
        sa.Column("data_inicio", sa.Date(), nullable=True),
        sa.Column("primeira_competencia", sa.Integer(), nullable=True),
        sa.Column("ultima_competencia", sa.Integer(), nullable=True),
        sa.Column("ativa", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("hash_origem", sa.String(64), nullable=True),
        sa.Column("ingested_by_version", sa.String(128), nullable=False),
        sa.Column("trust_level", sa.String(16), nullable=False),
        sa.Column("collected_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("tenant_id", "source_id", name="uq_wh_bcb_agencia"),
    )
    op.create_index("ix_wh_bcb_agencia_tenant_id", "wh_bcb_agencia", ["tenant_id"])
    op.create_index(
        "ix_wh_bcb_agencia_lookup",
        "wh_bcb_agencia",
        ["tenant_id", "banco_compe", "agencia_codigo"],
    )
    op.execute("DELETE FROM ref_bacen_agencia WHERE fonte = 'bcb_historico'")
    op.drop_column("ref_bacen_agencia", "fonte")
    op.drop_column("ref_bacen_agencia", "ativa")
    op.drop_column("ref_bacen_agencia", "ultima_competencia")
    op.drop_column("ref_bacen_agencia", "primeira_competencia")
    op.drop_column("ref_bacen_agencia", "cep")
    op.drop_column("ref_bacen_agencia", "bairro")
    op.drop_column("ref_bacen_agencia", "endereco")
