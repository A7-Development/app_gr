# Integracao CVM FIDC -- fonte publica federada via postgres_fdw

> Documento vivo. Descreve como o GR consome dados publicos do mercado de FIDCs
> (Informes Mensais da CVM) atraves de um ETL externo + DB dedicada +
> `postgres_fdw`. Primeiro (e por enquanto unico) exemplo do padrao de **fonte
> externa federada** descrito no CLAUDE.md 13.1.

---

## PARTE 1 -- Visao geral

**O que e:** ETL externo que baixa ZIPs da CVM (Informes Mensais de FIDC,
dados abertos), descompacta, insere em JSONB bruto e transforma em tabelas
tipadas. Os dados ficam num banco Postgres dedicado (`cvm_benchmark`) e sao
lidos pelo backend GR via `postgres_fdw` -- sem duplicacao.

**Por que existe separado do backend GR:**

1. Dado e **publico** -- nao tem `tenant_id`, nao entra no modelo multi-tenant
2. Ciclo de ingestao **mensal**, nao-transacional -- cadencia totalmente
   diferente da ingestao via adapters Bitfin/QiTech/etc.
3. Volume justifica DB dedicada -- backup, vacuum e lifecycle desacoplados do
   `gr_db`
4. Deploy e versionamento independentes -- o ETL tem seu proprio repositorio,
   sua propria CI, seu proprio cron
5. Mantem o bounded context `integracoes` do GR limpo -- ele cuida de fontes
   **transacionais por tenant**, nao de dados publicos de mercado

**Repo:** `A7-Development/etl-cvm` (privado no GitHub).
Branches: `develop` (atual, CI verde) -> `main` (promocao dispara deploy
automatico via self-hosted runner na VM 26 -- infra ainda nao ativada).

**Paths:**
- Dev local: `C:\cvm_fidc_etl\`
- Producao: `/var/www/etl-cvm/` na VM `192.168.100.26`

**Status (abril/26):** primeira ingestao manual validada em
`cvm_benchmark` na VM 27 (competencia 2026-02: 33.606 linhas raw + 7.468
tipadas). Aguardando provisionamento da VM 26 + promocao `develop -> main`
pra cron entrar em producao.

---

## PARTE 2 -- Arquitetura fisica

```
CVM Dados Abertos (ZIPs)
        |
        | HTTPS (tenta DADOS/ primeiro, fallback pra HIST/ em 404)
        v
VM 26: /var/www/etl-cvm          <- cron dia 20, 03:00, reprocessa ultimos 12 meses
        |
        | Downloader -> Extractor -> Stager -> Transformer
        v
VM 27: Postgres 16 (mesmo cluster do gr_db)
        |
   +----+--------------------------+
   |                               |
 gr_db                       cvm_benchmark
 (multi-tenant)              (publico, sem tenant_id)
   |                               |
   +---------- postgres_fdw -------+
              (gr_db le cvm_benchmark
               via schema `cvm_remote`)
   |
   v
