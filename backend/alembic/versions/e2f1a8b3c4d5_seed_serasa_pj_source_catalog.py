"""integracoes: seed source_catalog para bureau:serasa_pj.

Revision ID: e2f1a8b3c4d5
Revises: 7afc13ded02f
Create Date: 2026-05-01 17:00:00.000000

Insere linha de catalogo para o adapter Serasa PJ (Business Information
Report). Nao altera schema. O valor de enum BUREAU_SERASA_PJ ja existe em
`SourceType` desde o rename de 2026-05-01 — so fica registrada a metadata
do catalogo para a UI preencher o card do tenant.

Idempotente: ON CONFLICT DO NOTHING na source_type (PK).
"""

import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e2f1a8b3c4d5"
down_revision: str | None = "7afc13ded02f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


SERASA_PJ_INPUTS = [
    {
        "name": "cnpj",
        "type": "string",
        "format": "14_digits",
        "required": True,
        "description": "CNPJ da empresa-alvo, so digitos.",
    },
]

SERASA_PJ_OUTPUTS = [
    {
        "name": "registrationData",
        "description": "Dados cadastrais — razao social, situacao, atividades.",
    },
    {
        "name": "scoring",
        "description": "Score H4PJ + classe de risco + payload do modelo.",
    },
    {
        "name": "negativeData",
        "description": "Restricoes — REFIN, PEFIN, protestos, cheques sem fundo.",
    },
    {
        "name": "businessRecord",
        "description": "Anotacoes em orgaos publicos (ANBC).",
    },
    {
        "name": "businessParticipation",
        "description": "Participacao em outras empresas.",
    },
    {
        "name": "partners",
        "description": "Quadro societario e administradores.",
    },
    {
        "name": "address / phones / email",
        "description": "Dados de contato cadastrados.",
    },
]

SERASA_PJ_DESCRIPTION = (
    "Bureau de credito PJ. Endpoint /credit-services/business-information-"
    "report/v1/reports. A7 Credit consome como distribuidor — header "
    "X-Retailer-Document-Id obrigatorio em toda chamada. Modelo de score "
    "forcado: H4PJ. Features SPC bloqueadas no contrato distribuidor. "
    "MVP usa RELATORIO_AVANCADO_PJ_ANALITICO."
)


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO source_catalog (
                source_type, label, category, owner_org,
                rate_limit_per_minute, unit_cost_brl,
                inputs, outputs, description,
                created_at, updated_at
            )
            VALUES (
                :source_type, :label, :category, :owner_org,
                :rate_limit_per_minute, :unit_cost_brl,
                CAST(:inputs AS JSONB), CAST(:outputs AS JSONB), :description,
                now(), now()
            )
            ON CONFLICT (source_type) DO NOTHING
            """
        ),
        {
            "source_type": "BUREAU_SERASA_PJ",
            "label": "Serasa Experian — Business Information Report (PJ)",
            "category": "bureau_pj",
            "owner_org": "Serasa Experian",
            # A confirmar com o contrato A7. Distribuidores tipicamente tem rate
            # limit por hora, nao por minuto — deixa nulo ate ter numero oficial.
            "rate_limit_per_minute": None,
            # Custo varia por contrato e por reportType. Cobranca real cai no
            # decision_log com valor real do faturamento Serasa.
            "unit_cost_brl": None,
            "inputs": json.dumps(SERASA_PJ_INPUTS),
            "outputs": json.dumps(SERASA_PJ_OUTPUTS),
            "description": SERASA_PJ_DESCRIPTION,
        },
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM source_catalog WHERE source_type = 'BUREAU_SERASA_PJ'"
        )
    )
