"""Hierarquia de erros do adapter Infosimples (espelha bigdatacorp/errors)."""

from __future__ import annotations


class InfosimplesAdapterError(Exception):
    """Base de qualquer falha do adapter Infosimples."""


class InfosimplesAuthError(InfosimplesAdapterError):
    """Token Infosimples inválido/expirado (HTTP 401/403 ou code de auth)."""


class InfosimplesMissingFamilyCredentialError(InfosimplesAdapterError):
    """A credencial não tem o login da família de consulta (ex.: JUCESP).

    No Infosimples, consultas a portais autenticados (JUCESP, protestos)
    exigem CPF/senha PRÓPRIOS daquela família, além do token da API. Os
    campos vivem no mesmo secret da credencial (`jucesp_login_cpf`, ...).
    """

    def __init__(self, family: str) -> None:
        self.family = family
        super().__init__(
            f"Credencial Infosimples sem login da família '{family}'. "
            f"Cadastre {family}_login_cpf / {family}_login_senha na credencial "
            "(/admin/dados/provedores)."
        )


class InfosimplesHttpError(InfosimplesAdapterError):
    """HTTP não-2xx ao chamar a API."""

    def __init__(self, status_code: int, body_preview: str) -> None:
        self.status_code = status_code
        super().__init__(f"Infosimples HTTP {status_code}: {body_preview[:300]}")


class InfosimplesQueryError(InfosimplesAdapterError):
    """A API respondeu, mas a consulta não teve sucesso (code != 200).

    O `code` da Infosimples é aplicacional (200=ok; 6xx=falhas de consulta,
    ex.: site fonte fora do ar, credencial do portal inválida, sem resultado).
    """

    def __init__(self, code: int, message: str) -> None:
        self.code = code
        self.code_message = message
        super().__init__(f"Infosimples code {code}: {message}")


class InfosimplesPayloadError(InfosimplesAdapterError):
    """Resposta 200 com shape inesperado (mudança de layout do vendor)."""
