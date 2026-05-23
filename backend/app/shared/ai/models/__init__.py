"""SQLAlchemy models for the AI capability."""

from app.shared.ai.models.agent_config import AgentConfig
from app.shared.ai.models.agent_definition import AgentDefinition, AgentDefinitionActive
from app.shared.ai.models.agent_expertise import AgentExpertise, AgentExpertiseActive
from app.shared.ai.models.agent_persona import AgentPersona, AgentPersonaActive
from app.shared.ai.models.agent_session import AgentSession, AgentSessionStep
from app.shared.ai.models.conversation import AIConversation, AIConversationSummary
from app.shared.ai.models.credit_balance import AICreditBalance
from app.shared.ai.models.message import AIMessage
from app.shared.ai.models.permission import UserAIPermission
from app.shared.ai.models.prompt import AIPrompt, CacheStrategy
from app.shared.ai.models.prompt_active import AIPromptActive
from app.shared.ai.models.provider_credential import AIProviderCredential
from app.shared.ai.models.subscription import TenantAISubscription
from app.shared.ai.models.usage_event import AIUsageEvent

__all__ = [
    "AIConversation",
    "AIConversationSummary",
    "AICreditBalance",
    "AIMessage",
    "AIPrompt",
    "AIPromptActive",
    "AIProviderCredential",
    "AIUsageEvent",
    "AgentConfig",
    "AgentDefinition",
    "AgentDefinitionActive",
    "AgentExpertise",
    "AgentExpertiseActive",
    "AgentPersona",
    "AgentPersonaActive",
    "AgentSession",
    "AgentSessionStep",
    "CacheStrategy",
    "TenantAISubscription",
    "UserAIPermission",
]
