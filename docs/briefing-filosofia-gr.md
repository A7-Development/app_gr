# Briefing — Filosofia do Sistema GR

> Documento autocontido para apresentacao institucional do sistema GR (Gestao de Risco da A7 Credit). Serve de fonte para criacao de slides/material visual. NAO exige conhecimento previo do projeto.

---

## 1. Contexto em uma frase

> **O GR e uma plataforma de inteligencia de dados para FIDCs que transforma dados dispersos em decisoes auditaveis.**

---

## 2. O problema que resolve

Um FIDC (Fundo de Investimento em Direitos Creditorios) hoje opera com **dados ricos, mas dispersos e subutilizados**:

- **Dados operacionais** vivem no ERP (sistema de gestao)
- **Dados regulatorios oficiais** vivem na API do administrador (QiTech)
- **Dados transacionais detalhados** vivem em arquivos XML de NFe armazenados em pastas
- **Dados de credito** vivem em APIs de bureaus externos (Serasa, SCR Bacen)
- **Dados autodeclarados** pelo cedente vivem em formularios e documentos
- **Conhecimento de mercado** (bate de mercado) vive em telefonemas e memoria do analista

Cada decisao de credito passa por combinar isso **manualmente** — processo lento, inconsistente, e com **nenhuma trilha de auditoria** em um segmento que exige rastreabilidade regulatoria (CVM, ANBIMA, Bacen).

---

## 3. O que o GR **e**

- Uma **camada de inteligencia** em cima do ERP existente (nao o substitui)
- Uma **plataforma de agregacao e reconciliacao** de multiplas fontes de dados
- Um **laboratorio para validar teses preditivas** (ex.: correlacao entre atributos de NFe e inadimplencia)
- Um **sistema auditavel por design** — cada decisao carrega trilha de rastreabilidade ate as linhas originais do warehouse

## 4. O que o GR **nao e**

- Nao e um ERP (nao tira pedido, nao emite boleto, nao faz cobranca)
- Nao e um BI generico (nao e so dashboard — e inteligencia com proveniencia)
- Nao e um data lake sem proposito (todo dado ingerido tem uma tese por tras)
- Nao e caixa-preta (todo output e explicavel)

---

## 5. Arquitetura em camadas

```
┌────────────────────────────────────────────────────────────┐
│   Camada 1 — FONTES DE DADOS                               │
│   ERP interno  •  Admin API  •  NFe XML  •  Bureaus        │
│   Autodeclarado  •  Bate de mercado  •  Outras APIs        │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│   Camada 2 — ADAPTERS (plugin pattern)                     │
│   Um adapter por endpoint/API. Versionados.                │
│   Configuraveis por cliente. Zero refactor para nova fonte.│
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│   Camada 3 — STORAGE                                       │
│   RAW (blobs):  XMLs, PDFs, responses — preservacao intacta│
│   WAREHOUSE (Postgres):  modelo canonico entity-centric    │
│                          com PROVENIENCIA em cada linha    │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│   Camada 4 — INTELIGENCIA                                  │
│   Agregacoes  •  Reconciliacao  •  Scoring proprio         │
│   Laboratorio de teses  •  Alertas  •  Forecasts           │
└────────────────────────┬───────────────────────────────────┘
                         ▼
┌────────────────────────────────────────────────────────────┐
│   Camada 5 — APLICACAO                                     │
│   API REST multi-tenant modular                            │
│   Frontend com trust metadata visivel em cada numero       │
└────────────────────────────────────────────────────────────┘
```

---

## 6. Fontes de dados — o mapa

| Fonte | Tipo | Confiabilidade | Uso principal |
|---|---|---|---|
| ERP (Bitfin) | Operacional interna | Alta | Contratos, titulos, pagamentos |
| Admin (QiTech) | Regulatorio oficial | Alta | Numeros publicados CVM/bolsa |
| NFe (XMLs) | Terceiro factual | Alta | Detalhe da transacao (produto, regime, ticket) |
| Bureaus externos | Terceiro factual | Alta | Protestos, processos, socios, rating |
| Autodeclarado (cedente) | Cliente | Baixa/media | Balanco, DRE, faturamento, divida |
| Bate de mercado (peers) | Relacionamento | Media | Reputacao com outras instituicoes |

