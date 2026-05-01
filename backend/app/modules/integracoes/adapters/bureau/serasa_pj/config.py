"""SerasaPjConfig: parametros de integracao lidos de `tenant_source_config.config`.

A7 Credit e cliente distribuidor da Serasa Experian. Contrato exige:
    - HTTP Basic Auth (clientID:clientSecret) no login que emite Access Token.
    - Header `X-Retailer-Document-Id` em toda chamada de relatorio (CNPJ do
      consultante real). Sem ele, consumo conta para a A7 (default da Serasa).
    - Score model forcado: `H4PJ`.

Modelo de credencial: 1 por tenant — diferente do QiTech que tem 1 por UA.
Toda UA do tenant compartilha a mesma credencial Serasa, e usa o mesmo
`retailer_document_id` (decisao 2026-05-01: fixo no tenant).

Auth model: OAuth2 Client Credentials via HTTP Basic Authentication.
    POST {base_url}/security/iam/v1/client-identities/login
    Header: Authorization: Basic base64(client_id:client_secret)
    Response: { "AcessToken": "...", "ExpiresIn": "3600" }   (sic — "AcessToken")
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_BASE_URL = "https://api.serasaexperian.com.br"
DEFAULT_BASE_URL_UAT = "https://uat-api.serasaexperian.com.br"

# A Serasa cobra TTL de ~1h no token. O TTL real vem do campo `ExpiresIn` da
# resposta de login (em segundos, como string); o config so define um teto
# conservador para invalidar mesmo que o ExpiresIn venha alto demais.
DEFAULT_TOKEN_TTL_SECONDS = 3600
DEFAULT_TOKEN_REFRESH_SKEW_SECONDS = 60

# Modelo de score forcado para A7 (distribuidor). Valores alternativos
# (HLRD para PF) nao se aplicam aqui.
DEFAULT_SCORE_MODEL_PJ = "H4PJ"

# Tipo de relatorio padrao no MVP. Outros valores possiveis: PJ, TOP_SCORE_PJ,
# TOP_SCORE_PJ_ANALITICO, PJ_PME, PJ_PME_ANALITICO. So expandir quando o
# dossie real precisar — cada um tem custo proprio em consulta.
DEFAULT_REPORT_TYPE = "RELATORIO_AVANCADO_PJ_ANALITICO"

# Segmento de mercado autorizado pelo contrato Serasa do consultante.
# A7 Credit como distribuidor opera no segmento `028` (factoring/FIDC,
# validado contra prod 2026-05-01 — Serasa retorna 412 com a lista de
# segmentos disponiveis quando este parametro nao e informado).
DEFAULT_SEGMENT_ID = "028"


@dataclass(frozen=True)
class SerasaPjConfig:
    """Config por tenant para o adapter Serasa PJ.

    Attributes:
        base_url: URL raiz da Serasa. Producao
            (`api.serasaexperian.com.br`) ou UAT
            (`uat-api.serasaexperian.com.br`).
        client_id: identificador emitido pela Serasa Developers Portal.
            Vai no Basic Auth do request de login.
        client_secret: secret correspondente. Tratado como credencial
            sensivel — cifrado em rest via envelope.
        retailer_document_id: CNPJ (so digitos) do consultante real, vai
            no header `X-Retailer-Document-Id` em toda chamada de
            relatorio. Fixo por tenant — toda UA do tenant compartilha
            esse valor.
        score_model_pj: modelo de score PJ. Default `H4PJ` (forcado pelo
            contrato A7 distribuidor). Override so existe pra testes.
        default_report_type: tipo de relatorio default em
            `query_pj_analitico`. MVP: `RELATORIO_AVANCADO_PJ_ANALITICO`.
        token_ttl_seconds: teto local de TTL para o cache. O TTL real
            vem do `ExpiresIn` da resposta da Serasa; este campo so
            existe como guard-rail caso a Serasa devolva valor inflado.
        token_refresh_skew_seconds: janela de folga antes da expiracao
            para forcar refresh antecipado.
    """

    base_url: str = DEFAULT_BASE_URL
    client_id: str = ""
    client_secret: str = ""
    retailer_document_id: str = ""
    score_model_pj: str = DEFAULT_SCORE_MODEL_PJ
    default_report_type: str = DEFAULT_REPORT_TYPE
    default_segment_id: str = DEFAULT_SEGMENT_ID
    token_ttl_seconds: int = DEFAULT_TOKEN_TTL_SECONDS
    token_refresh_skew_seconds: int = DEFAULT_TOKEN_REFRESH_SKEW_SECONDS

    def has_credentials(self) -> bool:
        """True quando todos os campos obrigatorios estao preenchidos.

        `retailer_document_id` e tao obrigatorio quanto client_id/secret —
        sem ele, a A7 paga pela consulta no lugar do tenant.
        """
        return bool(
            self.client_id
            and self.client_secret
            and self.retailer_document_id
        )

    @classmethod
    def from_dict(cls, data: dict) -> SerasaPjConfig:
        """Materializa a config a partir do dict decifrado do envelope.

        Aceita config parcial (sem credenciais) — a UI pode salvar um
        rascunho. A validacao de presenca acontece no primeiro uso
        (`get_access_token`), nao aqui.

        `retailer_document_id` e normalizado pra so-digitos (remove pontos,
        barras, hifens) — a Serasa exige formato puro.
        """
        client_id = data.get("client_id") or ""
        client_secret = data.get("client_secret") or ""
        retailer = data.get("retailer_document_id") or ""

        if client_id and not isinstance(client_id, str):
            raise ValueError("Serasa PJ config.client_id deve ser string")
        if client_secret and not isinstance(client_secret, str):
            raise ValueError("Serasa PJ config.client_secret deve ser string")
        if retailer and not isinstance(retailer, str):
            raise ValueError(
                "Serasa PJ config.retailer_document_id deve ser string"
            )

        return cls(
            base_url=str(data.get("base_url") or DEFAULT_BASE_URL).rstrip("/"),
            client_id=str(client_id),
            client_secret=str(client_secret),
            retailer_document_id=_strip_non_digits(retailer),
            score_model_pj=str(
                data.get("score_model_pj") or DEFAULT_SCORE_MODEL_PJ
            ),
            default_report_type=str(
                data.get("default_report_type") or DEFAULT_REPORT_TYPE
            ),
            default_segment_id=str(
                data.get("default_segment_id") or DEFAULT_SEGMENT_ID
            ),
            token_ttl_seconds=int(
                data.get("token_ttl_seconds") or DEFAULT_TOKEN_TTL_SECONDS
            ),
            token_refresh_skew_seconds=int(
                data.get("token_refresh_skew_seconds")
                or DEFAULT_TOKEN_REFRESH_SKEW_SECONDS
            ),
        )


def _strip_non_digits(value: str) -> str:
    """Remove tudo que nao for digito — Serasa exige CNPJ puro."""
    return "".join(ch for ch in value if ch.isdigit())
