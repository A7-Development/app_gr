# Contratos de Dados — Governança de campos de fontes externas

> **Status:** documento vivo (rascunho de arquitetura). Iniciado 2026-06-06.
> Direção aprovada por Ricardo: criar uma forma única de organizar o
> tratamento dos dados de TODA fonte externa (BigDataCorp, QiTech, Bitfin,
> Serasa e futuras). Refinar antes de implementar.
>
> Tratar como referência viva, não especificação fechada. Decisões em aberto
> na seção 14.

---

## 0. TL;DR

Toda fonte externa devolve dados ricos. Hoje, **quem decide o que fazer com
cada campo é o dev, espalhado em código** (no mapper, na view, na tool, no
agente, no check). Isso é frágil, inconsistente e tira a decisão do dono do
negócio.

A proposta: **um Contrato de Dados por dataset** — uma definição única,
versionada e governada por humano, que descreve cada campo da fonte E decide,
**num lugar só**, o destino dele nas 5 superfícies de consumo:

1. **Silver** — vira coluna canônica?
2. **Tela** — é apresentado?
3. **Tools** — entra no output que o agente lê?
4. **Agentes** — fica disponível no contexto do agente?
5. **Checks** — alimenta verificação determinística?

**Dev constrói o mecanismo que lê o contrato; o usuário é dono da política.**
As 5 superfícies viram **projeções** do contrato — ninguém mais hardcoda
relevância de campo.

---

## 1. O problema

Cada fonte (BDC `CAD-PJ`, QiTech `fidc-estoque`, Bitfin carteira, Serasa PJ…)
devolve dezenas a centenas de campos. Para cada campo, alguém precisa decidir:

- guardo no silver? como coluna tipada ou no blob de overflow?
- mostro na tela? com que rótulo, em que ordem?
- entrego pra uma tool consumir?
- deixo o agente ver? com que descrição?
- uso num check determinístico?

Hoje essas decisões estão **dispersas e implícitas no código**, tomadas pelo
dev caso a caso. Sintomas concretos já observados:

- O `load_cadastral_silver_view` expunha 8 campos escolhidos a dedo (o dev
  decidindo relevância) — o resto do `basic_data` ficava invisível.