Backend GR (modulo BI) -> menu Benchmark -> frontend
```

**Principios:**

- Databases **separadas** no **mesmo cluster** Postgres 16 da VM 27 (ver
  CLAUDE.md 17). Zero acoplamento de ORM / migrations / roles.
- Role `etl_cvm` e dona das tabelas em `cvm_benchmark`. No MVP uma unica
  role faz escrita (ETL) e leitura (backend GR via FDW). Pode evoluir pra
  duas roles (writer/reader) quando houver necessidade.
- Senha do `etl_cvm` vive em `/etc/a7credit/etl-cvm.env` (chmod 600,
  systemd-friendly). Backend GR guarda a sua propria copia no mapeamento
  FDW.
- Deploy do ETL: **sem Docker**. GitHub Actions self-hosted runner na VM 26
  faz `rsync` do codigo pra `/var/www/etl-cvm`, `pip install -e .` dentro do
  venv, aplica DDL via `psql`, e cron dispara mensalmente. Workflow em
  `.github/workflows/ci.yml` do repo `etl-cvm`.
- Conexao do ETL com a VM 27 usa TCP keepalives + `sslmode=disable` (rede
  interna, sem SSL).

---

## PARTE 3 -- Schema do `cvm_benchmark` (ETL v0.3.0 -- cobertura completa do Informe Mensal)

**Principio do ETL (mantido desde v0.2.0):** cada coluna do CSV da CVM vira
uma coluna SQL com o **mesmo nome** (lowercase) e tipo inferido por
convencao de prefixo. Zero renomeacao semantica. Zero derivacao. Tudo que
e "PDD derivada", "indice de inadimplencia", "classe ANBIMA canonica"
vive no **consumer** (backend GR) -- versionado via `ADAPTER_VERSION` e
auditavel via `decision_log` (CLAUDE.md 14.2). O ETL e um dutao burro.

**Mudanca v0.2.0 -> v0.3.0 (abril/26):** cobertura foi de 9 tabs
principais (I..X) para **17 tabs** -- entraram as 8 sub-tabelas X_1..X_7
publicadas no ZIP mensal da CVM mas antes ignoradas. Detalhe abaixo.

Motivacao historica: v0.1.0 tinha derivacoes no ETL e nomes interpretados
(`patrimonio_liquido`, `percentual_pdd`). Quando a primeira ingestao real
rodou, as colunas derivadas vieram 100% NULL porque os nomes inferidos na
interpretacao nao batiam com os cabecalhos reais dos CSVs da CVM. Conclusao:
interpretar semanticamente no ETL antes de ter a primeira ingestao real
e projetar no escuro. v0.2.0 removeu todas as derivacoes.

**Schemas:**

| Schema | Proposito |
|---|---|
| `cvm_raw` | JSONB bruto + controle de ingestao (watermark) |
| `cvm` | Tabelas tipadas espelhando 1:1 o CSV |

**Tabelas raw:**

- `cvm_raw.inf_mensal_fidc_raw` -- JSONB com payload bruto de cada linha
  original da CVM. Indexada por `(competencia, tabela)`. Particionamento
  logico por competencia; fisico pode ser adotado quando volume pedir.
- `cvm_raw.ingestion_control` -- uma linha por (competencia, tabela) com
  status do pipeline: `downloaded`, `staged`, `transformed`, `failed`.
  Serve de watermark pra `--ultimos 12` nao refazer trabalho.

**Tabelas tipadas (cobertura v0.3.0 -- 17 tabs):**

Nomes **neutros** pra deixar claro que sao espelho bruto do CSV, nao
interpretacao. PK depende da granularidade natural do CSV -- ver
"Padroes de PK" abaixo.

Principais (1 linha por fundo/classe por competencia, PK
`(competencia, cnpj_fundo_classe)`):

| Tabela | Cols CSV | Conteudo (segundo a CVM) |
|---|---|---|
| `cvm.tab_i` | ~109 | Ativos do fundo (composicao por tipo de DC, aplicacoes financeiras, etc) |
| `cvm.tab_ii` | variavel | Comportamento da carteira (variacao do PL, serie historica) |
| `cvm.tab_iii` | variavel | Direitos creditorios adquiridos **-- criterio, prazo medio, taxa media** |
| `cvm.tab_iv` | 6 | **Patrimonio liquido (`tab_iv_a_vl_pl`)** + PL medio (`tab_iv_b_vl_pl_medio`) |
| `cvm.tab_v` | 37 | **Direitos creditorios por prazo** (a vencer A1-A10, inadimplente B1-B10, antecipado C1-C10) |
| `cvm.tab_vi` | variavel | Passivo + eventos |
| `cvm.tab_vii` | variavel | Prestadores de servico + cedentes |
| `cvm.tab_ix` | variavel | Cotistas por classe |
| `cvm.tab_x` | variavel | Classificacao SCR de risco (AA..H) dos DC |

**Tab VIII e ausente dos ZIPs da CVM** (eles pularam o numero 8 na serie).

Sub-tabelas de X (v0.3.0 -- granularidade por subclasse / tipo de operacao):

| Tabela | PK (alem de competencia) | Conteudo |
|---|---|---|
| `cvm.tab_x_1`   | `cnpj_fundo_classe, tab_x_classe_serie, id_subclasse` | Cotistas agregados por subclasse (Senior, Mezanino, Subordinada) |
| `cvm.tab_x_1_1` | `cnpj_fundo_classe` | **Cotistas por tipo de investidor x classe** (32 colunas Sen/Subord: PF, PJ, banco, corretora, clube, fundo, EAPC, seguradora, RPPS, demais) |
| `cvm.tab_x_2`   | `cnpj_fundo_classe, tab_x_classe_serie` | **NAV** -- valor de cota e qt em circulacao por subclasse |
| `cvm.tab_x_3`   | `cnpj_fundo_classe, tab_x_classe_serie` | **Rentabilidade %** apurada mes a mes por subclasse |
| `cvm.tab_x_4`   | `cnpj_fundo_classe, tab_x_tp_oper, tab_x_classe_serie` | Captacao / resgate / amortizacao por operacao x subclasse |
| `cvm.tab_x_5`   | `cnpj_fundo_classe` | **Liquidez escalonada** (0/30/60/90/180/360/>360 dias) |
| `cvm.tab_x_6`   | `cnpj_fundo_classe, tab_x_classe_serie` | Desempenho esperado vs realizado por subclasse |
| `cvm.tab_x_7`   | `cnpj_fundo_classe` | **Garantias** -- % e valor de direitos creditorios com garantia |

### Padroes de PK (detectados automaticamente por `_detect_pk`)

O gerador de DDL (`scripts/generate_ddl.py::_detect_pk`) varre as colunas
do CSV e monta a PK natural a partir das chaves presentes. Os 4 padroes
observados no v6.6:

1. `(competencia, cnpj_fundo_classe)` -- principais + X_1_1, X_5, X_7
2. `(competencia, cnpj_fundo_classe, tab_x_classe_serie)` -- X_2, X_3, X_6
3. `(competencia, cnpj_fundo_classe, tab_x_classe_serie, id_subclasse)` -- X_1
4. `(competencia, cnpj_fundo_classe, tab_x_tp_oper, tab_x_classe_serie)` -- X_4

Se a CVM inventar uma 5a chave, basta adicionar o `if` correspondente
em `_detect_pk` e regenerar o DDL.

**Campos comuns a todas as tabelas tipadas:**

```
competencia         DATE            NOT NULL   -- metadado nosso
tp_fundo_classe     TEXT                       -- do CSV
cnpj_fundo_classe   VARCHAR(30)                -- do CSV (PK com competencia)
denom_social        TEXT                       -- do CSV
dt_comptc           DATE                       -- do CSV (data de competencia na CVM)
<colunas especificas do CSV da tab>
raw_id              BIGINT                     -- FK pra cvm_raw.inf_mensal_fidc_raw.id
ingested_at         TIMESTAMPTZ     DEFAULT NOW()
```

**Convencao de inferencia de tipo** (mesma regra em
`scripts/generate_ddl.py` e `cvm_fidc/transformer.py::_infer_converter` --
formam um par):

| Prefixo / regex no nome da coluna CSV | Tipo SQL |
|---|---|
| `DT_*`, `DATA_*`, `DT_COMPTC` | `DATE` |
| `QT_*`, `NR_*`, contem `_QT_` ou `_NR_` (v0.3.0: necessario pra `TAB_X_NR_COTST_*`) | `INTEGER` |
| contem `VL_` em qualquer posicao (`^VL_`, `_VL_`) | `NUMERIC(21,4)` |
| contem `PR_` em qualquer posicao (`^PR_`, `_PR_`) | `NUMERIC(20,6)` (fracao 0.0-1.0; v0.3.0 subiu precisao) |
| `PRAZO_*` e **nao** contem `_TP_` | `INTEGER` |
| qualquer outra coisa (`CNPJ_*`, `CPF_*`, `TP_*`, descritivos) | `TEXT` / `VARCHAR(30)` |

Se a CVM mudar o header, basta:

1. `python scripts/generate_ddl.py` -- regenera `sql/03_tables_tipadas.sql`
2. `DROP SCHEMA cvm CASCADE` + aplica o SQL novo
3. `python -m cvm_fidc.main transform --competencia YYYY-MM` -- `cvm_raw` JSONB
   ja esta preservado, nao precisa re-baixar.

**Nada de views analiticas no ETL.** v0.1.0 tinha `v_fundo_evolucao`,
`v_top_pdd_atual` etc. Saiu tudo. Views que fazem sentido pro produto GR
vivem no backend como SQL no service, versionado via git + `ADAPTER_VERSION`.

**Campos de ingestao / auditabilidade:**

O ETL v0.2.0 minimalista tem so `raw_id` + `ingested_at` em cada linha.
Os demais campos do mixin `Auditable` do GR (CLAUDE.md 14.1) sao montados
**no consumer** a partir de:

- `source_type` = `public:cvm_fidc` (constante)
- `source_updated_at` = `competencia` da linha (granularidade mensal da CVM)
- `ingested_at` = coluna da linha
- `ingested_by_version` = `ADAPTER_VERSION` do ETL que ingeriu (v0.3.0:
  `cvm_fidc_etl_v0.3.0`). A constante vive em
  `cvm_fidc/transformer.py` do repo `etl-cvm` e e bumped sempre que a
  forma de carregar mudar (nao quando a CVM mudar um header).
- `trust_level` = `high` (fonte oficial reguladora)

---

## PARTE 4 -- Ponte com `gr_db` (Milestone M2, pendente)

Passos canonicos, rodados no `gr_db` como superuser. Primeira vez so.

```sql
-- 1) Extensao
CREATE EXTENSION IF NOT EXISTS postgres_fdw;

