"""Protesto — fonte cenprot-sp + colunas cancelamento/quitacao/completo.

1. Colunas novas (cenprot-sp/protestos traz isso; IEPTB nao -> nullable):
     wh_protesto_titulo.valor_cancelamento / valor_quitacao
     wh_protesto_consulta.completo (false = fonte so devolveu a 1a pagina)
2. Seed do dataset cenprot-sp (consulta robusta, SO token+cnpj, sem login gov.br):
     PROTESTO-SP-CENPROT -> cenprot-sp/protestos
   Os datasets IEPTB (PROTESTO-NACIONAL, PROTESTO-SP-DETALHE) CONTINUAM — sao a
   fonte com credor (submenu "Protestos · Credor SP", gated).

Revision ID: d2e8a4c1f9b7
Revises: c1d7f3a2b6e4
Create Date: 2026-06-22
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d2e8a4c1f9b7"
down_revision: str | None = "c1d7f3a2b6e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "wh_protesto_titulo",
        sa.Column("valor_cancelamento", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "wh_protesto_titulo",
        sa.Column("valor_quitacao", sa.Numeric(18, 2), nullable=True),
    )
    op.add_column(
        "wh_protesto_consulta",
        sa.Column(
            "completo", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
    )

    op.get_bind().execute(
        sa.text(
            "INSERT INTO provedor_dados_dataset "
            "(id, provider_id, provider_dataset_code, provider_api, "
            " public_code, provider_query_name, display_name_pt_br, "
            " categoria_ui, description_pt_br, enabled_for_sale, "
            " created_at, updated_at) "
            "SELECT gen_random_uuid(), p.id, 'CENPROT_SP_PROTESTOS', 'CENPROT', "
            "       'PROTESTO-SP-CENPROT', 'cenprot-sp/protestos', "
            "       'Protestos · CENPROT-SP (sem login)', 'restritivos', "
            "       'Protestos de CPF/CNPJ na Central de Protesto de SP "
            "(protestosp.com.br). Uma chamada, so token+documento (sem login "
            "gov.br). Traz cartorio, valor e cancelamento/quitacao por titulo. "
            "Nao identifica o credor; retorna so a 1a pagina; so SP.', "
            "       false, NOW(), NOW() "
            "FROM provedor_dados p WHERE p.slug = 'INFOSIMPLES' "
            "AND NOT EXISTS (SELECT 1 FROM provedor_dados_dataset "
            "                WHERE public_code = 'PROTESTO-SP-CENPROT')"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM provedor_dados_dataset "
            "WHERE public_code = 'PROTESTO-SP-CENPROT'"
        )
    )
    op.drop_column("wh_protesto_consulta", "completo")
    op.drop_column("wh_protesto_titulo", "valor_quitacao")
    op.drop_column("wh_protesto_titulo", "valor_cancelamento")
