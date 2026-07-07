"""PlaceholderNode — stub for node types declared in the catalog as
`available=False` ("em breve").

These types appear in the visual editor's palette to surface the product
roadmap without confusing users — but they cannot execute. If anyone tries
to run a workflow containing one, the engine raises a clear error pointing
to the node id and type so the user knows what's missing.

Use this single class for all "soon" entries — saves boilerplate and gives
a uniform error message across the unimplemented surface.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.workflows.nodes._base import BaseNode, NodeContext, NodeOutput


class PlaceholderNode(BaseNode):
    """Stub for `available=False` types in NODE_TYPES.

    Validation passes (so editor doesn't break on load), but execution
    explicitly errors. The graph validator (Fase 2) flags `available=False`
    nodes as warnings, so users see "em breve" badges before trying to run.
    """

    type = "_placeholder"

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        raise RuntimeError(
            "Esta etapa ainda nao foi implementada — esta marcada como "
            "'em breve' no catalogo. Substitua por um tipo wired antes "
            "de rodar este fluxo."
        )
