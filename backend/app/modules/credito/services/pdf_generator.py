"""PDF generator (skeleton) for the dossier final artifact.

MVP returns a stub `dict` with metadata. Full PDF rendering will use
ReportLab or a markdown-to-PDF chain in a follow-up. The output_generator
node calls this and stores the returned dict on its node output.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession


async def generate_dossier_artifact(
    *,
    dossier_id: UUID | str,
    tenant_id: UUID,
    previous_outputs: dict[str, dict[str, Any]],
    output_format: str,
    db: AsyncSession,
) -> dict[str, Any]:
    """Produce the final artifact descriptor.

    Returns a dict with:
    - format: 'pdf' | 'json'
    - file_path: where the file was written (None in MVP)
    - sections: list of section ids included in the artifact

    Currently a stub — full rendering is a follow-up. The dict is persisted
    on the output_generator node's output_data.
    """
    sections = [
        nid
        for nid, payload in previous_outputs.items()
        if isinstance(payload, dict) and payload.get("output")
    ]

    return {
        "format": output_format,
        "file_path": None,  # TODO: render to /opt/app_gr/uploads/<tenant>/dossier/<id>/output.pdf
        "sections": sections,
        "status": "stub",
        "message": (
            "PDF generation is a stub in the MVP. Sections collected for inclusion: "
            f"{len(sections)}. Full PDF rendering will be wired in a follow-up."
        ),
    }
