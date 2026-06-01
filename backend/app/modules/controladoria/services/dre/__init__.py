"""Service de classificacao DRE -- cascata override -> regra global -> None.

Uso:
    classifier = await load_dre_classifier(db, tenant_id)
    for bronze_row in payload:
        res = classifier.classify(bronze_row["fonte"], bronze_row["categoria"])
        if res is None or not res.ativo:
            continue  # row nao classificada / categoria EXCLUIDO
        # res.grupo_dre, res.subgrupo, res.ordem_grupo

Lookup canonico de `wh_dre_classification_rule` (CLAUDE.md secao 14.3).
Carregamento bulk: as 77 regras globais + overrides do tenant cabem em
memoria; 0 ida ao DB durante o mapping.
"""

from app.modules.controladoria.services.dre.classifier import (
    DreClassification,
    DreClassifier,
    load_dre_classifier,
)
from app.modules.controladoria.services.dre.leitura import (
    compute_breakdown,
    compute_drill_fornecedores,
    compute_pivot,
    compute_receita_por_natureza,
    listar_competencias,
)

__all__ = [
    "DreClassification",
    "DreClassifier",
    "compute_breakdown",
    "compute_drill_fornecedores",
    "compute_pivot",
    "compute_receita_por_natureza",
    "listar_competencias",
    "load_dre_classifier",
]
