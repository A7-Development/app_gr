"""Registry of node-type names → BaseNode subclass.

The engine looks up the class for each node in the graph here. Adding a
new node type means: implement BaseNode subclass + register here. The
visual editor reads the same registry to populate the node palette.

Flag `available=False` to show in the palette as "em breve" — instances
of that type validate at editor save but cannot run (engine raises).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agentic.playbooks.nodes._base import BaseNode
from app.agentic.playbooks.nodes._placeholder import PlaceholderNode
from app.agentic.playbooks.nodes.bureau_query import BureauQueryNode
from app.agentic.playbooks.nodes.cadastral_enrichment import CadastralEnrichmentNode
from app.agentic.playbooks.nodes.conditional_branch import ConditionalBranchNode
from app.agentic.playbooks.nodes.consolidator import ConsolidatorNode
from app.agentic.playbooks.nodes.deterministic_check import DeterministicCheckNode
from app.agentic.playbooks.nodes.document_extractor import DocumentExtractorNode
from app.agentic.playbooks.nodes.document_request import DocumentRequestNode
from app.agentic.playbooks.nodes.http_request import HttpRequestNode
from app.agentic.playbooks.nodes.human_input import HumanInputNode
from app.agentic.playbooks.nodes.human_review import HumanReviewNode
from app.agentic.playbooks.nodes.notification import NotificationNode
from app.agentic.playbooks.nodes.output_generator import OutputGeneratorNode
from app.agentic.playbooks.nodes.specialist_agent import SpecialistAgentNode
from app.agentic.playbooks.nodes.trigger import TriggerNode


def _soon(
    *,
    type: str,
    label: str,
    category: str,
    description: str,
    icon: str,
) -> NodeTypeMeta:
    """Helper para declarar nó 'em breve' (available=False, cls=Placeholder).

    Aparece na paleta do editor com badge "EM BREVE" e drag bloqueado.
    Tentar executar levanta erro claro (ver PlaceholderNode).
    """
    return NodeTypeMeta(
        type=type,
        cls=PlaceholderNode,
        label=label,
        category=category,
        description=description,
        available=False,
        icon=icon,
    )


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
    "cadastral_enrichment": NodeTypeMeta(
        type="cadastral_enrichment",
        cls=CadastralEnrichmentNode,
        label="Enriquecimento Cadastral",
        category="integracao",
        description=(
            "Consulta cadastral da empresa-alvo via codigo neutro de dataset "
            "(public_code, ex.: CAD-PJ) e grava o silver "
            "(situacao, CNAEs, capital, fundacao) em credit_dossier_company. "
            "Resolve o provedor em runtime — o vendor nunca aparece. Alimenta "
            "o gate de elegibilidade (checks de situacao/CNAE/idade)."
        ),
        available=True,
        icon="RiBuilding4Line",
        config_schema=(
            {
                "key": "public_code",
                "type": "string",
                "label": "Dataset (codigo)",
                "placeholder": "CAD-PJ",
                "required": True,
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
    # ─── Transformar (deterministico, sem IA) ───────────────────────────
    "consolidator": NodeTypeMeta(
        type="consolidator",
        cls=ConsolidatorNode,
        label="Consolidador",
        category="transformar",
        description=(
            "Combina dados de varias etapas anteriores em um unico conjunto "
            "de saida — sem IA, regra fixa. Use quando a logica e simples "
            "(pegar valor, min, max, somar, media, concatenar, primeiro "
            "nao-nulo, tamanho). Para sintese subjetiva, use Agente "
            "Especialista. Nomes com ponto (ex.: 'cabecalho.cnpj') geram "
            "objetos aninhados na saida."
        ),
        available=True,
        icon="RiMergeCellsHorizontal",
        config_schema=(
            {
                "key": "output_fields",
                "type": "json",
                "label": "Campos de saida (lista de objetos com name/type/op/args)",
                "required": True,
            },
        ),
    ),
    # ─── Logica (n8n-style) ──────────────────────────────────────────────
    "deterministic_check": NodeTypeMeta(
        type="deterministic_check",
        cls=DeterministicCheckNode,
        label="Validacao Deterministica",
        category="logica",
        description=(
            "Roda um check deterministico (Python puro, sem IA) sobre o grafo "
            "do dossie — ex.: idade da empresa (gate de elegibilidade), soma "
            "de participacoes dos socios. Grava decision_log (RULE_EVALUATION) "
            "e materializa red_flags estruturadas. Expoe `result` (bool) pra "
            "rotear via Branch Condicional."
        ),
        available=True,
        icon="RiShieldCheckLine",
        config_schema=(
            {
                "key": "check",
                "type": "string",
                "label": "Check",
                "placeholder": "company_founding_age",
                "required": True,
            },
            {
                "key": "policy_name",
                "type": "string",
                "label": "Politica (credit_policy)",
                "placeholder": "default",
            },
            {
                "key": "tolerance_pct",
                "type": "number",
                "label": "Tolerancia (%) — checks de soma",
                "placeholder": "0.5",
            },
        ),
    ),
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

    # ═══════════════════════════════════════════════════════════════════════
    # EM BREVE — vendendo a visão de produto sem implementar agora
    # (ver _placeholder.PlaceholderNode + brief de 2026-05-02)
    # ═══════════════════════════════════════════════════════════════════════

    # ─── Triggers ─────────────────────────────────────────────────────────
    "trigger_webhook": _soon(
        type="trigger_webhook",
        label="Webhook (proposta)",
        category="triggers",
        description="Recebe nova proposta via HTTP webhook (CRM, Loja, etc).",
        icon="RiWebhookLine",
    ),
    "trigger_schedule": _soon(
        type="trigger_schedule",
        label="Agendamento (cron)",
        category="triggers",
        description="Dispara em intervalos (revisao mensal, expiracao de score, etc).",
        icon="RiTimerLine",
    ),
    "trigger_batch_csv": _soon(
        type="trigger_batch_csv",
        label="Lote via CSV/planilha",
        category="triggers",
        description="Processa lista de CPFs/CNPJs subida via planilha — uma analise por linha.",
        icon="RiFileExcel2Line",
    ),
    "trigger_public_form": _soon(
        type="trigger_public_form",
        label="Formulario publico",
        category="triggers",
        description="URL publica que o cliente final preenche pra abrir analise.",
        icon="RiFileList2Line",
    ),
    "trigger_api_inbound": _soon(
        type="trigger_api_inbound",
        label="API REST inbound",
        category="triggers",
        description="Endpoint REST autenticado para sistemas terceiros disparem analises.",
        icon="RiCodeLine",
    ),
    "trigger_crm_event": _soon(
        type="trigger_crm_event",
        label="Evento de CRM",
        category="triggers",
        description="Dispara quando ha nova oportunidade no CRM (Salesforce, HubSpot, RD).",
        icon="RiCustomerService2Line",
    ),

    # ─── Bireau ────────────────────────────────────────────────────────
    "bureau_serasa_pf": _soon(
        type="bureau_serasa_pf",
        label="Serasa PF",
        category="integracao",
        description="Consulta de pessoa fisica no Serasa (score H4PF, restricoes).",
        icon="RiUserSearchLine",
    ),
    "bureau_spc_brasil": _soon(
        type="bureau_spc_brasil",
        label="SPC Brasil",
        category="integracao",
        description="Score + restricoes via SPC Brasil (PF/PJ).",
        icon="RiDatabase2Line",
    ),
    "bureau_boa_vista": _soon(
        type="bureau_boa_vista",
        label="Boa Vista / Equifax",
        category="integracao",
        description="Score Crednet + restricoes via Boa Vista (Equifax Brasil).",
        icon="RiDatabase2Line",
    ),
    "bureau_quod": _soon(
        type="bureau_quod",
        label="Quod",
        category="integracao",
        description="Score Quod (cadastro positivo + negativo).",
        icon="RiDatabase2Line",
    ),
    "bureau_scpc": _soon(
        type="bureau_scpc",
        label="SCPC",
        category="integracao",
        description="SCPC — Sistema Central de Protecao ao Credito.",
        icon="RiDatabase2Line",
    ),

    # ─── Dados especialistas ──────────────────────────────────────────────
    "data_receita_federal": _soon(
        type="data_receita_federal",
        label="Receita Federal",
        category="integracao",
        description="Situacao CPF/CNPJ, QSA, Cartao CNPJ, atividade economica.",
        icon="RiBuilding4Line",
    ),
    "data_processos_pj": _soon(
        type="data_processos_pj",
        label="Processos PJ",
        category="integracao",
        description="Processos judiciais ativos da empresa em todas as varas.",
        icon="RiScales3Line",
    ),
    "data_protestos_pj": _soon(
        type="data_protestos_pj",
        label="Protestos PJ",
        category="integracao",
        description="Protestos em cartorios (CENPROT) consolidados nacional.",
        icon="RiAlertLine",
    ),
    "data_relacionamento_pj": _soon(
        type="data_relacionamento_pj",
        label="Relacionamento PJ",
        category="integracao",
        description="Vinculos da empresa com socios, filiais, grupos economicos.",
        icon="RiLink",
    ),
    "data_relacionamento_pf": _soon(
        type="data_relacionamento_pf",
        label="Relacionamento PF",
        category="integracao",
        description="Vinculos da pessoa fisica com empresas, parentes, conjugues.",
        icon="RiLink",
    ),
    "data_kyc_pld_pep": _soon(
        type="data_kyc_pld_pep",
        label="KYC / PLD / Listas restritivas",
        category="integracao",
        description="OFAC, COAF, ONU, PEP — listas globais de sancoes e exposicao politica.",
        icon="RiShieldCheckLine",
    ),
    "data_pep": _soon(
        type="data_pep",
        label="PEP (Pessoas Politicamente Expostas)",
        category="integracao",
        description="Verificacao especifica em base de PEPs Brasil + estendida.",
        icon="RiShieldUserLine",
    ),
    "data_scr_bacen": _soon(
        type="data_scr_bacen",
        label="SCR Bacen",
        category="integracao",
        description="Endividamento total no SFN (Sistema Financeiro Nacional) via SCR.",
        icon="RiBankLine",
    ),
    "data_open_finance": _soon(
        type="data_open_finance",
        label="Open Finance",
        category="integracao",
        description="Extrato, investimentos, compromissos via Open Finance Brasil.",
        icon="RiExchangeBoxLine",
    ),
    "data_antifraude": _soon(
        type="data_antifraude",
        label="Antifraude (ClearSale/Idwall/Caf)",
        category="integracao",
        description="Verificacao biometrica + analise de risco de fraude.",
        icon="RiFingerprint2Line",
    ),
    "data_caged_rais": _soon(
        type="data_caged_rais",
        label="CAGED / RAIS",
        category="integracao",
        description="Vinculos empregaticios formais (Ministerio do Trabalho).",
        icon="RiBriefcase4Line",
    ),
    "data_dossie_patrimonial": _soon(
        type="data_dossie_patrimonial",
        label="Dossie Patrimonial",
        category="integracao",
        description="Imoveis (cartorios), veiculos (Detran), bens declarados.",
        icon="RiHome4Line",
    ),

    # ─── Machine Learning Proprietario ────────────────────────────────────
    "ml_score_proprio": _soon(
        type="ml_score_proprio",
        label="Score Proprio",
        category="agentes",
        description="Modelo de score treinado in-house com historia do tenant.",
        icon="RiBrainLine",
    ),
    "ml_propensao_inadimplencia": _soon(
        type="ml_propensao_inadimplencia",
        label="Propensao a Inadimplencia",
        category="agentes",
        description="Probabilidade 0-100% de inadimplencia em 6/12 meses.",
        icon="RiLineChartLine",
    ),
    "ml_capacidade_pagamento": _soon(
        type="ml_capacidade_pagamento",
        label="Capacidade de Pagamento",
        category="agentes",
        description="Estima capacidade mensal de pagamento da PF/PJ via Open Finance + bureaus.",
        icon="RiHandCoinLine",
    ),
    "ml_ltv_estimado": _soon(
        type="ml_ltv_estimado",
        label="LTV Estimado",
        category="agentes",
        description="Lifetime Value previsto se aprovar o cliente.",
        icon="RiCoinsLine",
    ),
    "ml_cluster_cliente": _soon(
        type="ml_cluster_cliente",
        label="Clusterizacao de Cliente",
        category="agentes",
        description="Atribui o cliente a um perfil (cluster) pra politicas diferenciadas.",
        icon="RiPieChart2Line",
    ),
    "ml_anomalia": _soon(
        type="ml_anomalia",
        label="Deteccao de Anomalias",
        category="agentes",
        description="Flag de outliers — comportamento muito diferente do esperado pro perfil.",
        icon="RiErrorWarningLine",
    ),
    "ml_champion_challenger": _soon(
        type="ml_champion_challenger",
        label="Champion vs Challenger",
        category="agentes",
        description="A/B test entre dois modelos pra evoluir politica de credito.",
        icon="RiSwap2Line",
    ),

    # ─── Calculo e Logica ─────────────────────────────────────────────────
    "calc_custom": _soon(
        type="calc_custom",
        label="Calculadora customizavel",
        category="logica",
        description="Formula livre tipo `renda * 0.3 - dividas`.",
        icon="RiCalculatorLine",
    ),
    "calc_dti": _soon(
        type="calc_dti",
        label="Calculo DTI",
        category="logica",
        description="Debt-to-Income — divida total / renda mensal.",
        icon="RiPercentLine",
    ),
    "calc_comprometimento_renda": _soon(
        type="calc_comprometimento_renda",
        label="Comprometimento de Renda",
        category="logica",
        description="% da renda comprometida com a operacao proposta + dividas existentes.",
        icon="RiPieChartLine",
    ),
    "calc_simulador_parcelas": _soon(
        type="calc_simulador_parcelas",
        label="Simulador (Price/SAC/CET)",
        category="logica",
        description="Simula parcelas, CET, IOF, taxa efetiva (Price ou SAC).",
        icon="RiCalendarTodoLine",
    ),
    "calc_aggregator": _soon(
        type="calc_aggregator",
        label="Agregador (sum/avg/max)",
        category="logica",
        description="Funcoes de agregacao sobre listas (sum, avg, max, count).",
        icon="RiFunctionLine",
    ),
    "logic_switch": _soon(
        type="logic_switch",
        label="Switch (multiplas saidas)",
        category="logica",
        description="Roteia o fluxo em N caminhos baseado no valor de uma variavel.",
        icon="RiNodeTree",
    ),
    "logic_loop": _soon(
        type="logic_loop",
        label="Loop / For Each",
        category="logica",
        description="Itera sobre uma lista executando um sub-fluxo por item.",
        icon="RiLoopLeftLine",
    ),
    "logic_parallel": _soon(
        type="logic_parallel",
        label="Paralelo (split/join)",
        category="logica",
        description="Executa N branches simultaneamente e espera todos terminarem.",
        icon="RiParenthesesLine",
    ),
    "logic_try_catch": _soon(
        type="logic_try_catch",
        label="Try/Catch",
        category="logica",
        description="Roteia pro caminho de erro quando uma etapa falha em vez de quebrar tudo.",
        icon="RiShieldFlashLine",
    ),
    "logic_delay": _soon(
        type="logic_delay",
        label="Delay / Aguardar",
        category="logica",
        description="Pausa o fluxo por X tempo (espera reanalise, prazo de carencia, etc).",
        icon="RiTimer2Line",
    ),
    "logic_filter": _soon(
        type="logic_filter",
        label="Filtro",
        category="logica",
        description="Filtra elementos de uma lista por criterio antes de seguir.",
        icon="RiFilter3Line",
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
