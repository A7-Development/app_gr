"""Tests do classifier DRE -- lookup + cascata override por tenant."""

from __future__ import annotations

from app.modules.controladoria.services.dre.classifier import (
    DreClassification,
    DreClassifier,
)


def _global(grupo: str, sub: str, ordem: int, ativo: bool = True) -> DreClassification:
    return DreClassification(
        grupo_dre=grupo,
        subgrupo=sub,
        ordem_grupo=ordem,
        ativo=ativo,
        rule_version=1,
        source="global",
    )


def _override(grupo: str, sub: str, ordem: int, ativo: bool = True) -> DreClassification:
    return DreClassification(
        grupo_dre=grupo,
        subgrupo=sub,
        ordem_grupo=ordem,
        ativo=ativo,
        rule_version=1,
        source="tenant_override",
    )


# ─── Hit / miss ──────────────────────────────────────────────────────────────


def test_hit_returns_classification() -> None:
    c = DreClassifier(
        {("DRE_OPERACIONAL", "Operação"): _global("RECEITA_OPERACIONAL", "Operação", 1)}
    )
    res = c.classify("DRE_OPERACIONAL", "Operação")
    assert res is not None
    assert res.grupo_dre == "RECEITA_OPERACIONAL"
    assert res.subgrupo == "Operação"
    assert res.ordem_grupo == 1


def test_miss_returns_none() -> None:
    c = DreClassifier({})
    assert c.classify("DRE_OPERACIONAL", "Operação") is None


def test_miss_on_different_fonte() -> None:
    c = DreClassifier(
        {("DRE_OPERACIONAL", "Operação"): _global("RECEITA_OPERACIONAL", "Operação", 1)}
    )
    assert c.classify("CONTAS_A_PAGAR", "Operação") is None


def test_miss_on_different_categoria_exact() -> None:
    """Match e case-sensitive e exact-string -- nao faz prefixo nem normalize."""
    c = DreClassifier(
        {("CONTAS_A_PAGAR", "Salário"): _global("DESPESA_ADMINISTRATIVA", "Pessoal", 8)}
    )
    assert c.classify("CONTAS_A_PAGAR", "salário") is None
    assert c.classify("CONTAS_A_PAGAR", "Salario") is None
    assert c.classify("CONTAS_A_PAGAR", "Salário ") is None


# ─── Categoria inativa (EXCLUIDO) ────────────────────────────────────────────


def test_inactive_category_is_returned_caller_handles() -> None:
    """Categoria EXCLUIDO retorna o resultado com ativo=False. Caller (mapper)
    e quem decide descartar -- classifier so reporta o que esta na regra."""
    c = DreClassifier(
        {
            ("CONTAS_A_PAGAR", "Investimento"): _global(
                "EXCLUIDO", "Excluido", 0, ativo=False
            )
        }
    )
    res = c.classify("CONTAS_A_PAGAR", "Investimento")
    assert res is not None
    assert res.ativo is False
    assert res.grupo_dre == "EXCLUIDO"


# ─── Cascata: override vence sobre global no dict de regras ──────────────────
# A funcao load_dre_classifier garante que o dict ja chegue com cascata
# aplicada (overrides sobrescrevem globais por (fonte, categoria)). Aqui
# validamos o efeito: se a regra estiver presente como override, source
# refletira isso.


def test_classifier_reports_source_global() -> None:
    c = DreClassifier(
        {("DRE_OPERACIONAL", "Operação"): _global("RECEITA_OPERACIONAL", "Operação", 1)}
    )
    res = c.classify("DRE_OPERACIONAL", "Operação")
    assert res is not None
    assert res.source == "global"


def test_classifier_reports_source_tenant_override() -> None:
    c = DreClassifier(
        {("DRE_OPERACIONAL", "Operação"): _override("RECEITA_CUSTOM", "Custom", 99)}
    )
    res = c.classify("DRE_OPERACIONAL", "Operação")
    assert res is not None
    assert res.source == "tenant_override"
    assert res.grupo_dre == "RECEITA_CUSTOM"


# ─── rule_count ──────────────────────────────────────────────────────────────


def test_rule_count_reports_loaded_size() -> None:
    c = DreClassifier(
        {
            ("DRE_OPERACIONAL", "Operação"): _global("RECEITA_OPERACIONAL", "Operação", 1),
            ("DRE_OPERACIONAL", "PDD"): _global("PROVISAO_PDD", "PDD", 6),
        }
    )
    assert c.rule_count == 2
