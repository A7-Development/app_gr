"""Registry of node-type names → BaseNode subclass.

The engine looks up the class for each node in the graph here. Adding a
new node type means: implement BaseNode subclass + register here. The
visual editor reads the same registry to populate the node palette.

Flag `available=False` to show in the palette as "em breve" — instances
of that type validate at editor save but cannot run (engine raises).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.shared.workflow.nodes._base import BaseNode
from app.shared.workflow.nodes.bureau_query import BureauQueryNode
from app.shared.workflow.nodes.conditional_branch import ConditionalBranchNode
from app.shared.workflow.nodes.document_extractor import DocumentExtractorNode
from app.shared.workflow.nodes.document_request import DocumentRequestNode
from app.shared.workflow.nodes.http_request import HttpRequestNode
from app.shared.workflow.nodes.human_input import HumanInputNode
from app.shared.workflow.nodes.human_review import HumanReviewNode
from app.shared.workflow.nodes.notification import NotificationNode
from app.shared.workflow.nodes.output_generator import OutputGeneratorNode
from app.shared.workflow.nodes.specialist_agent import SpecialistAgentNode
from app.shared.workflow.nodes.trigger import TriggerNode


@dataclass(frozen=True, slots=True)
class NodeTypeMeta:
    """Metadata about a node type — exposed to the visual editor."""

    type: str
    cls: type[BaseNode]
    label: str
    category: str         # 'triggers', 'humano', 'coleta', 'agentes', 'logica', 'integracao', 'output'
    description: str
    available: bool       # False = em breve (palette greyed-out)
    icon: str             # Remix icon name (e.g. "RiPlayCircleLine")
    # Schema dict describing the editable config fields for the visual
    # editor's Inspector. Each field: {key, type, label, placeholder?, required?}
    config_schema: tuple[dict, ...] = ()


NODE_TYPES: dict[str, NodeTypeMeta] = {
    # ─── Triggers ─────────────────────────────────────────────────────────
    "trigger": NodeTypeMeta(
        type="trigger",
        cls=TriggerNode,
        label="Trigger Manual",
        category="triggers",
        description="Inicia o workflow manualmente (analista cria dossie).",
        available=True,
        icon="RiPlayCircleLine",
    ),
    # ─── Humano ──────────────────────────────────────────────────────────
    "human_input": NodeTypeMeta(
        type="human_input",
        cls=HumanInputNode,
        label="Input do Analista",
        category="humano",
        description=(
            "Pausa o workflow para o analista preencher um formulario configurado "
            "via `config.fields`. Frontend renderiza o form dinamicamente segundo "
            "os tipos (string/cnpj/cpf/email/textarea/select/number/date/json/boolean)."
        ),
        available=True,
        icon="RiEditLine",
        config_schema=(
            {
                "key": "form_id",
                "type": "string",
                "label": "ID do form",
                "placeholder": "cadastro_empresa",
                "required": True,
            },
            {
                "key": "title",
                "type": "string",
                "label": "Titulo (UI)",
                "placeholder": "Cadastro basico da empresa",
            },
            {
                "key": "description",
                "type": "text",
                "label": "Descricao (UI)",
            },
            {
                "key": "fields",
                "type": "json",
                "label": "Campos do form (lista JSON)",
                "required": True,
            },
            {
                "key": "submit_label",
                "type": "string",
                "label": "Label do botao submit",
                "placeholder": "Salvar",
            },
        ),
    ),
    "human_review": NodeTypeMeta(
        type="human_review",
        cls=HumanReviewNode,
        label="Revisao Humana",
        category="humano",
        description="Pausa para o analista revisar e aprovar as analises antes do parecer.",
        available=True,
        icon="RiCheckboxCircleLine",
    ),
    # ─── Coleta ──────────────────────────────────────────────────────────
    "document_request": NodeTypeMeta(
        type="document_request",
        cls=DocumentRequestNode,
        label="Solicitar Documentos",
        category="coleta",
        description="Pausa ate o analista subir os documentos obrigatorios.",
        available=True,
        icon="RiUploadCloud2Line",
    ),
    "document_extractor": NodeTypeMeta(
        type="document_extractor",
        cls=DocumentExtractorNode,
        label="Extrair Documentos",
        category="coleta",
        description="IA multimodal extrai dados estruturados dos documentos enviados.",
        available=True,
        icon="RiFileSearchLine",
    ),
    "bureau_query": NodeTypeMeta(
        type="bureau_query",
        cls=BureauQueryNode,
        label="Consulta Bureau",
        category="integracao",
        description=(
            "Consulta bureau de credito (Serasa PJ wired; Serasa PF / BigData / "
            "InfoSimples virao em breve). Persiste raw + silver no warehouse e "
            "expoe consulta_id pra etapas seguintes lerem detalhes."
        ),
        available=True,  # serasa_pj wired (2026-05-01); demais caem em placeholder
        icon="RiDatabase2Line",
        config_schema=(
            {
                "key": "adapter",
                "type": "string",
                "label": "Bureau",
                "placeholder": "serasa_pj",
                "required": True,
            },
            {
                "key": "entity_ref",
                "type": "string",
                "label": "CNPJ a consultar",
                "placeholder": "{{trigger.cnpj}}",
                "required": True,
            },
            {
                "key": "environment",
                "type": "string",
                "label": "Ambiente",
                "placeholder": "production",
            },
        ),
    ),
    # ─── Agentes ─────────────────────────────────────────────────────────
    "specialist_agent": NodeTypeMeta(
        type="specialist_agent",
        cls=SpecialistAgentNode,
        label="Agente Especialista",
        category="agentes",
        description="Agente IA especialista (contrato social, financeiro, juridico, etc).",
        available=True,
        icon="RiRobot2Line",
    ),
    # ─── Logica (n8n-style) ──────────────────────────────────────────────
    "conditional_branch": NodeTypeMeta(
        type="conditional_branch",
        cls=ConditionalBranchNode,
        label="Branch Condicional",
        category="logica",
        description=(
            "Avalia uma expressao boolean (com {{node.X.output.field}}) e "
            "retorna {result: bool}. Use edges com `condition` saindo deste "
            "no para rotear o fluxo."
        ),
        available=True,
        icon="RiGitBranchLine",
        config_schema=(
            {
                "key": "expression",
                "type": "string",
                "label": "Expressao",
                "placeholder": "{{node.score.output.value}} >= 700",
                "required": True,
            },
        ),
    ),
    # ─── Integracao (n8n-style genericos) ────────────────────────────────
    "http_request": NodeTypeMeta(
        type="http_request",
        cls=HttpRequestNode,
        label="HTTP Request",
        category="integracao",
        description=(
            "Chama uma API externa (GET/POST/PUT/PATCH/DELETE). Suporta "
            "headers/body/query parametrizados via templates. Retorna "
            "{status_code, body, headers}."
        ),
        available=True,
        icon="RiGlobalLine",
        config_schema=(
            {"key": "method", "type": "string", "label": "Metodo HTTP", "placeholder": "GET", "required": True},
            {"key": "url", "type": "string", "label": "URL", "placeholder": "https://api.exemplo.com/...", "required": True},
            {"key": "headers", "type": "json", "label": "Headers (JSON)"},
            {"key": "json_body", "type": "json", "label": "Body JSON"},
            {"key": "query_params", "type": "json", "label": "Query params (JSON)"},
            {"key": "timeout_seconds", "type": "number", "label": "Timeout (s)", "placeholder": "30"},
        ),
    ),
    "notification": NodeTypeMeta(
        type="notification",
        cls=NotificationNode,
        label="Notificacao",
        category="integracao",
        description=(
            "Registra uma notificacao no workflow. MVP suporta canal `log`. "
            "Email vira na proxima iteracao."
        ),
        available=True,
        icon="RiNotification3Line",
        config_schema=(
            {"key": "channel", "type": "string", "label": "Canal", "placeholder": "log", "required": True},
            {"key": "to", "type": "string", "label": "Destinatario", "placeholder": "{{trigger.analyst_email}}"},
            {"key": "subject", "type": "string", "label": "Assunto"},
            {"key": "body", "type": "text", "label": "Corpo da mensagem", "required": True},
        ),
    ),
    # ─── Output ──────────────────────────────────────────────────────────
    "output_generator": NodeTypeMeta(
        type="output_generator",
        cls=OutputGeneratorNode,
        label="Gerar Output",
        category="output",
        description="Gera o artefato final do dossie (PDF, JSON).",
        available=True,
        icon="RiFilePdf2Line",
    ),
}


def get_node_class(node_type: str) -> type[BaseNode]:
    """Return the BaseNode subclass for a given type identifier.

    Raises ValueError if the type is unknown OR marked `available=False`.
    """
    meta = NODE_TYPES.get(node_type)
    if meta is None:
        raise ValueError(
            f"Tipo de no '{node_type}' nao registrado. "
            f"Conhecidos: {sorted(NODE_TYPES.keys())}"
        )
    if not meta.available:
        raise ValueError(
            f"Tipo de no '{node_type}' esta marcado como 'em breve' e ainda "
            "nao pode ser executado."
        )
    return meta.cls
