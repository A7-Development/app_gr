# Catalogo de Relatorios em Controladoria — Mapeamento (Phase 0 final)

> Output da Phase 0 do plano `~/.claude/plans/shimmering-snuggling-snail.md`. Inventario de endpoints QiTech sincronizados + decisoes aprovadas (2026-05-09).

## 1. Decisoes aprovadas

| Item | Decisao | Implicacao |
|---|---|---|
| **Tab Espelho** | **Opcao A — lente operacional** | Espelho le as MESMAS canonical tables que Padronizados. Pagina Espelho adiciona: status do ultimo sync, frescor (verde/amber/red), botao "Reprocessar agora" (so SOB_DEMANDA + WRITE+), drawer de `decision_log`. Zero tabela nova, respeita silver-only (§13.2.1). |
| **Permissao reprocessar** | **WRITE basta** em `Module.CONTROLADORIA` | `POST /<slug>/regenerate` exige `Permission.WRITE`. ADMIN nao e necessario. |
| **Label L2 sidebar** | **"Relatorios"** | Generico, escala alem de QiTech. Subtitle do PageHeader contextualiza ("Controladoria · Catalogo"). |
| **Filtro fundo** | FilterBar por pagina (§7.2) | Cada pagina de detalhe tem `FilterChip` fundo + `PeriodoPresets`. Backend resolve qual adapter foi consultado. |

## 2. Inventario de endpoints QiTech (estado atual)

### 2.1 Endpoints sincronos (12) — via `sync_dispatcher` (APScheduler)

Catalogo declarativo em [`backend/app/modules/integracoes/adapters/admin/qitech/endpoint_catalog.py`](../app/modules/integracoes/adapters/admin/qitech/endpoint_catalog.py). Per-tenant overrides em `tenant_source_endpoint_config`.

| # | endpoint_name | canonical_table | freq default | categoria |
|---|---|---|---|---|
| 1 | `market.outros_fundos` | `wh_posicao_cota_fundo` | DAILY 07:00 SP | Cota |
| 2 | `market.conta_corrente` | `wh_saldo_conta_corrente` | DAILY 07:30 SP | Posicao |
| 3 | `market.tesouraria` | `wh_saldo_tesouraria` | DAILY 07:30 SP | Posicao |
| 4 | `market.outros_ativos` | `wh_posicao_outros_ativos` | DAILY 08:00 SP | Posicao |
| 5 | `market.demonstrativo_caixa` | `wh_movimento_caixa` | DAILY 08:00 SP | Movimentacoes |
| 6 | `market.cpr` | `wh_cpr_movimento` | DAILY 08:30 SP | Custodia |
| 7 | `market.mec` | `wh_mec_evolucao_cotas` | DAILY 08:30 SP | Cota |
| 8 | `market.rentabilidade` | `wh_rentabilidade_fundo` | DAILY 09:00 SP | Outros |
| 9 | `market.rf` | `wh_posicao_renda_fixa` | DAILY 08:00 SP | Posicao |
| 10 | `market.rf_compromissadas` | `wh_posicao_compromissada` | DAILY 08:00 SP | Posicao |
| 11 | `bank_account.balance` | `wh_bank_account_balance` | DAILY 19:00 SP | Recebimentos |
| 12 | `bank_account.statement` | `wh_bank_account_statement` | INTERVAL 60min | Movimentacoes |

### 2.2 Endpoints assincronos (5) — fora do dispatcher

Disparo via REST (manualmente via `POST /v2/queue/scheduler/report/*`). Estado tracked em tabela `qitech_report_job` (operacional). Polling em `qitech_jobs_poll` (5 min). Mappers em `adapters/admin/qitech/mappers/`.

| # | endpoint_name | canonical_table | trigger | categoria | obs |
|---|---|---|---|---|---|
| 13 | `fidc_estoque` | `wh_estoque_recebivel` | manual / agenda externa | Estoque | CSV download (S3 presigned) |
| 14 | `liquidados_baixados` | `wh_liquidacao_recebivel` | manual | Movimentacoes | JSON wrapper `{liquidadosBaixados:[]}` |
| 15 | `detalhes_operacoes` | `wh_operacao_remessa` | manual | Movimentacoes | lista CNAB direta (1 linha por lote .rem) |
| 16 | `aquisicao_consolidada` | `wh_aquisicao_recebivel` | manual | Movimentacoes | wrapper `{aquisicaoConsolidada:[]}` |
| 17 | `movimento_aberto` | `wh_movimento_aberto` | manual | Movimentacoes | snapshot diario de cessoes pendentes |

### 2.3 Catalogo de cadencia ja existente (re-uso)

`backend/app/modules/integracoes/public.py` ja exporta:
- `endpoint_catalog(source_type)` -> tupla `EndpointSpec`
- `list_due_endpoints(...)` -> quem venceu
- `run_sync_endpoint(...)` -> dispara 1 endpoint
- `is_source_enabled(...)` -> tenant tem QiTech ligado?

**Decisao de implementacao:** o `report_definition` da Phase 1 **referencia** `endpoint_name` do catalogo de cadencia ja existente (string match). Isso evita duplicacao de freq / canonical_table em dois catalogos.

