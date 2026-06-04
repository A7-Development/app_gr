# Esteira de Crédito — Catálogo de Fontes Externas (BigDataCorp / Serasa / VADU)

> **Status:** documento vivo (iniciado 2026-06-04). Organiza os endpoints de
> dados externos que a esteira consome — por função, custo, modo e nível de
> credencial. Complementa [esteira-credito-ia-map.md](./esteira-credito-ia-map.md)
> (Camada 1 — cesta de primitivos). Cada dataset tem **dicionário de dados**
> próprio no BigDataCorp — puxar ao fiar o adapter/mapper (semântica de campo).

## 1. Modelo de credenciais e billing (decisão 2026-06-04, Ricardo)

- **Nível MANTENEDOR (global):** BigDataCorp (todos os datasets) + um **Serasa
  próprio**. Credenciais cifradas no nível do mantenedor — espelha o padrão de
  IA (`ai_provider_credential` global + `is_system_maintainer`, §19.2/§13).
- **Nível TENANT:** **apenas Serasa**, e **opcional** — só quando o cliente tem
  contrato próprio. Resolução em runtime: usa a credencial do tenant se existir;
  senão **cai na do mantenedor** (nosso Serasa).
- **Billing:** o tenant consome via sistema e **paga por consulta** conforme
  política comercial (a definir). Metering por consulta, espelhando
  `ai_usage_event`. Custo da fonte (tier abaixo) alimenta o preço.
- **Implementação futura:** `data_provider_credential` (global) +
  `tenant_source_config` (override Serasa por tenant) + metering + tabela de
  preço por fonte. Não implementar agora — registrar a forma.

## 2. Tiers de custo (combustível do guard de orçamento — transversal #2)

| Tier | Característica | Política de uso |
|---|---|---|
| **Barato** | cadastral, ~R$ 0,02, sync | liberal; roda cedo (gate antes do pago) |
| **Médio** | KYC, mídia, grupo, sync | node no grafo; sob orçamento |
| **Caro / async** | `ondemand-*`, Relacionamentos (batch) | node explícito, **gated por alerta**; engine durável (suspend/resume) |

## 3. Catálogo BigDataCorp

> Todos no nível **MANTENEDOR**. Status: **IN** = na fase exploratória ·
> **DEFER** = entra quando subir o tier de custo.

### 3.1 Empresa (PJ)
| Dataset (técnico) | Função | Dimensão | Custo | Modo | Status |
|---|---|---|---|---|---|
| `empresas-dados-cadastrais-basicos` | CNAE, situação, idade, capital, natureza, regime, histórico | **Gate A2** + cross-checks + contexto financeiro | **R$ 0,02** | sync | **IN** |
| `empresas-kyc-e-compliance` | sanções/PEP/restrições da PJ | Compliance | médio | sync | DEFER |
| `empresas-kyc-e-compliance-dos-socios` | KYC do QSA | Compliance | médio | sync | DEFER |
| `ondemand-receita-federal-qsa` | **QSA oficial da Receita** (sócios) | Societária (fonte-ouro p/ cross-check QSA × contrato) | caro/ondemand | async | DEFER |
| `ondemand-receita-federal-representante-legal` | **representante legal oficial** (Receita) | Societária / poderes | caro/ondemand | async | DEFER |
| `economic_group_kyc` | grupo econômico (empresas+pessoas, direto+indireto) | Vínculos/grupo | médio-alto | sync | DEFER |
| `Relacionamentos` (+ `Relacionamentos do Grupo Econômico`) | **arestas** empresa→entidades (societário, trabalho, grupo) | Vínculos/grupo | alto | **async/batch** | DEFER |

### 3.2 Pessoa (PF)
| Dataset (técnico) | Função | Dimensão | Custo | Modo | Status |
|---|---|---|---|---|---|
| `pessoas-dados-cadastrais-basicos` | identidade do sócio | Identidade | barato | sync | **IN** |
| `pessoas-historico-de-dados-basicos` | mudança cadastral (sinal de fachada) | Veracidade | barato | sync | **IN** |
| `pessoas-nivel-de-envolvimento-politico` | **score PEP** (doações, eleições, cargo) | Exposição política/PEP | confirmar (público→provável barato) | sync | **IN*** |
| `pessoas-candidatos-eleitorais` | foi candidato | PEP | confirmar | sync | **IN*** |
| `pessoas-historico-politico-familiar` | PEP por família | PEP | confirmar | sync | **IN*** |
| `pessoas-prestadores-de-servicos-eleitorais` | prestou serviço eleitoral (PEP indireto) | PEP | confirmar | sync | **IN*** |
| `pessoas-kyc-e-compliance` | KYC do sócio | Compliance | médio | sync | DEFER |
| `pessoas-kyc-e-compliance-familiares-primeiro-nivel` | **parentes 1º nível** + KYC | Vínculos (parentes) + Compliance | médio | sync | DEFER |
| `pessoas-exposicao-e-perfil-na-midia` + `pessoas-dados-de-popularidade` | mídia adversa / reputação | Reputação | confirmar | sync | DEFER |
| `ondemand-policia-civil-antecedentes-criminais-pessoa` | antecedentes criminais | Risco criminal | caro/ondemand | async | DEFER (gated) |

> *`IN*`* = entra na exploratória **se** o custo do cluster PEP confirmar barato
> (dado público eleitoral). Senão, DEFER. Ricardo marcou PEP como importante.

## 4. Serasa — DEFERIDO (fase posterior)
- Nível **TENANT** (contrato próprio do cliente) **OU** **MANTENEDOR** (nosso Serasa).
- Adapters já existem: `serasa_pj` wired. `serasa_pf` placeholder.
- GOTCHA conhecido: `score_h4pj` 100% NULL no contrato A7 segmento 028.

## 5. VADU — sem API → MANUAL
- Não automatizável. Entra como **passo humano** (analista consulta e declara;
  confrontado contra o descoberto pelas fontes automáticas).

## 6. Dicionários de dados
Cada dataset BigDataCorp tem um dicionário de dados próprio (semântica exata de
cada campo). **Puxar o dicionário ao construir o adapter/mapper** de cada
dataset — é o que garante o mapeamento raw→silver correto (§13.2).
