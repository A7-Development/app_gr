"""ORM models for the data-providers capability.

Importing this package wires the models to SQLAlchemy's metadata. Alembic
autogenerate inspects them via `app/core/database.py::Base`.
"""

from app.shared.data_providers.models.catalog_sync_run import (
    DataProviderCatalogSyncRun,
)
from app.shared.data_providers.models.contract import (
    DatasetContract,
    DatasetContractActive,
)
from app.shared.data_providers.models.credential import DataProviderCredential
from app.shared.data_providers.models.dataset import DataProviderDataset
from app.shared.data_providers.models.field import DatasetField
from app.shared.data_providers.models.price_history import (
    DataProviderDatasetPriceHistory,
)
from app.shared.data_providers.models.provider import DataProvider

__all__ = [
    "DataProvider",
    "DataProviderCatalogSyncRun",
    "DataProviderCredential",
    "DataProviderDataset",
    "DataProviderDatasetPriceHistory",
    "DatasetContract",
    "DatasetContractActive",
    "DatasetField",
]
