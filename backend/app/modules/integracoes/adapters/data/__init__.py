"""Adapters de provedores de dados externos (capability transversal A7).

Categoria criada em 2026-05-05 para isolar adapters que usam UMA credencial
global da A7 (revendida aos tenants), em contraste com `adapters/bureau/`
onde cada tenant tem credencial propria.

Vendors atuais:
    - bigdatacorp/  (Fase 1 — sync de catalogo + consultas on-demand)
    - infosimples/  (futuro)

Modelos de catalogo + credencial vivem em `app/shared/data_providers/`.
"""
