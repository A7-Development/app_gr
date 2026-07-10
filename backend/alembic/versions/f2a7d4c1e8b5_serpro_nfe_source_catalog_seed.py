"""integracoes: seed source_catalog para data:serpro_nfe.

Revision ID: f2a7d4c1e8b5
Revises: c5e2b8d1f4a9
Create Date: 2026-07-10 16:00:00.000000

Insere linha de catalogo para o adapter SERPRO Consulta NF-e (estado vivo
da nota + eventos, F0 do plano SERPRO). Nao altera schema — o enum
SourceType e native_enum=False (VARCHAR).

ATENCAO (gotcha SAEnum, 3a ocorrencia da familia): a coluna armazena o
NOME do enum ("DATA_SERPRO_NFE"), nao o value ("data:serpro_nfe"). Linha
com value minusculo vira enum orfa e derruba /integracoes/fontes com 500.

Idempotente: ON CONFLICT DO NOTHING na source_type (PK).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f2a7d4c1e8b5"
down_revision: str | None = "c5e2b8d1f4a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SERPRO_ROW = {
    "source_type": "DATA_SERPRO_NFE",
    "label": "SERPRO — Consulta NF-e",
    "category": "data",
    "owner_org": "SERPRO (Servico Federal de Processamento de Dados)",
    # Rate limit contratual nao documentado publicamente; confirmar na
    # Area do Cliente quando necessario.
    "rate_limit_per_minute": None,
    # Custo por consulta varia por plano (df fixo / escalonado por faixa);
    # apenas HTTP 200 e cobrado. Preencher quando o plano for confirmado.
    "unit_cost_brl": None,
    "description": (
        "API Consulta NF-e do SERPRO: estado vivo da nota por chave de "
        "acesso (cStat atual, cancelamento pos-autorizacao, manifestacao "
        "do destinatario) + eventos (procEventosNFe). OAuth2 "
        "client_credentials no gateway.apiserpro.serpro.gov.br; push de "
        "eventos via URL de notificacao (sem fila/retry). Somente leitura; "
        "so HTTP 200 e cobrado. Credencial compartilhada com o contrato "
        "consumido pelo Bitfin (decisao 2026-07-10)."
    ),
}


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO source_catalog (
                source_type, label, category, owner_org,
                rate_limit_per_minute, unit_cost_brl, description,
                created_at, updated_at
            )
            VALUES (
                :source_type, :label, :category, :owner_org,
                :rate_limit_per_minute, :unit_cost_brl, :description,
                now(), now()
            )
            ON CONFLICT (source_type) DO NOTHING
            """
        ),
        SERPRO_ROW,
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM source_catalog WHERE source_type = 'DATA_SERPRO_NFE'"
        )
    )
