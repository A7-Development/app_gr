"""Curadoria de liquidacoes + administracao do modelo de deteccao.

GET  /risco/curadoria-liquidacoes                     -> pagina (TODAS as liquidacoes,
                                                         score + regra dura + tag vigente)
POST /risco/curadoria-liquidacoes/{id}/tag            -> veredito humano (append-only)
GET  /risco/deteccao/modelos                          -> catalogo + versoes + ativa
POST /risco/deteccao/modelos/{nome}/treinar           -> treina versao nova (nasce INATIVA)
POST /risco/deteccao/modelos/{nome}/versoes/{v}/ativar-> ativa versao (rollback = ativar antiga)
POST /risco/deteccao/modelos/{nome}/pontuar           -> "forcar agora" do scoring (§7.3)

Permissoes: leitura READ; tag WRITE; treino/ativacao/pontuacao ADMIN.
"""

from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.enums import Module, Permission
from app.core.module_guard import require_module
from app.core.tenant_middleware import RequestPrincipal, get_current_principal
from app.modules.risco.models import (
    DeteccaoModelo,
    DeteccaoModeloAtivo,
    DeteccaoModeloVersao,
)
from app.modules.risco.schemas.deteccao import (
    CuradoriaTagCreate,
    CuradoriaTagOut,
    LiquidacaoCuradoriaPage,
    MemoriaLiquidacao,
    ModeloOut,
    ModeloVersaoOut,
    ScoringResult,
    TreinoRequest,
    TreinoResult,
)
from app.modules.risco.services import curadoria_liquidacao as svc
from app.modules.risco.services.cedente_risco import consolidar
from app.modules.risco.services.curadoria_memoria import montar_memoria
from app.modules.risco.services.deteccao_scoring import pontuar
from app.modules.risco.services.deteccao_treino import treinar
from app.shared.audit_log.decision_log import DecisionLog, DecisionType

router = APIRouter(tags=["risco:curadoria-liquidacoes"])

_GuardRead = Depends(require_module(Module.RISCO, Permission.READ))
_GuardWrite = Depends(require_module(Module.RISCO, Permission.WRITE))
_GuardAdmin = Depends(require_module(Module.RISCO, Permission.ADMIN))


@router.get("/curadoria-liquidacoes", response_model=LiquidacaoCuradoriaPage)
async def list_liquidacoes(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=10, le=200)] = 50,
    data_ini: date | None = None,
    data_fim: date | None = None,
    produto_sigla: str | None = None,
    cedente: str | None = None,
    sacado: str | None = None,
    documento: str | None = None,
    situacao_titulo: Annotated[int | None, Query(ge=0, le=9)] = None,
    tag: Annotated[str | None, Query(pattern="^(fraude|ok|sem_tag)$")] = None,
    score_min: Annotated[float | None, Query(ge=0, le=1)] = None,
    regra_dura: bool = False,
    sugeridos: bool = False,
    _: None = _GuardRead,
) -> LiquidacaoCuradoriaPage:
    resultado = await svc.listar_liquidacoes(
        db,
        principal.tenant_id,
        page=page,
        page_size=page_size,
        data_ini=data_ini,
        data_fim=data_fim,
        produto_sigla=produto_sigla,
        cedente_busca=cedente,
        sacado_busca=sacado,
        documento_busca=documento,
        situacao_titulo=situacao_titulo,
        tag=tag,
        score_min=score_min,
        somente_regra_dura=regra_dura,
        somente_sugeridos=sugeridos,
    )
    return LiquidacaoCuradoriaPage(**resultado)


@router.get(
    "/curadoria-liquidacoes/{liquidacao_id}",
    response_model=MemoriaLiquidacao,
)
async def detalhe_liquidacao(
    liquidacao_id: UUID,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardRead,
) -> MemoriaLiquidacao:
    """Memoria de calculo completa de uma liquidacao (evidencia por secao)."""
    memoria = await montar_memoria(db, principal.tenant_id, liquidacao_id)
    if memoria is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Liquidacao nao encontrada neste tenant.",
        )
    return MemoriaLiquidacao(**memoria)


@router.post(
    "/curadoria-liquidacoes/{liquidacao_id}/tag",
    response_model=CuradoriaTagOut,
    status_code=status.HTTP_201_CREATED,
)
async def criar_tag(
    liquidacao_id: UUID,
    body: CuradoriaTagCreate,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardWrite,
) -> CuradoriaTagOut:
    registro = await svc.registrar_tag(
        db,
        principal.tenant_id,
        liquidacao_id,
        tag=body.tag,
        nota=body.nota,
        autor=principal.user_id,
    )
    if registro is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Liquidacao nao encontrada neste tenant.",
        )
    db.add(
        DecisionLog(
            tenant_id=principal.tenant_id,
            decision_type=DecisionType.RULE_EVALUATION,
            inputs_ref={"liquidacao_id": str(liquidacao_id)},
            rule_or_model="curadoria_liquidacao",
            rule_or_model_version="liquidacao_boleto",
            output={"tag": body.tag, "nota": body.nota},
            explanation=f"curadoria: liquidacao marcada como {body.tag}",
            triggered_by=f"user:{principal.user_id}",
        )
    )
    await db.commit()
    return CuradoriaTagOut(
        id=registro.id,
        liquidacao_id=registro.liquidacao_id,
        tag=registro.tag,
        nota=registro.nota,
        created_at=registro.created_at,
    )


