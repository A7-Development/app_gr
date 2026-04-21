# Inventario do PowerBI atual + Mapa do modulo BI do GR

> Documento vivo. Consolida: (1) mapa oficial do modulo BI do GR, (2) inventario do PowerBI que ele substitui, (3) mapeamento com warehouse canonico. Atualizado pelo Ricardo + Claude em cada sprint.

---

## PARTE 1 — Mapa oficial do modulo BI do GR (decidido no Sprint 2)

### Hierarquia de navegacao (regra de 3 niveis — CLAUDE.md 11.6)

```
L1: BI                                       (sidebar grupo)

  L2: Operacoes          P1    /bi/operacoes
    L3 tabs: Volume | Taxa | Prazo | Ticket | Receita contratada | Dia util

  L2: Carteira           P2    /bi/carteira
    L3 tabs: Evolutivo | Prazo | Concentracao (Cedente/Sacado/Produto) |
             Vencidos | Aging | Vencidos/PL | PDD | Projecao PDD | Checagem

  L2: Comportamento      P3    /bi/comportamento
    L3 tabs: NPL | Liquidez (faixas) | Recompras | Prorrogados

  L2: Receitas           P4    /bi/receitas
    L3 tabs: Desagio | Tarifas | Multas | Juros atraso | Juros prorrogacao | Consolidado

  L2: Fluxo de caixa     P5    /bi/fluxo-caixa
    L3 tabs: Projecao liquidacoes (dia/sem/mes) | Apropriacao de desagio

  L2: DRE                P6    /bi/dre
    L3 tabs: Receita operacional | PDD | Despesa admin | Comissao | Resultado | Consolidado

  Drill-down: Ficha      P7    /bi/cedente/:id  e  /bi/sacado/:id
    L3 tabs: Visao geral | Operacoes | Carteira | Comportamento | Receitas

  L2: Benchmark          P8    /bi/benchmark
    L3 tabs: Visao geral | PDD | Evolucao | Fundos
    Fonte: CVM Dados Abertos (cvm_benchmark via postgres_fdw).
    Ver docs/integracao-cvm-fidc.md.
```

### Filtros globais (barra superior do modulo BI, URL-persisted)

Periodo (date range) · Produto · UA · Cedente · Sacado · Gerente

### Priorizacao para Sprint 5

P1 Operacoes → P2 Carteira → P3 Comportamento → P4 Receitas → P5 Fluxo de caixa → P6 DRE → P7 Ficha → P8 Benchmark

---

## PARTE 2 — Warehouse canonico em `gr_db` (entregue no S6)

| Tabela `gr_db` | Origem MSSQL | Linhas bootstrap | Serve L2 |
|---|---|---|---|
| `wh_titulo_snapshot` | `ANALYTICS.elig_snapshot_titulo` | ~214k (3.5 meses) | Carteira (P2), Comportamento (P3), Ficha (P7) |
| `wh_operacao` | Bitfin `Operacao` + `OperacaoResultado` | ~9k | Operacoes (P1), Receitas (P4), Ficha (P7) |
| `wh_operacao_item` | Bitfin `OperacaoItem` | ~94k | Operacoes (P1), drill-down |
| `wh_titulo` | Bitfin `Titulo` | ~94k | Fluxo de caixa (P5), Ficha (P7) |
| `wh_dre_mensal` | `ANALYTICS.vw_DRE` | ~3.8k | DRE (P6) |
| `wh_dim_mes` | `ANALYTICS.DimMes` | ~100 | calendario |
| `wh_dim_dre_classificacao` | `ANALYTICS.DREClassificacao` | ~50 | hierarquia DRE |

**Mixin `Auditable` em toda tabela `wh_`**: `source_type`, `source_id`, `source_updated_at`, `ingested_at`, `hash_origem`, `ingested_by_version`, `trust_level`, `collected_by`. Migration `25a3ad5c782c` aplicada em `gr_db`. Populacao pelo ETL no Sprint 3.

