# Central de Dados — Arquitetura

> Documento de arquitetura da **Central de Gestão de Dados**: o local único onde o
> mantenedor organiza, separa, entende, classifica e parametriza **todo** dado do
> sistema — venha de onde vier (bureaus, ERPs, admins de fundo, dados públicos,
> documentos, ou cálculo interno). Escala multi-tenant: 1 central, N clientes
> consumindo.
>
> Este doc é o **pai conceitual**. O roteamento campo→superfície
> ([`contratos-de-dados-fontes-externas.md`](./contratos-de-dados-fontes-externas.md))
> é uma peça dentro desta arquitetura.
>
> Status: desenho aprovado (Ricardo, 2026-06-07). Decisões 1–6 resolvidas (§13).

---

## 0. TL;DR

- A central é um **tradutor entre 3 mundos**: **Origem** (como o dado chega, do
  vendor), **Canônico** (o que o dado é, nosso), **Consumo** (como é entregue ao
  tenant/agente). Mantê-los separados e mapeados é a razão de existir da central.
- Hierarquia navegável: **Provedor → Serviço/API → Dataset de origem → Campo**
  (endpoint = atributo do Serviço; Serviço tem um **tipo** — §3.1).
- Duas camadas **transversais** costuram a árvore:
  - **Glossário de Termos Canônicos** — "CNPJ é CNPJ" venha de onde vier (§4).
  - **Produto de Dado (lógico)** — a unidade que o tenant/agente consome; é onde
    moram `public_code` e o contrato; um ou mais datasets de origem o alimentam (§5).
- Multi-tenant: **registro global** (mantenedor) + **entitlement** + **credencial**
  (BYOC vs revenda) + **override** por tenant (§8).

---

## 1. Princípio: a central é um tradutor entre 3 mundos

O mesmo dado é descrito em três línguas diferentes. A central existe para
mantê-las **separadas e mapeadas** — quando se misturam no código (ex.: agente
lendo `TaxIdNumber` do BDC direto), vira inferno ao escalar.

| Mundo | Pergunta | Quem fala |
|---|---|---|
| **Origem** (vendor) | "Como o dado *chega*?" — código do vendor, endpoint, shape cru, preço | BDC, Serasa, QiTech… |
| **Canônico** (nosso) | "O que o dado *é*?" — CNPJ é CNPJ, venha de onde vier | o sistema (silver) |
| **Consumo** (cliente) | "Como é *entregue e usado*?" — public_code, 5 superfícies, política, preço | tenants, agentes |

---

## 2. Melhores práticas de mercado (o que adotamos)

Catálogos maduros convergiram num padrão; pegamos o melhor de cada:

- **DataHub / Apache Atlas** — hierarquia `Plataforma → Container → Dataset →
  SchemaField`, identidade estável (URN), metadados como *aspects* plugáveis.
  → **identidade estável + metadados em grupos**, não colunas soltas.
- **Collibra / Alation** — **Glossário de Negócio** separado da estrutura física;
  termo ↔ coluna é ligação. → **camada semântica transversal** (§4).
- **Unity Catalog / AWS Glue / Dataplex** — **classificações** (PII/sensibilidade)
  das quais penduram **políticas** (mascaramento/acesso). → classifica uma vez,
  política aplica sozinha (§7).
- **Data Contracts (dbt/PayPal)** — contrato versionado produtor↔consumidor. → já
  temos (§5, contrato no produto).
- **Data Mesh** — **data product** com dono/contrato/consumidores + governança
  federada. → o **Produto de Dado** (§5) e o multi-tenant (§8).

Padrão comum: **hierarquia estrutural + glossário transversal + classificações/
políticas + contratos + linhagem + dono + entitlements.**

---

## 3. Hierarquia estrutural

```
Provedor          BDC · Serasa · QiTech · Bitfin · CVM · A7-interno
  └─ Serviço/API  (tipo + endpoint como atributos)   "Companies" · "Relatório PJ" · "FIDC"
       └─ Dataset de origem    o bloco que o vendor devolve: basic_data · cadastral
            └─ Campo de origem      TaxIdNumber · OfficialName   (jeito do vendor)
```

