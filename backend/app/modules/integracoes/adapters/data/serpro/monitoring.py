"""Monitoramento de NF-e via SERPRO Push (F3) -- enrolamento, inscricao,

renovacao, auditoria de entrega e processamento de pings.

Regras operacionais (validadas contra a doc/API em 2026-07-10):
- 1 solicitacao push = 1..500 chaves, validade 30 dias, SEM renovacao
  automatica — job re-inscreve chaves ativas ~5 dias antes de expirar.
- O ping NAO diz qual evento ocorreu — dispara GET /v1/nfe/{chave}
  (cobrado) que atualiza bronze+silver.
- Ping perdido (URL fora do ar) NAO e reenviado — a auditoria de entrega
  (GET /push/solicitacoes/{id}: `entregue`/`dataEntrega` por chave) pesca
  avisos que nao processamos.
- Latencia de propagacao SEFAZ->distribuicao existe (validado 2026-07-10):
  o monitoramento nao assume tempo-real absoluto.

Token do receiver: o SERPRO nao assina os POSTs; a defesa e um token
estatico embutido na urlNotificacao (derivavel de QITECH_WEBHOOK_SECRET
quando SERPRO_WEBHOOK_SECRET nao esta setado — zero mudanca de env).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.data.serpro.client import SerproClient
from app.modules.integracoes.adapters.data.serpro.config import SerproConfig
from app.modules.integracoes.adapters.data.serpro.errors import SerproError
from app.modules.integracoes.adapters.data.serpro.etl import consultar_e_persistir
from app.modules.integracoes.adapters.data.serpro.version import ADAPTER_VERSION
from app.modules.integracoes.models.serpro_nfe_monitor import SerproNfeMonitor
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.warehouse.nfe_estado import NfeSituacao
from app.warehouse.titulo import Titulo
from app.warehouse.titulo_fiscal import WhTituloFiscal

logger = logging.getLogger(__name__)

# Solicitacao vale 30d; re-inscrever quando faltar menos que isto.
RENOVAR_ANTES_DE = timedelta(days=5)
SOLICITACAO_VALIDADE = timedelta(days=30)
# Rate limit de reconsulta por ping (spoof/dupla entrega no maximo
# provoca 1 consulta por chave por janela).
MIN_INTERVALO_ENTRE_CONSULTAS = timedelta(minutes=5)
_BATCH_PUSH = 500

# Situacoes do silver que disparam alerta em chave monitorada.
SITUACOES_CRITICAS = {"cancelada", "cancelada_fora_prazo", "denegada"}

# Regra de escopo (decisao Ricardo 2026-07-11): titulo EM ABERTO no ERP
# (wh_titulo.situacao=0) => vigia a chave da nota que o lastreia
# (wh_titulo_fiscal). Vencimento NAO importa: titulo vencido em aberto
# continua vigiado; titulo liquidado/baixado/recomprado sai.
MOTIVO_TITULO_EM_ABERTO = "titulo_em_aberto"
SITUACAO_TITULO_EM_ABERTO = 0  # espelha conciliacao_boleto.SITUACAO_EM_ABERTO


# ---- Token do receiver ------------------------------------------------------


def webhook_token() -> str:
    """Token estatico esperado na query da urlNotificacao cadastrada."""
    settings = get_settings()
    secret = settings.SERPRO_WEBHOOK_SECRET or settings.QITECH_WEBHOOK_SECRET
    if not secret:
        return ""
    return hmac.new(
        secret.encode(), b"serpro-nfe-push", hashlib.sha256
    ).hexdigest()[:40]


def verify_webhook_token(token: str) -> bool:
    expected = webhook_token()
    if not expected:
        # DEV sem secret configurado: aceita (paridade com QiTech receiver).
        return True
    return hmac.compare_digest(token or "", expected)


def build_notification_url() -> str:
    """URL completa a cadastrar no SERPRO (POST/PUT /push/clientes)."""
    settings = get_settings()
    base = (
        settings.SERPRO_WEBHOOK_BASE_URL or settings.QITECH_WEBHOOK_BASE_URL
    ).rstrip("/")
    if not base:
        raise SerproError(
            "SERPRO_WEBHOOK_BASE_URL/QITECH_WEBHOOK_BASE_URL nao configuradas."
        )
    return (
        f"{base}/api/v1/integracoes/webhooks/serpro/nfe-push"
        f"?token={webhook_token()}"
    )


# ---- Client por tenant ------------------------------------------------------


async def build_client_config(db: AsyncSession, tenant_id: UUID) -> SerproConfig:
    """Resolve a credencial do tenant (tenant_source_config, cifrada)."""
    # Import local: source_config importa services que importam models amplos.
    from app.modules.integracoes.services.source_config import get_decrypted_config

    plain = await get_decrypted_config(
        db, tenant_id, SourceType.DATA_SERPRO_NFE, Environment.PRODUCTION
    )
    if plain is None:
        raise SerproError(
            f"Tenant {tenant_id} sem config DATA_SERPRO_NFE ativa."
        )
    return SerproConfig.from_dict(plain)


# ---- Enrolamento (escopo: titulo em aberto) ---------------------------------


def _escopo_titulos_abertos(tenant_id: UUID) -> sa.Select:
    """Chaves lastreando titulo EM ABERTO: wh_titulo (situacao=0) via ponte
    wh_titulo_fiscal. Vencimento e informativo (referencia_vencimento)."""
    return (
        sa.select(
            Titulo.tenant_id,
            WhTituloFiscal.chave_acesso,
            sa.literal(MOTIVO_TITULO_EM_ABERTO).label("motivo"),
            sa.cast(
                sa.func.max(Titulo.data_de_vencimento_efetiva), sa.Date
            ).label("referencia_vencimento"),
        )
        .join(
            WhTituloFiscal,
            sa.and_(
                WhTituloFiscal.tenant_id == Titulo.tenant_id,
                WhTituloFiscal.titulo_id == Titulo.titulo_id,
            ),
        )
        .where(
            Titulo.tenant_id == tenant_id,
            Titulo.situacao == SITUACAO_TITULO_EM_ABERTO,
        )
        .group_by(Titulo.tenant_id, WhTituloFiscal.chave_acesso)
    )


async def enrolar_chaves_no_escopo(db: AsyncSession, tenant_id: UUID) -> int:
    """Insere no monitor as chaves de titulos em aberto ainda nao vigiadas.

    Idempotente (ON CONFLICT DO NOTHING no UQ tenant+chave). Tambem
    REATIVA monitor encerrado cuja chave voltou ao escopo (titulo
    reaberto/estorno de baixa) — exceto nota_morta (alerta ja disparado;
    nota cancelada nao ressuscita). Nao commita.
    """
    # gen_random_uuid() DENTRO do SELECT: com include_defaults o SQLAlchemy
    # injetaria o default Python do `id` como CONSTANTE (mesmo UUID para
    # todas as linhas) — estoura a PK com 2+ chaves (bug pego na ativacao).
    sub = _escopo_titulos_abertos(tenant_id).subquery()
    escopo = sa.select(
        sa.func.gen_random_uuid().label("id"),
        sub.c.tenant_id,
        sub.c.chave_acesso,
        sub.c.motivo,
        sub.c.referencia_vencimento,
    )
    stmt = (
        pg_insert(SerproNfeMonitor)
        .from_select(
            ["id", "tenant_id", "chave_acesso", "motivo", "referencia_vencimento"],
            escopo,
            include_defaults=False,
        )
        .on_conflict_do_nothing(
            constraint="uq_serpro_nfe_monitor_tenant_chave"
        )
    )
    result = await db.execute(stmt)
    novos = result.rowcount or 0

    escopo_chaves = sa.select(
        _escopo_titulos_abertos(tenant_id).subquery().c.chave_acesso
    )
    reativados = (
        await db.execute(
            sa.update(SerproNfeMonitor)
            .where(
                SerproNfeMonitor.tenant_id == tenant_id,
                SerproNfeMonitor.ativo.is_(False),
                SerproNfeMonitor.encerrado_motivo != "nota_morta",
                SerproNfeMonitor.chave_acesso.in_(escopo_chaves),
            )
            .values(
                ativo=True,
                encerrado_em=None,
                encerrado_motivo=None,
                # Forca re-inscricao no push no mesmo tick.
                solicitacao_id=None,
                solicitacao_expira_em=None,
            )
        )
    ).rowcount or 0

    if novos or reativados:
        logger.info(
            "serpro monitor: %d chaves enroladas, %d reativadas (tenant=%s)",
            novos,
            reativados,
            tenant_id,
        )
    return novos + reativados


async def encerrar_fora_do_escopo(db: AsyncSession, tenant_id: UUID) -> int:
    """Desativa chaves sem titulo em aberto (liquidado/baixado) ou nota morta.

    Regra (Ricardo 2026-07-11): a permanencia e governada pelo ESTADO do
    titulo, nao pelo calendario — titulo vencido em aberto segue vigiado.
    """
    agora = datetime.now(UTC)
    escopo_chaves = sa.select(
        _escopo_titulos_abertos(tenant_id).subquery().c.chave_acesso
    )
    result = await db.execute(
        sa.update(SerproNfeMonitor)
        .where(
            SerproNfeMonitor.tenant_id == tenant_id,
            SerproNfeMonitor.ativo.is_(True),
            sa.or_(
                SerproNfeMonitor.ultima_situacao.in_(SITUACOES_CRITICAS),
                SerproNfeMonitor.chave_acesso.not_in(escopo_chaves),
            ),
        )
        .values(
            ativo=False,
            encerrado_em=agora,
            encerrado_motivo=sa.case(
                (
                    SerproNfeMonitor.ultima_situacao.in_(SITUACOES_CRITICAS),
                    "nota_morta",
                ),
                else_="titulo_encerrado",
            ),
        )
    )
    return result.rowcount or 0


# ---- Inscricao / renovacao no push ------------------------------------------


async def inscrever_pendentes(
    db: AsyncSession, client: SerproClient, tenant_id: UUID
) -> int:
    """Inscreve no push as chaves ativas sem solicitacao valida (batch 500)."""
    agora = datetime.now(UTC)
    limite_renovacao = agora + RENOVAR_ANTES_DE
    pendentes = (
        (
            await db.execute(
                sa.select(SerproNfeMonitor)
                .where(
                    SerproNfeMonitor.tenant_id == tenant_id,
                    SerproNfeMonitor.ativo.is_(True),
                    sa.or_(
                        SerproNfeMonitor.solicitacao_id.is_(None),
                        SerproNfeMonitor.solicitacao_expira_em < limite_renovacao,
                    ),
                )
                .order_by(SerproNfeMonitor.referencia_vencimento)
            )
        )
        .scalars()
        .all()
    )
    if not pendentes:
        return 0

    inscritas = 0
    for i in range(0, len(pendentes), _BATCH_PUSH):
        lote = pendentes[i : i + _BATCH_PUSH]
        try:
            resp = await client.push_criar_solicitacao(
                [m.chave_acesso for m in lote]
            )
        except SerproError as e:
            logger.warning("serpro push: falha ao inscrever lote: %s", e)
            continue
        solicitacao_id = str(
            resp.get("solicitacaoId") or resp.get("id") or ""
        )
        expira = agora + SOLICITACAO_VALIDADE
        for m in lote:
            m.solicitacao_id = solicitacao_id or None
            m.solicitacao_expira_em = expira
        inscritas += len(lote)

    if inscritas:
        db.add(
            DecisionLog(
                tenant_id=tenant_id,
                decision_type=DecisionType.SYNC,
                rule_or_model="serpro_push",
                rule_or_model_version=ADAPTER_VERSION,
                inputs_ref={"acao": "inscrever", "qtd": inscritas},
                output={"solicitacoes": (inscritas + _BATCH_PUSH - 1) // _BATCH_PUSH},
                explanation="Chaves inscritas na monitoracao push do SERPRO",
                triggered_by="serpro:monitor",
            )
        )
        await db.flush()
    return inscritas


# ---- Processamento de ping / consulta monitorada ---------------------------


@dataclass(slots=True)
class PingResult:
    accepted: bool
    reason: str
    chave: str
    consultado: bool = False
    situacao: str | None = None
    alerta: bool = False
    tenants: list[UUID] = field(default_factory=list)


async def _alertar_se_critico(
    db: AsyncSession, monitor: SerproNfeMonitor, situacao: str
) -> bool:
    """Grava ALERT no decision_log quando nota vigiada morre (1x por chave)."""
    if situacao not in SITUACOES_CRITICAS or monitor.alertado_em is not None:
        return False
    agora = datetime.now(UTC)
    db.add(
        DecisionLog(
            tenant_id=monitor.tenant_id,
            decision_type=DecisionType.ALERT,
            rule_or_model="serpro_monitor",
            rule_or_model_version=ADAPTER_VERSION,
            inputs_ref={
                "chave": monitor.chave_acesso,
                "motivo_monitoramento": monitor.motivo,
                "referencia_vencimento": (
                    monitor.referencia_vencimento.isoformat()
                    if monitor.referencia_vencimento
                    else None
                ),
            },
            output={"situacao": situacao},
            explanation=(
                f"NF-e monitorada mudou para '{situacao}' com duplicata a "
                "vencer — possivel perda de lastro pos-cessao."
            ),
            triggered_by="serpro:monitor",
        )
    )
    monitor.alertado_em = agora
    logger.warning(
        "serpro ALERTA: chave=%s situacao=%s (tenant=%s)",
        monitor.chave_acesso,
        situacao,
        monitor.tenant_id,
    )
    return True


async def consultar_chave_monitorada(
    db: AsyncSession,
    client: SerproClient,
    monitor: SerproNfeMonitor,
    *,
    trigger: str,
) -> str | None:
    """Consulta + persiste + atualiza telemetria + alerta. Retorna situacao."""
    await consultar_e_persistir(
        db,
        client,
        tenant_id=monitor.tenant_id,
        chave=monitor.chave_acesso,
        trigger=trigger,
        request_tag=f"monitor:{trigger}"[:32],
    )
    situacao = (
        await db.execute(
            sa.select(NfeSituacao.situacao).where(
                NfeSituacao.tenant_id == monitor.tenant_id,
                NfeSituacao.chave_acesso == monitor.chave_acesso,
            )
        )
    ).scalar_one_or_none()
    monitor.ultima_consulta_em = datetime.now(UTC)
    if situacao:
        monitor.ultima_situacao = situacao
        await _alertar_se_critico(db, monitor, situacao)
    await db.flush()
    return situacao


async def processar_ping(
    db: AsyncSession, *, chave: str, data_hora_envio: str
) -> PingResult:
    """Processa um POST do SERPRO na nossa urlNotificacao.

    A chave pode estar monitorada por N tenants (mesma nota em dois
    fundos nao acontece hoje, mas o modelo permite) — processa todos.
    Commita ao final de cada tenant processado.
    """
    monitores = (
        (
            await db.execute(
                sa.select(SerproNfeMonitor).where(
                    SerproNfeMonitor.chave_acesso == chave,
                    SerproNfeMonitor.ativo.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    if not monitores:
        logger.info("serpro ping para chave nao monitorada: %s", chave)
        return PingResult(accepted=True, reason="chave_nao_monitorada", chave=chave)

    agora = datetime.now(UTC)
    consultado = False
    situacao: str | None = None
    alerta = False
    for monitor in monitores:
        monitor.ultima_notificacao_em = agora
        # Rate limit: dupla entrega/spoof nao gera consulta em rajada.
        if (
            monitor.ultima_consulta_em is not None
            and agora - monitor.ultima_consulta_em < MIN_INTERVALO_ENTRE_CONSULTAS
        ):
            logger.info(
                "serpro ping rate-limited chave=%s (consultada ha <%s)",
                chave,
                MIN_INTERVALO_ENTRE_CONSULTAS,
            )
            continue
        try:
            config = await build_client_config(db, monitor.tenant_id)
            async with SerproClient(config=config) as client:
                alertado_antes = monitor.alertado_em
                situacao = await consultar_chave_monitorada(
                    db, client, monitor, trigger="webhook"
                )
                alerta = alerta or (monitor.alertado_em != alertado_antes)
            consultado = True
        except SerproError as e:
            # Tenant sem config/erro no gateway nao derruba o receiver —
            # a auditoria de entrega recupera este aviso no proximo tick.
            logger.warning(
                "serpro ping: consulta falhou chave=%s tenant=%s: %s",
                chave,
                monitor.tenant_id,
                e,
            )
        await db.commit()

    return PingResult(
        accepted=True,
        reason="ok" if consultado else "rate_limited",
        chave=chave,
        consultado=consultado,
        situacao=situacao,
        alerta=alerta,
        tenants=[m.tenant_id for m in monitores],
    )


# ---- Auditoria de entrega (pesca pings perdidos) ----------------------------


async def auditar_entregas(
    db: AsyncSession, client: SerproClient, tenant_id: UUID
) -> int:
    """Compara `entregue`/`dataEntrega` das solicitacoes com o que processamos.

    Aviso entregue pelo SERPRO depois da nossa ultima consulta = ping que
    nao viramos consulta (URL fora do ar, deploy, etc) -> reconsulta.
    Retorna quantas chaves foram recuperadas.
    """
    solicitacoes = (
        (
            await db.execute(
                sa.select(SerproNfeMonitor.solicitacao_id)
                .where(
                    SerproNfeMonitor.tenant_id == tenant_id,
                    SerproNfeMonitor.ativo.is_(True),
                    SerproNfeMonitor.solicitacao_id.is_not(None),
                )
                .distinct()
            )
        )
        .scalars()
        .all()
    )
    recuperadas = 0
    for sol_id in solicitacoes:
        try:
            detalhe = await client.push_consultar_solicitacao(sol_id)
        except SerproError as e:
            logger.warning("serpro auditoria: solicitacao %s: %s", sol_id, e)
            continue
        for item in detalhe.get("chavesMonitoracao") or []:
            if not isinstance(item, dict):
                continue
            entregue = str(item.get("entregue") or "").lower() in ("true", "1", "sim")
            if not entregue:
                continue
            chave = str(item.get("chave") or "")
            monitor = (
                await db.execute(
                    sa.select(SerproNfeMonitor).where(
                        SerproNfeMonitor.tenant_id == tenant_id,
                        SerproNfeMonitor.chave_acesso == chave,
                        SerproNfeMonitor.ativo.is_(True),
                    )
                )
            ).scalar_one_or_none()
            if monitor is None:
                continue
            data_entrega = _parse_dt(item.get("dataEntrega"))
            if (
                data_entrega is not None
                and monitor.ultima_consulta_em is not None
                and data_entrega <= monitor.ultima_consulta_em
            ):
                continue  # ja processamos esse aviso
            await consultar_chave_monitorada(db, client, monitor, trigger="sweep")
            recuperadas += 1
    return recuperadas


def _parse_dt(value: object) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


# ---- Ciclo completo (chamado pelo scheduler) --------------------------------


async def ciclo_monitoramento(db: AsyncSession, tenant_id: UUID) -> dict[str, int]:
    """Um tick do job: enrola -> encerra -> inscreve/renova -> audita."""
    novos = await enrolar_chaves_no_escopo(db, tenant_id)
    encerrados = await encerrar_fora_do_escopo(db, tenant_id)
    inscritas = recuperadas = 0
    config = await build_client_config(db, tenant_id)
    async with SerproClient(config=config) as client:
        # Guard: inscrever chaves sem urlNotificacao cadastrada mandaria os
        # pings pro nada. Setup e manual (scripts/serpro_push_setup.py
        # --register) porque muta o contrato SERPRO compartilhado.
        cliente_push = await client.push_consultar_cliente()
        if not (cliente_push or {}).get("urlNotificacao"):
            logger.warning(
                "serpro monitor: push sem urlNotificacao cadastrada — "
                "rode scripts/serpro_push_setup.py --register (tenant=%s)",
                tenant_id,
            )
        else:
            inscritas = await inscrever_pendentes(db, client, tenant_id)
            recuperadas = await auditar_entregas(db, client, tenant_id)
    await db.commit()
    stats = {
        "enroladas": novos,
        "encerradas": encerrados,
        "inscritas": inscritas,
        "recuperadas": recuperadas,
    }
    logger.info("serpro monitor tick tenant=%s %s", tenant_id, stats)
    return stats