> **Nota — dados publicos de mercado:** as tabelas `wh_*` cobrem apenas dados transacionais internos (Bitfin + ANALYTICS), com escopo por `tenant_id`. Dados publicos de mercado (CVM FIDC) vivem em DB **separada** `cvm_benchmark` no mesmo cluster Postgres da VM 27 e sao lidos pelo `gr_db` via `postgres_fdw` sob o schema `cvm_remote`. Servem o L2 **Benchmark** (P8). Arquitetura completa em [`integracao-cvm-fidc.md`](./integracao-cvm-fidc.md) e padrao definido em CLAUDE.md §13.1.

### Numeros de referencia (bootstrap de abril/26)

- Carteira ativa: R$ 45,03 MM · inadimplencia R$ 6,90 MM (~15,3%)
- 93 cedentes · 2.356 sacados · 10 produtos (FAT 32% · CMS 31% · DMS 9% · demais <10%)
- Abril/26 (ate 20): 135 operacoes efetivadas · R$ 21,19 MM bruto · R$ 613k de juros/desagio
- Titulos a vencer (horizonte ate abril/27): R$ 39,7 MM
- DRE: 9 meses disponiveis (ago/25 a abr/26)

---

## PARTE 3 — Pendencias do usuario (para completar o inventario)

Itens que Ricardo ainda vai complementar conforme lembrar:
- Aberturas especificas de Fluxo de caixa alem de "Projecao liquidacoes" e "Apropriacao de desagio"
- Conteudo completo da Ficha (alem das 5 tabs ja previstas)
- Qualquer L3 das 6 secoes que nao tenha entrado na lista inicial
- Formulas DAX especificas quando formos entrar em cada dashboard no Sprint 5

---

## PARTE 4 — Inventario detalhado do PowerBI (preenchimento incremental)

Preencha **um bloco por dashboard/relatorio** conforme for detalhando. Nao precisa ser perfeito na primeira passada — prefira cobrir todos os dashboards em alto nivel primeiro (secoes 1-4 de cada bloco) e depois retornar para detalhar formulas DAX (secao 5).

---

## Template por dashboard

Copie o bloco abaixo e preencha um por dashboard. Pode ser em ordem de importancia (mais usado primeiro).

```
### Dashboard: <Nome>

**1. Identificacao**
- Nome exato do tab/relatorio:
- Arquivo .pbix de origem (se mais de um):
- URL/path no PowerBI Service (se publicado):

**2. Quem usa e para que**
- Audiencia primaria: (ex.: analista de credito, gerente, diretoria, compliance)
- Frequencia tipica de consulta: (diaria / semanal / mensal / sob-demanda)
- Pergunta principal que responde: (uma frase)
- Decisoes que esse dashboard apoia: (bullets curtos)

**3. Visuais principais**
Liste cada visual/chart/tabela que aparece na tela, em ordem de destaque:
- [ ] Visual 1: <tipo> — <o que mostra>  (ex.: "KPI: Receita do mes")
- [ ] Visual 2: <tipo> — <o que mostra>  (ex.: "Linha: Receita mensal ultimos 12m")
- [ ] Visual 3: ...

**4. Filtros / slicers / parametros**
Campos que o usuario pode filtrar/ajustar:
- Periodo: (data inicial/final ou periodo relativo?)
- Unidade de negocio / filial:
- Produto / carteira:
- Outros:

**5. Metricas / medidas DAX**
(Pode preencher depois em segunda passada.)

Para cada numero/KPI, liste:
- **<Nome da metrica>**:
    - Tabela(s) Bitfin de origem: (ex.: dbo.Contratos, dbo.Titulos)
    - Calculo/formula (em DAX ou descricao em portugues): (ex.: "SUM(Titulos[Valor]) WHERE Titulos[Status] = 'Pago' AND Titulos[Data] IN periodo")
    - Granularidade: (dia / mes / ano / por cliente / etc)
    - Unidade: (R$ / % / unidade / dias)

**6. Drill-downs e interatividade**
- Ao clicar em um visual, o que acontece?
- Ha navegacao para outra pagina?
- Algum tooltip customizado com dados extras?

**7. Frequencia de atualizacao dos dados**
- Refresh agendado: (horario, ou on-demand)
- Fonte direta do Bitfin ou via view do ANALYTICS?

**8. Limitacoes / dores atuais**
- O que nao funciona bem hoje?
- O que voce gostaria de ver mas nao ve?
- Algum dashboard que abriu mao porque PowerBI nao da conta?
```

