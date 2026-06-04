"""Mappers BDC — payload cru (bronze) -> campos canonicos (silver).

Funcoes PURAS: recebem o envelope BDC, devolvem dataclass tipada. Sem DB,
sem rede — testaveis com o exemplo da doc do vendor. O service e quem
chama o mapper sobre a raw e persiste o silver (CLAUDE.md secao 13.2.1).
"""
