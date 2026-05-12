# Atribuição da Cota Subordinada via balancete patrimonial diário COSIF

> Documento de design da Fase 0 do PR3 da página `/controladoria/cota-sub`.
> Plano completo em `C:\Users\RicardoPimenta\.claude\plans\analise-esse-documento-que-elegant-moth.md`.
> Validado numericamente em 2026-05-11 via `scripts/spike_cota_sub_cosif.py` contra REALINVEST 07→08/05/2026.

## Equação fundamental

Para um FIDC administrado pela QiTech (e idealmente qualquer admin com plano COSIF II), o **PL da Cota Subordinada** num dia D é a soma do silver bruto menos as cotas Sr e Mezanino emitidas pelo fundo:

```
PL Cota Sub (D) = Σ_silver_TOTAL(D) − |Σ cotas_Sr_emitidas(D)| − |Σ cotas_Mez_emitidas(D)|

Δ PL Cota Sub (D-1 → D0) = ΔΣ_silver − Δ|Σ Sr emitidas| − Δ|Σ Mez emitidas|
```

Onde:

- `Σ_silver_TOTAL(D)` é a soma simples (sem classificação) de **todos** os valores nos silvers de posição/saldo do dia: `wh_saldo_conta_corrente`, `wh_saldo_tesouraria`, `wh_posicao_compromissada`, `wh_posicao_renda_fixa` (positivas + negativas — pares de compensação se anulam), `wh_posicao_cota_fundo`, `wh_posicao_outros_ativos`, `wh_cpr_movimento`.
- `|Σ cotas_Sr_emitidas(D)|` é `Σ |wh_posicao_renda_fixa.valor_bruto|` onde `nome_do_papel` casa regra de Senior **e** `quantidade < 0` (cotas emitidas pelo fundo, escrituradas como passivo na visão do cotista sub).
- Idem `|Σ cotas_Mez_emitidas(D)|` para Mezanino.

**Validação numérica REALINVEST 08/05/2026**:

| Métrica | Spike | PDF QiTech "Carteira Diária" |
|---|---|---|
| Σ silver D0 | 26.269.414,01 | — |
| \|Cotas Sr emitidas\| | 11.952.591,97 | 11.952.591,97 |
| \|Cotas Mez emitidas\| | 2.539.596,09 | 2.539.596,09 |
| PL Cota Sub D0 | **11.777.225,95** | **11.777.225,95** ✓ |
| Δ PL Cota Sub (vs D-1) | +36.942,77 | — |
| Variação % | **0,314667%** | **0,31466680%** ✓ |
| Resíduo da equação | **0,00** | — |

## Por que a equação funciona — dupla escrituração

Inspecionando `wh_posicao_renda_fixa` no dia, MEZAN e SRP aparecem em **pares** (qtde positiva + qtde negativa simétricas — mesmo PU, mesma data). Isso é a dupla escrituração do plano COSIF:

- **Conta de compensação 3** (lado positivo) → registro de emissão / circulação como ativo controlado
- **Conta de compensação 9** (lado negativo) → contrapartida

Quando somamos tudo no silver, esses pares se anulam — sobram apenas:
- Ativos reais do fundo (caixa, RF positivos sem par, cotas de fundo, op. crédito, PDD, liquidações)
- Passivo contábil (CPR — IOF, provisões pgto, taxa adm a pagar)
- **As cotas emitidas pelo fundo** (qtde<0 sem contrapartida no silver — porque a contrapartida é a saída de caixa do cotista no momento da subscrição, fora do balancete diário)

O **PL Total** que sobra é o patrimônio acumulado pelo fundo. Subtraindo as cotas Sr e Mez que têm prioridade sobre a Sub, sobra o PL da Cota Subordinada.

## Arquitetura de classificação COSIF

### Camada 1 — Catálogo

Tabela `cosif_catalog` com a árvore oficial do PLANO COSIF II:

```sql
cosif_catalog (
  codigo            varchar(20) PK,
  nome              varchar(200) NOT NULL,
  natureza          char(1)      CHECK (natureza IN ('D','C')),  -- Devedora/Credora
  parent_codigo     varchar(20)  REFERENCES cosif_catalog(codigo) NULL,
  nivel             smallint     NOT NULL,
  grupo             smallint     NOT NULL,  -- 1,3,4,6,7,8,9
  plano_id          smallint     DEFAULT 5,  -- 5 = PLANO COSIF II
)
```