**4 níveis.** "API" e "endpoint": **API/Serviço** = família de operações
(navegável); **endpoint** = a operação concreta (`POST /empresas`), guardada como
**atributo**. A unidade que *significa* algo e ganha contrato é o **Dataset**, não
o endpoint (no BDC, 1 endpoint serve dezenas de datasets via corpo da requisição).

### 3.1 Tipos de Serviço (enum no nó Serviço)

O **tipo** define a forma do adapter, a cadência, o método de descoberta e o
modelo de custo. "API REST síncrona" é só um dos casos:

| Tipo | Como funciona | Exemplos |
|---|---|---|
| `api_on_demand` | request→response síncrono, por entidade; paga por consulta | BDC, Serasa, Infosimples |
| `api_async` | pede→gera job→resultado depois (webhook/polling) | QiTech FIDC estoque |
| `webhook_push` | provedor *empurra* evento sem pedir | callbacks QiTech |
| `batch_pull` | a gente puxa periodicamente (cron) | Bitfin, CVM mensal |
| `db_direct` | ODBC/JDBC no banco do parceiro | Bitfin (SQL Server) |
| `fdw` | foreign tables, leitura remota | CVM (`postgres_fdw`) |
| `file_drop` | retorno bancário, SFTP, upload, e-mail | CNAB Cobrança (Bradesco/Itaú/Vórtx) |
| `doc_extraction` | PDF/imagem → dataset estruturado (OCR/IA) | declaração de faturamento (Opus) |
| `internal_compute` | nós *produzimos* o dataset a partir de outros | DRE, score próprio, classificações (provider = **A7-interno**) |
| `stream` *(futuro)* | eventos contínuos | event bus |

> **`internal_compute` é cidadão de 1ª classe.** Muito do dado mais valioso (DRE,
> scores, classificações) não vem de fora — nós produzimos. Tratar A7 como
> *provedor* com serviços de *compute* põe esses datasets na mesma central (com
> contrato, glossário, linhagem), em vez de soltos no código.

---

## 4. Camada semântica: Glossário de Termos Canônicos (decisão 1 ✅)

Transversal à árvore física. Cada **campo de origem aponta para um termo
canônico**:

```
TERMO CANÔNICO: "CNPJ"  (tipo: identificador-fiscal-PJ · sensibilidade: público)
   ▲                              ▲
BDC.basic_data.TaxIdNumber     Serasa.cadastral.documento
```

O que destrava:

- "CNPJ é CNPJ" deixa de ser promessa e vira **ligação no banco**.
- O **agente raciocina em termos canônicos** ("preciso do CNPJ e do faturamento"),
  não em `TaxIdNumber` — desacopla o agente do vendor.
- **Fallback multi-provedor** fica trivial (§5).

Um termo carrega: nome canônico, descrição/glossário, tipo semântico,
sensibilidade default, unidade (quando numérico). É o **dicionário** que alimenta
agentes e a curadoria.

---

## 5. Produto de Dado (lógico) vs Dataset de Origem (físico) (decisão 2 ✅)

```
PRODUTO DE DADO (lógico — o que o tenant/agente pede):  "Cadastro PJ"   public_code = CAD-PJ
   ├─ servido por →  BDC · Companies · basic_data        (origem física 1)
   └─ servido por →  Serasa · Relatório PJ · cadastral   (origem física 2)
```

- **`public_code` e o Contrato vivem no PRODUTO lógico**, não no dataset do vendor.
  White-label de graça: o tenant pede "CAD-PJ" sem saber a origem.
- Cada **dataset de origem** mapeia seus campos ao produto via **termos canônicos**.
- **Política de roteamento** (qual provedor usar, prioridade, fallback, custo) é
  atributo do produto.
- O **Contrato** (5 superfícies, versionado imutável + ponteiro ativo) ancora no
  produto; campos referenciam o termo canônico.

