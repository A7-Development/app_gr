"""Consumidor fiscal (landing zone -> wh_nfe/wh_cte) -- parser + ETL + §10.

Cobre:
- conversao XML->JSONB canonica (lista p/ tag repetida, @attr, Signature fora);
- parse curado NF-e (duplicatas, autorizacao) e CT-e (elo chaves NF-e);
- ETL: zip explode, roteamento por raiz, procEventoNFe descartado, PDF
  ignorado, raw+silver gravados, consumed_at, idempotencia por chave;
- isolamento: drenar tenant A nao toca pendencia de B.
"""

from __future__ import annotations

import hashlib
import io
import zipfile
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.fiscal import etl as etl_mod
from app.modules.integracoes.adapters.fiscal.etl import sync_fiscal
from app.modules.integracoes.adapters.fiscal.parsers import parse_cte, parse_nfe
from app.modules.integracoes.adapters.fiscal.xml_json import xml_to_dict
from app.modules.integracoes.models.file_landing import FileLanding
from app.shared.identity.tenant import Tenant
from app.shared.storage.local_disk import LocalDiskStorage
from app.warehouse.fiscal_cte import Cte, CteNfe
from app.warehouse.fiscal_nfe import Nfe, NfeDuplicata, NfeRawDocumento

CHAVE_NFE = "35260724744074000109550010000176781181064464"
CHAVE_NFE_2 = "35260724744074000109550010000176791924919059"
CHAVE_CTE = "35260103203556000173570010003129861003129864"

_NS_NFE = 'xmlns="http://www.portalfiscal.inf.br/nfe"'


def _nfe_xml(chave: str, *, dups: int = 2, assinada: bool = True) -> bytes:
    dup_xml = "".join(
        f"<dup><nDup>{i:03d}</nDup><dVenc>2026-07-2{i}</dVenc><vDup>5400.00</vDup></dup>"
        for i in range(1, dups + 1)
    )
    sig = "<Signature><SignedInfo>lixo</SignedInfo></Signature>" if assinada else ""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<nfeProc {_NS_NFE} versao="4.00"><NFe {_NS_NFE}><infNFe Id="NFe{chave}" versao="4.00">
<ide><cUF>35</cUF><natOp>VENDA DE MERCADORIA</natOp><mod>55</mod><serie>1</serie>
<nNF>17678</nNF><dhEmi>2026-07-02T16:27:00-03:00</dhEmi><tpNF>1</tpNF><finNFe>1</finNFe></ide>
<emit><CNPJ>24744074000109</CNPJ><xNome>CAMPO FINO ALIMENTOS</xNome>
<enderEmit><xMun>COLINA</xMun><UF>SP</UF></enderEmit><CRT>3</CRT></emit>
<dest><CNPJ>67727685000305</CNPJ><xNome>FERNANDO HENRIQUE THOME</xNome>
<enderDest><xMun>BARRETOS</xMun><UF>SP</UF></enderDest></dest>
<det nItem="1"><prod><xProd>ARROZ</xProd><vProd>10800.00</vProd></prod></det>
<total><ICMSTot><vProd>10800.00</vProd><vFrete>0</vFrete><vDesc>0</vDesc>
<vNF>10800.00</vNF><vTotTrib>1234.56</vTotTrib></ICMSTot></total>
<transp><modFrete>0</modFrete></transp>
<cobr><fat><nFat>1000017678</nFat><vOrig>10800.00</vOrig><vLiq>10800.00</vLiq></fat>{dup_xml}</cobr>
<pag><detPag><indPag>1</indPag><tPag>15</tPag><vPag>10800.00</vPag></detPag></pag>
</infNFe>{sig}</NFe>
<protNFe {_NS_NFE} versao="4.00"><infProt><tpAmb>1</tpAmb><chNFe>{chave}</chNFe>
<dhRecbto>2026-07-02T16:36:43-03:00</dhRecbto><nProt>135262619302482</nProt>
<cStat>100</cStat><xMotivo>Autorizado o uso da NF-e</xMotivo></infProt></protNFe></nfeProc>""".encode()


def _cte_xml(chave: str) -> bytes:
    ns = 'xmlns="http://www.portalfiscal.inf.br/cte"'
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<cteProc {ns} versao="3.00"><CTe {ns}><infCte Id="CTe{chave}" versao="3.00">
<ide><cUF>35</cUF><CFOP>5352</CFOP><natOp>PREST.SERV.TRANSP</natOp><mod>57</mod>
<serie>1</serie><nCT>312986</nCT><dhEmi>2026-01-26T14:30:00-03:00</dhEmi><tpCTe>0</tpCTe>
<xMunIni>PIRACICABA</xMunIni><UFIni>SP</UFIni><xMunFim>MOGI-GUACU</xMunFim><UFFim>SP</UFFim>
<toma3><toma>3</toma></toma3></ide>
<emit><CNPJ>03203556000173</CNPJ><xNome>LOTRANS LOGISTICA</xNome></emit>
<rem><CNPJ>50855584000155</CNPJ><xNome>MARCON CEREAIS</xNome></rem>
<dest><CNPJ>05969945000482</CNPJ><xNome>OMYA DO BRASIL</xNome></dest>
<vPrest><vTPrest>783.00</vTPrest><vRec>783.00</vRec></vPrest>
<infCTeNorm><infCarga><vCarga>50000.00</vCarga><proPred>CEREAIS</proPred></infCarga>
<infDoc><infNFe><chave>{CHAVE_NFE}</chave></infNFe><infNFe><chave>{CHAVE_NFE_2}</chave></infNFe></infDoc>
</infCTeNorm></infCte></CTe>
<protCTe {ns} versao="3.00"><infProt><chCTe>{chave}</chCTe>
<dhRecbto>2026-01-26T14:31:10-03:00</dhRecbto><nProt>135260398344474</nProt>
<cStat>100</cStat><xMotivo>Autorizado o uso do CT-e.</xMotivo></infProt></protCTe></cteProc>""".encode()