---

## Exemplo preenchido (ficticio, para voce ter como referencia)

```
### Dashboard: Inadimplencia Geral

**1. Identificacao**
- Nome exato do tab/relatorio: Inadimplencia
- Arquivo .pbix de origem: RelatoriosGR.pbix
- URL/path no PowerBI Service: https://app.powerbi.com/groups/<id>/reports/<id>

**2. Quem usa e para que**
- Audiencia primaria: analista de credito + diretoria
- Frequencia tipica de consulta: diaria (manha)
- Pergunta principal: Qual a taxa de inadimplencia corrente e como evoluiu?
- Decisoes apoiadas: priorizar cobranca, alertar diretoria, revisar limites.

**3. Visuais principais**
- [ ] Visual 1: KPI — Taxa de inadimplencia D+1 (ex: 3.6%)
- [ ] Visual 2: KPI — Valor inadimplente total (R$)
- [ ] Visual 3: Linha — Evolucao da inadimplencia ultimos 12 meses
- [ ] Visual 4: Barras empilhadas — Inadimplencia por faixa de atraso (0-30, 31-60, 61-90, 90+)
- [ ] Visual 5: Tabela — Top 20 cedentes com maior inadimplencia

**4. Filtros / slicers / parametros**
- Periodo: datepicker (default: mes vigente)
- Filial: dropdown (Matriz / Filiais)
- Produto: dropdown multi-select

**5. Metricas / medidas DAX**
- **Taxa de inadimplencia D+1**:
    - Tabela(s): dbo.Titulos
    - Formula: SUM(titulos em atraso > 1 dia) / SUM(titulos ativos)
    - Granularidade: carteira inteira (do filial/produto selecionados)
    - Unidade: %

- **Valor inadimplente total**:
    - Tabela(s): dbo.Titulos
    - Formula: SUM(Titulos[ValorAberto] WHERE Titulos[DiasAtraso] > 0)
    - Granularidade: idem
    - Unidade: R$

**6. Drill-downs e interatividade**
- Clicar em barra de faixa → abre lista de titulos daquela faixa
- Clicar em cedente da Top 20 → abre dashboard individual (outra pagina)

**7. Frequencia de atualizacao dos dados**
- Refresh agendado: a cada 4h (06, 10, 14, 18)
- Fonte: ANALYTICS.vw_Inadimplencia (view que consolida de dbo.Titulos + dbo.Contratos)

**8. Limitacoes / dores atuais**
- Refresh lento — as vezes demora 30min
- Nao cruza com bate-de-mercado (info fora do ERP)
- Dashboard cai se tiver mais que 500k titulos
```

---

## Dica de preenchimento em estagios

Se voce tiver muitos dashboards (ex: 15+), sugiro **3 passadas**:

1. **Passada 1 (rapida — 1h):** preencha secoes 1-4 de TODOS os dashboards (sem detalhar DAX)
2. **Passada 2 (media — 2-3h):** preencha secao 5 (formulas) nos dashboards mais criticos
3. **Passada 3 (opcional):** secoes 6-8 para refinamento

Na passada 1 ja me entrega lista suficiente para comecar o Sprint 2. Detalhes de formula vamos destrinchar dashboard por dashboard.

---

## O que EU vou fazer em paralelo (enquanto voce preenche)

- Explorar o schema `UNLTD_A7CREDIT` (Bitfin): tabelas principais, chaves, relacoes
- Explorar o schema `ANALYTICS`: views e tabelas existentes, entender o que ja esta pre-computado
- Documentar aqui embaixo (secao "Anexo A — Schema Bitfin") os achados

