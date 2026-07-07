"""risco_produto_contrato_liquidacao

Revision ID: b5d7e2a9c4f1
Revises: f3a8c5d2e7b4
Create Date: 2026-07-07

Contrato de liquidacao por produto — primeiro primitivo do modulo Risco
(programa antifraude auto-liquidacao, decisao Ricardo 2026-07-07):

1. Tabela `produto_contrato_liquidacao`, versionada estilo premise_set
   (append-only; contrato ativo = maior version; produto SEM linha =
   contrato "em aberto" — motor de sinais nao pontua).
2. Seed dos 13 produtos com contrato FECHADO na sessao de curadoria
   2026-07-07 (por tenant, a partir de wh_dim_produto). Os 7 restantes
   (CSG, CUS, CAM, CCE, NCE, CPR, LCC) ficam deliberadamente em aberto —
   "definir se ganhar volume".

SAEnum native_enum=False armazena o NOME do enum (uppercase) — o seed
insere 'BOLETO_BANCARIO', 'OBRIGATORIO', etc (gotcha SAEnum-le-pelo-NOME).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b5d7e2a9c4f1"
down_revision: str | Sequence[str] | None = "f3a8c5d2e7b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (fluxo_esperado, boleto, baixa_manual) por sigla — valores FECHADOS 2026-07-07.
_SEED: dict[str, tuple[str, str, str]] = {
    # Boleto bancario obrigatorio + baixa manual ANOMALA
    "FAT": ("BOLETO_BANCARIO", "OBRIGATORIO", "ANOMALA"),
    "CBV": ("BOLETO_BANCARIO", "OBRIGATORIO", "ANOMALA"),
    "CBS": ("BOLETO_BANCARIO", "OBRIGATORIO", "ANOMALA"),
    # Deposito em conta + boleto nao esperado + baixa normal
    "CMS": ("DEPOSITO_EM_CONTA", "NAO_ESPERADO", "NORMAL"),
    # DMS ajustado pos-analise 90d (2026-07-07): opera legitimamente em 2
    # modos (bancarizado E deposito direto) -> boleto PERMITIDO, sem alerta.
    "DMS": ("DEPOSITO_EM_CONTA", "PERMITIDO", "NORMAL"),
    "RCS": ("DEPOSITO_EM_CONTA", "NAO_ESPERADO", "NORMAL"),
    "TVB": ("DEPOSITO_EM_CONTA", "NAO_ESPERADO", "NORMAL"),
    "EXP": ("DEPOSITO_EM_CONTA", "NAO_ESPERADO", "NORMAL"),
    "CCB": ("DEPOSITO_EM_CONTA", "NAO_ESPERADO", "NORMAL"),
    "NOT": ("DEPOSITO_EM_CONTA", "NAO_ESPERADO", "NORMAL"),
    "CFD": ("DEPOSITO_EM_CONTA", "NAO_ESPERADO", "NORMAL"),
    # Intercompany: boleto PERMITIDO (pode acontecer, sem alerta)
    "INT": ("DEPOSITO_EM_CONTA", "PERMITIDO", "NORMAL"),
    # Fomento: liquidacao interna (recompra comum; deposito aceitavel)
    "FOM": ("LIQUIDACAO_INTERNA", "NAO_ESPERADO", "NORMAL"),
}

_SEED_JUSTIFICATIVA = (
    "Seed inicial — contrato de liquidacao por produto fechado na sessao "
    "de curadoria de 2026-07-07."
)


def upgrade() -> None:
    op.create_table(
        "produto_contrato_liquidacao",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("produto_sigla", sa.String(10), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("fluxo_esperado", sa.String(32), nullable=False),
        sa.Column("boleto", sa.String(32), nullable=False),
        sa.Column("baixa_manual", sa.String(32), nullable=False),
        sa.Column("justificativa", sa.String(512), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "produto_sigla",
            "version",
            name="uq_contrato_liquidacao_produto_version",
        ),
    )
    op.create_index(
        "ix_produto_contrato_liquidacao_tenant_id",
        "produto_contrato_liquidacao",
        ["tenant_id"],
    )
    op.create_index(
        "ix_produto_contrato_liquidacao_produto_sigla",
        "produto_contrato_liquidacao",
        ["produto_sigla"],
    )

    # Seed v1 por tenant que tem o produto na dimensao. Idempotente
    # (ON CONFLICT DO NOTHING na UNIQUE tenant+sigla+version).
    for sigla, (fluxo, boleto, baixa) in _SEED.items():
        op.execute(
            sa.text(
                """
                INSERT INTO produto_contrato_liquidacao
                    (id, tenant_id, produto_sigla, version,
                     fluxo_esperado, boleto, baixa_manual,
                     justificativa, created_at)
                SELECT gen_random_uuid(), dp.tenant_id, dp.sigla, 1,
                       :fluxo, :boleto, :baixa, :justificativa, now()
                FROM wh_dim_produto dp
                WHERE dp.sigla = :sigla
                ON CONFLICT ON CONSTRAINT uq_contrato_liquidacao_produto_version
                DO NOTHING
                """
            ).bindparams(
                sigla=sigla,
                fluxo=fluxo,
                boleto=boleto,
                baixa=baixa,
                justificativa=_SEED_JUSTIFICATIVA,
            )
        )


def downgrade() -> None:
    op.drop_index(
        "ix_produto_contrato_liquidacao_produto_sigla",
        table_name="produto_contrato_liquidacao",
    )
    op.drop_index(
        "ix_produto_contrato_liquidacao_tenant_id",
        table_name="produto_contrato_liquidacao",
    )
    op.drop_table("produto_contrato_liquidacao")
