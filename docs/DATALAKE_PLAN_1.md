# Datalake FIDC — Arquitetura e Escopo

Documento de referência para construção do datalake da plataforma de analytics FIDC. Serve como contexto para sessões de desenvolvimento (Claude Code, Cursor) e como registro das decisões arquiteturais.

---

## 1. Objetivo

Construir um datalake capaz de consolidar todas as fontes de dados relevantes para análise de risco, monitoramento operacional e modelos preditivos (inicialmente default prediction), preservando histórico imutável e permitindo análise longitudinal por CNPJ ao longo do tempo — independentemente da relação atual do CNPJ com o fundo.

---

## 2. Princípios arquiteturais

- **Grão longitudinal por CNPJ:** toda empresa observada tem registro histórico completo, permitindo reconstituir o estado dela em qualquer ponto no tempo.
- **Raw imutável:** documentos originais (XML, JSON, PDF) nunca são modificados. Parsers são versionados; reprocessamento é sempre possível.
- **Separação quente/frio:** dados analíticos consultáveis ficam em Postgres; histórico bruto e snapshots ficam em S3.
- **Modelo de três zonas:** sensível / enriquecimento / inteligência, como base para futuros deployments híbridos on-premises.
- **Schema separado, mesma instância:** o datalake vive em schema dedicado no Postgres do sistema, não em banco separado.

---

## 3. Arquitetura alvo

### 3.1 Camadas

| Camada | Tecnologia | Função |
|---|---|---|
| Raw imutável | S3 | XMLs, JSONs de API, PDFs originais; nunca modificados |
| Analítica quente | Postgres (schema dedicado) | Tabelas estruturadas, indicadores calculados, features para modelos |
| Histórico frio | S3 Parquet | Snapshots periódicos das tabelas analíticas, particionados por data e CNPJ |
| Motor de query | DuckDB embutido no FastAPI | Consulta unificada sobre Postgres + Parquet; executor do dbt |
| Transformações | dbt-duckdb | Versionamento e orquestração das transformações bronze → gold |

### 3.2 Fluxo conceitual

```
Fontes → Raw imutável (S3) → Parsing/ingestão → Postgres analítico → Snapshots Parquet (S3)
                                       ↓
                                 dbt-duckdb transforma
                                       ↓
                                 Features para modelos + Dashboards
```

---

## 4. Inventário de fontes

### 4.1 XMLs operacionais
- **Localização atual:** pasta no servidor Windows `192.168.100.16`
- **Referência de cruzamento:** tabela no banco `UNLTD_A7CREDIT` (SQL Server) com o nome do documento
- **Volume:** alto, acumulativo
- **Destino raw:** S3, particionado por data/cedente
- **Destino estruturado:** Postgres (schema do datalake)
- **Parser:** nfelib + regras customizadas; versionado

### 4.2 Dados comportamentais internos
- **Origem:** banco `UNLTD_A7CREDIT` (SQL Server)
- **Escopo:** liquidez, inadimplência (diversas faixas), recompra, produtos, volumes, taxas, prazos, checagem, confirmação, presença de canhoto, risco, concentrações, sacados, entre outros
- **Status atual:** poucos indicadores já calculados no sistema; maioria precisa ser construída do zero dentro do datalake, caso a caso conforme a modelagem avança
- **Destino:** Postgres (schema do datalake), com indicadores materializados via dbt

### 4.3 Dados auto-declarados
- **Origem:** banco `UNLTD_A7CREDIT` (SQL Server)
- **Escopo:** faturamento, endividamento e outros informes recorrentes da cedente
- **Destino:** Postgres (schema do datalake), com histórico versionado por data de declaração

### 4.4 Enriquecimento externo (APIs)
- **Status atual:** APIs já são consumidas pelo sistema
- **Fontes mapeadas:**
  - Serasa (raw JSON armazenado em tabela no `UNLTD_A7CREDIT`; API mapeada para consultas pontuais ou recorrência paralela)
  - Processos judiciais
  - Protestos
  - Sócios
  - SCR Bacen
  - Contrato social da Junta Comercial (retorna PDF)
  - Outras
- **Trabalho novo:** apenas a eventual orquestração de disparos — a ideia é que o sistema de gestão de risco conduza essa orquestração
- **Destino raw:** S3 (JSONs e PDFs originais)
- **Destino estruturado:** Postgres (schema do datalake), com campos normalizados por tipo de consulta