## 3. Modelo `report_definition` (esboco para Phase 1)

```python
# backend/app/modules/integracoes/models/report_definition.py

class ReportCategory(str, Enum):
    POSICAO = "posicao"
    COTA = "cota"
    ESTOQUE = "estoque"
    EVENTOS = "eventos"  # placeholder pra futuro
    RECEBIMENTOS = "recebimentos"
    CUSTODIA = "custodia"
    MOVIMENTACOES = "movimentacoes"
    OUTROS = "outros"


class ReportRefreshKind(str, Enum):
    DAILY = "daily"           # rodado por sync_dispatcher
    INTERVAL = "interval"     # rodado por sync_dispatcher (intervalo curto)
    ON_DEMAND_ASYNC = "on_demand_async"  # job model (qitech_report_job)


class ReportDefinition(Base):
    __tablename__ = "report_definition"
    # GLOBAL (sem tenant_id; e catalogo de produto)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    slug: Mapped[str] = mapped_column(unique=True)              # ex.: "qitech-posicao-cota-fundo"
    name: Mapped[str]                                            # "Posicao em outros fundos"
    description: Mapped[str]
    category: Mapped[ReportCategory]
    administradora: Mapped[SourceType]                           # ADMIN_QITECH (futuro: ADMIN_KANASTRA, ...)
    endpoint_name: Mapped[str]                                   # "market.outros_fundos" — match com endpoint_catalog
    canonical_table: Mapped[str]                                 # "wh_posicao_cota_fundo"
    schema_columns: Mapped[dict]                                 # JSONB: [{key, label, dtype, format}]
    refresh_kind: Mapped[ReportRefreshKind]
    default_permission: Mapped[Permission] = mapped_column(default=Permission.READ)
```

**Por que `administradora` em vez de `kind=PADRONIZADO|ESPELHO`?** A tab "Espelho" e UM RENDERER do mesmo catalogo, nao uma classe diferente de relatorio (Opcao A). Nenhuma linha do catalogo e "exclusivamente espelho". As duas tabs leem a MESMA lista; a diferenca e visual (agrupamento + lentes).

## 4. Endpoints REST (esboco para Phase 1)

`backend/app/modules/controladoria/api/reports.py`:

| Endpoint | Proposito | Permissao |
|---|---|---|
| `GET /api/v1/controladoria/relatorios/catalog` | Lista todos os relatorios visiveis ao tenant | READ |
| `GET /api/v1/controladoria/relatorios/<slug>?fundo_id=&periodo_inicio=&periodo_fim=&page=&page_size=` | Linhas + proveniencia | READ |
| `POST /api/v1/controladoria/relatorios/<slug>/regenerate` | Dispara sync sob demanda (so `ON_DEMAND_ASYNC`) | WRITE |
| `GET /api/v1/controladoria/relatorios/<slug>/sync-status` | Status do ultimo sync (timestamp, version, cobertura) — para a lente do Espelho | READ |

Toda query passa por `_apply_filters(stmt, tenant_id=..., **filters)` (§7.2). Toda chamada registra entrada em `decision_log` (§14.2). Response inclui metadata de proveniencia (§14.5).

## 5. Categorias para o `<SegmentSwitch>` da pagina catalogo

| Categoria | Endpoints |
|---|---|
| **Cota** | outros_fundos, mec |
| **Posicao** | conta_corrente, tesouraria, outros_ativos, rf, rf_compromissadas |
| **Movimentacoes** | demonstrativo_caixa, statement, liquidados_baixados, detalhes_operacoes, aquisicao_consolidada, movimento_aberto |
| **Custodia** | cpr |
| **Recebimentos** | balance |
| **Estoque** | fidc_estoque |
| **Outros** | rentabilidade |

Cor por categoria via novo token `frontend/src/design-system/tokens/reportCategoryTokens.ts` (sem `bg-X-N` solto na callsite — §4 do CLAUDE.md).

## 6. Pendencias resolvidas

- [x] Inventariar endpoints sincronos -- 12 endpoints listados.
- [x] Inventariar endpoints assincronos -- 5 endpoints + canonical tables confirmadas via leitura dos mappers.
- [x] Decidir tab Espelho (Opcao A — lente operacional).
- [x] Decidir permissao Reprocessar (WRITE).
- [x] Decidir label L2 ("Relatorios").
- [x] Confirmar reuso do catalogo de cadencia existente (`endpoint_catalog` + `tenant_source_endpoint_config`).

## 7. Pendencias restantes para Phase 1

- [ ] Definir slugs estaveis (ex.: `qitech-posicao-cota-fundo`, `qitech-fidc-estoque`). Convencao proposta: `<admin>-<categoria>-<entidade>` em kebab-case.
- [ ] Definir `schema_columns` por slug (key, label pt-BR, dtype, format). Pode entrar via seed inicial ou via TS-types no frontend.
- [ ] Verificar onboarding de novos tenants — quem decide quais relatorios estao visiveis: `tenant_source_config` (per-tenant + adapter habilitado) + `user_module_permission(controladoria)`?
