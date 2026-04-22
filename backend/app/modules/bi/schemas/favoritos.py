"""Schemas para a lista de fundos favoritos do usuario (BI/Benchmark)."""

from datetime import datetime

from pydantic import BaseModel, Field


class FavoritoItem(BaseModel):
    """Um fundo favoritado. `denom_social` vem de `cvm_remote.tab_i` (pode ser
    None se o CNPJ favoritado nao existir mais na ultima competencia CVM)."""

    cnpj: str = Field(description="CNPJ digits-only (14 digitos)")
    denom_social: str | None = Field(default=None, description="Denominacao social CVM")
    created_at: datetime = Field(description="Quando o usuario favoritou")


class FavoritosLista(BaseModel):
    """Lista completa de favoritos do usuario logado (sem paginacao)."""

    favoritos: list[FavoritoItem]
    total: int