> **Modelar o nível lógico desde já**, mesmo com 1 provedor por produto no início
> (o produto vira quase um alias da origem). Retrofitar identidade depois é caro —
> lição recorrente do projeto.

### 5.1 O que vai pro silver (regra de promoção)

A pergunta "o que grava no silver vs o que fica só no raw" se resolve assim:

**O raw guarda 100%, sempre.** A camada raw (`wh_<vendor>_raw_*`, §13.2 do
CLAUDE.md) grava o payload cru inteiro, imutável — não se decide nada lá, nada se
joga fora. A decisão é só **o que do raw eu PROMOVO a coluna silver**.

**Silver = recorte promovido por NECESSIDADE downstream, não por palpite.** "A
análise define a coluna." Promove-se um campo quando:

- um **check** precisa validá-lo (determinístico/tipado) — **`to_check ⇒ to_silver`**
  (check nunca lê raw, §13.2.1);
- uma **tool** precisa **filtrar / juntar / calcular / reconciliar** sobre ele;
- ele é **identidade canônica** da entidade (CNPJ, data, valor);
- precisa de **tipagem** (data/número/enum) pra operação determinística.

**Fica só no raw** quando é **contexto** que ninguém computa (texto livre,
descrição, blob aninhado), campo raro/exploratório (🆕 não curado), ou quando
promover só cria coluna que ninguém filtra/junta (peso morto).

**Onde se define:** no contrato, campo a campo, pelo flag **`to_silver`** (+
`silver_target` = a coluna canônica do produto). **Quem decide é o mantenedor**;
campo novo nasce **no raw** (🆕) e é promovido sob demanda. Ver a cadeia completa
entre as 5 superfícies em
[`contratos-de-dados-fontes-externas.md` §4](./contratos-de-dados-fontes-externas.md).

**Default conservador (na dúvida, raw).** Promover depois é **barato** (raw
imutável + mapper idempotente → flip `to_silver`, atualiza mapper, re-roda o ETL
sobre o raw, re-mapeia o histórico). Acoplar consumo ao raw é **caro**. Por isso o
consumo é **silver-only** (§13.2.1): serviço/tela/agente/check leem só silver; só o
mapper toca o raw.

> Regra de bolso: **tudo no raw, sempre; promove pro silver o que alguém vai
> consultar/calcular/checar de forma determinística — decidido no contrato, pelo
> mantenedor. Na dúvida, deixa no raw.**

### 5.2 Convenção de nomes do warehouse

**Princípio (o mais importante):** a silver é nomeada pelo **que o dado É**
(entidade/assunto), **nunca** por quem consome nem por como chegou.

| Eixo | Exemplo | Onde mora |
|---|---|---|
| por **vendor** | `wh_bdc_*` | ❌ só no **raw** (`wh_<vendor>_raw_*`) |
| por **utilidade/uso** | `wh_credito_*`, `wh_consulta_externa_*` | ❌ não na silver → é o **Produto de Dado** (consumo) |
| por **entidade/assunto** | `wh_pj_cadastro` | ✅ **silver** |

Razão: silver existe pra ser **reutilizada** por muitos consumidores. O cadastro
de uma PJ serve crédito, risco e BI — então é nomeado pela entidade, não por um
caso de uso. "Como chegou" é da origem (raw); "quem consome" é do produto.
(Inmon: *subject-oriented*; Kimball: conformado por assunto; medallion: silver
agnóstico a propósito, gold/produto por uso.)

**Taxonomia de prefixos `wh_` (silver):**

| Prefixo | Significado | Exemplos |
|---|---|---|
| `wh_dim_` | dimensão | `wh_dim_mes`, `wh_dim_produto` |
| `wh_posicao_` | posição/snapshot | `wh_posicao_renda_fixa` |
| `wh_saldo_` / `wh_movimento_` | saldo / movimento (FIDC interno) | `wh_saldo_bancario_diario` |
| (entidade nua) | fato/transação interna | `wh_operacao`, `wh_titulo` |
| **`wh_pj_*` / `wh_pf_*`** | **dado de referência de TERCEIRO** (PJ/PF analisada; bureau/registro; vendor-neutro) | `wh_pj_cadastro`, `wh_pj_restricao`, `wh_pj_socio`, `wh_pj_score` |

