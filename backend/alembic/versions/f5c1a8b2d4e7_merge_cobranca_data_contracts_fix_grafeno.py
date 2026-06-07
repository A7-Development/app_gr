"""merge heads (cobranca + data_contracts) + fix orfa COBRANCA_GRAFENO no catalogo

Unifica os dois heads divergentes que vinham sendo geridos a mao:

    b8d2f4a6c1e3  (cobranca: wh_cobranca_sync_run)        -> aplicado via alembic
    f1a2c3d4e5b6  (data contracts fase 1 + esteira)        -> aplicado via SQL na VM

A divergencia nasceu no branchpoint 39f86beb8fd0 e fez `alembic upgrade head`
falhar com "Multiple head revisions" -> nenhuma migration nova aplicava no
deploy. Esta migration de merge re-unifica a arvore.

Alem do merge, corrige um efeito colateral do rename do enum `SourceType`:
o valor `COBRANCA_GRAFENO` foi dividido em `COBRANCA_BMP` (cod 274) e
`COBRANCA_VORTX` (cod 310). Os dados de `wh_boleto` foram remapeados pra
VORTX, mas a linha semeada em `source_catalog` pela migration
b7e1c3a9f2d4 (concilia_boletos) ficou como 'COBRANCA_GRAFENO' — valor que o
enum atual nao conhece. Como a coluna guarda o NOME do membro (sem
values_callable), qualquer `select(SourceCatalog)` via ORM estourava
`LookupError: 'COBRANCA_GRAFENO' is not among the defined enum values`,
derrubando a pagina Integracoes > Fontes e o badge de saude de sync (500
mascarado como CORS, pois o ServerErrorMiddleware fica fora do CORSMiddleware).

O fix abaixo e idempotente: num rebuild de DB do zero, b7e1c3a9f2d4 re-semeia
'COBRANCA_GRAFENO' e esta migration o re-alinha pra 'COBRANCA_VORTX'. Em prod
(onde a linha ja foi corrigida a mao) e no-op.

Revision ID: f5c1a8b2d4e7
Revises: b8d2f4a6c1e3, f1a2c3d4e5b6
Create Date: 2026-06-06
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f5c1a8b2d4e7"
down_revision: tuple[str, str] = ("b8d2f4a6c1e3", "f1a2c3d4e5b6")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    # Renomeia a orfa grafeno -> vortx quando ainda nao houver linha vortx.
    bind.execute(
        sa.text(
            """
            UPDATE source_catalog
            SET source_type = 'COBRANCA_VORTX',
                label = 'Vortx — Cobranca (CNAB)',
                owner_org = 'Vortx',
                description = 'Boletos de cobranca via arquivo de retorno/remessa CNAB (codigo 310, header CNAB).',
                updated_at = now()
            WHERE source_type = 'COBRANCA_GRAFENO'
              AND NOT EXISTS (
                  SELECT 1 FROM source_catalog WHERE source_type = 'COBRANCA_VORTX'
              )
            """
        )
    )
    # Se vortx ja existir (fix manual ja aplicado em prod) e a orfa ainda
    # estiver la, remove-a — evita deixar valor invalido pro enum.
    bind.execute(
        sa.text("DELETE FROM source_catalog WHERE source_type = 'COBRANCA_GRAFENO'")
    )


def downgrade() -> None:
    # Merge migration: o downgrade re-separa os heads automaticamente ao
    # remover esta revisao. A correcao de catalogo nao e revertida de
    # proposito — 'COBRANCA_GRAFENO' nao e um valor valido do enum atual e
    # reintroduzi-lo voltaria a quebrar `select(SourceCatalog)`.
    pass