-- 2) Servidor remoto (aponta pro mesmo Postgres, outra DB)
CREATE SERVER cvm_benchmark_server
  FOREIGN DATA WRAPPER postgres_fdw
  OPTIONS (host '192.168.100.27', dbname 'cvm_benchmark', port '5432');

-- 3) Mapeamento de usuario (role do GR -> role etl_cvm no outro DB)
CREATE USER MAPPING FOR <role_do_backend_gr>
  SERVER cvm_benchmark_server
  OPTIONS (user 'etl_cvm', password '<senha>');

-- 4) Schema local que vai hospedar as foreign tables
CREATE SCHEMA cvm_remote;

-- 5) Importar schema `cvm` (17 tabelas tipadas em v0.3.0) do servidor remoto.
--    IMPORTANTE: toda vez que o schema mudar (novo tab, coluna nova por
--    mudanca de CVM), DROP SCHEMA cvm_remote CASCADE + re-rodar este passo.
--    Migracao v0.2.0 -> v0.3.0 exige esta reimportacao (8 tabelas novas).
IMPORT FOREIGN SCHEMA cvm
  FROM SERVER cvm_benchmark_server
  INTO cvm_remote;

-- Opcional: importar tambem cvm_raw pra debug / investigacao
-- IMPORT FOREIGN SCHEMA cvm_raw
--   FROM SERVER cvm_benchmark_server
--   INTO cvm_raw_remote;