_EVENTO = b"""<?xml version="1.0"?><procEventoNFe xmlns="http://www.portalfiscal.inf.br/nfe" versao="1.00">
<evento versao="1.00"><infEvento><tpEvento>110111</tpEvento></infEvento></evento></procEventoNFe>"""


# ---- Unidade: conversor + parsers -------------------------------------------


def test_xml_to_dict_canonico() -> None:
    root, doc = xml_to_dict(_nfe_xml(CHAVE_NFE, dups=2))
    assert root == "nfeProc"
    assert doc["@versao"] == "4.00"
    inf = doc["NFe"]["infNFe"]
    assert inf["@Id"] == f"NFe{CHAVE_NFE}"
    # tag repetida vira lista
    assert isinstance(inf["cobr"]["dup"], list) and len(inf["cobr"]["dup"]) == 2
    # Signature omitida do raw (permanece no bronze)
    assert "Signature" not in doc["NFe"]
    # folha vira string
    assert inf["total"]["ICMSTot"]["vNF"] == "10800.00"


def test_parse_nfe_curado() -> None:
    _, doc = xml_to_dict(_nfe_xml(CHAVE_NFE))
    p = parse_nfe(doc)
    assert p is not None
    assert p.chave_acesso == CHAVE_NFE
    assert p.numero == 17678
    assert p.emitente_documento == "24744074000109"
    assert p.destinatario_documento == "67727685000305"
    assert p.destinatario_tipo_pessoa == "pj"
    assert p.valor_total == Decimal("10800.00")
    assert p.meio_pagamento == "15"  # boleto
    assert p.autorizada is True and p.cstat == 100
    assert len(p.duplicatas) == 2
    assert p.duplicatas[0].numero == "001"
    assert p.duplicatas[0].valor == Decimal("5400.00")


def test_parse_cte_curado() -> None:
    _, doc = xml_to_dict(_cte_xml(CHAVE_CTE))
    p = parse_cte(doc)
    assert p is not None
    assert p.chave_acesso == CHAVE_CTE
    assert p.emitente_documento == "03203556000173"
    assert p.remetente_documento == "50855584000155"
    assert p.tomador_codigo == "3"
    assert p.valor_prestacao == Decimal("783.00")
    assert p.valor_carga == Decimal("50000.00")
    assert p.chaves_nfe == [CHAVE_NFE, CHAVE_NFE_2]
    assert p.autorizada is True


# ---- ETL (gr_db_test) --------------------------------------------------------


@pytest.fixture
def storage(monkeypatch: pytest.MonkeyPatch, tmp_path) -> LocalDiskStorage:
    backend = LocalDiskStorage(str(tmp_path))
    monkeypatch.setattr(etl_mod, "get_storage_backend", lambda: backend)
    return backend


