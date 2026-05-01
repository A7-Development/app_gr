"""QiTechConfig: parametros de integracao lidos de `tenant_source_config.config`.

Cada tenant tem seu proprio contrato com a QiTech — base_url, credenciais
(client_id + client_secret) e (opcionalmente) lifetime do token. O adapter
recebe o dict decifrado do envelope e materializa essa dataclass; zero leitura
de variavel de ambiente.

Auth model: OAuth2 Client Credentials via HTTP Basic Authentication.
    POST {base_url}/v2/painel/token/api
    Header: Authorization: Basic base64(client_id:client_secret)
    Response: { "apiToken": "..." }
"""

from __future__ import annotations

from dataclasses import dataclass, field

DEFAULT_BASE_URL = "https://api-portal.singulare.com.br"
# Margem de seguranca para trocar o token antes de expirar (em segundos).
# Muitas APIs emitem tokens de 1h; 60s de folga evita race condition na virada.
DEFAULT_TOKEN_TTL_SECONDS = 3600
DEFAULT_TOKEN_REFRESH_SKEW_SECONDS = 60


@dataclass(frozen=True)
class QiTechBankAccount:
    """Conta-corrente da UA acessivel via familia /v2/bank-account/* da QiTech.

    Cada item representa uma conta da entidade administrada (UA) na Singulare.
    O CNPJ titular da conta vem implicitamente da UA dona da config (via
    `tenant_source_config.unidade_administrativa_id`) — nao se cadastra aqui
    para nao duplicar fonte de verdade.

    Attributes:
        agencia: codigo da agencia da Singulare como aparece no path da
            QiTech, zero-padded a 4 digitos (ex.: "0001"). String literal —
            viaja exatamente como cadastrado, sem normalizacao do adapter.
            Admin e responsavel por cadastrar conforme a Singulare aceita
            (validado em 2026-05-01: agencia "0001" funcionou no statement).
        conta: numero da conta-corrente (sem digito verificador, como a
            QiTech espera no path).
        label: apelido amigavel para exibir na UI ("Conta principal",
            "Cobranca", "Garantia"). Nao viaja para a QiTech.
        enabled: permite desativar uma conta sem deletar — preserva
            historico de syncs anteriores e evita perder o registro quando
            a conta e fechada / migrada.
    """

    agencia: str
    conta: str
    label: str = ""
    enabled: bool = True

    @classmethod
    def from_dict(cls, data: dict) -> QiTechBankAccount:
        agencia = data.get("agencia")
        conta = data.get("conta")
        if not isinstance(agencia, str) or not agencia:
            raise ValueError(
                "QiTechBankAccount.agencia deve ser string nao-vazia"
            )
        if not isinstance(conta, str) or not conta:
            raise ValueError(
                "QiTechBankAccount.conta deve ser string nao-vazia"
            )
        label = data.get("label") or ""
        if not isinstance(label, str):
            raise ValueError("QiTechBankAccount.label deve ser string")
        enabled = data.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("QiTechBankAccount.enabled deve ser bool")
        return cls(
            agencia=agencia,
            conta=conta,
            label=label,
            enabled=enabled,
        )


@dataclass(frozen=True)
class QiTechConfig:
    """Config por tenant para o adapter QiTech.

    Attributes:
        base_url: URL raiz da API QiTech. Cada tenant pode apontar para
            producao ou homologacao independentemente.
        client_id: identificador emitido pela QiTech ao tenant. Vai no
            Basic Auth do request de token.
        client_secret: secret correspondente ao client_id. Tratado como
            credencial sensivel (cifrada em rest via envelope).
        token_ttl_seconds: quanto tempo o token permanece no cache antes
            do refresh forcado. Override so se a QiTech confirmar TTL
            diferente para o tenant.
        token_refresh_skew_seconds: janela de folga antes da expiracao para
            disparar refresh antecipado.
        bank_accounts: contas-corrente da UA acessiveis via familia
            /v2/bank-account/balance e /v2/bank-account/statement. Tupla
            (imutavel) consistente com `frozen=True`. Default vazio — UA
            sem conta cadastrada continua valida (so nao consulta saldo /
            extrato; demais endpoints da QiTech seguem funcionando).
    """

    base_url: str = DEFAULT_BASE_URL
    client_id: str = ""
    client_secret: str = ""
    token_ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS
    token_refresh_skew_seconds: int = DEFAULT_TOKEN_REFRESH_SKEW_SECONDS
    bank_accounts: tuple[QiTechBankAccount, ...] = field(default_factory=tuple)

    def has_credentials(self) -> bool:
        """True quando client_id e client_secret estao ambos preenchidos."""
        return bool(self.client_id) and bool(self.client_secret)

    def enabled_bank_accounts(self) -> tuple[QiTechBankAccount, ...]:
        """Subset de bank_accounts com `enabled=True`. Atalho para os ETLs
        de saldo/extrato iterarem sem precisar filtrar a cada chamada."""
        return tuple(a for a in self.bank_accounts if a.enabled)

    @classmethod
    def from_dict(cls, data: dict) -> QiTechConfig:
        """Materializa a config a partir do dict decifrado do envelope.

        Aceita base_url sem credenciais (draft configs). A validacao de
        presenca das credenciais acontece no primeiro uso (get_api_token),
        nao aqui — assim a UI consegue salvar uma config parcial.
        """
        # Retrocompat: ate 2026-04-24 gravavamos `credentials: {...}` em
        # vez de client_id/client_secret. Se vier, mergeia antes de ler.
        legacy = data.get("credentials")
        if isinstance(legacy, dict):
            merged: dict = {**legacy, **data}
        else:
            merged = dict(data)

        client_id = merged.get("client_id") or ""
        client_secret = merged.get("client_secret") or ""

        if client_id and not isinstance(client_id, str):
            raise ValueError("QiTech config.client_id deve ser string")
        if client_secret and not isinstance(client_secret, str):
            raise ValueError("QiTech config.client_secret deve ser string")

        raw_accounts = merged.get("bank_accounts") or []
        if not isinstance(raw_accounts, list):
            raise ValueError(
                "QiTech config.bank_accounts deve ser lista de objetos"
            )
        accounts = tuple(
            QiTechBankAccount.from_dict(item) for item in raw_accounts
        )

        return cls(
            base_url=str(merged.get("base_url") or DEFAULT_BASE_URL).rstrip("/"),
            client_id=str(client_id),
            client_secret=str(client_secret),
            token_ttl_seconds=int(
                merged.get("token_ttl_seconds") or DEFAULT_TOKEN_TTL_SECONDS
            ),
            token_refresh_skew_seconds=int(
                merged.get("token_refresh_skew_seconds")
                or DEFAULT_TOKEN_REFRESH_SKEW_SECONDS
            ),
            bank_accounts=accounts,
        )
