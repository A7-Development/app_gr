"""Unit tests dos mappers do sync de liquidacoes declaradas (F3).

Fronteira testada = mapper puro (dict como o SELECT devolve -> row do
silver), padrao test_entidades_sync. Sem DB, sem conexao MSSQL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from app.core.enums import SourceType
from app.modules.integracoes.adapters.erp.bitfin.liquidacao_sync import (
    CANAL_BAIXA_ADMINISTRATIVA,
    CANAL_BAIXA_MANUAL,
    CANAL_BANCARIA,
    CANAL_PERDA,
    CANAL_RECOMPRA,
    EVIDENCIA_BAIXA_CONFIRMADA,
    EVIDENCIA_RECOMPRA_EFETIVADA,
    EVIDENCIA_SEM_OCORRENCIA,
    EVIDENCIA_SEM_REGISTRO,
    EVIDENCIA_TRANSFERENCIA,
    _map_baixa_admin,
    _map_baixa_manual,
    _map_bancaria,
    _map_recompra,
    _map_transferencia,
)
from app.modules.integracoes.adapters.erp.bitfin.version import ADAPTER_VERSION

TENANT = uuid4()
_DATA = datetime(2026, 6, 25, 9, 6, tzinfo=UTC)


def _base_titulo(**extra) -> dict:
    return {
        "titulo_id": 4242,
        "operacao_id": 100,
        "unidade_administrativa_id": 7,
        "situacao_titulo": 1,
        "valor_titulo": Decimal("1000.00"),
        "data_evento": _DATA,
        **extra,
    }


def test_map_bancaria_liquidacao_normal_com_praca():
    row = _base_titulo(
        meio_codigo="36",
        data_credito=_DATA,
        valor_pago=Decimal("980.50"),
        juros=Decimal("12.00"),
        agencia_id=555,
        local_pagamento="AG BRADESCO 1417",
        pago_fora_praca_sacado=True,
        pago_na_praca_cliente=True,
        pago_na_agencia_cliente=False,
        pago_na_agencia_sacado=False,
        pago_em_banco_digital=False,
        registrado=True,
        carteira_bancaria_id=3,
    )
    out = _map_bancaria(row, TENANT)
    assert out["canal"] == CANAL_BANCARIA
    assert out["evidencia"] is None
    assert out["meio_codigo"] == "36"
    assert out["source_id"] == "liq:4242"
    assert out["valor_pago"] == Decimal("980.50")
    assert out["pago_fora_praca_sacado"] is True
    assert out["agencia_id"] == 555
    # Proveniencia completa (Auditable)
    assert out["tenant_id"] == TENANT
    assert out["source_type"] == SourceType.ERP_BITFIN
    assert out["ingested_by_version"] == ADAPTER_VERSION
    assert out["hash_origem"]


def test_map_baixa_manual_evidencias():
    # Registrado + ocorrencia 05 = baixa confirmada (padrao MFL, FORTE)
    forte = _map_baixa_manual(
        _base_titulo(registrado=True, teve_baixa_confirmada=1), TENANT
    )
    assert forte["canal"] == CANAL_BAIXA_MANUAL
    assert forte["evidencia"] == EVIDENCIA_BAIXA_CONFIRMADA
    assert forte["source_id"] == "man:4242"

    # Nunca registrado = deposito direto plausivel
    sem_reg = _map_baixa_manual(
        _base_titulo(registrado=None, teve_baixa_confirmada=None), TENANT
    )
    assert sem_reg["evidencia"] == EVIDENCIA_SEM_REGISTRO

    # Registrado sem ocorrencia alguma = fraco
    fraco = _map_baixa_manual(
        _base_titulo(registrado=True, teve_baixa_confirmada=0), TENANT
    )
    assert fraco["evidencia"] == EVIDENCIA_SEM_OCORRENCIA


def test_map_recompra_business_key_inclui_recompra_id():
    """Titulo pode aparecer em MULTIPLAS recompras (94 casos no recon) —
    a business key precisa distinguir os eventos."""
    row = _base_titulo(
        situacao_titulo=5,
        recompra_id=77,
        valor_pago=Decimal("1100.00"),
        juros=Decimal("100.00"),
    )
    out = _map_recompra(row, TENANT)
    assert out["canal"] == CANAL_RECOMPRA
    assert out["evidencia"] == EVIDENCIA_RECOMPRA_EFETIVADA
    assert out["source_id"] == "rec:77:4242"
    assert out["recompra_id"] == 77

    out2 = _map_recompra({**row, "recompra_id": 78}, TENANT)
    assert out2["source_id"] != out["source_id"]


def test_map_transferencia_recompra():
    """Caminho 2 da recompra — o que a view de elegibilidade do Bitfin perde."""
    row = _base_titulo(situacao_titulo=3, operacao_destino_id=900)
    out = _map_transferencia(row, TENANT)
    assert out["canal"] == CANAL_RECOMPRA
    assert out["evidencia"] == EVIDENCIA_TRANSFERENCIA
    assert out["source_id"] == "tra:4242:900"


def test_map_baixa_admin_e_perda():
    baixado = _map_baixa_admin(
        _base_titulo(situacao_titulo=3, valor_pago=Decimal("0")), TENANT
    )
    assert baixado["canal"] == CANAL_BAIXA_ADMINISTRATIVA
    assert baixado["source_id"] == "bxa:4242"

    perda = _map_baixa_admin(
        _base_titulo(situacao_titulo=9, valor_pago=Decimal("0")), TENANT
    )
    assert perda["canal"] == CANAL_PERDA
    assert perda["source_id"] == "per:4242"