Seu preenchimento + minha exploracao convergem no **desenho do warehouse canonico** (Sprint 2 fim) — o subset de tabelas que o GR vai manter em `gr_db` para servir o modulo BI.

---

## Anexo A — Schema Bitfin `UNLTD_A7CREDIT` (preenchido via MCP)

**Escala:** 294 tabelas, schema `dbo`.

### Tabelas mais relevantes para BI (top por volume + importancia)

| Tabela | Rows | Dominio |
|---|---|---|
| `Endereco` | 1.311.126 | Cadastros |
| `Titulo` | 93.772 | Titulos (duplicatas, cheques, notas) |
| `OperacaoItem` | 94.391 | Itens de operacao |
| `TituloDuplicata` | 90.369 | Duplicatas |
| `Trajeto` | 95.047 | Logistica |
| `ProcedimentoDeCobranca` | 91.476 | Cobranca |
| `CobrancaAcoesOcorrencia` | 70.139 | Cobranca |
| `SuporteDeTituloLoteItem` | 68.535 | Titulos |
| `PosicaoHistoricaReciprocidade` | 66.562 | Posicao historica |
| `TituloFiscal` | 58.568 | NFe relacionada |
| `OperacaoSacado` | 54.390 | Operacao x Sacado |
| `DocumentoFiscalNFe` | 40.445 | **NFe (relevante para Etapa C/laboratorio)** |
| `Operacao` | 9.044 | **Operacoes (master)** |
| `OperacaoResultado` | 9.044 | Resultado de operacao |
| `OperacaoRentabilidade` | 13.319 | Rentabilidade |
| `Empresa` | 15.316 | Empresas (cedentes + sacados) |
| `Sacado` | 15.930 | Sacados |
| `Cliente` | 521 | **Cedentes (clientes do FIDC)** |
| `DemonstrativoDeResultado` | 3.399 | DRE |
| `IndicesFinanceiros` | 1.760 | Indices |

**Conclusao:** fonte riquissima, mas **complexa demais** para o MVP. O pulo do gato e que o ANALYTICS **ja resolve** essa complexidade com views pre-agregadas.

---

## Anexo B — Schema ANALYTICS (preenchido via MCP) — **ACHADO-CHAVE DO SPRINT 2**

**Escala:** 6 objetos apenas (3 tabelas + 3 views) — mas tudo pre-estruturado para consumo BI.

### Objetos

| Nome | Tipo | Volume | Periodo | Proposito |
|---|---|---|---|---|
| `DimMes` | tabela (dimensao) | — | — | Calendario (Ano/Mes/Trimestre/Semestre/MesNome) |
| `DREClassificacao` | tabela (dimensao) | — | — | Hierarquia DRE (Categoria, GrupoDRE, SubGrupo) |
| `vw_DRE` | view | 3.851 | **2025-08 a 2026-04** (9 meses) | DRE mensal (Receita, Custo, Resultado por grupo/subgrupo) |
| `vw_elig_titulo_carteira_total` | view | 93.725 | hoje (live) | Carteira atual de titulos com aging + dimensoes |
| `vw_elig_titulo_base` | view | 5.831 | hoje (live) | Subset elegivel (provavelmente carteira ativa nao vencida ou similar) |
| `elig_snapshot_titulo` | **tabela** (fato historico) | **214.028** | **2026-01-02 a 2026-04-19** (3.5 meses) | **Snapshots diarios materializados** |

### Schema de `elig_snapshot_titulo` (a estrela do BI)

Dimensoes ja desnormalizadas:
- **Temporal:** `snapshot_id`, `data_ref` (date)
- **Produto:** `produto_sigla` (FAT/CMS/DMS/CBV/NOT/INT/FOM/CFD/CBS/CCB), `produto_descricao`, `recebivel_sigla`, `recebivel_descricao`
- **Status:** `Status`, `Situacao`, `situacao_descricao`
- **Cedente:** id, nome, documento (CNPJ), grupo economico (id+nome), flag RJ, CNAE completo (secao/divisao/grupo/classe/subclasse/denominacao)
- **Sacado:** id, nome, documento, grupo economico, flag RJ
- **Unidade:** `UnidadeAdministrativaId`
- **Outros:** `gerente_nome/documento`, `Coobrigacao`

