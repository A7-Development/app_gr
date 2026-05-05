"""Enums for the data-providers capability.

`DataProvider` lista os vendors globais que a A7 revende. Note que valores aqui
COINCIDEM intencionalmente com `BureauSource` em `app/core/enums.py` (que e o
vocabulario do dominio credito) — ambos referenciam o mesmo vendor, mas vivem
em camadas diferentes: BureauSource e identidade no workflow do credito;
DataProvider e a entidade no catalogo global de servicos vendidos.

Adicionar valor aqui = nova row em `provedor_dados` (seed via migration) +
adapter HTTP em `app/modules/integracoes/adapters/data/<vendor>/`.
"""

from __future__ import annotations

import enum


class DataProviderSlug(enum.StrEnum):
    """Vendors de dados externos providos centralmente pela A7.

    Renomeado de `DataProvider` para nao colidir com a classe SQLAlchemy
    `DataProvider` em `models/provider.py`. Este e o slug textual; a classe
    e o registro no DB.
    """

    BIGDATACORP = "bigdatacorp"
    INFOSIMPLES = "infosimples"


class CatalogSyncStatus(enum.StrEnum):
    """Status terminal de uma execucao de sync de catalogo."""

    OK = "ok"
    ERROR = "error"
    IN_PROGRESS = "in_progress"


class PriceChangeKind(enum.StrEnum):
    """Tipo de mudanca detectada em uma faixa de preco do dataset.

    `INITIAL` registra a primeira observacao do preco (quando o dataset e
    descoberto pelo sync). `DELTA` registra cada mudanca subsequente —
    `previous_price_brl` aponta para a faixa imediatamente anterior. `MANUAL`
    registra override do mantenedor (ainda nao implementado na Fase 1, mas
    reservado).
    """

    INITIAL = "initial"
    DELTA = "delta"
    MANUAL = "manual"