-- 6) Smoke test (tab_i e a identificacao dos fundos, base de tudo)
SELECT count(*) FROM cvm_remote.tab_i;
SELECT competencia, count(*) FROM cvm_remote.tab_i GROUP BY 1 ORDER BY 1;
```

**Armadilha comum:** `IMPORT FOREIGN SCHEMA` usa o `USER MAPPING` da role
que esta **executando** o IMPORT, nao da role que vai ler depois. Se voce
roda como `postgres` e a role do backend GR e `gr_app`, tem que criar
mapping pras **duas**.

**Resultado:** backend GR trata `cvm_remote.tab_i`, `cvm_remote.tab_iv`,
`cvm_remote.tab_v`, etc. como se fossem tabelas locais do `gr_db`. Queries
JOINando dado do mercado com dado proprio do cliente funcionam
transparentemente.

**Nao duplicar dado.** A tentacao de "copiar pro gr_db pra performance"
deve ser resistida. Se performance virar problema, abordagens corretas:
(1) materialized view local refletindo `cvm_remote`, (2) adicionar indices
no `cvm_benchmark`, (3) evoluir pra schema-per-tenant + replica dedicada.
Nunca fazer o backend GR manter copia propria de dado publico.

---

## PARTE 5 -- Consumo pelo modulo BI (Milestone M3, pendente)

Novo **L2** na sidebar do BI: **Benchmark** (`/bi/benchmark`). Respeita a
regra de 3 niveis (CLAUDE.md 11.6). L3 previstas:

| L3 Tab | Rota | Conteudo | Derivacao |
|---|---|---|---|
| Visao geral | `?tab=visao-geral&competencia=YYYY-MM` | KPIs agregados do mercado + evolucao | total fundos, soma PL (`tab_iv_a_vl_pl`), mediana PL |
| PDD | `?tab=pdd&competencia=YYYY-MM&bucket=...` | Histograma + top-20 fundos | **PDD derivada** = `tab_v.tab_v_b_vl_dircred_inad` / `tab_iv.tab_iv_a_vl_pl` (logica no service, versionada) |
| Evolucao | `?tab=evolucao&cnpj=...` | Input CNPJ -> chart multi-serie | PL (`tab_iv_a_vl_pl`) por competencia + PDD derivada |
| Fundos | `?tab=fundos&q=...&classe=...` | Tabela Tremor com paginacao + filtros (classe ANBIMA, porte, situacao) | JOIN `tab_i` + `tab_iv` + `tab_v` por `(competencia, cnpj_fundo_classe)` |

**Principio v0.2.0:** todo numero derivado (PDD%, indice de inadimplencia,
cobertura, classe ANBIMA canonica) e **calculado no service do backend**,
nunca no ETL. O service registra a formula usada no `decision_log`
(CLAUDE.md 14.5). Isso garante que mudar a definicao de "PDD" nao
reprocessa CSVs -- muda so o service + `ADAPTER_VERSION`.

### 5.1 Backend (`app_gr/backend/app/modules/bi/`)

```
modules/bi/
  services/
    benchmark_service.py       <- le cvm_remote.*, agrega metricas
  schemas/
    benchmark.py               <- pydantic v2 (request/response)
  api/
    benchmark.py               <- endpoints
