"""Cota Sub services — explainers, COSIF→bucket mapping, etc.

A partir de 2026-05-17 (refactor "balancete = fonte de verdade") os explainers
da Cota Sub deixam de calcular `delta_brl` em fontes paralelas e passam a
particionar contas COSIF do balancete por bucket — Σ buckets ≡ ΔPL contabil
por construcao. Heuristicas (MEC/CPR/RF/estoque) viram enriquecedoras de
evidencia, nao mais fonte de calculo. Ver `cosif_to_bucket.py`.
"""