- Um campo objeto (`LegalNature = {Code, Activity}`) renderizado cru quebrou a
  tela inteira (React #31), porque o tratamento por campo não era governado.
- Não há forma de o **dono do negócio** dizer "esse campo importa, aquele não"
  sem pedir deploy.

**Princípio fundador (Ricardo, 2026-06-06):** o dev/agente **nunca** decide
quais campos de um dataset externo são relevantes. Default = preservar e expor
tudo; a curadoria de relevância é do usuário.

---

## 2. Princípios

1. **Fonte única da verdade.** Um contrato por dataset descreve cada campo e
   seu roteamento. As 5 superfícies leem o contrato — não reimplementam a
   decisão.
2. **Dev = mecanismo, usuário = política.** O dev constrói o motor que lê o
   contrato e projeta. O usuário edita o contrato (rótulo, relevância,
   roteamento) sem deploy — igual aos prompts em DB (§19.4), credit_policy, e o
   white-label (§13/§19).
3. **Nada se perde.** O raw (bronze) guarda 100% sempre (§13.2). O contrato
   decide o que SOBE/APARECE, nunca o que é descartado na origem.
4. **Defaults sãos, curadoria incremental.** Default tela = mostrar tudo.
   Default silver/tool/agente/check = só o que algum consumidor pediu. Campo
   novo entra como `não classificado` e é sinalizado. Cura-se o que importa,
   quando importa.
5. **Fato vs contexto.** Cada campo é marcado como **fato determinístico**
   (auditável, pode alimentar check/score) ou **contexto** (informa a narrativa
   do agente). Mantém a fronteira do §14 (número é fato; julgamento é do
   agente).
6. **White-label e PII por tag, não por código.** Sensibilidade do campo
   (público/interno/PII) é metadado; os consumidores agem pela tag (esconder
   vendor §13/§19, redigir PII §19.9).
7. **Proveniência sempre.** Todo campo carrega de onde veio (fonte, versão do
   adapter) pra auditoria; o agente cita.

---

## 3. Conceito: Contrato de Dados (Data Contract)

Espelha o conceito de **Data Contract** do mercado: um acordo formal,
versionado, com dono, que define schema + semântica + qualidade + governança de
um dataset — **em nível de campo**.

Para nós, o contrato tem duas partes:

- **Cabeçalho do contrato** (1 por dataset): identidade da fonte/dataset,
  versão, dono, status, white-label (public_code neutro).
- **Campos do contrato** (N por dataset): um registro por campo, com metadado +
  flags de roteamento para as 5 superfícies.

### 3.1 Hierarquia: Provedor → API/Endpoint → Dataset → Campo

Um provedor não é um endpoint só. O BDC, por exemplo, tem **várias APIs**
(Empresas, Pessoas, Notas Fiscais…), e cada API serve **vários datasets** (o
parâmetro `Datasets` da chamada). O contrato precisa dessa hierarquia de 4
níveis:

```
Provedor            ex.: BigDataCorp            (credenciais, base_url, billing)
  └─ API/Endpoint   ex.: Empresas (POST /empresas), Pessoas (POST /pessoas)
       └─ Dataset   ex.: basic_data, ondemand_rf_qsa, relationships, political_involvement (PEP)
            └─ Campo ex.: TaxIdStatus, Activities[].Code, LegalNature.Activity
```

O **Contrato de Dados é por DATASET** (o nível onde os campos vivem); Provedor e
API são os **agrupadores** acima dele — para navegação, credenciais e billing.

Exemplos de identidade:

| Provedor | API/Endpoint | Dataset (code) | public_code | Conteúdo |
|---|---|---|---|---|
| BigDataCorp | Empresas | `basic_data` | `CAD-PJ` | dados cadastrais PJ |
| BigDataCorp | Empresas | `ondemand_rf_qsa` | `QSA-PJ` | QSA oficial Receita |
| BigDataCorp | Pessoas | `basic_data` | `CAD-PF` | dados cadastrais PF |
| BigDataCorp | Pessoas | `political_involvement` | `PEP-PF` | PEP |
| QiTech | FIDC | `fidc-estoque` | — | estoque de recebíveis |
| Bitfin | Carteira | `carteira` | — | posição da carteira |
| Serasa PJ | Relatório | `relatorio_pj` | — | business information report |

> White-label: Provedor/API/dataset_code são **internos** (vendor); o
> tenant/agente só vê o `public_code` + rótulos. A gestão (admin/maintainer) vê a
> hierarquia completa.

---

## 4. As 5 superfícies e a dependência entre elas

As superfícies **não são independentes** — há uma cadeia natural:

```
check   ⇒  precisa de coluna SILVER tipada + validada   (§13.2.1: check nunca lê raw)
silver  ⇒  promove o campo quando ALGUÉM determinístico precisa ("a análise define a coluna")
tool    ⇒  lê silver (fato) e/ou normaliza do raw (contexto)
agente  ⇒  lê o output da tool + a descrição do campo   (o que ele PODE ver, não o que "usa")
tela    ⇒  pode mostrar qualquer campo                  (default = tudo; raw blob ok)
```

Regras que caem disso:

- **Campo usado por check ⇒ tem que ser coluna silver.** Check é o consumidor
  mais exigente (determinístico, tipado, auditável).
- **Promoção a silver é dirigida por necessidade downstream**, não por palpite.
  Um campo vira coluna quando um check/tool/cruzamento precisa
  consultar/juntar/calcular sobre ele.
- **Agente ≠ check.** Pra check, crava-se o campo exato e tipado. Pro agente,
  decide-se o que ele **pode ver** (no output da tool) + a **descrição**; o
  raciocínio escolhe o que usar. Não se micro-gerencia "o que o agente usa".
- **Tela é a mais permissiva** (default mostrar tudo); a curadoria só melhora
  rótulo/ordem e esconde ruído.

---

## 5. Tratamento agêntico (o "novo conceito")

Em sistema com agentes, "o que o agente usa" não é um gate duro — é
**engenharia de contexto**. Diretrizes:

- **Tool é a API do agente pros dados.** O agente não lê o banco; lê o **output
  da tool**, tipado e **com descrição por campo**. A descrição do campo (do
  contrato) vira o **dicionário** que o modelo entende.
- **Contexto curado e generoso, não cru nem dump.** Entregar ao agente o
  conjunto **normalizado** (campos `to_agent`) + descrições. Evitar despejar o
  blob vendor-shaped cru (o mesmo objeto que quebrou a tela confunde o modelo e
  gasta token). Mas — princípio §2 — o dev não corta relevância: o default é
  generoso, a curadoria afina.
- **Fato vs contexto explícito.** A tool entrega os fatos (`eh_fato`) como
  números auditáveis; o agente raciocina, não recalcula (§14). Campos de
  contexto informam a narrativa.
- **Least-privilege por escopo.** O agente só recebe tools/dados do seu
  `ScopedContext` (tenant/módulo/permissão — §19). O contrato roteia; o registry
  filtra por escopo.
- **PII e white-label antes do LLM.** Campos `sensibilidade=PII` são redigidos
  antes de subir (§19.9); campos `interno` (identidade de vendor) nunca entram
  no contexto tenant-facing nem no do agente.

---

## 6. Camadas e onde o contrato atua

```
Fonte externa
   │  fetch (adapter §13)
   ▼
BRONZE  wh_<vendor>_raw_*        ← payload cru, imutável, 100% preservado (§13.2)
   │  mapper (lê o CONTRATO: quais campos promover, tipos, normalização)
   ▼
SILVER  wh_<entidade> / colunas canônicas + blob de overflow
   │  projeções (lêem o CONTRATO)
   ├──▶ TELA      (campos on_screen, ordem/rótulo)
   ├──▶ TOOL      (campos to_tool, normalizados)  ──▶ AGENTE (to_agent + descrição)
   └──▶ CHECK     (campos to_check ⇒ colunas silver)
```

O contrato é **lido nos dois sentidos**:
- **No mapper** (bronze→silver): decide o que promover e como tipar/normalizar.
- **Nas projeções** (silver→superfícies): decide o que cada consumidor vê.

---

## 7. Modelo de dados (proposta a refinar)

Duas tabelas. (Para BDC, o cabeçalho pode reaproveitar/linkar o
`provedor_dados_dataset` que já existe; para QiTech/Bitfin/Serasa, nasce do
genérico. Ver decisão aberta 14.1.)

### 7.1 `dataset_contract` — cabeçalho (1 por dataset)

| Coluna | Tipo | Nota |
|---|---|---|
| id | uuid | |
| provider | text | `bdc` / `qitech` / `bitfin` / `serasa_pj` … (agrupador 1) |
| api_endpoint | text | `empresas` / `pessoas` / `fidc` … (agrupador 2 — ver 3.1) |
| dataset_code | text | código técnico do dataset (onde os campos vivem) |
| public_code | text null | white-label tenant-facing (quando aplicável) |
| version | int | versão do contrato (imutável — ver 7.3) |
| status | enum | `draft` / `active` / `archived` |
| owner | text | dono da governança |
| description | text | |
| tenant_id | uuid null | **Começa sempre global (NULL).** Override por tenant é futuro (ver 14.3) |

`(provider, api_endpoint, dataset_code, version)` UNIQUE. **Tabela NOVA e
genérica** (decisão 14.1) — não estende `provedor_dados_dataset`; este último
(white-label BDC) apenas **linka** para o contrato via `public_code`.

> Provedor + API são **agrupadores** (seção 3.1), usados para navegação na UI,
> credenciais e billing. Metadados de provedor (base_url, credencial) já vivem no
> catálogo de provedores existente; aqui carregamos `provider` + `api_endpoint`
> como atributos do contrato para não fragmentar a resolução. Se a navegação
> pedir, promovem-se a tabelas próprias (`data_provider` / `provider_api`).

### 7.2 `dataset_field` — campo do contrato (N por dataset)

| Coluna | Tipo | Decide / serve |
|---|---|---|
| id | uuid | |
| contract_id | uuid FK | |
| field_path | text | ex.: `LegalNature.Activity`, `AdditionalOutputData.CapitalRS` |
| public_label | text | rótulo pt-BR (tela + dicionário do agente) |
| description | text | glossário — para humano E agente |
| semantic_type | enum | text/number/date/bool/money/cnpj/cnae/enum/object |
| categoria_ui | text | identidade/situação/atividade/capital/histórico… |
| sensibilidade | enum | `publico` / `interno` / `pii` |
| eh_fato | enum | `fato_deterministico` / `contexto` |
| **to_silver** | bool | promove a coluna canônica? |
| silver_target | text null | nome da coluna/tabela silver alvo |
| **on_screen** | bool | exibe na tela? |
| screen_order | int null | ordem na tela |
| **to_tool** | bool | entra no output da read-tool? |
| **to_agent** | bool | entra no contexto do agente? (default = `to_tool`) |
| **to_check** | bool | usado por check? (⇒ implica `to_silver`) |
| status | enum | `curado` / `novo_nao_classificado` |
| classified_by | text null | quem curou |
| classified_at | timestamptz null | |

### 7.3 Versionamento (decisão 14.2: IMUTÁVEL + ponteiro ativo)

Espelha `ai_prompt` / `playbook_definition`:

- `dataset_contract` é **imutável por versão** — toda edição (campos, rótulos,
  roteamento) **cria uma nova versão**, copiando a base + patch. A versão base
  nunca muda (preserva audit trail).
- **`dataset_contract_active`** — uma linha por `(source_type, dataset_code
  [, tenant_id])` apontando para a `dataset_contract_id` em produção. Trocar de
  versão = 1 UPDATE (**rollback de 1 clique, sem deploy**).
- `dataset_field` pertence a uma versão do contrato (FK para `contract_id`), logo
  acompanha a imutabilidade.
- As superfícies resolvem **sempre a versão ativa** (`resolve_contract` lê o
  ponteiro), salvo quando uma execução fixa uma versão para reprodutibilidade
  (auditoria §14).

---

### 7.4 Convenção de `field_path` (decisão 14.5)

Notação intuitiva, sem ambiguidade:

- **Objeto aninhado:** ponto. Ex.: `LegalNature.Activity`,
  `AdditionalOutputData.CapitalRS`.
- **Array de objetos:** `[]` marca o nível do array; o caminho **continua** para
  o campo do elemento. Ex.: o array em si = `Activities[]`
  (`semantic_type=array`); os campos por elemento = `Activities[].Code`,
  `Activities[].Activity`, `Activities[].IsMain`. O roteamento definido no campo
  do elemento (ex.: `to_screen` em `Activities[].Activity`) vale para **todos**
  os elementos.
- **Array de escalares:** `Tags[]` (`semantic_type=array`).

O detector de campo novo (seção 9) gera o `field_path` por esta convenção ao
varrer o payload.

## 8. Como cada superfície consome o contrato

- **Mapper (bronze→silver):** itera os campos `to_silver`, lê `field_path` do
  raw, normaliza por `semantic_type` (inclui coerção objeto→texto que evitou o
  React #31), grava em `silver_target`. Campos não-`to_silver` ficam no blob de
  overflow (já preservados no raw).
- **Tela:** endpoint devolve resumo (campos validados) + projeção dos campos
  `on_screen` ordenados por `screen_order`, com `public_label`. Render genérico
  já existe (`RawDataFields`); passa a ler o contrato p/ rótulo/ordem.
- **Tool:** a read-tool monta o output só com campos `to_tool`, normalizados,
  cada um com sua `description` (vira o dicionário do agente).
- **Agente:** recebe o output da tool (campos `to_agent`) + descrições. Fatos
  (`eh_fato`) tratados como números auditáveis; contexto informa narrativa.
- **Check:** lê a coluna silver de campos `to_check` (sempre `to_silver`).
  Determinístico, tipado, auditável.

Mecanismo central: um **resolver de contrato** (`resolve_contract(source,
dataset)`) que cada superfície chama para obter os campos do seu interesse.

---

## 9. Campo novo + ciclo de curadoria (HITL)

Quando uma consulta traz um campo **fora do contrato**:

1. Detector insere o campo como `status=novo_nao_classificado`.
2. **Default = mostrar na tela + sinalizar** (transparência; decisão Ricardo
   2026-06-06). Nada fica escondido sem o usuário saber.
3. O campo aparece numa fila de curadoria pro usuário: rotular, categorizar,
   decidir roteamento (silver/tool/agente/check).
4. Curadoria é versionada e auditável.

Reaproveita o padrão de curadoria HITL já desenhado (ver
`project_curadoria_classificacao` — guard → fila → humano decide → ativa
versionado → audita).

---

## 10. Generalização (vale pra todas as fontes)

O contrato é **por dataset**, então o conceito se aplica igual a:

- **BigDataCorp** — `CAD-PJ` (cadastral), e futuros PEP/QSA/vínculos. Cabeçalho
  liga no `provedor_dados_dataset` (white-label).
- **QiTech** — `fidc-estoque`, posição de cota, etc. Hoje cada um tem mapper
  ad-hoc; passariam a ler o contrato.
- **Bitfin** — carteira/títulos (SQL Server). Mapper dirigido por contrato.
- **Serasa PJ/PF** — relatórios. Hoje mapper dedicado; idem.

Ganho: **uma disciplina só** pra ingerir, tipar, expor e governar dados de
qualquer fonte — em vez de N tratamentos artesanais.

---

## 11. Boas práticas de mercado (referência)

- **Data Contracts** — acordo versionado por dataset, dono humano, em nível de
  campo. É a espinha desta proposta.
- **Medallion (bronze/silver/gold)** — raw→canônico→consumo. Já adotado (§13.2);
  as 5 superfícies são "gold".
- **Semantic/Metrics layer** (dbt, Cube, LookML) — defina uma vez, consuma em
  todo lugar. As superfícies como projeções.
- **Data catalog c/ metadata de campo** (DataHub, OpenMetadata, Collibra) —
  governança em nível de campo: rótulo, glossário, tags, lineage, dono.
- **Tagging + policy-as-code** — tags (PII, interno, exibível) que os
  consumidores respeitam.
- **Feature store** — features definidas uma vez, servidas a treino+inferência
  iguais. Precursor do score próprio.
- **Agentic / context engineering** — tool schema + descrições de campo como a
  API e o dicionário do agente; least-privilege; fato vs contexto.

---

## 12. Não-objetivos (evitar)

- **Não** virar um cadastro gigante obrigatório que trava ingestão. Defaults
  sãos resolvem 90%; curadoria é incremental.
- **Não** descartar dado na origem. Raw sempre completo.
- **Não** acoplar a um vendor. O contrato é genérico; white-label preservado.
- **Não** transformar o agente num consumidor de whitelist rígida (isso é
  check). Agente recebe contexto curado + descrição e raciocina.

---

## 13. Roadmap de implementação (proposta)

1. **Fase 0 — Conceito (este doc).** Alinhar e refinar.
2. **Fase 1 — Modelo + resolver.** Tabelas `dataset_contract` +
   `dataset_contract_active` + `dataset_field` (global, imutável + ponteiro);
   `resolve_contract()` lê a versão ativa; seed do contrato do `CAD-PJ` (BDC) a
   partir dos campos reais já conhecidos.
3. **Fase 2 — Projeção de tela dirigida por contrato.** O card cadastral passa a
   ler `on_screen`/`public_label`/`screen_order`. Detector de campo novo.
4. **Fase 5 — UI de curadoria de campos** (admin, a *folha*) + 🆕. ✅ *feita.*
5. **Fase F — Fundação / Catálogo (o tronco) ← PRÓXIMA.** Navegador
   `Provedor → API/Endpoint → Dataset` sobre `provedor_dados_dataset` (§15.3):
   curadoria de dataset (habilitar + `public_code` + nome pt-BR + categoria +
   markup), coluna de estado do Contrato, drill pro dataset, "criar contrato"
   pré-populado por `flatten_paths()`. A tela de campos (Fase 5) vira o drill.
   Resolve as decisões 14.8/14.9 antes de codar.
6. **Fase 3 — Tool/agente dirigidos por contrato.** `get_dados_cadastrais`
   monta output por `to_agent` + descrições.
7. **Fase 4 — Silver/check dirigidos por contrato.** Promoção a coluna por
   `to_silver`; checks leem `to_check`.
8. **Fase 6 — Generalizar** para QiTech/Bitfin/Serasa (origem *adapter*: linha
   de catálogo cadastrada à mão + contrato semeado, §15.1).

---

## 14. Decisões

### Resolvidas (2026-06-06, Ricardo)

1. ✅ **Onde mora o cabeçalho:** **tabela NOVA e genérica** (`dataset_contract`),
   não estender `provedor_dados_dataset`. O catálogo BDC/white-label apenas linka
   pro contrato via `public_code`.
2. ✅ **Versionamento:** **imutável + ponteiro ativo** (`dataset_contract_active`),
   estilo `ai_prompt` — rollback de 1 clique. Ver 7.3.
3. ✅ **Override por tenant:** **começar global** (tenant_id NULL). Override por
   tenant fica como evolução futura (sem quebrar o modelo — basta preencher
   tenant_id depois).
4. ✅ **Agente ≠ check:** confirmado. Pro agente cura-se o que ele *pode ver*
   (`to_agent`) + descrição, e o raciocínio escolhe; só o **check** tem whitelist
   tipada rígida (campos `to_check` ⇒ colunas silver). Ver seções 4 e 5.

5. ✅ **Granularidade do `field_path`:** notação ponto + `[]` (ver 7.4).
6. ✅ **Metadado por campo:** `eh_fato` + `semantic_type` **bastam** por ora.
   Metadado extra de qualidade (nullable, domínio, regra de validação) fica
   adiado até um caso de uso concreto pedir — mantém o modelo enxuto.
7. ✅ **Ordem de migração dos mappers:** **BDC → QiTech → Bitfin → Serasa.**
   (BDC `CAD-PJ` já é o seed da Fase 1; as demais seguem nessa ordem na Fase 6.)

### Resolvidas (fundação — 2026-06-06, Ricardo)

8. ✅ **Nomeação do dataset (`public_code` + `display_name_pt_br`):
   auto-sugerida + aprovação.** O Catálogo deriva uma sugestão do código do
   vendor (ex.: `ondemand_rf_qsa` → `QSA-PJ` / "QSA Receita") como **rascunho
   cinza**; nada fica habilitado/exposto até o mantenedor confirmar. Respeita
   "usuário é a política" (§2 — nada vai ao ar sem aprovação) sem o custo de 792
   campos em branco. Aprovar = grava como valor curado.
9. ✅ **"Criar contrato" pré-populado sobre payload real.** Ao criar a 1ª versão
   do contrato de um dataset, partir de `flatten_paths()` sobre um payload real
   de `wh_bdc_raw_consulta` (quando houver) — pré-popula a folha com todos os
   `field_path` detectados, status `novo_nao_classificado`. Descobre e mostra,
   mantenedor classifica. Sem payload real, contrato nasce vazio (campos entram
   via 🆕 na 1ª consulta).
10. ✅ **Modo (Marketplace/Adapter) mora na relação `(provedor × tenant)`**, não
    numa coluna fixa do dataset (ver §15.1). No catálogo global do mantenedor o
    modo exibido é o de revenda (Marketplace); BYOC por tenant (ex.: Serasa
    próprio) entra junto com o override por tenant (decisão 14.3, futuro).

> Arquitetura central + fundação de navegação resolvidas. Doc estável — pronto
> para a **Fase F** (Catálogo).

---

## 15. Gestão (UI) — a fundação primeiro

> **Por que esta seção foi reescrita (2026-06-06, Ricardo).** A primeira tela de
> Contratos listava **só o CAD-PJ**. Faltava o *tronco*: não havia como navegar os
> provedores, suas APIs/endpoints e os datasets disponíveis, nem cadastrar o
> "nome da consulta". Construímos a **folha** (curadoria de campos de 1 dataset)
> sem o **tronco** (o catálogo de tudo que existe). Esta seção desenha o tronco.

### 15.0 O tamanho real do problema (por que o tronco importa)

O catálogo do BDC, hoje em `provedor_dados_dataset`, já está sincronizado e é
grande. Curado, quase nada:

| Provedor | APIs/Endpoints | Datasets | Habilitados | Com nome/public_code |
|---|---:|---:|---:|---:|
| BigDataCorp | **15** | **792** | **1** | **1** (CAD-PJ) |
| QiTech / Bitfin / Serasa | (adapters) | — | — | contrato semeado direto |

15 endpoints do BDC: `People` (297), `Companies` (173), `Ondemand` (107),
`Marketplace` (95), `Addresses` (27), `Validations` (25), `Biogenerativa` (16),
`Custom` (16), `Products` (8), `Aiservices` (8), `Misc` (6), `Lawsuits` (5),
`Invoices` (4), `Vehicles` (3), `Receipts` (2). Uma tela que começa pelos
*campos* de *um* dataset não escala pra isso. Precisamos primeiro de uma tela que
**navegue os 792 e deixe o mantenedor decidir o que vira produto**.

### 15.1 As duas origens de um dataset — definidas pela *relação*, não pelo provedor

O modo de um dataset **não é um atributo fixo do provedor**; depende de **de quem
é o contrato/credencial** com o vendor. Mesmo provedor pode operar nos dois modos
ao mesmo tempo, por tenant:

| Origem | Quem detém a credencial | Catálogo é populado por | Preço/markup? |
|---|---|---|---|
| **Marketplace (revenda)** | **mantenedor** — o tenant consome o dado do mantenedor (não tem contrato próprio, ou prefere não usar) | sync de `/precos/` do vendor (descoberta automática) | **sim** (revenda c/ markup) |
| **Adapter (BYOC)** | **o próprio tenant** (*bring your own credential*) ou consumo interno A7 | cadastro à mão / seed (não há catálogo de preços a varrer) | **não** (passthrough/interno) |

**Casos canônicos:**

- **BDC** → sempre Marketplace (credencial do mantenedor; revenda).
- **QiTech, Bitfin** → sempre Adapter (integração própria/interna; sem revenda).
- **Serasa** → **dual**. Marketplace quando o tenant *não tem* contrato Serasa e
  prefere usar o dado do mantenedor (revenda c/ markup); vira Adapter (passthrough,
  sem markup) quando o tenant pluga o **próprio** contrato Serasa.

A chave é **onde mora a credencial daquela relação**: credencial do mantenedor ⇒
Marketplace (mostra custo+markup, switch *Vender*); credencial do tenant ⇒ Adapter
(esconde markup; mostra só *Habilitar*). O **default** de um provedor dual é
Marketplace (revenda do mantenedor); o tenant migra pra Adapter quando traz a
credencial própria — sem mudar o Contrato de campos (o schema do dataset é o mesmo).

Ambas as origens terminam no **mesmo lugar**: uma linha de dataset que pode ganhar
um **Contrato de campos**. O navegador trata as duas; o que muda é só a coluna de
preço/markup e o rótulo do switch.

### 15.2 A hierarquia de navegação (3 níveis no Admin › Dados)

A sidebar do Admin ganha o grupo **Dados** com três níveis, do tronco à folha:

| Nível | Tela | Pergunta que responde | Pattern |
|---|---|---|---|
| **1 · Provedores** | `/admin/dados/provedores` *(existe)* | "Quais fontes eu conecto? Credenciais, base_url, billing." | `ListagemCrudInline` |
| **2 · Catálogo** | `/admin/dados/catalogo` *(NOVO — o tronco)* | "O que cada fonte oferece? Quais APIs/endpoints/datasets existem, e qual eu vendo/uso? Como ele se chama?" | navegador `Provedor → API → Dataset` |
| **3 · Contrato de campos** | drill do Catálogo *(folha, ex-`/contratos`)* | "Dentro deste dataset, o que cada campo faz nas 5 superfícies?" | tabela de campos (Fase 5 atual) |

> A tela de **Contratos** que existe hoje (`/admin/dados/contratos`) deixa de ser
> uma entrada de topo e vira o **drill do Catálogo**: você chega nela clicando num
> dataset. Topo de navegação = Catálogo (o tronco); campo = folha.

### 15.3 Catálogo — o navegador (tela nova, o coração da fundação)

Navega `provedor_dados_dataset` agrupado por **provider → provider_api
(endpoint)**, com curadoria *no nível do dataset*. É aqui que se cadastra o
**nome da consulta** (o `public_code` + `display_name_pt_br`).

```
Admin › Dados › Catálogo
────────────────────────────────────────────────────────────────────────────────
Provedor [ BigDataCorp ▾ ]   Buscar dataset…   ☐ só habilitados  ☐ só sem contrato
                                                            792 datasets · 1 habilitado

▾ Companies · /empresas                                                   173 datasets
  ┌───────────────────────────────────────────────────────────────────────────────┐
  │ Dataset (vendor)     Nome (pt-BR) · public_code   Vender Contrato  Custo  Ações│
  │ basic_data           Cadastro PJ · CAD-PJ           ☑    ● v3 ✓    R$0,12  ⋯   │
  │ ondemand_rf_qsa      QSA Receita · QSA-PJ           ☑    ○ criar   R$0,40  ⋯   │
  │ relationships        — (sugerir: REL-PJ)            ☐    ○ —       R$0,08  ⋯   │
  │ owners_and_…         — (sugerir: …)                 ☐    ○ —       R$0,15  ⋯   │
  └───────────────────────────────────────────────────────────────────────────────┘
▸ People · /pessoas                                                       297 datasets
▸ Ondemand · /ondemand                                                    107 datasets
▸ Marketplace …                                                            95 datasets
```

Colunas e o que cada uma cadastra:

- **Nome (pt-BR) · public_code** — o *nome da consulta*. Editável inline ou no
  drill. Enquanto vazio, mostra `—` + uma **sugestão** (ver decisão 14.8). O
  `public_code` é o único identificador que vaza pro tenant/agente (white-label).
- **Vender** (`enabled_for_sale`) — switch mestre. Dataset novo nasce `☐` (não
  some, mas não é vendável/usável até o mantenedor revisar).
- **Contrato** — estado do Contrato de campos do dataset:
  - `● v3 ✓` tem contrato ativo (badge clicável → drill pra folha §15.4)
  - `○ criar` sem contrato ainda → botão cria a 1ª versão e abre a folha
  - `○ —` sem contrato e sem urgência (dataset não habilitado)
- **Custo** (`current_cost_brl`) + **markup** (no drill) — só origem Marketplace.
- **⋯ Ações** — Editar nome/categoria/markup · Ver schema/exemplo · Criar/abrir
  contrato · Habilitar/desabilitar.

**Drill do dataset** (DrillDownSheet, antes de descer pros campos): nome pt-BR +
`public_code` + categoria + descrição + markup + custo + **exemplo de payload
real** (de `wh_bdc_raw_consulta`) + atalho **"Abrir contrato de campos →"**.

### 15.4 Folha — curadoria de campos (a tela que já existe)

Inalterada no conteúdo; só muda o *como se chega*. Chega-se do Catálogo (clicando
em `● v3` ou `○ criar`), não mais por seletor de chips de topo.

```
Catálogo › Companies › basic_data (CAD-PJ)              v3 (ativa) ●   [ ← Catálogo ]
──────────────────────────────────────────────────────────────────────────────
⚠ 2 campos novos não classificados        [ Revisar ]     [ + Nova versão ]

Buscar…   Categoria ▾   Sensibilidade ▾   ☐ só não classificados
                                                        │ projeção p/ superfície
Campo                  Rótulo (pt-BR)     Cat.    Fato   │ Silv Tela Tool Agt Chk
TaxIdStatus            Situação cadastral situação fato  │  ☑   ☑    ☑   ☑   ☑
FoundedDate            Data de fundação   situação fato  │  ☑   ☑    ☑   ☑   ☑
LegalNature.Activity   Natureza jurídica  identid. ctx   │  ☐   ☑    ☑   ☑   ☐
Activities[].Code      CNAE (código)      atividade fato │  ☑   ☑    ☑   ☑   ☑
HistoricalData…        Histórico          histórico ctx  │  ☐   ☑    ☐   ☑   ☐  🆕
```

Drill por campo: `field_path`, tipo, sensibilidade, proveniência · **Rótulo
pt-BR** + **Descrição/glossário** (dicionário do agente) · Categoria ·
Fato/Contexto · os **5 toggles** com regras embutidas (Check ⇒ liga Silver) ·
**valor de exemplo real** ao lado. Salvar = nova versão imutável → **Ativar**.

### 15.5 Mapa completo das telas de gestão

| Grupo | Telas |
|---|---|
| **IA / Agentes** | Agentes & Personas · Prompts · Playbooks · Tools/Checks · Provedores LLM · Assinaturas · Uso · Conversas |
| **Dados** | **Provedores** (conexão) · **Catálogo** (datasets — tronco) · **Contrato de campos** (folha, drill) · Sincronizações/Cobertura |
| **Crédito** | Política (CNAEs/limites) · Templates de documento · Checks |
| **Plataforma** | Tenants · Usuários · Permissões/Módulos |

### 15.6 Princípios de UX

- **Tronco → folha.** Sempre se navega do amplo (provedor/endpoint/dataset) pro
  específico (campo). Nunca se cai numa folha sem ver a árvore.
- **Default transparente.** Dataset novo e campo novo aparecem (`☐` / 🆕) — nada
  some sem o mantenedor ver. Curadoria *revela e organiza*, nunca esconde por
  conta própria (princípio §2).
- **Curar vendo o dado.** Exemplo de payload real ao lado, tanto no dataset
  quanto no campo. Decisão informada, não no abstrato.
- **Efeito visível.** Coluna "Contrato" no Catálogo e as 5 colunas de toggle na
  folha mostram, numa olhada, o estado de cada coisa.
- **Sem deploy.** Tudo em DB; nome/markup do dataset preservados entre syncs;
  contrato versionado com ponteiro ativo.

---

Relacionado: CLAUDE.md §13 (adapter + bronze/silver), §13.2.1 (silver-only),
§14 (auditabilidade), §19 (camada agêntica), `docs/esteira-credito-fontes-externas.md`,
`docs/WAREHOUSE_LAYERS.md`.
