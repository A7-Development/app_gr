"""cosif: contrapartida espelhada SR/MEZ/SUB para grupo 3 (compensacao)

Fix do bug reportado em 2026-05-12: contrapartidas positivas espelhadas
(SRP/MEZAN qtde>0 em wh_posicao_renda_fixa) estavam caindo no bucket
"Pendente" da arvore COSIF porque a regra `rf.contrapartida_compensacao`
retornava `cosif=None` mesmo casando.

Inconsistencia visual: _build_cobertura contava como "rule" (100%
cobertura), mas _classify_and_aggregate agregava em analytic[None]
(bucket Pendente da UI). Soma das positivas = soma das emitidas em modulo
(14.492.188,06 em REALINVEST 08/05/2026) — espelho 1:1.

Fix:
  1. Cria sub-arvore grupo 3 (compensacao) ate a conta folha
     `3.9.9.30.50.001 COTAS EMITIDAS - CONTRAPARTIDA INTERNA`.
  2. Atualiza `rf.contrapartida_compensacao` para apontar pra essa
     folha em vez de NULL.

Resultado:
  - Modo default da UI: bucket Pendente some (cobertura real 100%).
  - Auditoria avancada ON: aparece grupo 3 com saldo da contrapartida
    espelhando o saldo das cotas emitidas em 6.1.1.70.30.001.

Revision ID: 7f1a9c4e2d83
Revises: ba7032c76c17
Create Date: 2026-05-12 12:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "7f1a9c4e2d83"
down_revision: str | None = "ba7032c76c17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Sub-arvore COSIF grupo 3 — controle de custodia / compensacao do Ativo.
# Plano oficial BACEN tem o grupo 3 reservado para isso. Mantemos seed
# minimo: apenas a cadeia ate `3.9.9.30.50.001`. Outras contas de
# compensacao serao adicionadas quando aparecerem em fundos reais.
CATALOG_ADD: list[tuple[str, str, str, str | None, int, int]] = [
    # (codigo, nome, natureza, parent_codigo, nivel, grupo)
    ("3",                "COMPENSACAO - ATIVO",                            "D", None,             1, 3),
    ("3.9",              "COMPENSACAO - OUTROS CONTROLES",                 "D", "3",              2, 3),
    ("3.9.9",            "COMPENSACAO - CONTROLES DIVERSOS",               "D", "3.9",            3, 3),
    ("3.9.9.30",         "COTAS EMITIDAS - CONTRAPARTIDA",                 "D", "3.9.9",          4, 3),
    ("3.9.9.30.50.001",  "COTAS EMITIDAS - CONTRAPARTIDA INTERNA",         "D", "3.9.9.30",       6, 3),
]


def upgrade() -> None:
    # 1) Insere a sub-arvore grupo 3.
    catalog_table = sa.table(
        "cosif_catalog",
        sa.column("codigo", sa.String),
        sa.column("nome", sa.String),
        sa.column("natureza", sa.String),
        sa.column("parent_codigo", sa.String),
        sa.column("nivel", sa.SmallInteger),
        sa.column("grupo", sa.SmallInteger),
    )
    op.bulk_insert(catalog_table, [
        {
            "codigo": c, "nome": n, "natureza": nat,
            "parent_codigo": p, "nivel": niv, "grupo": g,
        }
        for (c, n, nat, p, niv, g) in CATALOG_ADD
    ])

    # 2) Aponta a regra rf.contrapartida_compensacao para a folha 3.9.9.30.50.001.
    op.execute(
        """
        UPDATE cosif_rule
           SET cosif_codigo = '3.9.9.30.50.001',
               confidence   = 'alta'
         WHERE rule_id_humano = 'rf.contrapartida_compensacao'
        """
    )


def downgrade() -> None:
    # Volta a regra para NULL (estado pre-fix).
    op.execute(
        """
        UPDATE cosif_rule
           SET cosif_codigo = NULL,
               confidence   = 'media'
         WHERE rule_id_humano = 'rf.contrapartida_compensacao'
        """
    )
    # Remove a sub-arvore (ordem: filhos antes do pai por causa do FK).
    op.execute(
        """
        DELETE FROM cosif_catalog
         WHERE codigo IN (
           '3.9.9.30.50.001',
           '3.9.9.30',
           '3.9.9',
           '3.9',
           '3'
         )
        """
    )