**Filosofia:** nenhuma fonte isolada conta a historia toda. O valor esta em **cruzar** todas.

---

## 7. Tratamento dos dados — os 5 pilares

### 7.1 Proveniencia obrigatoria
Cada linha do warehouse carrega, como metadado obrigatorio:
`source_type` • `source_id` • `ingested_at` • `source_updated_at` • `trust_level` • `versao do adapter`

Nao ha dado anonimo. Voce sabe **de onde veio**, **quando chegou**, e **quao confiavel e**.

### 7.2 Entity resolution
Mesma empresa ou pessoa aparece em varias fontes com grafias/ids diferentes. O GR unifica essas aparicoes em uma **entidade canonica** (CNPJ/CPF normalizado + heuristicas de nome), criando um dossie completo por entidade.

### 7.3 Cross-validation
Sistema compara automaticamente o mesmo fato em fontes diferentes:
- Faturamento declarado × soma das NFes emitidas
- Endividamento declarado × SCR Bacen
- Bitfin × QiTech
- "Principais clientes" declarados × destinatarios recorrentes das NFes

Divergencias viram **alertas** ou **entradas no painel de reconciliacao**.

### 7.4 Versionamento
Premissas, regras e modelos **nao sao hard-coded** — vivem em tabelas versionadas. Uma decisao tomada com v1 jamais se "atualiza" — referencia v1 eternamente. Auditor pode rodar qualquer decisao antiga com os mesmos inputs e reproduzir o mesmo output 5 anos depois.

### 7.5 Audit trail
Tabelas append-only (`decision_log`, `premise_set`) registram todas decisoes/calculos. Sem UPDATE, sem DELETE. Correcao se da por nova entrada que referencia a anterior.

---

## 8. Os 8 modulos do sistema

```
┌──────────────────────┬──────────────────────┐
│   BI                 │   CADASTROS          │
│   Dashboards,        │   Empresas, pessoas, │
│   analises, relat.   │   cedentes, sacados  │
├──────────────────────┼──────────────────────┤
│   OPERACOES          │   CONTROLADORIA      │
│   Contratos, titulos,│   Contabilidade,     │
│   pagamentos         │   DRE, balancete     │
├──────────────────────┼──────────────────────┤
│   RISCO              │   INTEGRACOES        │
│   Scoring, PDD,      │   Adapters, catalogo │
│   stress, limites    │   de fontes, sync    │
├──────────────────────┼──────────────────────┤
│   LABORATORIO        │   ADMIN              │
│   Teses, correlacoes,│   Tenants, users,    │
│   experimentos       │   roles, config      │
└──────────────────────┴──────────────────────┘
```

Cada modulo e:
- **Isolado em codigo** (bounded context)
- **Permissionado** por usuario (RBAC granular)
- **Licenciavel** separadamente (relevante para spinoff B2B)
- **Acessivel via UI** com entry point proprio

---

## 9. Objetivos em fases

### Fase 0 (MVP — 4-6 semanas)
> **Substituir o PowerBI atual por um modulo BI nativo**

Time de credito e risco para de usar PowerBI e passa a usar o GR para os dashboards do dia a dia. Dados vem direto do ERP com proveniencia visivel.

### Fase 1 — Reconciliacao
Painel automatico Bitfin ↔ QiTech. Divergencias surgem na tela antes do auditor perguntar.

### Fase 2 — Ficha consolidada do cedente
Uma tela por cedente mostrando tudo que o sistema sabe dele: NFes, endividamento, processos, socios, autodeclarado, bate de mercado, historico interno.

### Fase 3 — Laboratorio de teses
Ambiente para testar hipoteses: "sera que regime tributario correlaciona com inadimplencia?" — valida ou invalida com dados historicos reais.

### Fase 4 — Catalogo de bureaus + enriquecimento
Framework extensivel de fontes externas. Adicionar bureau novo = dado (config), nao codigo.

### Fase 5 — Scoring proprio (esteira evolutiva)
- **v1:** heuristica explicavel (regras)
- **v2:** modelos interpretaveis (regressao, GBM com SHAP)
- **v3:** ML avancado com explicabilidade preservada