async def _seed(
    storage: LocalDiskStorage,
    tenant_id: UUID,
    *,
    nome: str,
    body: bytes,
    source_label: str,
) -> UUID:
    sha = hashlib.sha256(body).hexdigest()
    key = f"{tenant_id}/sem-ua/{source_label}/2026/07/{sha}"
    await storage.put(key, body)
    async with AsyncSessionLocal() as db:
        row = FileLanding(
            tenant_id=tenant_id,
            source_label=source_label,
            nome_arquivo=nome,
            sha256=sha,
            size_bytes=len(body),
            storage_key=key,
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
    return row.id


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_etl_fiscal_ponta_a_ponta(
    tenant_a: Tenant, storage: LocalDiskStorage
) -> None:
    lote = _zip(
        {
            f"NFe{CHAVE_NFE}.xml": _nfe_xml(CHAVE_NFE),
            f"NFe{CHAVE_NFE_2}.xml": _nfe_xml(CHAVE_NFE_2, dups=1),
            "evento.xml": _EVENTO,
            "danfe.pdf": b"%PDF-1.4 lixo",
        }
    )
    await _seed(storage, tenant_a.id, nome="LOTE_NFE.zip", body=lote, source_label="fiscal_nfe")
    await _seed(
        storage, tenant_a.id, nome=f"CTe{CHAVE_CTE}.xml",
        body=_cte_xml(CHAVE_CTE), source_label="fiscal_cte",
    )

    async with AsyncSessionLocal() as db:
        result = await sync_fiscal(db, tenant_id=tenant_a.id)

    assert result.landings_processados == 2
    assert result.nfe_novas == 2
    assert result.cte_novos == 1
    assert result.eventos_descartados == 1
    assert result.entradas_ignoradas == 1  # o PDF
    assert result.xml_invalidos == 0

    async with AsyncSessionLocal() as db:
        raw = (
            await db.execute(
                select(NfeRawDocumento).where(
                    NfeRawDocumento.tenant_id == tenant_a.id,
                    NfeRawDocumento.chave_acesso == CHAVE_NFE,
                )
            )
        ).scalar_one()
        # Raw JSONB integral: qualquer campo consultavel (aqui, o CRT do emitente)
        assert raw.documento["NFe"]["infNFe"]["emit"]["CRT"] == "3"

        nfe = (
            await db.execute(
                select(Nfe).where(
                    Nfe.tenant_id == tenant_a.id, Nfe.chave_acesso == CHAVE_NFE
                )
            )
        ).scalar_one()
        assert nfe.valor_total == Decimal("10800.00")
        assert nfe.autorizada is True
        assert nfe.raw_documento_id == raw.id
        dups = (
            (await db.execute(select(NfeDuplicata).where(NfeDuplicata.nfe_id == nfe.id)))
            .scalars()
            .all()
        )
        assert len(dups) == 2

        cte = (
            await db.execute(select(Cte).where(Cte.tenant_id == tenant_a.id))
        ).scalar_one()
        links = (
            (await db.execute(select(CteNfe).where(CteNfe.cte_id == cte.id)))
            .scalars()
            .all()
        )
        assert sorted(link.chave_nfe for link in links) == sorted([CHAVE_NFE, CHAVE_NFE_2])

        pendentes = (
            await db.execute(
                select(FileLanding).where(
                    FileLanding.tenant_id == tenant_a.id,
                    FileLanding.consumed_at.is_(None),
                )
            )
        ).scalars().all()
        assert pendentes == []

    # Idempotencia: o MESMO documento reaparecendo (zip do dia seguinte que
    # re-empacota) nao duplica silver.
    relote = _zip({f"NFe{CHAVE_NFE}.xml": _nfe_xml(CHAVE_NFE)})
    await _seed(storage, tenant_a.id, nome="RELOTE.zip", body=relote, source_label="fiscal_nfe")
    async with AsyncSessionLocal() as db:
        result2 = await sync_fiscal(db, tenant_id=tenant_a.id)
    assert result2.nfe_novas == 0
    assert result2.nfe_duplicadas == 1
    async with AsyncSessionLocal() as db:
        n = (
            await db.execute(
                select(Nfe).where(
                    Nfe.tenant_id == tenant_a.id, Nfe.chave_acesso == CHAVE_NFE
                )
            )
        ).scalars().all()
    assert len(n) == 1


@pytest.mark.asyncio
async def test_isolamento_drenar_a_nao_toca_b(
    tenant_a: Tenant, tenant_b: Tenant, storage: LocalDiskStorage
) -> None:
    id_b = await _seed(
        storage, tenant_b.id, nome="b.xml",
        body=_nfe_xml(CHAVE_NFE), source_label="fiscal_nfe",
    )
    async with AsyncSessionLocal() as db:
        result = await sync_fiscal(db, tenant_id=tenant_a.id)
    assert result.landings_processados == 0

    async with AsyncSessionLocal() as db:
        row_b = (
            await db.execute(select(FileLanding).where(FileLanding.id == id_b))
        ).scalar_one()
        assert row_b.consumed_at is None
        nfes_b = (
            await db.execute(select(Nfe).where(Nfe.tenant_id == tenant_b.id))
        ).scalars().all()
        assert nfes_b == []