Seed inicial a partir do balancete oficial REALINVEST mar/2026 (222 contas extraídas) + lista BACEN PLANO COSIF II completa quando disponibilizada. Migration de Fase 1 carrega o seed.

### Camada 2 — Regras estruturais

Tabela `cosif_rule` com predicados serializáveis:

```sql
cosif_rule (
  id               uuid PK,
  silver_origin    varchar(50)  NOT NULL,  -- nome da tabela silver
  predicate_jsonb  jsonb        NOT NULL,
  cosif_codigo     varchar(20)  NOT NULL REFERENCES cosif_catalog,
  classe_sr_mez_sub varchar(20) NULL,  -- senior | mezanino | subordinado | compensacao
  priority         smallint     NOT NULL,  -- maior = mais específica
  confidence       varchar(10)  DEFAULT 'alta' CHECK IN ('alta','media','baixa'),
  rule_id_humano   varchar(80),  -- ex.: 'rf.cota_sr_emitida'
  valid_from       date         DEFAULT CURRENT_DATE,
  valid_to         date         NULL,
  classifier_version varchar(20) DEFAULT '1.0.0',
)
```

Predicados serializados em JSON, exemplos validados no spike:

```json
{"silver":"wh_posicao_renda_fixa","qtde_signal":"negative","papel_starts_with":"SR"}
  -> cosif "6.1.1.70.30.001" classe "senior"

{"silver":"wh_posicao_renda_fixa","qtde_signal":"negative","papel_starts_with":"MEZ"}
  -> cosif "6.1.1.70.30.001" classe "mezanino"

{"silver":"wh_posicao_renda_fixa","papel_contains":"NTN"}
  -> cosif "1.3.1.10.07.001"

{"silver":"wh_cpr_movimento","historico_contains":"IOF"}
  -> cosif "4.9.1.10.00.001"
```

Lista completa das ~30 regras MVP validadas em `backend/scripts/spike_cota_sub_cosif.py::classify`. Migration de Fase 1 popula `cosif_rule` com essas entradas.

### Camada 3 — Override por tenant

Tabela `tenant_papel_classificacao`, editável livremente pelo admin do tenant via `/admin/controladoria/cosif`:

```sql
tenant_papel_classificacao (
  id                uuid PK,
  tenant_id         uuid NOT NULL,
  fundo_id          uuid NOT NULL,  -- FK unidade_administrativa
  silver_origin     varchar(50) NOT NULL,
  identificador     varchar(80) NOT NULL,  -- valor do campo `codigo` no payload
  cosif_override    varchar(20) NOT NULL REFERENCES cosif_catalog,
  classe_sr_mez_sub varchar(20) NULL,
  motivo            text NULL,
  created_by        uuid REFERENCES users,
  created_at        timestamptz DEFAULT now(),
  UNIQUE (tenant_id, fundo_id, silver_origin, identificador)
)
```

Identificador usado no MVP REALINVEST (validados no spike):

| silver_origin | identificador | cosif |
|---|---|---|
| `wh_saldo_conta_corrente` | `BRADESCO` | `1.1.2.80.00.002` |
| `wh_saldo_conta_corrente` | `SOCOPA` | `1.1.2.80.00.007` |
| `wh_saldo_conta_corrente` | `CONCILIA` | `4.9.9.30.90.005` |
| `wh_posicao_cota_fundo` | `REALIAVE` | `1.6.1.30.00.001` |
| `wh_posicao_cota_fundo` | `REALIVEN` | `1.6.1.30.00.002` |
| `wh_posicao_outros_ativos` | `PDD` | `1.6.9.97.00.001` |

Seed inicial **opcional** — o admin pode preencher via UI. Cobertura sem essas linhas: rules ainda classificam corretamente os 4 primeiros, mas com confidence média (depende de inferir "BRADESCO" → "1.1.2.80.00.002" pelo nome). Override transforma média em alta.

### Classifier — cascata

Função `classify(row, tenant_id, fundo_id) → CosifResolution`:

