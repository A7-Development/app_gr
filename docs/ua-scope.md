# Design: `ua_scope` em fontes/integracoes

> Status: rascunho aprovado (2026-05-22). Aguardando virar PRs implementaveis.
> Discussao original: sessao `worktree-operacoes4` com Ricardo, 2026-05-22.

---

## Problema

Um tenant do Strata tem N **unidades administrativas (UAs)**. Hoje o tenant
`a7-credit` tem 3:

- A7 Credit (`ua_id=1`)
- RealInvest FIDC (`ua_id=2`)
- Onboard (`ua_id=3`)

E cada **fonte de dado** (ERP, admin API, bureau) se relaciona com essas UAs
de forma **estruturalmente diferente** — nao e convencao, e arquitetura da
fonte. O modelo atual de `tenant_source_config` (TSC) com
`unidade_administrativa_id` nullable nao declara essa natureza, forcando o
usuario a entender por contexto. Isso causa 2 problemas concretos vistos
em 2026-05-22:

1. **TSC do Bitfin** aponta pra UUID `6170ce55...` que **nao existe** em
   `wh_dim_unidade_administrativa` (placeholder de migration antiga). Mas
   o sync funciona porque o adapter Bitfin **ignora UA** (`_ =
   unidade_administrativa_id` em `adapter.py:94`).
2. **UI mostra seletor de UA pro Bitfin** mas selecionar A7 Credit ou
   RealInvest nao muda o sync — o que e confuso pro admin.

## Premissas

- **1 tenant = N UAs** (3 hoje em A7 Credit; outros tenants podem ter 1 ou 10).
- **UAs podem ter perfis de integracao distintos**: Onboard pode ter conta
  Serasa propria, A7 Credit usa distribuidor Serasa, RealInvest no futuro
  pode usar Singulare em vez de QiTech.
- **Fontes tem 3 naturezas estruturalmente diferentes** em relacao a UA:

| Natureza | Como a fonte se relaciona com UA | Exemplos |
|---|---|---|
| **`tenant_wide`** | Credencial pertence ao tenant juridico, mesma conta serve TODAS UAs. UA nao e dimensao da fonte. | Reservado para fontes futuras de dados realmente globais (ex.: market data API, dados publicos via auth do tenant). Nenhuma fonte atual cai aqui. |
| **`per_ua`** | Credencial/setup separado **por UA**. Cada UA e um cliente distinto da fonte externa. | QiTech (1 admin por fundo), Serasa PJ (cada UA pode ter conta propria), Singulare/Vortx/BRL Trust no futuro |
| **`shared_multi_ua`** | 1 instancia da fonte atende **N UAs do tenant**. UA e dado dentro do payload (nao setup). | Bitfin (1 banco UNLTD_<X> serve N UAs internas) |

## Decisao

### 1. `ua_scope` declarado no catalogo do adapter (codigo)

`ua_scope` e propriedade **intrinseca** da fonte, nao negociavel por
tenant. Bitfin nao pode virar `per_ua` (arquitetura e 1 banco-N UAs);
QiTech nao pode virar `shared_multi_ua` (cada UA tem admin distinto).
Versionado em git, evolui com release do adapter.

```python
# app/core/enums.py
class UAScope(str, Enum):
    TENANT_WIDE     = "tenant_wide"
    PER_UA          = "per_ua"
    SHARED_MULTI_UA = "shared_multi_ua"

# app/shared/endpoint_catalog.py
@dataclass(frozen=True)
class EndpointSpec:
    # ... campos existentes ...
    ua_scope: UAScope  # OBRIGATORIO
```

### 2. Schema: tabela junction `tenant_source_config_ua_coverage`

```sql
-- ─── Em tenant_source_config ─────────────────────────────────
ALTER TABLE tenant_source_config
    ADD COLUMN ua_scope VARCHAR(20) NOT NULL DEFAULT 'per_ua'
        CHECK (ua_scope IN ('tenant_wide', 'per_ua', 'shared_multi_ua'));

-- coluna unidade_administrativa_id sobrevive por compat mas vira
-- redundante (junction e a fonte da verdade). Plano de remocao: fase 4.

-- ─── Nova tabela: cobertura explicita N:N ────────────────────
CREATE TABLE tenant_source_config_ua_coverage (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    tenant_source_config_id UUID NOT NULL
        REFERENCES tenant_source_config(id) ON DELETE CASCADE,
    unidade_administrativa_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by UUID,
    UNIQUE (tenant_source_config_id, unidade_administrativa_id)
);

CREATE INDEX ix_tsc_uac_ua
    ON tenant_source_config_ua_coverage(unidade_administrativa_id);
CREATE INDEX ix_tsc_uac_tenant
    ON tenant_source_config_ua_coverage(tenant_id);
```

