"""cosif: regra rf.nota_comercial passa a reconhecer "VCNC" (nota comercial vencida)

Fix reportado em 2026-05-27 (analise da variacao da Cota Sub REALINVEST 25/05):
o driver "Op Estruturadas" mostrava -40.035,02 enquanto a renda fixa total
so mexeu +4.609 — o MEC publicava dPL Sub +37.242 mas o modelo somava ~0
(residuo +39.219).

Causa raiz: a regra `rf.nota_comercial` so casava `nome_do_papel` contendo
"NCPX" ou "NOTA". Notas comerciais VENCIDAS entram em
`wh_posicao_renda_fixa` com `nome_do_papel = "VCNC"` (Vencido Nota Comercial),
que nao casa nenhum dos dois termos. Resultado: `classify()` devolvia
`cosif=None` (pendente) e o papel caia fora da particao patrimonial — visivel
no MEC, invisivel no somatorio dos drivers, vazando pro residuo.

Confirmado pelo gestor: VCNC e nota comercial vencida — mesmo COSIF
(1.3.1.10.16.001 NOTA COMERCIAL), mesmo bucket "Op Estruturadas".

Blast radius: VCNC aparece em 93 dias / 16 codigos de papel desde 2025-04-28
em REALINVEST. Como `classify()` recomputa ao vivo contra as regras ativas
HOJE (sem snapshot historico de classificacao — ver load_rules_cache, que
filtra por `valid_from <= CURRENT_DATE`), esta correcao e RETROATIVA: todos
os dias historicos passam a classificar VCNC como Op Estruturadas na proxima
renderizacao da pagina.

Fix: adiciona um terceiro termo `contains "VCNC"` ao predicate `any[]` da
regra `rf.nota_comercial` (UPDATE in-place, mesmo padrao de
7f1a9c4e2d83). rule_id_humano e cosif_codigo permanecem estaveis.

Revision ID: e7a1c3f9b4d6
Revises: a9f4c2e7b1d8
Create Date: 2026-05-27 00:00:00.000000

"""
from collections.abc import Sequence

from alembic import op


revision: str = "e7a1c3f9b4d6"
down_revision: str | None = "a9f4c2e7b1d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Predicate com VCNC incluido (estado alvo).
_PREDICATE_COM_VCNC = (
    '{"any": ['
    '{"op": "contains", "field": "nome_do_papel", "value": "NCPX"}, '
    '{"op": "contains", "field": "nome_do_papel", "value": "NOTA"}, '
    '{"op": "contains", "field": "nome_do_papel", "value": "VCNC"}'
    ']}'
)

# Predicate original (estado pre-fix) — para o downgrade.
_PREDICATE_SEM_VCNC = (
    '{"any": ['
    '{"op": "contains", "field": "nome_do_papel", "value": "NCPX"}, '
    '{"op": "contains", "field": "nome_do_papel", "value": "NOTA"}'
    ']}'
)


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE cosif_rule
           SET predicate_jsonb = '{_PREDICATE_COM_VCNC}'::jsonb
         WHERE rule_id_humano = 'rf.nota_comercial'
           AND silver_origin = 'wh_posicao_renda_fixa'
        """
    )


def downgrade() -> None:
    op.execute(
        f"""
        UPDATE cosif_rule
           SET predicate_jsonb = '{_PREDICATE_SEM_VCNC}'::jsonb
         WHERE rule_id_humano = 'rf.nota_comercial'
           AND silver_origin = 'wh_posicao_renda_fixa'
        """
    )
