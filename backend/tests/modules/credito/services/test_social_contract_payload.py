"""Unit tests da camada determinística do contrato social (funções puras).

Cobre `_estrutura` (QSA: soma, controlador, idade) e `_cruzamentos`
(contrato x cadastro oficial) — o fato que a read-tool entrega ao agente e
que o check `contrato_social_consistente` transforma em red flags.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.modules.credito.services.social_contract import (
    _cruzamentos,
    _estrutura,
    _norm_name,
    _redact_socio,
)


class _Company:
    """Stub de CreditDossierCompany (só os campos lidos pelos cruzamentos)."""

    def __init__(
        self,
        *,
        cnpj: str = "12345678000190",
        name: str = "ACME COMERCIO LTDA",
        capital_social: Decimal | None = Decimal("100000"),
        founding_date: date | None = date(2015, 3, 10),
    ) -> None:
        self.cnpj = cnpj
        self.name = name
        self.capital_social = capital_social
        self.founding_date = founding_date


def _socios(*pcts: float | None) -> list[dict]:
    return [
        _redact_socio({"nome": f"Socio {i}", "cpf": "12345678901", "participacao_pct": p})
        for i, p in enumerate(pcts, start=1)
    ]


# ─── _redact_socio (LGPD) ────────────────────────────────────────────────────


def test_redact_socio_nunca_vaza_cpf_inteiro():
    s = _redact_socio({"nome": "Maria", "cpf": "123.456.789-01", "participacao_pct": 60})
    assert s == {"nome": "Maria", "cpf_ultimos4": "8901", "participacao_pct": 60.0}


def test_redact_socio_sem_nome_descarta():
    assert _redact_socio({"cpf": "12345678901"}) is None
    assert _redact_socio("string") is None


# ─── _estrutura ──────────────────────────────────────────────────────────────


def test_estrutura_soma_confere_e_controlador():
    e = _estrutura(_socios(60, 40), date(2015, 3, 10))
    assert e["n_socios"] == 2
    assert e["soma_participacoes_pct"] == 100.0
    assert e["soma_confere"] is True
    assert e["controlador"]["nome"] == "Socio 1"
    assert e["controlador"]["controle_majoritario"] is True
    assert e["idade_empresa_anos"] is not None and e["idade_empresa_anos"] > 9


def test_estrutura_soma_divergente_e_socio_sem_pct():
    e = _estrutura(_socios(50, 30, None), None)
    assert e["soma_participacoes_pct"] == 80.0
    assert e["soma_confere"] is False
    assert e["socios_sem_participacao"] == 1
    assert e["idade_empresa_anos"] is None


# ─── _norm_name ──────────────────────────────────────────────────────────────


def test_norm_name_ignora_sufixo_acento_pontuacao():
    assert _norm_name("Acmé Comércio Ltda.") == _norm_name("ACME COMERCIO")


# ─── _cruzamentos ────────────────────────────────────────────────────────────


def _fields(**over) -> dict:
    base = {
        "cnpj": "12.345.678/0001-90",
        "razao_social": "Acme Comercio Ltda",
        "capital_social": 100000,
        "data_constituicao": "2015-03-10",
    }
    base.update(over)
    return base


def _by_campo(out: list[dict]) -> dict[str, dict]:
    return {c["campo"]: c for c in out}


def test_cruzamentos_tudo_confere():
    out = _by_campo(_cruzamentos(_fields(), _Company(), "12345678000190"))
    assert out["cnpj"]["confere"] is True
    assert out["razao_social"]["confere"] is True
    assert out["capital_social"]["confere"] is True
    assert out["data_constituicao"]["confere"] is True


def test_cruzamentos_cnpj_de_outra_empresa():
    out = _by_campo(
        _cruzamentos(_fields(cnpj="99.999.999/0001-99"), _Company(), "12345678000190")
    )
    assert out["cnpj"]["confere"] is False


def test_cruzamentos_capital_divergente_fora_da_tolerancia():
    out = _by_campo(
        _cruzamentos(_fields(capital_social=150000), _Company(), "12345678000190")
    )
    assert out["capital_social"]["confere"] is False
    assert "diverge" in out["capital_social"]["detalhe"]


def test_cruzamentos_sem_cadastro_oficial_compara_so_cnpj():
    out = _cruzamentos(_fields(), None, "12345678000190")
    campos = {c["campo"] for c in out}
    assert campos == {"cnpj"}


def test_cruzamentos_sem_base_marca_nao_comparavel():
    out = _by_campo(
        _cruzamentos(
            _fields(capital_social=None),
            _Company(capital_social=None),
            "12345678000190",
        )
    )
    assert "capital_social" not in out or out["capital_social"]["confere"] is None