Metricas ja agregadas:
- **Saldos:** `saldo_total`
- **Aging (valor):** `vencido`, `vencido_mais_5_dias`, `vencido_d0_a_d5`, `vencido_ate_d30`, `vencido_ate_d60`, `vencido_60_ate_120`, `vencido_maior_d120`
- **Quantidades:** `qtd_titulos`, `qtd_operacoes`, `qtd_cedentes`, `qtd_sacados`
- **Ticket:** `ticket_medio`
- **Atraso:** `atraso_max`, `atraso_medio`

### Numeros reais (hoje, 2026-04-19)

| Indicador | Valor |
|---|---|
| Carteira total | **R$ 45,03 MM** |
| Inadimplencia (vencido) | **R$ 6,90 MM (~15,3%)** |
| Cedentes ativos | 93 |
| Sacados ativos | 2.356 |
| Operacoes abertas (~) | 2.661 linhas no snapshot |

### Evolucao semanal (ultimos ~20 dias)

Vai de R$ 43,7 MM (01/04) → R$ 45,0 MM (19/04). Dados bem consistentes, com snapshots **diarios** (so ha gaps em fins de semana/feriado).

### Composicao da carteira por produto (hoje)

| Produto | Saldo (R$) | % |
|---|---|---|
| Faturização (FAT) | 14,65 MM | 32.5% |
| Comissária (CMS) | 14,01 MM | 31.1% |
| Domicílio Simples (DMS) | 4,17 MM | 9.3% |
| Cobrança Vinculada (CBV) | 2,85 MM | 6.3% |
| Nota Comercial (NOT) | 2,50 MM | 5.6% |
| Intercompany (INT) | 2,48 MM | 5.5% |
| Fomento (FOM) | 1,72 MM | 3.8% |
| Confissão de Dívida (CFD) | 1,70 MM | 3.8% |
| Cobrança Simples (CBS) | 0,85 MM | 1.9% |
| CCB | 0,12 MM | 0.3% |

### Schema de `vw_DRE`

- Temporal: `Ano`, `Mes`, `Competencia` (date)
- Hierarquia: `OrdemGrupo`, `GrupoDRE` (9 grupos: RECEITA_OPERACIONAL, PROVISAO_PDD, DESPESA_ADMINISTRATIVA, COMISSAO_COMERCIAL), `SubGrupo`, `Descricao`
- Medidas: `Receita`, `Custo`, `Resultado`, `Quantidade`
- Dimensoes adicionais: `Fornecedor`, `FornecedorDocumento`, `EntidadeId`, `ProdutoId`, `UnidadeAdministrativaId`, `Fonte`

### Implicacao estrategica para Sprint 2+

> **O ANALYTICS ja e o warehouse BI.** O que a gente tem que fazer e **copiar/sincronizar essas views para o `gr_db`**, adicionando metadata de proveniencia. Nao precisamos remodelar 294 tabelas do Bitfin.

**Proposta de tabelas no `gr_db` (warehouse do GR):**

1. `warehouse_fact_titulo_snapshot` — espelho de `elig_snapshot_titulo` + colunas Auditable
2. `warehouse_fact_titulo_carteira_atual` — espelho de `vw_elig_titulo_carteira_total` + Auditable (atualizado diariamente)
3. `warehouse_fact_dre_mensal` — espelho de `vw_DRE` + Auditable
4. `warehouse_dim_mes` — espelho de `DimMes`
5. `warehouse_dim_dre_classificacao` — espelho de `DREClassificacao`

ETL no Sprint 3: leitura incremental por `data_ref` / `Competencia` + upsert com metadata de proveniencia (`source_type="erp:bitfin"` — via ANALYTICS — `ingested_at`, `source_updated_at`, `ingested_by_version="analytics_adapter_v1.0.0"`).

**Carteira inicial no bootstrap:** ingerir os 214k snapshots historicos (3.5 meses) + DRE mensal (9 meses) de uma vez.