```

Endpoints (todos sob `Depends(require_module(Module.BI, Permission.READ))`):

- `GET /api/v1/bi/benchmark/visao-geral?competencia=<YYYY-MM>`
- `GET /api/v1/bi/benchmark/pdd?competencia=<YYYY-MM>&bucket=<...>`
- `GET /api/v1/bi/benchmark/evolucao?cnpj=<CNPJ>`
- `GET /api/v1/bi/benchmark/fundos?q=<busca>&classe=<...>`

Cada endpoint que calcula metrica agregada registra `decision_log`
(CLAUDE.md 14.2) com:

- `source_type = 'public:cvm_fidc'`
- `rule_or_model = 'benchmark_service.<funcao>'` + versao
- `inputs_ref` = dict com competencia, filtros, CNPJ
- `output` = resumo estruturado
- `explanation` = como a metrica foi calculada (formula, cohort)

### 5.2 Frontend (`app_gr/frontend/src/app/(app)/bi/benchmark/`)

Estrutura canonica (seguindo templates de `src/templates/` quando
existirem):

```
(app)/bi/benchmark/
  page.tsx              <- L2 container com TabNavigation
  visao-geral/
    page.tsx            <- KPIs (Card do Tremor) + chart Area/Bar
  pdd/
    page.tsx            <- histograma + Table top-20
  evolucao/
    page.tsx            <- input CNPJ + chart multi-serie
  fundos/
    page.tsx            <- Table com sort/filter/paginacao
```

Regras obrigatorias (CLAUDE.md 14.6):

- `<DataOriginBadge />` ao lado de cada KPI/numero:
  - Source: `CVM Dados Abertos`
  - Competencia: `YYYY-MM`
  - Ingerido em: `DD/MM/YYYY HH:MM`
  - Adapter: `cvm_fidc_etl vX.Y.Z`
  - Trust: `high`
- `<ShowPremisesButton />` em qualquer KPI que seja derivado (ex.:
  "mediana do percentual_pdd" -- explicar quais fundos entraram na cohort)
- URL como fonte de verdade (deep-link em `?tab=...&competencia=...`)
- Sidebar **nao aninha** Benchmark -- ele e L2 plano no modulo BI

---

## PARTE 6 -- Operacao

**Agendamento:** cron mensal no dia 20 as 03:00 (horario da VM 26):

```cron
0 3 20 * * cd /var/www/etl-cvm && .venv/bin/python -m cvm_fidc.main ingest --ultimos 12 >> /var/www/etl-cvm/logs/cron.log 2>&1
```

**Por que dia 20:**

- FIDCs entregam o Informe Mensal a CVM ate o **15o dia util** do mes
  seguinte a competencia
- CVM processa e publica nos dados abertos geralmente ate dia 18-19
- Dia 20 e margem segura

**Por que `--ultimos 12`:** a CVM atualiza semanalmente os arquivos dos
meses anteriores (reapresentacoes). Reprocessar 12 meses garante que
correcoes entram no banco sem refazer ingest manual.

**Health check SQL** (qualquer monitor externo pode rodar):

```sql
SELECT MAX(competencia)      AS ultima_competencia,
       MAX(fim_transform)    AS ultima_execucao
