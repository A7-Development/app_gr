"""Testes do mapper bronze -> silver (wh_nfe_situacao + wh_nfe_evento).

Payloads modelados sobre os retornos REAIS da bancada 2026-07-10:
cancelamento com retCStat 135 e 155, eventos desordenados, manifestacao
posterior ao cancelamento.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
import sqlalchemy as sa

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.data.serpro.client import SerproNfeResponse
from app.modules.integracoes.adapters.data.serpro.etl import persistir_snapshot
from app.modules.integracoes.adapters.data.serpro.mappers.nfe_estado import (
    mapear_snapshot,
)
from app.shared.identity.tenant import Tenant
from app.warehouse.nfe_estado import NfeEvento, NfeSituacao
from app.warehouse.serpro_raw_nfe import SerproRawNfe

CHAVE = "35260621391351000140550010000039021326121852"


def _evento(
    tp: int,
    dh: str,
    *,
    ret_cstat: int = 135,
    desc: str = "",
    xjust: str | None = None,
    nseq: int = 1,
) -> dict[str, Any]:
    return {
        "evento": {
            "infEvento": {
                "cOrgao": "35",
                "tpAmb": 1,
                "CNPJ": 21391351000140,
                "chNFe": CHAVE,
                "dhEvento": dh,
                "tpEvento": tp,
                "nSeqEvento": str(nseq),
                "verEvento": 1,
                "detEvento": {
                    "descEvento": desc,
                    "xJust": xjust,
                    "_versao": "1.00",
                },
                "Id": f"ID{tp}{CHAVE}0{nseq}",
            }
        },
        "retEvento": {
            "infEvento": {
                "verAplic": "SP_EVENTOS_PL_100",
                "cOrgao": "35",
                "cStat": str(ret_cstat),
                "xMotivo": "Evento registrado e vinculado a NF-e",
                "chNFe": CHAVE,
                "tpEvento": str(tp),
                "xEvento": desc,
                "nSeqEvento": str(nseq),
                "CPFDest": "47489148820",
                "dhRegEvento": dh,
                "nProt": "135220002175443",
            }
        },
    }


def _payload(eventos: list[dict] | None, cstat: int = 100) -> dict[str, Any]:
    return {
        "nfeProc": {
            "versao": 4.0,
            "protNFe": {
                "infProt": {
                    "tpAmb": 1,
                    "verAplic": "SP_NFE_PL009_V4",
                    "chNFe": CHAVE,
                    "dhRecbto": "2026-06-20T10:00:00-03:00",
                    "nProt": 135262677425143,
                    "digVal": "abc=",
                    "cStat": cstat,
                    "xMotivo": "Autorizado o uso da NF-e",
                }
            },
        },
        "procEventoNFe": eventos,
    }


async def _persistir_e_mapear(tenant_id, payload: dict) -> None:
    text = json.dumps(payload)
    resp = SerproNfeResponse(
        chave=CHAVE,
        raw=json.loads(text),
        text=text,
        http_status=200,
        latency_ms=1.0,
        request_tag="test",
    )
    async with AsyncSessionLocal() as db:
        result = await persistir_snapshot(
            db, tenant_id=tenant_id, response=resp, trigger="bancada"
        )
        raw = (
            await db.execute(
                sa.select(SerproRawNfe).where(SerproRawNfe.id == result.raw_id)
            )
        ).scalar_one()
        await mapear_snapshot(db, raw)
        await db.commit()


async def _situacao(tenant_id) -> NfeSituacao:
    async with AsyncSessionLocal() as db:
        return (
            await db.execute(
                sa.select(NfeSituacao).where(NfeSituacao.tenant_id == tenant_id)
            )
        ).scalar_one()


@pytest.mark.asyncio
async def test_cancelada_fora_prazo_com_eventos_desordenados(
    tenant_a: Tenant,
) -> None:
    """Caso real cancelada-1: cancelamento 155 + ciencia + nao-realizada,

    array FORA de ordem cronologica."""
    eventos = [
        _evento(110111, "2026-07-03T09:43:06-03:00", ret_cstat=155,
                desc="Cancelamento", xjust="dados incorretos"),
        _evento(210210, "2026-07-01T08:14:06-03:00", desc="Ciencia da Operacao"),
        _evento(210240, "2026-07-04T00:39:54-03:00",
                desc="Operacao nao Realizada"),
    ]
    await _persistir_e_mapear(tenant_a.id, _payload(eventos))

    sit = await _situacao(tenant_a.id)
    # protNFe.cStat=100, mas o EVENTO manda: cancelada fora de prazo.
    assert sit.prot_c_stat == 100
    assert sit.situacao == "cancelada_fora_prazo"
    assert sit.cancelada is True
    assert sit.dh_cancelamento is not None
    # Manifestacao mais recente por dh_evento = nao-realizada (04/07),
    # mesmo listada por ULTIMO no array.
    assert sit.manifestacao == "operacao_nao_realizada"
    assert sit.qtd_eventos == 3

    async with AsyncSessionLocal() as db:
        eventos_rows = (
            await db.execute(
                sa.select(NfeEvento)
                .where(NfeEvento.tenant_id == tenant_a.id)
                .order_by(NfeEvento.dh_evento)
            )
        ).scalars().all()
    assert [e.tp_evento for e in eventos_rows] == [210210, 110111, 210240]
    cancel = eventos_rows[1]
    assert cancel.ret_c_stat == 155
    assert cancel.x_just == "dados incorretos"
    # Perda zero: subarvores verbatim presentes.
    assert cancel.evento_json["infEvento"]["detEvento"]["_versao"] == "1.00"
    assert cancel.ret_evento_json["infEvento"]["CPFDest"] == "47489148820"


@pytest.mark.asyncio
async def test_autorizada_sem_eventos(tenant_a: Tenant) -> None:
    # procEventoNFe vem null (nao lista vazia) na API real.
    await _persistir_e_mapear(tenant_a.id, _payload(None))
    sit = await _situacao(tenant_a.id)
    assert sit.situacao == "autorizada"
    assert sit.cancelada is False
    assert sit.manifestacao is None
    assert sit.qtd_eventos == 0
    assert sit.prot_json["verAplic"] == "SP_NFE_PL009_V4"


@pytest.mark.asyncio
async def test_snapshot_novo_atualiza_situacao_sem_duplicar_eventos(
    tenant_a: Tenant,
) -> None:
    """Nota autorizada com ciencia -> snapshot novo traz cancelamento."""
    ciencia = _evento(210210, "2026-07-01T08:14:06-03:00",
                      desc="Ciencia da Operacao")
    await _persistir_e_mapear(tenant_a.id, _payload([ciencia]))

    sit1 = await _situacao(tenant_a.id)
    assert sit1.situacao == "autorizada"
    assert sit1.manifestacao == "ciencia"

    cancelamento = _evento(110111, "2026-07-03T15:00:19-03:00",
                           desc="Cancelamento", xjust="NF COM PRECO ERRADO")
    await _persistir_e_mapear(tenant_a.id, _payload([ciencia, cancelamento]))

    sit2 = await _situacao(tenant_a.id)
    assert sit2.situacao == "cancelada"
    assert sit2.cancelada is True
    assert sit2.qtd_eventos == 2
    assert sit2.id == sit1.id  # upsert da MESMA linha, nao linha nova

    async with AsyncSessionLocal() as db:
        count = (
            await db.execute(
                sa.select(sa.func.count()).select_from(NfeEvento).where(
                    NfeEvento.tenant_id == tenant_a.id
                )
            )
        ).scalar_one()
    assert count == 2  # ciencia NAO duplicou no segundo mapeamento


@pytest.mark.asyncio
async def test_cstat_desconhecido_nao_falha_silencioso(tenant_a: Tenant) -> None:
    await _persistir_e_mapear(tenant_a.id, _payload(None, cstat=999))
    sit = await _situacao(tenant_a.id)
    assert sit.situacao == "desconhecida"
    assert sit.prot_c_stat == 999


@pytest.mark.asyncio
async def test_isolamento_tenant_silver(tenant_a: Tenant, tenant_b: Tenant) -> None:
    """§10.4: silver de B nao ve dado de A."""
    await _persistir_e_mapear(tenant_a.id, _payload(None))
    async with AsyncSessionLocal() as db:
        rows_b = (
            await db.execute(
                sa.select(NfeSituacao).where(NfeSituacao.tenant_id == tenant_b.id)
            )
        ).scalars().all()
    assert rows_b == []
