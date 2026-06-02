"""seed prompts de extracao por tipo de documento (extract.<doc_type>)

Hoje so existe extract.document (generico). Estes prompts pinam o que extrair
de cada tipo (DRE, balanco, faturamento, contrato social) no formato
DocumentExtraction {document_type, extracted_fields, confidence, notes}.

Principio (handoff §7): o agente EXTRAI os numeros crus do documento; os
INDICES (margens, liquidez, alavancagem) sao calculados em Python depois
(services/financial.py). Por isso os prompts pedem so valores absolutos.

Revision ID: a7e3c1f9d2b4
Revises: c5e9a1d7b3f0
Create Date: 2026-06-02
"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7e3c1f9d2b4"
down_revision: str | None = "c5e9a1d7b3f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MODEL = "claude-sonnet-4-5"

_COMMON = (
    "Voce e um extrator de documentos financeiros/societarios de uma esteira "
    "de credito FIDC. O documento esta anexado (PDF/imagem). Leia-o e extraia "
    "os dados pedidos.\n\n"
    "REGRAS DURAS:\n"
    "- Extraia APENAS valores que estao no documento. Campo ausente => null. "
    "NUNCA invente ou estime.\n"
    "- NAO calcule indices/margens/razoes — extraia so os valores absolutos "
    "crus (o sistema calcula os indices depois).\n"
    "- Valores monetarios: numero com ponto decimal, sem separador de milhar, "
    "sem simbolo. Ex.: 1234567.00.\n"
    "- Datas no formato YYYY-MM-DD.\n"
    "- `confidence` (0..1): quao legivel/confiavel foi a leitura.\n"
    "- Responda APENAS um objeto JSON dentro de ```json ... ``` no formato:\n"
    '{"document_type":"<tipo>","extracted_fields":{...},"confidence":0.0,'
    '"notes":"observacoes ou null"}'
)

_PROMPTS = [
    {
        "name": "extract.dre",
        "system_text": (
            _COMMON
            + "\n\nTIPO: DRE (Demonstracao do Resultado do Exercicio).\n"
            "extracted_fields deve conter as chaves (null se ausente): "
            "cnpj, period_start, period_end, revenue (receita liquida), cogs "
            "(custo dos produtos/servicos), gross_profit (lucro bruto), "
            "operating_expenses (despesas operacionais), ebitda, "
            "financial_result (resultado financeiro), net_income (lucro liquido)."
        ),
        "description": "Extrai DRE -> extracted_fields (valores crus).",
    },
    {
        "name": "extract.balance_sheet",
        "system_text": (
            _COMMON
            + "\n\nTIPO: Balanco Patrimonial.\n"
            "extracted_fields deve conter as chaves (null se ausente): "
            "cnpj, period_start, period_end, total_assets (ativo total), "
            "current_assets (ativo circulante), total_liabilities (passivo "
            "total exigivel), current_liabilities (passivo circulante), "
            "equity (patrimonio liquido)."
        ),
        "description": "Extrai Balanco -> extracted_fields (valores crus).",
    },
    {
        "name": "extract.revenue_report",
        "system_text": (
            _COMMON
            + "\n\nTIPO: Declaracao/Relatorio de Faturamento.\n"
            "extracted_fields deve conter (null se ausente): cnpj, "
            "period_start, period_end, revenue (faturamento total do periodo), "
            "monthly (lista opcional de {month: 'YYYY-MM', value: numero})."
        ),
        "description": "Extrai faturamento declarado -> extracted_fields.",
    },
    {
        "name": "extract.social_contract",
        "system_text": (
            _COMMON
            + "\n\nTIPO: Contrato Social (e alteracoes).\n"
            "extracted_fields deve conter (null se ausente): cnpj, "
            "razao_social, capital_social (numero), data_constituicao "
            "(YYYY-MM-DD), objeto_social (texto), endereco (texto), "
            "socios (lista de {nome, cpf, participacao_pct})."
        ),
        "description": "Extrai contrato social -> extracted_fields (societario).",
    },
]


def upgrade() -> None:
    bind = op.get_bind()
    for p in _PROMPTS:
        exists = bind.execute(
            sa.text(
                "SELECT 1 FROM ai_prompt WHERE name = :n AND version = 'v1'"
            ).bindparams(n=p["name"])
        ).first()
        if not exists:
            bind.execute(
                sa.text(
                    "INSERT INTO ai_prompt "
                    "(id, name, version, system_text, model, temperature, "
                    " max_tokens, cache_strategy, description) "
                    "VALUES (gen_random_uuid(), :n, 'v1', :st, :m, 0.1, 4096, "
                    " 'after_system', :d)"
                ).bindparams(
                    n=p["name"], st=p["system_text"], m=_MODEL, d=p["description"]
                )
            )
        bind.execute(
            sa.text(
                "INSERT INTO ai_prompt_active (name, active_version) "
                "VALUES (:n, 'v1') ON CONFLICT (name) DO NOTHING"
            ).bindparams(n=p["name"])
        )


def downgrade() -> None:
    names = [p["name"] for p in _PROMPTS]
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM ai_prompt_active WHERE name = ANY(:ns)").bindparams(
            ns=names
        )
    )
    bind.execute(
        sa.text("DELETE FROM ai_prompt WHERE name = ANY(:ns)").bindparams(ns=names)
    )
