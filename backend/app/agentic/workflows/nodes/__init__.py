"""Node type implementations for the workflow engine.

Each module in this package defines one node type — a class implementing
`BaseNode.execute()`. The engine looks up the type by string name from the
node's `type` field in the graph.

Catalog of node types (MVP, see plan):
- trigger              — manual or API kickoff
- human_input          — pauses for analyst to fill a form
- document_request     — pauses for analyst to upload required documents
- document_extractor   — runs Claude Vision multimodal to structure a doc
- bureau_query         — calls a bureau adapter (Serasa, BigData, etc)
- specialist_agent     — runs a SpecialistAgent from app.agentic.engine.catalog
- human_review         — pauses for analyst to validate before continuing
- output_generator     — produces final artifact (PDF, JSON)

Future ("em breve" in the visual editor palette):
- decision_branch      — conditional routing
- notification         — email/SMS dispatch
- webhook_trigger      — external API kickoff
- parallel             — explicit fan-out container (engine handles it
                         implicitly via graph topology, but a parallel
                         container helps the visual editor group)
"""

from app.agentic.workflows.nodes._base import BaseNode, NodeContext, NodeOutput

__all__ = ["BaseNode", "NodeContext", "NodeOutput"]
