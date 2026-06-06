"""Unit tests for ResolvedContract projections (pure, no DB).

Run: pytest backend/tests/shared/data_providers/test_contract_resolver.py --noconftest
"""

from __future__ import annotations

from app.shared.data_providers.contract_resolver import ResolvedContract
from app.shared.data_providers.models.contract import DatasetContract
from app.shared.data_providers.models.field import DatasetField


def _field(path, **kw):
    f = DatasetField(field_path=path)
    f.on_screen = kw.get("on_screen", True)
    f.screen_order = kw.get("screen_order")
    f.to_tool = kw.get("to_tool", False)
    f.to_agent = kw.get("to_agent", False)
    f.to_silver = kw.get("to_silver", False)
    f.to_check = kw.get("to_check", False)
    return f


def _resolved():
    fields = [
        _field("B", on_screen=True, screen_order=2, to_tool=True, to_agent=True),
        _field("A", on_screen=True, screen_order=1, to_tool=True, to_silver=True, to_check=True),
        _field("C", on_screen=False, to_tool=False),
        _field("D", on_screen=True, screen_order=None, to_agent=True),
    ]
    return ResolvedContract(contract=DatasetContract(), fields=fields)


def test_for_screen_orders_and_filters():
    r = _resolved()
    paths = [f.field_path for f in r.for_screen()]
    # C oculto; A(1), B(2), D(sem ordem -> fim)
    assert paths == ["A", "B", "D"]


def test_for_tool():
    assert {f.field_path for f in _resolved().for_tool()} == {"A", "B"}


def test_for_agent():
    assert {f.field_path for f in _resolved().for_agent()} == {"B", "D"}


def test_for_silver_and_check():
    r = _resolved()
    assert {f.field_path for f in r.for_silver()} == {"A"}
    assert {f.field_path for f in r.for_check()} == {"A"}


def test_field_paths():
    assert _resolved().field_paths() == {"A", "B", "C", "D"}
