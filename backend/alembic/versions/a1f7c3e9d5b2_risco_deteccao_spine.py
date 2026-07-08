"""risco_deteccao_spine

Revision ID: a1f7c3e9d5b2
Revises: e8b3c6a1d9f4
Create Date: 2026-07-08

Espinha multi-modelo de deteccao de anomalias (handoff 2026-07-08, memoria
project_deteccao_anomalias_liquidacao):

1. `deteccao_modelo` — catalogo GLOBAL (sem tenant_id, como source_catalog).
2. `deteccao_modelo_versao` — versao treinada IMUTAVEL por tenant
   (coeficientes da logistica em JSONB auditavel; sem pickle/MLflow).
3. `deteccao_modelo_ativo` — ponteiro de versao ativa (rollback 1 UPDATE;
   padrao ai_prompt_active). Versao recem-treinada nasce INATIVA.
4. `deteccao_score` — ultimo score por (tenant, modelo, liquidacao) +
   fatores de explicabilidade (§14.3) + snapshot de features.
5. `curadoria_tag` — veredito humano APPEND-ONLY (IA opina, humano
   homologa; nunca UPDATE/DELETE).

Seed do catalogo (2 linhas):
- `liquidacao_boleto` (modelo 1 — padrao de liquidacao, supervisionado)
- `lastro_inconsistente` (alvo A — registrado adormecido, sem versao)

SAEnum native_enum=False armazena o NOME do enum (uppercase) — seed insere
'SUPERVISIONADO' (gotcha SAEnum-le-pelo-NOME).
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "a1f7c3e9d5b2"
down_revision: str | Sequence[str] | None = "e8b3c6a1d9f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Catalogo global (sem tenant_id — define O QUE o modelo e, nao o que aprendeu)
    op.create_table(
        "deteccao_modelo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nome", sa.String(64), nullable=False, unique=True),
        sa.Column("alvo", sa.String(255), nullable=False),
        sa.Column("tipo", sa.String(24), nullable=False),
        sa.Column("modulo", sa.String(24), nullable=False),
        sa.Column("unidade", sa.String(64), nullable=False),
        sa.Column("descricao", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 2. Versoes imutaveis (tenant-scoped: coeficientes aprendidos do dado do tenant)
    op.create_table(
        "deteccao_modelo_versao",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "modelo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deteccao_modelo.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("versao", sa.Integer(), nullable=False),
        sa.Column("coeficientes", postgresql.JSONB(), nullable=False),
        sa.Column("threshold", sa.Numeric(6, 5), nullable=True),
        sa.Column("metrics", postgresql.JSONB(), nullable=True),
        sa.Column("n_amostras", sa.Integer(), nullable=True),
        sa.Column("n_positivos", sa.Integer(), nullable=True),
        sa.Column(
            "trained_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "trained_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("notas", sa.String(512), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "modelo_id", "versao", name="uq_deteccao_modelo_versao"
        ),
    )
    op.create_index(
        "ix_deteccao_modelo_versao_tenant_id", "deteccao_modelo_versao", ["tenant_id"]
    )
    op.create_index(
        "ix_deteccao_modelo_versao_modelo_id", "deteccao_modelo_versao", ["modelo_id"]
    )

    # 3. Ponteiro de versao ativa
    op.create_table(
        "deteccao_modelo_ativo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "modelo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deteccao_modelo.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "versao_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deteccao_modelo_versao.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "activated_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.UniqueConstraint("tenant_id", "modelo_id", name="uq_deteccao_modelo_ativo"),
    )
    op.create_index(
        "ix_deteccao_modelo_ativo_tenant_id", "deteccao_modelo_ativo", ["tenant_id"]
    )

    # 4. Scores (1 linha por unidade, re-escrita por versao ativa mais nova)
    op.create_table(
        "deteccao_score",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "modelo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deteccao_modelo.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "versao_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deteccao_modelo_versao.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "liquidacao_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wh_liquidacao.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Numeric(6, 5), nullable=True),
        sa.Column("fatores", postgresql.JSONB(), nullable=True),
        sa.Column("features", postgresql.JSONB(), nullable=True),
        sa.Column(
            "regra_dura", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("regra_dura_motivo", sa.String(255), nullable=True),
        sa.Column(
            "computed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "modelo_id", "liquidacao_id", name="uq_deteccao_score_unidade"
        ),
    )
    op.create_index("ix_deteccao_score_tenant_id", "deteccao_score", ["tenant_id"])
    op.create_index("ix_deteccao_score_modelo_id", "deteccao_score", ["modelo_id"])
    op.create_index(
        "ix_deteccao_score_liquidacao_id", "deteccao_score", ["liquidacao_id"]
    )
    # Listagem/ranking da curadoria ordena por score desc dentro do tenant+modelo
    op.create_index(
        "ix_deteccao_score_ranking",
        "deteccao_score",
        ["tenant_id", "modelo_id", "score"],
    )

    # 5. Tags de curadoria (append-only — sem UPDATE/DELETE, por convencao dura)
    op.create_table(
        "curadoria_tag",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "modelo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("deteccao_modelo.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "liquidacao_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("wh_liquidacao.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tag", sa.String(16), nullable=False),
        sa.Column("nota", sa.String(512), nullable=True),
        sa.Column(
            "autor",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_curadoria_tag_tenant_id", "curadoria_tag", ["tenant_id"])
    op.create_index("ix_curadoria_tag_modelo_id", "curadoria_tag", ["modelo_id"])
    op.create_index("ix_curadoria_tag_liquidacao_id", "curadoria_tag", ["liquidacao_id"])
    # Lookup "ultima tag vigente" por unidade
    op.create_index(
        "ix_curadoria_tag_vigente",
        "curadoria_tag",
        ["tenant_id", "modelo_id", "liquidacao_id", "created_at"],
    )

    # Seed do catalogo global — modelo 1 ativo em construcao + alvo A adormecido
    modelo_tbl = sa.table(
        "deteccao_modelo",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("nome", sa.String),
        sa.column("alvo", sa.String),
        sa.column("tipo", sa.String),
        sa.column("modulo", sa.String),
        sa.column("unidade", sa.String),
        sa.column("descricao", sa.String),
    )
    op.bulk_insert(
        modelo_tbl,
        [
            {
                "id": uuid.UUID("d1e7ec7a-0b0e-4e70-9f1a-000000000001"),
                "nome": "liquidacao_boleto",
                "alvo": "liquidacao anomala (auto-liquidacao pelo cedente)",
                "tipo": "SUPERVISIONADO",
                "modulo": "risco",
                "unidade": "wh_liquidacao",
                "descricao": (
                    "Modelo 1 do programa antifraude: classifica eventos de "
                    "liquidacao (canais bancaria + baixa_manual) usando praca, "
                    "canal, fingerprint do sacado, mecanica declarada, timing e "
                    "contrato do produto. Regras duras deterministicas rodam a "
                    "parte e nao dependem de treino."
                ),
            },
            {
                "id": uuid.UUID("d1e7ec7a-0b0e-4e70-9f1a-000000000002"),
                "nome": "lastro_inconsistente",
                "alvo": "titulo sem lastro real (fraude documental)",
                "tipo": "SUPERVISIONADO",
                "modulo": "risco",
                "unidade": "wh_titulo",
                "descricao": (
                    "Alvo A — segunda linha do catalogo, ADORMECIDO por decisao "
                    "(2026-07-08). Melhor base de rotulos da casa (Titulo.Status=3, "
                    "65 cedentes / 7 anos); features fiscais/XML. Nao construir "
                    "antes do modelo 1 fechar o loop de curadoria."
                ),
            },
        ],
    )


def downgrade() -> None:
    op.drop_table("curadoria_tag")
    op.drop_table("deteccao_score")
    op.drop_table("deteccao_modelo_ativo")
    op.drop_table("deteccao_modelo_versao")
    op.drop_table("deteccao_modelo")