**Semantica por scope:**

| ua_scope | TSC.unidade_administrativa_id | Junction rows | Significado |
|---|---|---|---|
| `tenant_wide` | NULL | 0 (cobertura implicita = TODAS as UAs) | Credencial do tenant juridico |
| `per_ua` | UA especifica (back-compat) | 1 row (mesma UA do TSC) | 1 setup isolado por UA |
| `shared_multi_ua` | NULL | N rows (UAs cobertas, explicitas) | 1 setup compartilhado |

### 3. Adapter contract

```python
# Toda assinatura de sync_endpoint recebe a lista de UAs cobertas.
# Adapter decide o que faz com a lista conforme seu ua_scope.
async def sync_endpoint(
    tenant_id: UUID,
    config: dict,
    endpoint_name: str,
    *,
    covered_uas: list[UUID],  # << NOVO, substitui unidade_administrativa_id
    since: date | None = None,
    triggered_by: str = "system:scheduler",
    environment: Environment = Environment.PRODUCTION,
) -> dict[str, Any]: ...
```

Comportamento por scope:

| Scope | Adapter usa `covered_uas`? |
|---|---|
| `tenant_wide` | Ignora (nao filtra) |
| `per_ua` | Assume `len(covered_uas) == 1` e filtra por essa UA |
| `shared_multi_ua` | Ignora pra fetch (puxa tudo do banco). Usa pra **validar atribuicao** apos sync: cada row gravada deve ter UA ∈ `covered_uas` (ou descartada / quarentena) |

### 4. UI por scope

#### Lista de fontes (`/integracoes/fontes`)

```
┌──────────────────────────────────────────┐
│ Bitfin    [shared_multi_ua]              │
│ Configurada · Cobre: A7 Credit,          │
│             RealInvest, Onboard          │
│ Ultimo sync: ha 2h · OK                  │
└──────────────────────────────────────────┘

┌──────────────────────────────────────────┐
│ QiTech    [per_ua]                       │
│ ▸ A7 Credit       : Configurada · OK     │
│ ▸ RealInvest FIDC : Nao configurada      │
│ ▸ Onboard         : Nao configurada      │
└──────────────────────────────────────────┘

┌──────────────────────────────────────────┐
│ Serasa PJ [per_ua]                       │
│ ▸ A7 Credit : Configurada · OK           │
│ ▸ Onboard   : Configurada · OK           │
│ ▸ RealInvest: Nao configurada            │
└──────────────────────────────────────────┘
```

#### Pagina da fonte (`/integracoes/fontes/<source>`)

| Tela | tenant_wide | per_ua | shared_multi_ua |
|---|---|---|---|
| Seletor de UA no header | Ausente | Obrigatorio | Ausente |
| Aba "Cobertura" | Mostra "Todas as UAs do tenant" (passivo) | N/A | Multi-select editavel: `☑ A7 ☑ Real ☐ Onboard` |
| Sincronizar agora | 1 botao unico | 1 botao por UA | 1 botao unico |
| Endpoints listados | Por TSC | Por (TSC, UA) selecionada | Por TSC |

#### Setup (criar TSC)

| Scope | Formulario |
|---|---|
| `tenant_wide` | Credenciais. Sem seletor de UA. |
| `per_ua` | Credenciais + dropdown "UA" obrigatorio. Cria 1 TSC por UA. |
| `shared_multi_ua` | Credenciais + multi-select "UAs cobertas" obrigatorio. 1 TSC com N rows de junction. |

## Exemplo concreto: tenant A7 Credit pos-migration