@router.get("/deteccao/modelos", response_model=list[ModeloOut])
async def list_modelos(
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardRead,
) -> list[ModeloOut]:
    modelos = (
        (
            await db.execute(
                select(DeteccaoModelo)
                .where(DeteccaoModelo.archived_at.is_(None))
                .order_by(DeteccaoModelo.nome)
            )
        )
        .scalars()
        .all()
    )
    saida: list[ModeloOut] = []
    for m in modelos:
        versoes = (
            (
                await db.execute(
                    select(DeteccaoModeloVersao)
                    .where(
                        DeteccaoModeloVersao.tenant_id == principal.tenant_id,
                        DeteccaoModeloVersao.modelo_id == m.id,
                    )
                    .order_by(DeteccaoModeloVersao.versao.desc())
                )
            )
            .scalars()
            .all()
        )
        ativo = (
            await db.execute(
                select(DeteccaoModeloAtivo.versao_id).where(
                    DeteccaoModeloAtivo.tenant_id == principal.tenant_id,
                    DeteccaoModeloAtivo.modelo_id == m.id,
                )
            )
        ).scalar_one_or_none()
        versao_ativa = next((v.versao for v in versoes if v.id == ativo), None)
        saida.append(
            ModeloOut(
                id=m.id,
                nome=m.nome,
                alvo=m.alvo,
                tipo=m.tipo,
                unidade=m.unidade,
                descricao=m.descricao,
                versao_ativa=versao_ativa,
                versoes=[
                    ModeloVersaoOut(
                        id=v.id,
                        versao=v.versao,
                        metrics=v.metrics,
                        n_amostras=v.n_amostras,
                        n_positivos=v.n_positivos,
                        trained_at=v.trained_at,
                        notas=v.notas,
                        ativa=v.id == ativo,
                    )
                    for v in versoes
                ],
            )
        )
    return saida


@router.post("/deteccao/modelos/{modelo_nome}/treinar", response_model=TreinoResult)
async def treinar_modelo(
    modelo_nome: str,
    body: TreinoRequest,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardAdmin,
) -> TreinoResult:
    try:
        resultado = await treinar(
            db,
            principal.tenant_id,
            modelo_nome=modelo_nome,
            janela_dias=body.janela_dias,
            oot_dias=body.oot_dias,
            trained_by=principal.user_id,
            triggered_by=f"user:{principal.user_id}",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    await db.commit()
    return TreinoResult(**resultado)


@router.post(
    "/deteccao/modelos/{modelo_nome}/versoes/{versao}/ativar",
    response_model=ModeloVersaoOut,
)
async def ativar_versao(
    modelo_nome: str,
    versao: int,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardAdmin,
) -> ModeloVersaoOut:
    modelo = (
        await db.execute(select(DeteccaoModelo).where(DeteccaoModelo.nome == modelo_nome))
    ).scalar_one_or_none()
    if modelo is None:
        raise HTTPException(status_code=404, detail="Modelo nao encontrado.")
    v = (
        await db.execute(
            select(DeteccaoModeloVersao).where(
                DeteccaoModeloVersao.tenant_id == principal.tenant_id,
                DeteccaoModeloVersao.modelo_id == modelo.id,
                DeteccaoModeloVersao.versao == versao,
            )
        )
    ).scalar_one_or_none()
    if v is None:
        raise HTTPException(status_code=404, detail="Versao nao encontrada.")

    ativo = (
        await db.execute(
            select(DeteccaoModeloAtivo).where(
                DeteccaoModeloAtivo.tenant_id == principal.tenant_id,
                DeteccaoModeloAtivo.modelo_id == modelo.id,
            )
        )
    ).scalar_one_or_none()
    if ativo is None:
        ativo = DeteccaoModeloAtivo(
            tenant_id=principal.tenant_id,
            modelo_id=modelo.id,
            versao_id=v.id,
            activated_by=principal.user_id,
        )
        db.add(ativo)
    else:
        ativo.versao_id = v.id
        ativo.activated_by = principal.user_id

    db.add(
        DecisionLog(
            tenant_id=principal.tenant_id,
            decision_type=DecisionType.CONFIGURATION_CHANGE,
            inputs_ref={"modelo": modelo_nome, "versao": versao},
            rule_or_model=modelo_nome,
            rule_or_model_version=f"{modelo_nome}@v{versao}",
            output={"versao_id": str(v.id)},
            explanation=f"versao v{versao} do modelo {modelo_nome} ativada",
            triggered_by=f"user:{principal.user_id}",
        )
    )
    await db.commit()
    return ModeloVersaoOut(
        id=v.id,
        versao=v.versao,
        metrics=v.metrics,
        n_amostras=v.n_amostras,
        n_positivos=v.n_positivos,
        trained_at=v.trained_at,
        notas=v.notas,
        ativa=True,
    )


@router.post("/deteccao/modelos/{modelo_nome}/pontuar", response_model=ScoringResult)
async def pontuar_agora(
    modelo_nome: str,
    principal: Annotated[RequestPrincipal, Depends(get_current_principal)],
    db: Annotated[AsyncSession, Depends(get_db)],
    _: None = _GuardAdmin,
) -> ScoringResult:
    try:
        resultado = await pontuar(
            db,
            principal.tenant_id,
            modelo_nome=modelo_nome,
            triggered_by=f"user:{principal.user_id}",
        )
        # Painel de cedentes acompanha o scoring na mesma transacao.
        await consolidar(
            db, principal.tenant_id, triggered_by=f"user:{principal.user_id}"
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return ScoringResult(**resultado)