### Fase 6 — Spinoff
Plataforma B2B para o segmento de FIDCs: onboarding de clientes externos, billing, SSO, audit exportavel.

---

## 10. O moat — por que nao comoditiza

Em um mundo onde **todos** terao acesso a IA generica para escrever codigo e construir dashboards, o que **resiste** ao tempo?

**O que a IA comoditiza:**
- Escrita de codigo, UI, adapters, arquitetura basica

**O que a IA NAO comoditiza:**
- **Dados proprietarios acumulados** (label store de desfechos, teses validadas)
- **Rede de participantes** (bate de mercado estruturado entre FIDCs)
- **Confianca regulatoria** (auditabilidade como DNA, nao feature)
- **Calibracao especifica do segmento** (score treinado com o portfolio real de voces)
- **Processos validados** (workflow embutido que o cliente nao quer refazer)

> **Em um mundo de commoditizacao, vence quem tem o contexto que a IA precisa.**
> O GR nao e "software com IA dentro". E a plataforma que **acumula o contexto que transforma IA generica em IA util para FIDC**.

---

## 11. Pilar transversal — Confianca regulatoria

Em mercado financeiro regulado, **explicabilidade + rastreabilidade valem mais que sofisticacao**. Recomendacao de IA sem trilha de auditoria nao passa em compliance. O GR e construido com essa disciplina em **todas as camadas** desde o dia 1.

### Traduzido em produto:

- **Immutable decision log** — toda decisao registrada, imutavel
- **Premissas como dado** — editaveis, versionadas, visiveis
- **Replay** — rodar decisao antiga com os dados antigos, mesmo output
- **What-if** — mudar premissa e ver impacto, sem exportar Excel
- **Trust metadata na UI** — badges e tooltips mostrando origem de cada numero
- **Explicacao por decisao** — 3-5 fatores principais sempre registrados

---

## 12. Sugestoes de metaforas visuais

Para a apresentacao, metaforas que podem ajudar a comunicar:

- **"Rio de dados"** — multiplas nascentes convergindo em um warehouse canonico
- **"DNA de auditabilidade"** — helice dupla representando proveniencia + rastreio
- **"Torre de controle"** — GR como centro de observacao de todas as fontes
- **"Laboratorio"** — bancada com teses em teste, validadas, descartadas
- **"Rede neural de FIDCs"** — no futuro, peers conectados via bate-de-mercado estruturado

---

## 13. Sequencia sugerida de slides

Uma possivel estrutura narrativa (adaptavel):

1. **Capa** — "GR: Inteligencia auditavel para FIDCs"
2. **O problema** — dados dispersos, decisoes manuais, sem auditoria
3. **A solucao em uma frase** — camada de inteligencia auditavel
4. **O que e / o que nao e** — lado a lado
5. **As 6 fontes de dados** — cards lado a lado
6. **Arquitetura em 5 camadas** — diagrama vertical
7. **Os 5 pilares do tratamento** — proveniencia, entity resolution, cross-validation, versionamento, audit trail
8. **Os 8 modulos** — grid 4×2
9. **Roadmap** — timeline com 7 fases
10. **O moat** — texto forte sobre diferenciacao no mundo com IA comoditizada
11. **Pilar transversal: auditabilidade** — destaque visual
12. **Proxima entrega** — MVP de substituicao do PowerBI em 4-6 semanas
13. **Encerramento / CTA**

---

## 14. Paleta sugerida (opcional)

Se fizer sentido para a identidade A7 Credit:

- **Amarelo A7** (`#F0B000` aprox.) — destaque, identidade
- **Azul A7** (`#1E56A0` aprox.) — estrutura, confianca
- **Cinzas neutros** — corpo de texto, bordas
- **Verde** — sucesso, dado confiavel
- **Vermelho** — alerta, divergencia, dado de baixa confianca

---

## 15. O que **nao** colocar nos slides

- Detalhes tecnicos de implementacao (FastAPI, Postgres, adapters, etc.) — audiencia e estrategica
- Nomes de bibliotecas
- Codigo
- Arquitetura de pastas
- Credenciais ou referencias a clientes especificos

Foco: **o que o sistema faz**, **por que importa**, **para onde vai**.
