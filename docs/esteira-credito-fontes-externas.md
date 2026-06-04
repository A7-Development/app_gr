# Esteira de Crédito — Catálogo de Fontes Externas (BigDataCorp / Serasa / VADU)

> **Status:** documento vivo (iniciado 2026-06-04). Organiza os endpoints de
> dados externos da esteira por **dimensão de análise**, custo, modo e nível de
> credencial. Complementa [esteira-credito-ia-map.md](./esteira-credito-ia-map.md)
> (Camada 1 — cesta de primitivos).
>
> **IN** = na fase exploratória (consultas baratas) · **DEFER** = entra quando
> subir o tier de custo · `IN*` = entra se o custo confirmar barato.

## 0. Como acessar o catálogo completo (mecanismo)

`curl` funciona do ambiente. A doc do BigDataCorp expõe um índice pra agentes:

- **Índice completo:** `curl https://docs.bigdatacorp.com.br/llms.txt` → ~700KB,
  **662 páginas / 254 datasets** (markdown, com descrição por linha).
- **Página de cada dataset:** `…/plataforma/reference/<dataset>.md` — carrega
  descrição + **OpenAPI embutido** (schema request/response = **dicionário de
  dados estruturado**). Baixar cru e ler (sem o summarizer do WebFetch).
- **Preço:** via **API de Preços** (canônica, ver §0.1) — não raspar `.md`.

> Regra: ao construir o adapter/mapper de um dataset, **puxar o `.md` dele** pra
> ter o dicionário exato (OpenAPI → silver, §13.2); o preço vem da API de Preços.

### 0.1 API de Preços (`POST plataforma.bigdatacorp.com.br/precos`)

**Consulta gratuita** (não tem custo). Mesma auth da plataforma (`AccessToken` +
`TokenId`). Dois modos:

1. **Tabela completa** — body `{}` → **todos os datasets habilitados pro cliente
   + tabela de preço com faixas de desconto**. → **fonte de verdade do nosso
   catálogo de custo**; sincronizar periodicamente (alimenta o billing).