```python
@dataclass
class CosifResolution:
    cosif: str               # codigo do catalogo OU "PENDENTE"
    source: Literal["override", "rule", "pendente"]
    rule_id: str | None      # rule_id_humano se source=rule
    override_id: UUID | None # id da linha tenant_papel_classificacao se source=override
    confidence: Literal["alta", "media", "baixa"]
    classe_sr_mez_sub: str | None  # senior|mezanino|subordinado|compensacao

def classify(row, tenant_id, fundo_id):
    # 1. Override
    ovr = SELECT * FROM tenant_papel_classificacao 
          WHERE tenant_id=? AND fundo_id=? AND silver_origin=? AND identificador=?
    if ovr:
        return CosifResolution(ovr.cosif_override, "override", ...)
    
    # 2. Regras estruturais
    for rule in active_rules_for(row.silver_origin) order by priority desc:
        if rule.predicate matches row:
            return CosifResolution(rule.cosif_codigo, "rule", rule.rule_id_humano, ...)
    
    # 3. Pendente
    return CosifResolution("PENDENTE", "pendente", ...)
```

Performance: ~200 rows/dia para REALINVEST. Sem cache no MVP. Se virar gargalo, adicionar LRU cache de:
- regras ativas por `silver_origin` (carregadas 1× por request)
- overrides por `(tenant_id, fundo_id, silver_origin, identificador)`

### Cobertura

Endpoint `GET /api/v1/admin/cosif/cobertura?tenant_id=X&fundo_id=Y&data=Z` retorna:

```json
{
  "totais": {"override": 6, "rule": 63, "pendente": 0},
  "valor_total_por_source": {"override": 515685.00, "rule": 25753729.01, "pendente": 14492188.06},
  "top_pendentes": [
    {"silver_origin": "wh_posicao_renda_fixa", "identificador": "...", "valor": 814737.49}
  ]
}
```

Página `/admin/controladoria/cosif-coverage` lista pendentes em ordem decrescente de |valor| — admin clica e cria override via formulário. KPI semáforo (verde/amber/red) com base em `% saldo_pendente / saldo_total`.

## Sr/Mez/Sub: regra de identificação

A classe não vem dos endpoints QiTech. Hoje (REALINVEST), inferimos via:

1. **Override do tenant** (mais alta confiança): admin classifica explicitamente o papel em `tenant_papel_classificacao.classe_sr_mez_sub`.
2. **Regra estrutural por prefixo do nome do papel**:
   - `nome_do_papel LIKE 'SR%'` → senior
   - `nome_do_papel LIKE 'MEZ%'` → mezanino
   - `nome_do_papel LIKE 'SUB%'` → subordinado
3. **Fallback**: papel sem prefixo conhecido + qtde<0 = pendente, alerta no admin.

Subordinado **não** aparece em RF (qtde<0) no REALINVEST porque o cotista sub é o "residual" — não há papel emitido para a Sub. A Cota Sub é calculada **por subtração** (PL Total − Sr − Mez), não somando o papel SUB.

Outros tenants podem ter cotas SUB emitidas explicitamente (multi-classe). Nesse caso, mesma regra (`SUB%` prefix) + subtração final.

## Classe (Sr/Mez/Sub) como dimensão paralela ao COSIF

Decisão de design 2026-05-11: o balancete oficial COSIF II **não** tem conta separada por classe — agrupa apenas por PF/PJ e emissão/resgate (`6.1.1.70.20.x` PF, `6.1.1.70.30.x` PJ). A classe é uma **dimensão paralela** que precisamos manter sem quebrar a fidelidade com o plano oficial.

Solução: o classifier sempre preenche `classe_sr_mez_sub` em `CosifResolution` (já implementado no spike). A API de balancete inclui agregação adicional por classe:

```json
{
  "conta": "6.1.1.70.30.001",
  "nome": "PESSOAS JURIDICAS - EMISSAO",
  "d_minus_1": -14606280.11,
  "d_zero":    -14616688.06,
  "delta":        -10407.95,
  "drill_classe": [
    {"classe": "senior",      "d_minus_1": -11944126.27, "d_zero": -11952591.97, "delta": -8465.70},
    {"classe": "mezanino",    "d_minus_1":  -2537653.84, "d_zero":  -2539596.09, "delta": -1942.25},
    {"classe": "aporte",      "d_minus_1":   -124500.00, "d_zero":   -124500.00, "delta":      0.00}
  ]
}
```

Custo de funding do dia = soma dos Δ de classe `senior` + `mezanino` (no exemplo: −R$ 10.407,95 em 08/05/2026).

**Apresentação na UI (decisão 2026-05-11 — "Ambos")**:

1. **Z2 Waterfall hero** ganha barras explícitas para custo de funding:
   ```
   ΔAtivo (+) | ΔPassivo CPR (-) | ΔCusto Sr (-) | ΔCusto Mez (-) | ΔPL Sub esperado | ΔPL Sub real | Resíduo
   ```
   Mostra ao cotista subordinado o impacto direto do funding na sua fatia, sem precisar drill.

2. **Z3 Balancete hierárquico** mantém estrutura COSIF oficial. Clica em `6.1.1.70.30.001 PJ EMISSAO` → expande sub-rows por classe (Senior, Mezanino, Aporte) com Δ individual. Auditoria preservada.

Para isso a tabela `wh_posicao_renda_fixa` precisa do `classifier` na hora de agregar — não exige nada novo no silver.

## Compensação (grupos 3 e 9 do COSIF)

A contrapartida positiva das cotas Sr/Mez emitidas (papéis com qtde>0 que casam prefixo Sr/Mez/Sub) vai para conta de compensação. **No MVP** ficam marcadas como `PENDENTE` com `rule_id="rf.contrapartida_compensacao"` e ocultas da árvore principal. **Comportamento esperado** — controller não enxerga grupos 3/9 no balancete oficial (ocultos por padrão).

Modo "auditoria avançada" da UI liga a exibição.

Para mapear corretamente em Fase 1: criar contas no `cosif_catalog`:
```
3.0.9.15.05.001 EMISSÕES                (grupo 3)
3.0.9.15.15.001 COTAS EM CIRCULAÇÃO     (grupo 3)
9.0.9.17.05.001 EMISSÕES                (grupo 9)
9.0.9.17.15.001 CIRCULAÇÃO              (grupo 9)
```

E regra estrutural: `wh_posicao_renda_fixa qtde>0 papel_starts_with('SR','MEZ','SUB')` → `3.0.9.15.15.001`.

## Mapeamento silver → COSIF (semáforo de cobertura)

Validado no spike contra REALINVEST 08/05/2026. **100% dos saldos classificados** (0 pendentes salvo a compensação esperada):

| Silver | Cobertura | Notas |
|---|---|---|
| `wh_saldo_conta_corrente` | 🟢 100% (3/3) | 100% via override (BRADESCO, SOCOPA, CONCILIA) |
| `wh_saldo_tesouraria` | 🟢 100% | Regra estrutural única (1.1.2.80.00.001) |
| `wh_posicao_compromissada` | 🟢 — | Nenhuma linha em 08/05 (válido) |
| `wh_posicao_renda_fixa` | 🟢 100% | Regras agnósticas por sinal qtde + prefixo papel |
| `wh_posicao_cota_fundo` | 🟢 100% (3/3) | 2 overrides (REALIAVE/REALIVEN) + 1 regra (ITAU SOBERANO) |
| `wh_posicao_outros_ativos` | 🟢 100% (1/1) | Override (PDD) |
| `wh_cpr_movimento` | 🟢 100% (15/15) | Regras por `historico_traduzido` em **2 dimensões**: (1) cosif por natureza econômica — `8.1.7.x` se contém "Apropriada" (DRE competência), `4.9.9.30.x` se "com pagamento DD/MM" (passivo a pagar), `1.9.9.10.00` se "Diferimento", `1.8.4.30.00.005` se "Liquidados", `4.9.1.10.00.001` se "IOF", `6.1.1.70.x` se "Aporte"; (2) cosif por item específico — Auditoria/Custódia/Adm/Gestão/etc. **CPR no silver QiTech contém AMBAS contas COSIF** (DRE 8.x acumulado + Passivo 4.x a pagar) em linhas separadas — classifier separa pelo texto. Validado em REALINVEST 08/05/2026: Apropriações crescendo R$ 676,77/dia (Custódia), pagamentos zerando passivos 4.9.9.83. |

**Não usados (futuro)**:
- `wh_movimento_caixa` — útil para drill de extraordinários (aporte, recebimento, pagamento atípico). Mapear na Fase 1.
- `wh_mec_evolucao_cotas` — útil para extraordinários de subscrição/resgate de cotistas (Δqtde sobre cotas).
- `wh_estoque_recebivel` / `wh_titulo` — base para explainer de PDD (qual DC mudou aging) e drill de op. crédito. Mapear na Fase 1.

## Convenções