FROM cvm_raw.ingestion_control
WHERE status = 'transformed';
-- se ultima_execucao < NOW() - INTERVAL '35 days' => alerta
```

**Log:** `/var/www/etl-cvm/logs/cron.log` (append-only, rotacionado por
logrotate se a VM tiver; se nao, configurar).

**CLI operacional** (rodar na VM 26 depois de `cd /var/www/etl-cvm &&
source .venv/bin/activate`):

```bash
python -m cvm_fidc.main status                       # estado geral
python -m cvm_fidc.main ingest --competencia 2026-02 # forcar uma competencia
python -m cvm_fidc.main ingest --ultimos 12          # replay reapresentacoes
python -m cvm_fidc.main download --competencia ...   # so baixar (sem staging)
python -m cvm_fidc.main transform --competencia ...  # so transformar (raw -> tipado)
```

---

## PARTE 7 -- Auditabilidade e proveniencia

Mesmo sendo dado publico (sem `tenant_id`), o consumo pelo GR segue o DNA
de auditabilidade (CLAUDE.md 14):

1. **Proveniencia ao nivel da linha** -- toda linha em `cvm.*` carrega
   source_type, ingested_at, ingested_by_version, hash_origem. O GR le
   via FDW e expoe no badge do frontend.
2. **Decisoes calculadas pelo backend GR** -- cada agregacao/benchmark
   ponderado/score gera entrada em `decision_log` com
   `source_type='public:cvm_fidc'`, `inputs_ref` (filtros), `output`,
   `explanation`. Append-only, igual a qualquer outro decision_log.
3. **Premissas derivadas** -- se alguma metrica usar premissa configuravel
   (ex.: "bucket de PDD = faixas [0-2%, 2-5%, ...]"), a premissa vive em
   `premise_set` (CLAUDE.md 14.3) e a metrica referencia a versao usada.
4. **Trust level** -- `high` fixo (fonte oficial reguladora).
5. **Badge visivel na UI** (CLAUDE.md 14.6): `<DataOriginBadge />` com
   tooltip "CVM Dados Abertos -- competencia YYYY-MM -- ingerido em
   DD/MM HH:MM -- cvm_fidc_etl vX.Y.Z".

---

## PARTE 8 -- Roadmap resumido

(referencia canonica fica em `C:\cvm_fidc_etl\ROADMAP.md`; este resumo
ajuda o Claude/dev do `app_gr` a entender sem sair do projeto)

### M1 -- ETL funcional em producao (em andamento)

- [x] Codigo Python (downloader/extractor/stager/transformer)
- [x] CLI (ingest, download, transform, status)
- [x] Testes unitarios + CI verde no GitHub
- [x] Repo `A7-Development/etl-cvm` + branch `develop` publicada
- [x] `cvm_benchmark` provisionado na VM 27 (role + schemas)
- [x] Primeira ingestao validada (2026-02: 33.606 linhas raw)
- [x] **v0.2.0** -- rewrite pra espelho 1:1 do CSV (generator + transformer)
- [x] **v0.3.0** -- cobertura completa (17 tabs: principais + X_1..X_7);
  `_detect_pk` natural; `_NR_` no meio infere INTEGER; regex do extractor
  e do generate_ddl captura sub-tabelas
- [ ] Aplicar DDL v0.3.0 em `cvm_benchmark` (`scripts/drop_recreate_cvm_schema.sh`)
- [ ] Reprocessar `cvm_raw` -> `cvm` (transform --ultimos 15; backfill 2025-01..2026-03)
- [ ] `gr_db`: `DROP SCHEMA cvm_remote CASCADE` + re-`IMPORT FOREIGN SCHEMA cvm`
- [ ] Rodar smoke test `pytest tests/bi/test_benchmark_schema.py`
- [ ] VM 26: self-hosted runner + `/etc/a7credit/etl-cvm.env`
- [ ] Rodar `deploy_initial.sh` na VM 26
- [ ] Promover `develop -> main` e disparar deploy via Actions
- [ ] Habilitar cron (`scripts/cron_entry.txt`)

### M2 -- Ponte `gr_db` -> `cvm_benchmark` (postgres_fdw)

Pre-requisito: M1 concluido. Steps detalhados em Parte 4 acima.

### M3 -- Menu Benchmark no modulo BI

Pre-requisito: M2 concluido. Detalhes em Parte 5 acima.

### M4 -- Consumo dos blocos granulares v0.3.0 pelo backend/UI

Pre-requisito: M1 (v0.3.0 deployed + backfill) + M2 (FDW reimportado).
As 8 tabelas X_1..X_7 ja sao espelhadas em `cvm_remote`; o que falta
sao servicos e views no modulo BI:

- Ficha unitaria do fundo (`GET /bi/benchmark/fundo/{cnpj}`) consumindo
  cotistas (X_1_1), NAV (X_2), rentabilidade (X_3), liquidez (X_5),
  garantias (X_7)
- Comparativo estendido agregando cotistas/rentabilidade/liquidez aos
  indicadores atuais
- Tabs correspondentes no frontend `/bi/benchmark` (seguindo regra de 3
  niveis, CLAUDE.md 11.6)

### M5 -- Observabilidade

- Alerta email/slack se ultima ingestao > 35 dias
- Metrica de linhas ingeridas por competencia em dashboard interno
- Endpoint `/health` no ETL pra uptime-check externo

---

## PARTE 9 -- Glossario

- **FIDC** -- Fundo de Investimento em Direitos Creditorios
- **Informe Mensal** -- reporte obrigatorio que cada FIDC envia a CVM
  ate o 15o dia util do mes seguinte a competencia
- **Competencia** -- mes de referencia do dado (formato `YYYY-MM`)
- **Reapresentacao** -- correcao de Informe ja publicado. A CVM atualiza
  os arquivos dos meses anteriores semanalmente, por isso o cron
  reprocessa `--ultimos 12`.
- **Tab I..X** -- cada "aba" do CSV da CVM:
  - I = identificacao do fundo
  - II = comportamento da carteira
  - III = direitos creditorios adquiridos
  - IV = caracteristicas dos DC
  - V = informacoes gerais (PDD, publico-alvo, situacao)
  - VI-X = passivos, prestadores, cotas, cotistas, etc.
- **ANBIMA** -- Associacao Brasileira das Entidades dos Mercados
  Financeiro e de Capitais. Define a classificacao "classe ANBIMA" que
  aparece em `tab_i_identificacao`.
- **postgres_fdw** -- Foreign Data Wrapper nativo do Postgres pra ler
  outras databases (do mesmo cluster ou remotas) como se fossem locais.
  Padrao usado aqui pra o `gr_db` enxergar o `cvm_benchmark`.

---

## Referencias cruzadas

- **CLAUDE.md 13.1** -- definicao do padrao "fontes externas federadas"
- **CLAUDE.md 17** -- lista de databases no cluster da VM 27
- **CLAUDE.md 11.6** -- regra de 3 niveis da navegacao (L2 Benchmark cai aqui)
- **CLAUDE.md 14** -- auditabilidade (decision_log, proveniencia, badges)
- **docs/inventario-powerbi.md** -- hierarquia oficial do modulo BI (L2 Benchmark = P8)
- **Repo externo `A7-Development/etl-cvm`** -- codigo do ETL
  - `README.md` -- operacao do ETL
  - `ROADMAP.md` -- roadmap canonico M1..M5
  - `sql/01..03b_*.sql` -- DDL
  - `scripts/cron_entry.txt` -- agendamento
  - `.github/workflows/ci.yml` -- deploy
