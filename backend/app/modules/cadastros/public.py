"""Public contract do modulo Cadastros (CLAUDE.md secao 11.3).

Outros modulos importam DAQUI -- nunca de internals (`models/`, `services/`).
A `UnidadeAdministrativa` e o conceito que outros modulos referenciam quando
precisam de "qual UA um dado pertence" (BI filtra por UA, integracoes
referenciam UA, controladoria amarra DRE a UA).
"""

from app.modules.cadastros.models.unidade_administrativa import (
    TipoUnidadeAdministrativa,
    UnidadeAdministrativa,
)

__all__ = ["TipoUnidadeAdministrativa", "UnidadeAdministrativa"]
