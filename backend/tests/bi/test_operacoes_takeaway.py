"""Testes unitarios para `_build_takeaway_pt`.

Funcao pura, sem DB — verifica as 3 ramificacoes de formato da narrativa:
  1. Periodo completo (com volume anterior + produto lider acima de 20% share)
  2. Sem volume anterior (primeiro periodo, "N/A" na comparacao)
  3. Produto lider com share < 20% (omite "puxado por")

Regra: takeaway retorna None quando periodo vazio (`volume_atual <= 0`).
"""

from __future__ import annotations

from app.modules.bi.services.operacoes import _build_takeaway_pt


def test_takeaway_periodo_completo() -> None:
    """Caso canonico: volume + delta vs anterior + produto lider + ticket."""
    frase = _build_takeaway_pt(
        volume_atual=118_200_000.0,
        volume_anterior=112_400_000.0,
        ticket_atual=85_000.0,
        ticket_anterior=82_400.0,
        produto_lider_sigla="FAT",
        produto_lider_nome="Faturizacao",
        produto_lider_share_pct=42.0,
    )
    assert frase is not None
    assert "R$ 118,2 mi" in frase
    assert "+5,2% vs anterior" in frase
    assert "puxado por Faturizacao" in frase
    assert "42% de participacao" in frase
    assert "Ticket medio subiu 3,2%" in frase


def test_takeaway_sem_comparacao() -> None:
    """Primeiro periodo / sem base: omite o trecho '(X% vs anterior)'."""
    frase = _build_takeaway_pt(
        volume_atual=50_000_000.0,
        volume_anterior=None,
        ticket_atual=70_000.0,
        ticket_anterior=None,
        produto_lider_sigla="DUP",
        produto_lider_nome="Duplicata",
        produto_lider_share_pct=55.0,
    )
    assert frase is not None
    assert "R$ 50,0 mi" in frase
    assert "vs anterior" not in frase
    assert "Ticket medio" not in frase  # sem base, nao narra ticket
    assert "puxado por Duplicata" in frase


def test_takeaway_sem_produto_lider_claro() -> None:
    """Share < 20%: omite 'puxado por' — nao ha driver claro."""
    frase = _build_takeaway_pt(
        volume_atual=30_000_000.0,
        volume_anterior=30_300_000.0,
        ticket_atual=65_000.0,
        ticket_anterior=65_200.0,
        produto_lider_sigla="FAT",
        produto_lider_nome="Faturizacao",
        produto_lider_share_pct=18.0,
    )
    assert frase is not None
    assert "puxado por" not in frase
    assert "Ticket medio estavel" in frase  # |delta| < 1%


def test_takeaway_periodo_vazio_retorna_none() -> None:
    """Volume zero -> None (frontend nao renderiza a faixa)."""
    frase = _build_takeaway_pt(
        volume_atual=0.0,
        volume_anterior=100_000.0,
        ticket_atual=0.0,
        ticket_anterior=50_000.0,
        produto_lider_sigla=None,
        produto_lider_nome=None,
        produto_lider_share_pct=None,
    )
    assert frase is None


def test_takeaway_ticket_caiu() -> None:
    """Sinal de ticket_delta negativo vira 'caiu X%'."""
    frase = _build_takeaway_pt(
        volume_atual=40_000_000.0,
        volume_anterior=45_000_000.0,
        ticket_atual=60_000.0,
        ticket_anterior=66_000.0,
        produto_lider_sigla="DUP",
        produto_lider_nome="Duplicata",
        produto_lider_share_pct=35.0,
    )
    assert frase is not None
    assert "Ticket medio caiu 9,1%" in frase
