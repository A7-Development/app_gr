"""Pydantic schemas — Controladoria · Chat-investigador da variacao (Camada 2).

Q&A conversacional sobre a variacao da Cota Sub de um dia. O backend pre-carrega
o contexto estruturado (headline + detalhamento) e passa pro agente, que so
chama tool quando precisa investigar. Ver §19 (camada agentica).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ChatMensagem(BaseModel):
    """Uma mensagem da conversa (pra dar memoria multi-turn ao agente)."""

    role:    Literal["user", "assistant"]
    content: str


class ChatVariacaoRequest(BaseModel):
    """Pergunta do controller + historico da conversa."""

    pergunta:  str = Field(min_length=1, max_length=2000)
    historico: list[ChatMensagem] = Field(default_factory=list, max_length=30)


class ChatVariacaoResposta(BaseModel):
    """Resposta do agente investigador."""

    resposta:     str
    tools_usadas: list[str] = Field(default_factory=list)


class ChatAgenteInfo(BaseModel):
    """Identidade DISCRETA do agente que atende esta janela de chat.

    Expoe so o codigo (ex.: AGT-AB5F5221) — pra rastreabilidade na UI sem
    revelar o nome interno do agente ao usuario final. Derivado no backend
    da constante do endpoint (fonte unica da verdade)."""

    code: str