```
TENANT: A7 Credit (id=7f00cc2b...)
├── UA A7 Credit       (0de66bf0..., ua_id=1, classe=originador)
├── UA RealInvest FIDC (db603df6..., ua_id=2, classe=fidc)
└── UA Onboard         (515b9f77..., ua_id=3, classe=originador)

────────  TSC POS-MIGRATION  ────────

ERP_BITFIN     scope=shared_multi_ua    ua_id=NULL
  config: { db=UNLTD_A7CREDIT, ... }
  coverage: 3 rows
    ├── A7 Credit
    ├── RealInvest FIDC
    └── Onboard

ADMIN_QITECH   scope=per_ua             ua_id=0de66bf0 (A7 Credit)
  config: { admin_account_A7_Credit_QITECH ... }
  coverage: 1 row
    └── A7 Credit
  (RealInvest e Onboard: nao tem TSC QiTech hoje)

BUREAU_SERASA_PJ  scope=per_ua          ua_id=0de66bf0 (A7 Credit)
  config: { distributor_token, retailer_id_A7Credit, ... }
  coverage: 1 row
    └── A7 Credit
  (futuro: Onboard cria TSC propria com sua conta Serasa direta)
```

## Plano de migration de dados

Estado atual (2026-05-22):

```
ERP_BITFIN    : TSC com ua=6170ce55... (UUID fantasma, nao existe na dim)
ADMIN_QITECH  : TSC com ua=6170ce55... (mesmo UUID fantasma)
BUREAU_SERASA_PJ: TSC com ua=6170ce55... (mesmo UUID fantasma)
```

Migration de dados (Alembic):

```sql
-- Adiciona scope e junction (DDL)
-- ... (ver secao Schema acima)

-- Bitfin: corrige pra shared_multi_ua, popula junction com TODAS UAs
UPDATE tenant_source_config
SET ua_scope = 'shared_multi_ua',
    unidade_administrativa_id = NULL
WHERE source_type = 'ERP_BITFIN';

INSERT INTO tenant_source_config_ua_coverage
  (tenant_id, tenant_source_config_id, unidade_administrativa_id)
SELECT
  tsc.tenant_id,
  tsc.id,
  ua.id
FROM tenant_source_config tsc
JOIN wh_dim_unidade_administrativa ua
  ON ua.tenant_id = tsc.tenant_id AND ua.ativa = true
WHERE tsc.source_type = 'ERP_BITFIN'
ON CONFLICT DO NOTHING;

-- QiTech: per_ua, ua = UA principal do tenant (heuristica)
-- Default: usa a primeira UA com classe=originador (A7 Credit no caso A7)
UPDATE tenant_source_config tsc
SET ua_scope = 'per_ua',
    unidade_administrativa_id = (
      SELECT id FROM wh_dim_unidade_administrativa ua
      WHERE ua.tenant_id = tsc.tenant_id AND ua.ativa = true
      ORDER BY ua.ua_id LIMIT 1
    )
WHERE source_type = 'ADMIN_QITECH';

-- Espelha em junction
INSERT INTO tenant_source_config_ua_coverage (...)
SELECT tenant_id, id, unidade_administrativa_id
FROM tenant_source_config
WHERE source_type = 'ADMIN_QITECH' AND unidade_administrativa_id IS NOT NULL
ON CONFLICT DO NOTHING;

-- Serasa PJ: mesmo tratamento que QiTech (per_ua, UA principal)
UPDATE tenant_source_config tsc
SET ua_scope = 'per_ua',
    unidade_administrativa_id = (
      SELECT id FROM wh_dim_unidade_administrativa ua
      WHERE ua.tenant_id = tsc.tenant_id AND ua.ativa = true
      ORDER BY ua.ua_id LIMIT 1
    )
WHERE source_type = 'BUREAU_SERASA_PJ';

INSERT INTO tenant_source_config_ua_coverage (...) ...;
```

**Validacao pos-migration**: nenhuma TSC pode ter
`unidade_administrativa_id` apontando pra UUID que nao existe em
`wh_dim_unidade_administrativa`.

## Plano de PRs

Sequencia recomendada (cada PR pode mergear independente, mas em ordem):

### PR 1 — Catalogo + schema (sem efeito visivel)

