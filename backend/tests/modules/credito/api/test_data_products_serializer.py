"""_serialize_data_product — contrato WHITE-LABEL (sem vendor).

Garante que o serializer tenant-facing nunca deixa escapar provider_slug,
provider_api, provider_dataset_code, provider_query_name, preco ou markup.
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.credito.api.workflow import (
    DataProductRead,
    _serialize_data_product,
)
from app.shared.data_providers.models.dataset import DataProviderDataset


def _dataset(**over) -> DataProviderDataset:
    defaults = {
        "public_code": "CAD-PJ",
        "display_name_pt_br": "Consulta Cadastral PJ",
        "categoria_ui": "empresas",
        "description_pt_br": "Situacao, CNAEs, capital, fundacao.",
        # vendor-layer (NAO pode vazar):
        "provider_dataset_code": "BASIC_DATA_V1",
        "provider_api": "Companies",
        "provider_query_name": "basic_data",
        "current_cost_brl": Decimal("0.02"),
        "markup_pct": Decimal("50.0"),
        "enabled_for_sale": True,
    }
    defaults.update(over)
    return DataProviderDataset(**defaults)


def test_serializer_only_exposes_neutral_fields() -> None:
    out = _serialize_data_product(_dataset())
    assert isinstance(out, DataProductRead)

    payload = out.model_dump()
    # so os 4 campos neutros
    assert set(payload.keys()) == {
        "public_code",
        "display_name",
        "categoria_ui",
        "description",
    }
    assert payload["public_code"] == "CAD-PJ"
    assert payload["display_name"] == "Consulta Cadastral PJ"

    # nenhum valor de vendor aparece serializado
    blob = str(payload)
    for leaked in ("BASIC_DATA_V1", "Companies", "basic_data", "0.02", "50.0", "bigdatacorp"):
        assert leaked not in blob


def test_serializer_falls_back_to_public_code_when_no_display_name() -> None:
    out = _serialize_data_product(_dataset(display_name_pt_br=None))
    assert out.display_name == "CAD-PJ"
