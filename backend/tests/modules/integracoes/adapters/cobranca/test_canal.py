"""Classificador de canal (F2): heuristica de segmento + resolucao de praca.

Nomes reais do CSV de participantes do STR (2026-07-07) e casos do padrao-ouro
JCL/MFL. Regra de ouro sob teste: ausencia de resolucao NUNCA vira o canal
mais conveniente (a licao do ERP que contava 'sem agencia' como 'na praca').
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

from app.modules.integracoes.adapters.cobranca.canal import (
    CANAL_BANCO_PRACA,
    CANAL_BANCO_SEM_PRACA,
    CANAL_COOPERATIVA,
    CANAL_IP,
    CANAL_NAO_RESOLVIDO,
    RefBacenResolver,
)
from app.modules.integracoes.adapters.data.bacen.etl import (
    _pad_agencia,
    extrair_posto_codigo,
    inferir_segmento,
)

_NOW = datetime.now(UTC)


def _inst(codigo, nome_red, nome_ext):
    return SimpleNamespace(
        codigo_compe=codigo,
        nome_reduzido=nome_red,
        segmento=inferir_segmento(nome_ext, nome_red),
    )


def _ag(banco, agencia, municipio, uf, ibge=None):
    return SimpleNamespace(
        banco_compe=banco, agencia_codigo=agencia,
        municipio=municipio, uf=uf, municipio_ibge=ibge,
    )


def _resolver() -> RefBacenResolver:
    instituicoes = {
        i.codigo_compe: i
        for i in [
            _inst("237", "BCO BRADESCO S.A.", "Banco Bradesco S.A."),
            _inst("341", "ITAÚ UNIBANCO S.A.", "Itaú Unibanco S.A."),
            _inst("756", "BANCO SICOOB S.A.", "BANCO COOPERATIVO SICOOB S.A. - BANCO SICOOB"),
            _inst("748", "BCO COOPERATIVO SICREDI S.A.", "BANCO COOPERATIVO SICREDI S.A."),
            _inst("323", "MERCADO PAGO IP LTDA.", "MERCADO PAGO INSTITUIÇÃO DE PAGAMENTO LTDA."),
            _inst("016", "CCM DESP TRÂNS SC E RS", "COOPERATIVA DE CRÉDITO MÚTUO DOS DESPACHANTES DE TRÂNSITO DE SANTA CATARINA E RIO GRANDE DO SUL - SICOOB CREDITRAN"),
        ]
    }
    agencias = {
        (a.banco_compe, a.agencia_codigo): a
        for a in [
            _ag("237", "03372", "SOROCABA", "SP", 3552205),
            _ag("237", "00001", "OSASCO", "SP"),
        ]
    }
    return RefBacenResolver(instituicoes, agencias)


def test_segmento_heuristica_nomes_reais() -> None:
    assert inferir_segmento("BANCO COOPERATIVO SICOOB S.A. - BANCO SICOOB") == "banco_cooperativo"
    assert inferir_segmento("BANCO COOPERATIVO SICREDI S.A.") == "banco_cooperativo"
    assert inferir_segmento("COOPERATIVA DE CRÉDITO MÚTUO ... SICOOB CREDITRAN") == "cooperativa"
    assert inferir_segmento("MERCADO PAGO INSTITUIÇÃO DE PAGAMENTO LTDA.") == "ip"
    assert inferir_segmento("PAGSEGURO INTERNET INSTITUIÇÃO DE PAGAMENTO S.A.") == "ip"
    assert inferir_segmento("CELCOIN INSTITUICAO DE PAGAMENTO S.A.", "CELCOIN IP S.A.") == "ip"
    assert inferir_segmento("CELCOIN SOCIEDADE DE CRÉDITO DIRETO S.A.") == "scd"
    assert inferir_segmento("Banco Bradesco S.A.") == "banco"
    assert inferir_segmento("Banco do Brasil S.A.", "BCO DO BRASIL S.A.") == "banco"


def test_banco_com_agencia_resolvida_vira_praca() -> None:
    p = _resolver().resolver("237", "3372")
    assert p.canal == CANAL_BANCO_PRACA
    assert (p.municipio, p.uf) == ("SOROCABA", "SP")
    assert p.praca_resolvida is True


def test_agencia_fora_da_ref_nao_vira_praca() -> None:
    # Itau 8544: numeracao interna/extinta — a licao do ERP: nao inventar praca.
    p = _resolver().resolver("341", "8544")
    assert p.canal == CANAL_BANCO_SEM_PRACA
    assert p.praca_resolvida is False
    assert p.municipio is None


def test_agencia_matriz_0001_nao_e_praca_mesmo_resolvida() -> None:
    p = _resolver().resolver("237", "1")
    assert p.canal == CANAL_BANCO_SEM_PRACA
    assert p.praca_resolvida is False
    assert p.municipio == "OSASCO"  # cidade preservada como contexto


def test_cooperativa_e_canal_proprio_sem_praca() -> None:
    p = _resolver().resolver("756", "07723")
    assert p.canal == CANAL_COOPERATIVA
    assert p.instituicao == "BANCO SICOOB S.A."
    assert p.praca_resolvida is False


def test_ip_e_canal_proprio() -> None:
    p = _resolver().resolver("323", "00001")
    assert p.canal == CANAL_IP


def test_banco_desconhecido_e_nao_resolvido() -> None:
    p = _resolver().resolver("999", "00001")
    assert p.canal == CANAL_NAO_RESOLVIDO
    assert p.praca_resolvida is False


def test_pad_agencia() -> None:
    assert _pad_agencia("3372") == "03372"
    assert _pad_agencia(1039) == "01039"
    assert _pad_agencia("0") is None
    assert _pad_agencia("") is None
    assert _pad_agencia(None) is None


def _resolver_com_postos() -> RefBacenResolver:
    """Resolver com CEF (104) e um posto codificado — sem agencia Olinda p/ ela."""
    instituicoes = {
        i.codigo_compe: i
        for i in [
            _inst("104", "CAIXA ECONOMICA FEDERAL", "Caixa Economica Federal"),
            _inst("237", "BCO BRADESCO S.A.", "Banco Bradesco S.A."),
        ]
    }
    agencias = {
        (a.banco_compe, a.agencia_codigo): a
        for a in [_ag("237", "03372", "SOROCABA", "SP", 3552205)]
    }
    # (banco, agencia) -> (municipio, uf, tipo_posto)
    postos = {
        ("104", "06425"): ("PIRACICABA", "SP", "AG EMPRESARIAL"),
        # tambem existe como agencia historica BCB -> BCB deve vencer o posto:
        ("237", "09090"): ("CAMPINAS", "SP", "PAB"),
    }
    bcb = {("237", "09090"): ("SANTOS", "SP")}
    return RefBacenResolver(instituicoes, agencias, {}, bcb, postos)


def test_posto_resolve_praca_quando_agencia_e_bcb_falham() -> None:
    # CEF 6425: nao esta no Informes_Agencias nem na serie BCB, mas e um posto
    # (AG Empresarial) — hoje cairia em banco_sem_praca; agora resolve.
    p = _resolver_com_postos().resolver("104", "6425")
    assert p.canal == CANAL_BANCO_PRACA
    assert (p.municipio, p.uf) == ("PIRACICABA", "SP")
    assert p.praca_resolvida is True
    assert p.praca_fonte == "bcb_posto"
    assert p.tipo_posto == "AG EMPRESARIAL"


def test_bcb_historico_vence_posto_na_escada() -> None:
    # Mesma chave em BCB e em posto: o degrau BCB (2o) vem antes do posto (3o).
    p = _resolver_com_postos().resolver("237", "9090")
    assert p.canal == CANAL_BANCO_PRACA
    assert p.municipio == "SANTOS"  # BCB, nao CAMPINAS (posto)
    assert p.praca_fonte == "bcb_historico"
    assert p.tipo_posto is None


def test_posto_sem_codigo_nao_resolve() -> None:
    # Banco sem posto codificado p/ a agencia -> permanece banco_sem_praca.
    p = _resolver_com_postos().resolver("104", "99999")
    assert p.canal == CANAL_BANCO_SEM_PRACA
    assert p.praca_resolvida is False


def test_extrair_posto_codigo() -> None:
    assert extrair_posto_codigo("6425 - PLATAFORMA EMPRESAS PIRACICABA") == "06425"
    assert extrair_posto_codigo("05501 - AG EMPRESARIAL MOGI") == "05501"
    assert extrair_posto_codigo("123 – POSTO COM TRAVESSAO UNICODE") == "00123"  # noqa: RUF001
    assert extrair_posto_codigo("PAB DETRAN SP") is None
    assert extrair_posto_codigo("0 - POSTO CODIGO ZERO") is None
    assert extrair_posto_codigo("") is None
    assert extrair_posto_codigo(None) is None