2. **Preço estimado** — body `{"API":"People|Companies|...","Datasets":"basic_data, phones, ..."}`
   → **custo total da consulta ANTES de rodar**. → é o **guard de orçamento**
   (transversal #2): o node/agente estima o gasto e decide. Indica também se um
   dataset está em outra API.

> Nomes técnicos na API (ex.: `basic_data`, `phones`, `ondemand_rf_status`) são
> **curtos e agrupados por API** (People/Companies/...) — diferentes do slug da
> doc (`empresas-dados-cadastrais-basicos`). A Tabela Completa dá o **de-para
> autoritativo** (nome técnico ↔ preço ↔ API) do que de fato temos contratado.

## 1. Modelo de credenciais e billing (decisão 2026-06-04)

- **Nível MANTENEDOR (global):** BigDataCorp (todos) + **Serasa próprio**.
  Credenciais cifradas no mantenedor — espelha `ai_provider_credential` +
  `is_system_maintainer` (§19.2/§13).
- **Nível TENANT:** **só Serasa**, **opcional** (contrato próprio do cliente).
  Runtime: usa a do tenant se existir; senão **cai na do mantenedor**.
- **Billing:** tenant consome via sistema e **paga por consulta** (política
  comercial a definir). Metering espelha `ai_usage_event`; o tier de custo
  alimenta o preço.
- **Implementação futura:** `data_provider_credential` (global) +
  `tenant_source_config` (override Serasa) + metering + preço por fonte.

## 2. Tiers de custo (régua do guard de orçamento — transversal #2)

| Tier | Característica | Uso |
|---|---|---|
| **Barato** | cadastral (~R$ 0,02), sync | liberal; roda cedo (gate antes do pago) |
| **Médio** | KYC, mídia, risco, grupo, sync | node; sob orçamento |
| **Caro/async** | `ondemand-*` (certidões), `relacionamentos` (batch) | node explícito, **gated por alerta**; engine durável |

---

## 3. Catálogo BigDataCorp por dimensão

> Todos no nível **MANTENEDOR**. Datasets com `*-de-recencia-configuravel` deixam
> ajustar o quão recente o dado precisa ser (trade-off custo×frescor).

### 3.1 Identidade & cadastral
| Dataset (técnico) | Ent | Função | Status |
|---|---|---|---|
| `empresas-dados-cadastrais-basicos` | PJ | CNAE, situação, idade, capital, natureza, regime, histórico — **R$ 0,02** | **IN** |
| `empresas-historico-de-dados-basicos` | PJ | mudanças cadastrais (sinal de fachada) | **IN** |
| `empresas-evolucao-da-empresa` | PJ | evolução/porte ao longo do tempo | DEFER |
| `empresas-dados-de-registro` | PJ | dados de registro detalhados | DEFER |
| `empresas-dados-de-categoria-comercial-mcc` | PJ | MCC (categoria comercial) | DEFER |
| `pessoas-dados-cadastrais-basicos` | PF | identidade do sócio | **IN** |
| `pessoas-dados-cadastrais-de-recencia-configuravel` | PF | cadastral com frescor ajustável | DEFER |
| `pessoas-historico-de-dados-basicos` | PF | mudança cadastral (fachada) | **IN** |
| `pessoas-informacoes-socio-demograficas` | PF | perfil socio-demográfico | DEFER |
| `empresas/pessoas-enderecos / -telefones / -emails` (+ `-de-pessoas-relacionadas`) | PJ/PF | contatos (e dos relacionados → vínculo) | DEFER |

### 3.2 Societário, vínculos & grupo econômico
| Dataset (técnico) | Ent | Função | Status |
|---|---|---|---|
| `empresas-qsa-de-recencia-configuravel` | PJ | **QSA** (sócios/admins) — mais barato que o ondemand Receita | `IN*` |
| `ondemand-receita-federal-qsa` | PJ | **QSA oficial Receita** (fonte-ouro p/ cross-check) | DEFER (ondemand) |
| `ondemand-receita-federal-representante-legal` | PJ | representante legal oficial | DEFER (ondemand) |
| `empresas-relacionamentos` | PJ | **arestas** empresa→entidades (societário/trabalho) | DEFER (async) |
| `empresas-relacionamentos-do-grupo-economico` | PJ | estrutura do grupo econômico | DEFER (async) |
| `empresas-kyc-e-compliance-do-grupo-economico` | PJ | grupo (empresas+pessoas, direto+indireto) + KYC | DEFER |
| `empresas-influencia-do-quadro-societario` | PJ | peso/influência dos sócios | DEFER |
| `pessoas-kyc-e-compliance-familiares-primeiro-nivel` | PF | **parentes 1º nível** + KYC | DEFER |
| `pessoas-enderecos/-telefones/-emails-de-pessoas-relacionadas` | PF | rede de relacionados | DEFER |

### 3.3 Financeiro & risco
| Dataset (técnico) | Ent | Função | Status |
|---|---|---|---|
| `empresas-comportamento-financeiro-digital` | PJ | comportamento financeiro digital | DEFER |
| `empresas-indicadores-de-atividade` | PJ | indicadores de atividade/operação | DEFER |
| `empresas-presenca-em-cobranca` | PJ | está em cobrança? | DEFER |
| `empresas-devedores-do-governo` | PJ | dívida com governo | DEFER |
| `empresas-mercado-financeiro` | PJ | exposição em mercado financeiro | DEFER |
| `empresas-dados-de-fundos-de-investimento` | PJ | vínculo com fundos | DEFER |
| `empresas-dados-unificados-para-modelagem-x1-5` | PJ | **bundle pronto p/ score** | DEFER |
| `pessoas-risco-financeiro` (+ `-familiar`) | PF | score de risco financeiro | DEFER |
| `pessoas-probabilidade-de-negativacao` | PF | prob. de negativação | DEFER |
| `pessoas-presenca-em-cobranca` | PF | em cobrança? | DEFER |
| `pessoas-informacoes-financeiras` (+ `-de-familiares`) | PF | informações financeiras | DEFER |
| `pessoas-comportamento-financeiro-digital` | PF | comportamento financeiro | DEFER |
| `pessoas-dados-unificados-para-modelagem-x1-5` | PF | bundle p/ score | DEFER |

### 3.4 Jurídico & processos
| Dataset (técnico) | Ent | Função | Status |
|---|---|---|---|
| `empresas-processos-judiciais-e-administrativos` (+ `-dos-socios`) | PJ | processos da empresa e sócios | DEFER |
| `empresas-dados-de-distribuicao-de-processos-judiciais` (+ `-dos-socios`) | PJ | volume/distribuição de processos | DEFER |
| `pessoas-processos-judiciais-e-administrativos` (+ `-de-familiares-de-primeiro-nivel`) | PF | processos da pessoa e familiares | DEFER |
| `pessoas-dados-de-distribuicao-de-processos-judiciais` (+ familiares) | PF | distribuição de processos PF | DEFER |

### 3.5 Compliance & exposição (PEP / sanções / mídia)
| Dataset (técnico) | Ent | Função | Status |
|---|---|---|---|
| `empresas-kyc-e-compliance` (+ `-dos-socios` / `-dos-funcionarios`) | PJ | sanções/PEP/restrições | DEFER |
| `pessoas-kyc-e-compliance` | PF | KYC do sócio | DEFER |
| `pessoas-nivel-de-envolvimento-politico` | PF | **score PEP** (doações, eleições, cargo) | `IN*` |
| `pessoas-candidatos-eleitorais` | PF | foi candidato | `IN*` |
| `pessoas-doacoes-eleitorais` / `empresas-doacoes-eleitorais` (+socios) | PF/PJ | doações eleitorais | `IN*` |
| `pessoas-historico-politico-familiar` | PF | PEP por família | `IN*` |
| `pessoas-prestadores-de-servicos-eleitorais` / `empresas-…` | PF/PJ | serviço eleitoral (PEP indireto) | `IN*` |
| `empresas-envolvimento-politico` | PJ | envolvimento político da PJ | DEFER |
| `pessoas/empresas-exposicao-e-perfil-na-midia` | PF/PJ | mídia adversa | DEFER |
| `pessoas-dados-de-popularidade` | PF | popularidade/exposição | DEFER |
| `pessoas-presenca-online` (+ `-familiar`) / `-passagens-pela-web` | PF | pegada digital | DEFER |
| `pessoas-propensao-aposta-online` / `pessoas-compliance-casas-de-apostas` | PF | exposição a apostas | DEFER |

### 3.6 Certidões & regularidade (on-demand — caras/async, gated)
| Dataset (técnico) | Ent | Função |
|---|---|---|
| `ondemand-receita-federal-situacao-cnpj` | PJ | situação CNPJ oficial |
| `ondemand-pgfn` (+ `-pessoa`) | PJ/PF | dívida ativa PGFN |
| `ondemand-debitos-trabalhistas-negativa` / `-debitos-estaduais-negativa` (+pessoa) | PJ/PF | débitos trabalhistas/estaduais |
| `ondemand-cnj-negativa` (+pessoa) / `ondemand-cgu-negativa` / `-cgu-correcional-negativa-pessoa` | PJ/PF | CNJ / CGU |
| `ondemand-acoes-trabalhistas` (+pessoa) / `ondemand-acoes-judiciais-nada-consta-pessoa` | PJ/PF | ações trabalhistas/judiciais |
| `ondemand-policia-civil-antecedentes-criminais-pessoa` / `-policia-federal-…` | PF | antecedentes criminais |
| `ondemand-optante-simples` / `-arrecadacao-simples-nacional-mei` / `-inscricao-municipal` / `-sintegra-empresa` | PJ | regime/fiscal |
| `ondemand-fgts` / `-habilitacao-comex` / `-tse-quitacao-eleitoral-pessoa` | PJ/PF | regularidade diversa |
| `ondemand-ibama-*` / `-licencas-sanitarias` / `-sicar` / `-siproquim` | PJ/PF | ambiental/sanitário (relevância setorial) |

### 3.7 Contexto adicional (uso pontual)
`empresas-dados-de-sites` · `-anuncios-online` · `-marketplaces` · `-avaliacoes-e-reputacao` · `-premios-e-certificacoes` · `-dados-de-obras-civis` · `-acordos-sindicais` · `-consciencia-social` · `-propriedades-industriais(+socios/func)` | `pessoas-dados-profissionais` · `-conselhos-de-classe` · `-servidores-publicos` · `-turnover-profissional` · `-veiculos-associados-a-pessoa` · `-historico-escolar-e-academico` · `-licencas-e-autorizacoes` · `-programas-de-beneficios-e-assistencia-social(+familiares)`.

---

## 4. Serasa — DEFERIDO (fase posterior)
Nível **TENANT** (contrato próprio) **OU** **MANTENEDOR** (nosso Serasa). Adapters:
`serasa_pj` wired; `serasa_pf` placeholder. GOTCHA: `score_h4pj` 100% NULL no
contrato A7 segmento 028.

## 5. VADU — sem API → MANUAL
Não automatizável. Passo **humano** (analista consulta e declara; confrontado
contra o descoberto pelas fontes automáticas).

## 5.1 APIs de apoio / operação (BDC)

Não são datasets de dado — são APIs operacionais que sustentam o adapter:

| API | Função | Uso no desenho |
|---|---|---|
| **Status / Health** (`GET plataforma.bigdatacorp.com.br/pessoas` e `/empresas`) | API funcional? + **tempo de resposta médio (últimos 5 min)** | **health-gate do adapter**: checar saúde+latência antes de disparar consulta paga/async; circuit-breaker; decisão sync×async (§13 observabilidade) |
| **API de Preços** (`POST /precos`) | tabela de preço + estimativa (gratuita) | sync de custo (billing) + **guard de orçamento** (§0.1) |
| **API de Estatísticas de Uso** (`api-de-estatisticas-de-uso`) | consumo/uso por período | observabilidade de billing / conciliação de consumo |
| **API de Monitoramento** (`api-de-monitoramento-*`: configurar/atualizar/detalhes/diferenças/desabilitar) | **monitora uma entidade e reporta mudanças** ao longo do tempo | **Fase G (monitoramento/reavaliação)** — reanalisar dossiê quando a entidade muda |
| **Chamadas Assíncronas** (`chamadas-assincronas-obter-metadado`) | metadado de jobs async | suporte ao padrão async (Relacionamentos, ondemand) no engine durável |

## 6. Conjunto IN-SCOPE da exploratória (resumo)
`empresas-dados-cadastrais-basicos` (gate A2) · `empresas/pessoas-historico-de-dados-basicos`
(fachada) · `pessoas-dados-cadastrais-basicos` (identidade) · cluster **PEP**
(`IN*`, confirmar custo) · `empresas-qsa-de-recencia-configuravel` (`IN*`, QSA barato).
Resto DEFER até subir o tier de custo.
