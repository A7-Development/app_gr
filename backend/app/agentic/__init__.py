"""Camada agentica — arquitetura horizontal estrutural (CLAUDE.md sec 19).

Strata e plataforma agentica. Esta camada (motor + tools + playbooks +
memoria + agentes) e **horizontal** e atravessa todos os 9 modulos. Os
modulos sao "pacotes de dominio" que registram tools e playbooks proprios;
o motor de agente e unico.

Sub-camadas:
    engine/      Motor unico de agente (runtime, tool loop, catalog, prompts)
    agents/      Catalogo central de agentes (futuro F2 — hoje vive em engine/catalog.py)
    tools/       Registry dinamico de tools (futuro F2 — hoje vive em engine/tools/)
    playbooks/   Workflows declarativos (futuro F3 — hoje vive em modules/credito/workflows/)
    memory/      Sessao + tenant + global (futuro F1)

Vocabulario canonico: agents, tools, playbooks, memory — usar exatamente
esses termos. "Skill" NUNCA significa playbook agentico (skill = comando
Claude Code).

Referencias:
    CLAUDE.md sec 19.0   Vocabulario canonico e blocos
    CLAUDE.md sec 19.10  Playbooks
    CLAUDE.md sec 19.11  Memoria de sessao
    CLAUDE.md sec 19.12  Catalogo central de agentes
"""