- **Sinal canônico**: contas Devedoras (Ativo) somam positivo; Credoras (Passivo, PL, Receitas) somam negativo. O silver QiTech já entrega com sinal correto em CPR (despesa apropriada = valor negativo). PDD em `outros_ativos` vem negativa (-315.579,22) — natureza C do cosif `1.6.9.97.00.001` confere.
- **CPR é SALDO a pagar, não apropriação do dia**: cada linha em `wh_cpr_movimento` representa o saldo acumulado de uma provisão (ex.: Taxa de Custódia a pagar -3.383,85 em 08/05). Δ entre D-1 e D0 = `apropriação_competência − pagamento_caixa`. Validado em REALINVEST 08/05/2026: Taxa Custódia caiu de -16.242 para -3.383 (Δ +12.858), reflexo de pagamento da provisão acumulada — não reversão de despesa. **Para isolar custo do dia**, precisaria cruzar com `wh_movimento_caixa` (saídas efetivas) ou reservar a interpretação para o explainer da conta de despesa correspondente.
- **Compensação 3/9**: oculta por default; ligada via modo "auditoria avançada".
- **Tolerância do resíduo**:
  - <0,1pp do |PL Sub D-1| — verde "balancete conciliado"
  - 0,1pp a 1pp — amber "investigar"
  - >1pp — red "erro grave"
  - No spike REALINVEST: **0,00pp** (modelo exato)
- **Convenção de DU**: irrelevante para o balancete patrimonial (não há cálculo de carry — saldos vêm prontos do silver com o dia de cada um).

## Inventário de explainers (Fase 1)

Quando |Δ| numa conta excede threshold (default 0,01pp do PL ou R$ 5k absoluto), o componente carrega um explainer com dados adicionais:

| Conta COSIF | Explainer | Fonte | Status |
|---|---|---|---|
| `1.6.9.97.00.001` PDD | Carteira que mudou aging | `wh_estoque_recebivel` ou `fidc-estoque` | 🟡 depende de assinatura do endpoint |
| `1.6.1.30.00.001/2` Receb. | Novas operações/liquidações | `wh_aquisicao_recebivel`, `wh_liquidacao_recebivel` | 🟢 silver existe |
| `1.3.1.10.16.001` NCPX | Nova nota comercial | `wh_posicao_renda_fixa` diff D-1 vs D0 (papel novo) | 🟢 silver existe |
| `6.1.1.70.30.001` (cotas Sr/Mez via classe) | Subscrição/resgate | `wh_mec_evolucao_cotas` ou Δqtde silver RF | 🟢 silver existe |
| `1.9.9.10.00` Diferimentos | Diferimento ativo + vencimento | `wh_cpr_movimento` filtrando "DIFERIMENTO" | 🟢 silver existe |
| `wh_movimento_caixa` | Aporte/retirada não-recorrente | `wh_movimento_caixa` lançamentos no dia | 🟢 silver existe |

Explainers são **opcionais**: se tenant não assina `fidc-estoque`, o explainer da PDD retorna `null` + nota "detalhamento requer assinatura do endpoint X".

## Plano de implementação (resumido)

Plano completo em `C:\Users\RicardoPimenta\.claude\plans\analise-esse-documento-que-elegant-moth.md`.

**Fase 0** (concluída em 2026-05-11):
- ✅ Spike Python validou modelo numericamente (resíduo 0,00 em REALINVEST 08/05/2026)
- ✅ Cobertura 100% no MVP (6 overrides + 24 regras estruturais)
- ✅ Documento de design (este arquivo)

**Fase 1** (próxima — backend + UI):
- Migration `cosif_catalog`, `cosif_rule`, `tenant_papel_classificacao` + seeds
- `services/cosif/classifier.py` + `services/cota_sub/balancete_diario.py`
- Endpoint `GET /api/v1/controladoria/cota-sub/balancete-diario`
- Endpoint admin CRUD em `tenant_papel_classificacao` + cobertura
- UI: `ReconciliacaoWaterfallCard` (Z2) + `BalanceteDiarioTable` (Z3) + `ResiduoAlertCard` (Z4) + `CosifDrillSheet` + `EventosDiaTab` recomposto

**Fase 2** — silver derivado `wh_balancete_diario_snapshot` + job mensal de conciliação com balancete oficial.

**Fase 3** — IA narrativa (`insight.cota_sub_balancete_diario@v1`).