- `app/core/enums.py`: enum `UAScope`
- `app/shared/endpoint_catalog.py`: campo `ua_scope` em `EndpointSpec` (default `PER_UA` por back-compat)
- Cada `endpoint_catalog.py` por adapter declara seu scope explicitamente:
  - `bitfin/endpoint_catalog.py` → `UAScope.SHARED_MULTI_UA`
  - `qitech/endpoint_catalog.py` → `UAScope.PER_UA`
  - `serasa_pj/endpoint_catalog.py` → `UAScope.PER_UA`
- Migration: `ALTER TABLE tenant_source_config ADD COLUMN ua_scope` + CREATE TABLE `tenant_source_config_ua_coverage`
- Sem mudanca de logica — apenas adiciona dados.

### PR 2 — Migration de dados existentes

- Migration Alembic com `UPDATE`s + `INSERT`s para popular `ua_scope` e junction baseado no estado conhecido.
- Validacao: assertion que nenhuma TSC fica com `unidade_administrativa_id` apontando pra UUID inexistente.

### PR 3 — Adapter contract: `covered_uas`

- Refator de `run_sync_endpoint` em `sync_runner.py`: resolve `covered_uas` da junction antes de chamar adapter.
- Adapter base aceita novo parametro. Implementacoes:
  - Bitfin: ignora (continua puxando tudo, mas valida que cada row gravada tem UA ∈ covered_uas)
  - QiTech: assume `len == 1`, filtra
  - Serasa PJ: assume `len == 1`, filtra
- Endpoint POST `/sources/<src>/endpoints/<name>/sync` continua aceitando `?ua=<UUID>` por back-compat (resolve pra `covered_uas=[uuid]`) MAS so para `per_ua`. Para outros scopes, ignora `?ua` com warning.

### PR 4 — UI por scope (lista de fontes)

- `/integracoes/fontes` lista cards diferenciados:
  - `tenant_wide` e `shared_multi_ua`: 1 card unico com badge de cobertura
  - `per_ua`: card expansivel listando 1 entrada por UA configurada/nao-configurada

### PR 5 — UI por scope (pagina da fonte)

- `/integracoes/fontes/<src>` esconde/mostra seletor de UA conforme scope.
- Aba "Cobertura" nova para `shared_multi_ua` (multi-select editavel).
- Botao "Sincronizar agora" comporta-se por scope.

### PR 6 — Setup (criar TSC)

- Formulario de credenciais condicional ao scope da fonte.
- Para `shared_multi_ua`: multi-select de UAs cobertas (obrigatorio).
- Para `per_ua`: dropdown de UA + cria 1 TSC.
- Para `tenant_wide`: sem seletor.

### PR 7 — Limpeza (futuro)

- Depreciar `tenant_source_config.unidade_administrativa_id` (passa a ser
  redundante com a junction). Migration final remove a coluna.
- Sera feita apenas apos todos os callers passarem a usar a junction.

## O que NAO faz parte deste design

- **Cadastro de UA em si** (CRUD de UAs): vive em outro lugar (modulo
  cadastros/admin). Aqui assumimos UAs ja cadastradas em
  `wh_dim_unidade_administrativa`.
- **Mapeamento "UA externa da fonte" → UA interna do GR**: Bitfin tem
  `UnidadeAdministrativaId` como integer (1, 2, 3). GR tem `ua_id` (int)
  + `id` (UUID). O mapeamento integer → UUID acontece via
  `wh_dim_unidade_administrativa.ua_id` (back-compat). Esta logica nao
  muda.
- **Multi-tenant per-adapter**: Bitfin pode estar configurado pra varios
  tenants distintos (cada um com seu UNLTD_<X>). Esta fora do escopo —
  cada tenant tem seu proprio TSC.
- **Override de scope por tenant**: por ora, scope vem 100% do catalogo
  (codigo). Se aparecer caso real onde isso nao funciona, abrir issue
  separada.

## Referencias

- CLAUDE.md §10 (multi-tenant absoluto)
- CLAUDE.md §11.6 (hierarquia de navegacao)
- CLAUDE.md §13 (adapter pattern)
- `app/modules/integracoes/adapters/erp/bitfin/adapter.py:94` (ignora UA hoje)
- `app/modules/integracoes/services/sync_runner.py:398` (run_sync_endpoint atual)
- `app/modules/integracoes/routers/endpoints.py:627` (POST sync atual)
