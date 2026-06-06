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

Cada dataset externo tem uma **identidade estável**, ex.:

| Fonte | dataset_code | Exemplo |
|---|---|---|
| BigDataCorp | `CAD-PJ` (public_code) | dados cadastrais PJ |
| QiTech | `fidc-estoque` | estoque de recebíveis |
| Bitfin | `carteira` | posição da carteira |
| Serasa PJ | `relatorio_pj` | business information report |

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
| source_type | text | `bdc` / `qitech` / `bitfin` / `serasa_pj` … |
| dataset_code | text | código técnico/neutro do dataset |
| public_code | text null | white-label tenant-facing (quando aplicável) |
| version | int | versão do contrato (imutável — ver 7.3) |
| status | enum | `draft` / `active` / `archived` |
| owner | text | dono da governança |
| description | text | |
| tenant_id | uuid null | **Começa sempre global (NULL).** Override por tenant é futuro (ver 14.3) |

`(source_type, dataset_code, version)` UNIQUE. **Tabela NOVA e genérica**
(decisão 14.1) — não estende `provedor_dados_dataset`; este último (white-label
BDC) apenas **linka** para o contrato via `public_code`.

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
4. **Fase 3 — Tool/agente dirigidos por contrato.** `get_dados_cadastrais`
   monta output por `to_agent` + descrições.
5. **Fase 4 — Silver/check dirigidos por contrato.** Promoção a coluna por
   `to_silver`; checks leem `to_check`.
6. **Fase 5 — UI de curadoria** (admin) + fila de campo novo.
7. **Fase 6 — Generalizar** para QiTech/Bitfin/Serasa.

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

> Todas as decisões de arquitetura estão resolvidas. Doc estável — pronto para
> a Fase 1 (implementação).

---

Relacionado: CLAUDE.md §13 (adapter + bronze/silver), §13.2.1 (silver-only),
§14 (auditabilidade), §19 (camada agêntica), `docs/esteira-credito-fontes-externas.md`,
`docs/WAREHOUSE_LAYERS.md`.