`wh_` já separa do operacional (`tenant`, `user`, `cadastros_unidade_administrativa`
**não** levam `wh_`). `wh_pj_*` clusteriza tudo sobre uma empresa analisada e é
impossível de confundir com FIDC interno (`wh_operacao`) ou cadastro operacional.

> **Dívida conhecida:** `wh_serasa_pj_*` carrega vendor no nome da silver (padrão
> antigo). O alvo canônico é `wh_pj_*`, alimentado por BDC **e** Serasa; a
> migração do silver Serasa pro canônico é follow-up.

---

## 6. Facetas (metadados em grupos, por nó)

Estilo *aspects* do DataHub — não um amontoado de colunas:

- **Identidade** — código do vendor (origem) · `public_code` (consumo) · versão.
- **Descoberta** — sync de catálogo (BDC `/precos`) · declarado à mão (Serasa,
  QiTech) · introspecção de foreign table (CVM).
- **Acesso** — tipo de serviço (§3.1) · cadência · custo unitário.
- **Canônico** — termo do glossário (campo) · tabela/coluna silver alvo (dataset).
- **Consumo (5 superfícies)** — silver / tela / tool / agente / check (o contrato).
- **Classificação & política** — PII/sensibilidade → mascaramento/redação/acesso (§7).
- **Comercial** — revenda (markup) · BYOC · interno (relação tenant×provedor, §8).
- **Governança** — dono · linhagem (origem→silver→consumidores) · auditoria.

---

## 7. Classificação & política

Classifica-se o **campo/termo** uma vez (vocabulário controlado: `publico`,
`pii`, `sigiloso`, `financeiro`…); a **política** se aplica sozinha:

- **PII** → redação antes de subir a LLM (§19.9 do CLAUDE.md) + mascaramento na tela
  por permissão.
- **Sigiloso** → restringe superfícies (ex.: nunca `to_agent`).
- **Regra dura herdada do contrato:** campo em `check` ⇒ coluna silver tipada.

---

## 8. Multi-tenant (o eixo de escala)

```
REGISTRO GLOBAL (mantenedor)  ── o catálogo de TUDO; contratos globais
        │
        ├─ Entitlement por tenant ── a quais PRODUTOS o tenant tem acesso (assina)
        ├─ Credencial por tenant  ── BYOC (Serasa próprio) vs usa a do mantenedor (revenda)
        └─ Override por tenant     ── contrato/política específica (raro; ponteiro próprio)
```

Mantenedor cura o global uma vez; tenant herda. O que varia por tenant é
**entitlement + credencial + override** — linha/ponteiro extra, sem fork de código.

---

## 9. Modelo de objetos (existente × novo)

| Entidade | Papel | Hoje | Ação |
|---|---|---|---|
| **Provedor** | fonte (governança) | `provedor_dados` (só BDC) | generalizar: + descritores; registrar Serasa/QiTech/Bitfin/CVM/A7-interno |
| **Serviço/API** | grupo navegável + tipo (§3.1) | atributo `api_endpoint` | promover a nível leve (tabela ou agrupador) com `service_type` |
| **Dataset de origem** | bloco do vendor (físico) | `provedor_dados_dataset` | + `origin`/descoberta; passa a mapear p/ produto |
| **Produto de Dado (lógico)** | unidade de consumo + `public_code` + âncora do contrato | ❌ não existe | **NOVO** |
| **Termo Canônico (glossário)** | semântica transversal | ❌ não existe | **NOVO** |
| **Campo** | folha + roteamento 5 superfícies | `dataset_field` | + `termo_canonico_id` |
| **Contrato** | versão imutável + ativo | `dataset_contract(+active)` | âncora migra p/ produto lógico |
| **Classificação/Política** | PII→mascaramento | `sensibilidade` (texto) | virar vocabulário + política |
| **Entitlement tenant×produto** | quem consome o quê | parcial | **NOVO** (futuro próximo) |

