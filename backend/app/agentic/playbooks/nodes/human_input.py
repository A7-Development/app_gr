"""HumanInputNode — pauses the workflow waiting for the analyst to fill a form.

The form is fully described by `config.fields` (a list of FormField specs),
so the frontend can render a dynamic form without hardcoding anything per
form_id. Tenants customizing their workflow simply edit the `fields` config.

Behavior:
- First execution: returns `should_pause=True` with the form descriptor,
  marking the node WAITING_INPUT. The engine persists that and stops.
- Resume: when the analyst submits via
  `POST /credito/dossies/{id}/nodes/{node_id}/submit`, the engine calls
  `resume_run` with the values, and this node re-executes returning the
  values as its output.

Config schema:
    {
        "form_id": "cadastro_empresa",     # required — identifies the form
        "title": "Cadastro basico da empresa",  # optional, shown in dialog header
        "description": "Identifique a empresa-alvo da analise.",  # optional
        "fields": [                        # required — list of FormField
            {
                "key": "cnpj",
                "type": "cnpj",            # string|cnpj|cpf|email|textarea|select|number|date|json|boolean
                "label": "CNPJ",
                "required": true,
                "placeholder": "00.000.000/0000-00",
                "options": [...]           # only for type=select
            },
            ...
        ],
        "submit_label": "Salvar"           # optional, default "Salvar"
    }

Output (after resume):
    Whatever the analyst submitted — the dict of {field_key: value}.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.playbooks.nodes._base import (
    BaseNode,
    NodeContext,
    NodeOutput,
    VarType,
)

_VALID_FIELD_TYPES = {
    "string",
    "cnpj",
    "cpf",
    "email",
    "textarea",
    "select",
    "number",
    "date",
    "json",
    "boolean",
}

# Maps form field type -> semantic VarType. Form types not listed here
# default to STRING (free text).
_FIELD_TYPE_TO_VAR: dict[str, VarType] = {
    "string": VarType.STRING,
    "textarea": VarType.STRING,
    "select": VarType.STRING,
    "cnpj": VarType.CNPJ,
    "cpf": VarType.CPF,
    "email": VarType.EMAIL,
    "number": VarType.NUMBER,
    "date": VarType.DATE,
    "boolean": VarType.BOOLEAN,
    "json": VarType.OBJECT,
}


class HumanInputNode(BaseNode):
    """Pauses for analyst input via a dynamic form (fields described in config)."""

    type = "human_input"

    def validate_config(self) -> None:
        # Backward compat: accept either form_id or legacy `form`.
        if not self.config.get("form_id") and not self.config.get("form"):
            raise ValueError(
                "human_input: `config.form_id` is required (identifies the form)"
            )

        fields = self.config.get("fields")
        if fields is not None:
            if not isinstance(fields, list):
                raise ValueError("human_input: `config.fields` must be a list of FormField objects")
            for i, f in enumerate(fields):
                if not isinstance(f, dict):
                    raise ValueError(f"human_input: fields[{i}] must be an object")
                if not f.get("key"):
                    raise ValueError(f"human_input: fields[{i}].key is required")
                if not f.get("label"):
                    raise ValueError(f"human_input: fields[{i}].label is required")
                ftype = f.get("type", "string")
                if ftype not in _VALID_FIELD_TYPES:
                    raise ValueError(
                        f"human_input: fields[{i}].type='{ftype}' is invalid. "
                        f"Valid types: {sorted(_VALID_FIELD_TYPES)}"
                    )

    def produces(self) -> dict[str, VarType]:
        """Cada field do form vira uma variável tipada exposta no output.

        Quando o nó está pausado (sem submit ainda) o output expõe o
        descritor do form (`form_id`, `fields`, etc), mas downstream nodes
        só serão executados após o resume — quando `output.data` é o dict
        de valores submetidos. Por isso aqui declaramos os campos.
        """
        out: dict[str, VarType] = {}
        for f in self.config.get("fields", []) or []:
            key = f.get("key")
            if not isinstance(key, str) or not key:
                continue
            ftype = f.get("type", "string")
            out[key] = _FIELD_TYPE_TO_VAR.get(ftype, VarType.STRING)
        return out

    async def execute(self, ctx: NodeContext, db: AsyncSession) -> NodeOutput:
        # When resumed, the engine writes the submitted data to
        # `previous_outputs[<this_node>]["pending_input"]` so this node can
        # complete. See engine.resume_run().
        pending = ctx.previous_outputs.get(ctx.node_id, {}).get("pending_input")
        if pending is None:
            return NodeOutput(
                data={
                    "form_id": self.config.get("form_id") or self.config.get("form"),
                    "title": self.config.get("title"),
                    "description": self.config.get("description"),
                    "fields": self.config.get("fields", []),
                    "submit_label": self.config.get("submit_label", "Salvar"),
                },
                should_pause=True,
                status_hint="Aguardando preenchimento do analista",
            )
        return NodeOutput(
            data=pending,
            status_hint="Preenchido",
        )