### 4.5 Conformidade documental
- **Origem:** banco `UNLTD_A7CREDIT` (SQL Server)
- **Escopo:** declaração de faturamento, declaração de endividamento, outros informes recorrentes obrigatórios
- **Destino:** Postgres (schema do datalake), com rastreabilidade de datas de entrega e status

---

## 5. Desafios específicos por fonte

### 5.1 XMLs operacionais
- Entender a estrutura completa dos XMLs (são densos e variados)
- Definir quais campos extrair e como modelar as tabelas destino no Postgres
- Garantir cruzamento confiável entre o nome do arquivo na pasta Windows e o registro em `UNLTD_A7CREDIT`
- Estabelecer rotina de cópia diária dos XMLs para S3 sem perda

### 5.2 Indicadores comportamentais
- Maioria precisa ser construída do zero — análise caso a caso
- Definir o grão correto de cada indicador (por operação, por cedente, por sacado, por safra, por período)
- Decidir quais são materializados via dbt e quais são calculados sob demanda
- Garantir consistência com eventuais cálculos pré-existentes no sistema

### 5.3 APIs externas
- Normalização dos retornos heterogêneos (JSON do Serasa, PDF da Junta Comercial, estruturas diferentes por fornecedor)
- Orquestração de disparos (novo) integrada ao sistema de gestão de risco
- Política de cache e revalidação por tipo de consulta
- Extração estruturada de PDFs (Junta Comercial) usando pipeline de LLM + Pydantic quando aplicável

### 5.4 Conformidade documental
- Modelar entidades de "obrigação recorrente" com cadência, prazo, status e histórico
- Conectar com alertas e KPIs do sistema

---

## 6. Modelo de dados — princípios

- **Grão primário analítico:** uma observação por CNPJ por data, com todos os campos conhecidos naquele momento
- **Tabelas de fato separadas por domínio:** operações, indicadores comportamentais, consultas externas, auto-declarados, conformidade
- **Dimensão central:** entidade CNPJ com histórico de vínculos (cedente atual, cedente passado, sacado, sócio, etc.)
- **Snapshots periódicos em Parquet:** cadência a definir (candidato inicial: diário para operacional, mensal para enriquecimento externo)

---

## 7. Próximos passos concretos

1. **Mapear estrutura dos XMLs** — inventariar campos disponíveis, frequências, variações; priorizar por ser o ponto mais denso e menos conhecido
2. **Inventariar tabelas relevantes do `UNLTD_A7CREDIT`** — identificar quais alimentam comportamentais, auto-declarados, conformidade, e raw Serasa
3. **Modelar schema do datalake no Postgres** — tabelas dimensionais (CNPJ, cedente, sacado, tempo) e de fato por domínio
4. **Construir pipeline de um cedente piloto end-to-end** — do raw à feature materializada, validando cada camada antes de escalar
5. **Definir rotina de snapshots em Parquet** — cadência, particionamento, nomenclatura
6. **Integrar orquestração de APIs externas ao sistema de gestão de risco** — disparos, cache, escrita no datalake

---

## 8. Decisões registradas

| Decisão | Justificativa |
|---|---|
| Datalake em schema separado do mesmo Postgres | Simplicidade de infraestrutura, separação lógica suficiente |
| Raw sempre em S3, nunca sobrescrito | Reprocessamento garantido, audit trail, compliance |
| DuckDB como motor embutido | Elimina camada Dremio; consulta unificada Postgres + Parquet |
| dbt-duckdb para transformações | Versionamento, testes, documentação automática |
| SQL Server (`UNLTD_A7CREDIT`) permanece operacional intocado | Fonte de verdade transacional; datalake apenas consome |
| Indicadores comportamentais construídos caso a caso | Maioria não existe calculada hoje; análise incremental |
| Orquestração de APIs delegada ao sistema de gestão de risco | APIs já consumidas; novo trabalho é só orquestração |

---

## 9. Fora de escopo deste documento

- Cronograma e marcos semanais (documento separado)
- Especificação dos modelos preditivos que consumirão as features
- Detalhamento do frontend e dashboards
- Estratégia de deployment híbrido on-premises (preservada na arquitetura, mas não executada nesta fase)