---

## 10. Exemplo ponta a ponta

> Tenant pede o **produto "CAD-PJ"** do CNPJ X.
> Central resolve: produto → origem ativa = BDC/Companies/basic_data (ou Serasa, fallback).
> **Adapter** do BDC (código) → payload cru (**origem**).
> Mapper normaliza: `TaxIdNumber→` termo **CNPJ** → coluna silver `cnpj`;
> `OfficialName→` termo **Razão Social** → `razao_social` (**canônico**).
> Contrato do produto roteia campos p/ silver+tela+tool+agente+check; campo PII é
> mascarado por política.
> Agente lê em termos canônicos; tenant vê só "CAD-PJ" + rótulos pt-BR (**consumo**).

Um dado, três mundos, costurados pela central.

---

## 11. O que muda no que já existe (Fase F)

O **Catálogo** (`/admin/dados/catalogo`) e o **Contrato de campos** já no ar
**continuam válidos** — viram a base física (datasets de origem) + o roteamento.
O aprofundamento **adiciona** três camadas conceituais por cima:

1. **Glossário de termos canônicos** (novo).
2. **Produto de Dado lógico** (novo; o `public_code` migra do dataset físico p/ ele).
3. **Classificação/política como vocabulário** (evolui o `sensibilidade` texto).

Nada do que está no ar é jogado fora; é envelopado.

---

## 12. Ordem de construção (proposta)

1. **Generalizar o Provedor** + `service_type` (§3.1) + descritores; registrar
   Serasa/QiTech/Bitfin/CVM/A7-interno como provedores (datasets por
   auto-declaração; campos das colunas silver via introspecção).
2. **Glossário de Termos Canônicos** + ligação `campo → termo`.
3. **Produto de Dado lógico**: mover `public_code`/contrato p/ o produto; dataset
   de origem mapeia pra ele.
4. **Classificação/política** como vocabulário + aplicação (redação/mascaramento).
5. **Entitlement por tenant** + credencial (BYOC) + override.
6. Generalizar mappers (BDC→QiTech→Bitfin→Serasa) pro modelo canônico+termo.

---

## 13. Decisões

### Resolvidas (2026-06-07, Ricardo)

1. ✅ **Glossário de termos canônicos** como cidadão de 1ª classe (§4).
2. ✅ **Produto de Dado lógico** modelado desde já (público no produto; vendor
   mapeia) (§5).
3. ✅ **4 níveis** Provedor→Serviço→Dataset→Campo, endpoint como atributo (§3).
4. ✅ **`service_type` enum** no nó Serviço (§3.1), incluindo `internal_compute`.
5. ✅ Descritores substituem o falso "marketplace vs adapter": **descoberta +
   acesso + comercial** são atributos ortogonais (§6).
6. ✅ **Adapter é mecanismo de implementação** (§13 do CLAUDE.md), não tipo de
   provedor — todo provedor é alcançado por um adapter.

---

## 14. Glossário do documento

- **Provedor** — a fonte/empresa (BDC, Serasa, A7-interno).
- **Serviço/API** — superfície de acesso do provedor; tem `service_type` + endpoint.
- **Dataset de origem** — bloco coerente que uma consulta/sync devolve (físico, vendor).
- **Produto de Dado** — unidade lógica de consumo; carrega `public_code` + contrato.
- **Campo** — dado atômico; aponta para um termo canônico.
- **Termo Canônico** — conceito de negócio vendor-agnóstico (CNPJ, Razão Social).
- **Adapter** — código que fala com um Serviço e converte pro canônico.
- **Contrato** — versão imutável (+ponteiro ativo) que roteia campos às 5 superfícies.

---

Relacionado: [`contratos-de-dados-fontes-externas.md`](./contratos-de-dados-fontes-externas.md)
(roteamento campo→superfície), CLAUDE.md §13 (adapter + bronze/silver), §13.2.1
(silver-only), §14 (auditabilidade), §19 (camada agêntica).
