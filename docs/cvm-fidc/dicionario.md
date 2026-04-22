# Dicionario CVM FIDC -- Informes Mensais

> Catalogo editorial das tabelas do Informe Mensal FIDC da CVM, organizado em
> formato Q&A ("onde esta X?") para consulta rapida por humanos e pelo Claude
> via Grep. Complementa o YAML estruturado em [`dicionario.yaml`](./dicionario.yaml)
> -- aquele arquivo vem dos metadados oficiais da CVM e e regenerado via script;
> **este** e mantido a mao e captura **conhecimento implicito** que so aparece
> quando voce cruza o schema com dados reais.
>
> **Fonte:** https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/META/
> **Ingestao:** ETL externo `etl-cvm` (repo `A7-Development/etl-cvm`, VM 26)
> popula a DB `cvm_benchmark`; backend GR le via postgres_fdw sob o schema
> `cvm_remote.*` (ver [`integracao-cvm-fidc.md`](../integracao-cvm-fidc.md)).
>
> **Regenerar o YAML:**
> ```
> python scripts/parse_cvm_metadata.py --versao v5
> ```
> Para atualizar: baixe o zip novo da CVM, extraia em
> `docs/cvm-fidc/raw/v<N>/`, rode o script e commit.

## Onde esta X? (Q&A)

### PL total do fundo/classe
`cvm_remote.tab_iv.tab_iv_a_vl_pl` (numeric, R$). Media trimestral em
`tab_iv_b_vl_pl_medio`. **E o unico valor de PL agregado** -- nao existe quebra
por subclasse em nenhuma outra tabela.

### PL por subclasse/serie
**Nao ha campo direto.** A unica derivacao oficial e
`tab_x_2.tab_x_qt_cota * tab_x_2.tab_x_vl_cota`. Porem `tab_x_qt_cota` e
opcional no preenchimento e vem NULL para muitos fundos (ver
[Omissoes conhecidas](#omissoes-conhecidas-e-como-lidar)).

### Quantidade de cotistas
- Por **classe/serie**: `cvm_remote.tab_x_1.tab_x_nr_cotst`
  (chave `tab_x_classe_serie` + `id_subclasse`).
- Por **tipo de investidor** (banco, PF, PJ, EAPC, EFPC, RPPS, InvNR, FII,
  clube, seguradora, corretora, capitalizacao, cota_fidc, outro_fi, outros):
  `cvm_remote.tab_x_1_1.tab_x_nr_cotst_{senior|subord}_<tipo>` -- quebra e
  apenas Senior vs Subordinada, **nao por serie**.

### Rentabilidade mensal por serie
`cvm_remote.tab_x_3.tab_x_vl_rentab_mes` (numeric percentual, ex.: `1.25` = 1,25%).
Chave: `tab_x_classe_serie`.

### Desempenho esperado vs real
`cvm_remote.tab_x_6.tab_x_pr_desemp_esperado` e `tab_x_pr_desemp_real`
(percentuais, por `tab_x_classe_serie`). E a unica fonte CVM de **meta**.

### Composicao da carteira em R$ (cabecalho Austin pag.2)
`cvm_remote.tab_i` -- mapeamento pratico:
- DC a vencer: `tab_i2a_vl_dircred_risco` (soma) + decomposicao em `tab_v.tab_v_a_vl_dircred_prazo`
- DC inadimplente: `tab_v.tab_v_b_vl_dircred_inad`
- DC antecipado: `tab_v.tab_v_c_vl_dircred_antecipado`
- Titulos Publicos Federais: `tab_i2d_vl_titpub_fed`
- CDBs: `tab_i2e_vl_cdb`
- Outros Renda Fixa: `tab_i2g_vl_outro_rf`
- Cotas FIF: `tab_i2c5_vl_cota_fif`
- Cotas de outros FIDCs: `tab_i2h_vl_cota_fidc`
- Disponibilidades (tesouraria): `tab_i1_vl_disp`
- PDD (aproximacao): `tab_i2a11_vl_reducao_recup`

### Inadimplencia em buckets de atraso
`cvm_remote.tab_v.tab_v_b1..b10_vl_inad_*`. **10 buckets**: 30/60/90/120/150/180/360/720/1080/>1080d.
**Atencao:** CVM NAO tem bucket "ate 15 dias" (usado por Austin). Apresentar
os 10 buckets nativos com nota inline na UI.

### Prazo medio da carteira
**Nao ha campo direto.** Derivar como media ponderada dos pontos medios
dos buckets de `tab_v_a*` (`tab_v_a1..a10_vl_prazo_venc_*`):
- 15, 45, 75, 105, 135, 165, 270, 540, 900, 1260 dias.

### Concentracao de cedentes
`cvm_remote.tab_i.tab_i2a12_pr_cedente_1..9` (percentuais, top-9).
**CVM so coleta top-9.** Top-10/20 da Austin usa fonte do administrador.
**NAO ha** campo para concentracao de SACADOS.

### Composicao setorial dos DC
`cvm_remote.tab_ii.*` -- 11 categorias top-level com ~3-4 subcategorias cada.
Labels humanos ja estao mapeados em `backend/app/modules/bi/services/benchmark.py::_SETOR_LABELS`.
Substitui parcialmente a "natureza DC" (duplicata/cheque/CCB/NP) da Austin, que **nao existe** no CVM.

### Liquidez escalonada
`cvm_remote.tab_x_5.tab_x_vl_liquidez_{0,30,60,90,180,360,maior_360}` (R$, 7 faixas).
Ativos que podem ser liquidados em ate N dias.

### Movimentacao de cotas (captacao / resgate / amortizacao)
`cvm_remote.tab_x_4`, chave `tab_x_tp_oper` x `tab_x_classe_serie`.
Tipos observados: `Captacoes no Mes`, `Resgates no Mes`, `Resgates Solicitados`,
`Amortizacoes`. Campos: `tab_x_vl_total` (R$, sempre populado) e
`tab_x_qt_cota` (frequentemente NULL).

### SCR por rating (AA..H)
`cvm_remote.tab_x.tab_x_scr_risco_{devedor|oper}_{aa,a,b,c,d,e,f,g,h}`
-- **colunas text** com valores numericos, precisa parse no servico.
Sao **dois eixos**: risco do devedor (cedente/sacado PF/PJ) e risco da operacao.

### Garantias
`cvm_remote.tab_x_7.tab_x_vl_garantia_dircred` (R$) e `tab_x_pr_garantia_dircred` (% do DC).

### Mercado secundario (precos de negociacao)
`cvm_remote.tab_ix` -- precos min/medio/max de compra e venda segmentados por
6 faixas de rentabilidade (a, b, c, d, e, f) e 2 tipos (1, 2). 40 colunas.
Usado raramente -- so para FIDCs com cotas negociadas.

## Resumo por tabela

| Tabela | Granularidade | Serve para... |
|---|---|---|
| `tab_i` | fundo/classe x mes | Cabecalho + posicao carteira R$ (~109 campos) |
| `tab_ii` | fundo/classe x mes | Composicao setorial DC |
| `tab_iii` | fundo/classe x mes | DC adquiridos no mes (volume + prazo + taxa) |
| `tab_iv` | fundo/classe x mes | PL total + PL medio trimestral |
| `tab_v` | fundo/classe x mes | DC a vencer / inadimplente / antecipado por bucket de prazo |
| `tab_vi` | fundo/classe x mes | Passivo por prazo (mesmo esquema de buckets) |
| `tab_vii` | fundo/classe x mes | Complementos (despesas, provisoes) |
| `tab_ix` | fundo/classe x mes | Mercado secundario |
| `tab_x` | fundo/classe x mes | SCR ratings AA..H |
| `tab_x_1` | fundo x mes x **serie** | Nr de cotistas por serie |
| `tab_x_1_1` | fundo x mes | Nr de cotistas por **tipo de investidor** (Senior/Subord) |
| `tab_x_2` | fundo x mes x **serie** | Qt + vl de cota |
| `tab_x_3` | fundo x mes x **serie** | Rentabilidade mensal % |
| `tab_x_4` | fundo x mes x **serie** x tp_oper | Captacao / resgate / amortizacao |
| `tab_x_5` | fundo/classe x mes | Liquidez escalonada 7 faixas |
| `tab_x_6` | fundo x mes x **serie** | Desempenho esperado vs real % |
| `tab_x_7` | fundo/classe x mes | Garantias (R$ + %) |

Granularidade "x serie" = 1 linha por subclasse por mes. Observar que `tab_i`,
`tab_iv`, `tab_ii`, `tab_v`, `tab_ix`, `tab_x`, `tab_x_5`, `tab_x_7` sao
**por fundo inteiro** (nao separam por subclasse).

## Omissoes conhecidas e como lidar

Campos opcionais que frequentemente vem em branco OU limitacoes estruturais do
esquema CVM. **Esta e a secao mais importante para o Claude** -- sempre que
der "dado nao vem", consultar aqui antes de supor bug.

### tab_x_2.tab_x_qt_cota (NULL sistematico)
**Sintoma:** PL por subclasse nao calcula.
**Causa:** campo opcional no preenchimento; administrador nao envia.
**Casos conhecidos:**
- `13.805.152/0001-03` (Puma FIDC NP Multissetorial / admin QI Corretora) -- NULL em toda a serie 2025-02..2026-03.
**Mitigacao:** na UI, mostrar `vl_cota` + `nr_cotst`; deixar PL/%PL em branco
com nota "nao reportado pelo administrador a CVM". NAO fazer rateio por
`nr_cotst` (subordinada costuma ter 1-2 cotistas concentrando grande %PL).

### tab_x_4.tab_x_qt_cota (NULL sistematico quando tab_x_2 tambem e NULL)
**Sintoma:** nao da pra derivar estoque de cotas via fluxo acumulado.
**Casos conhecidos:** mesmos fundos que omitem `tab_x_2.tab_x_qt_cota`.
**Mitigacao:** derivar fluxo em R$ via `tab_x_vl_total` (sempre populado).

### tab_i.tab_i2a12_pr_cedente_{1..9} -- so top-9
**Sintoma:** relatorios de agencias citam top-10 e top-20.
**Causa:** CVM decidiu que 9 e o limite.
**Mitigacao:** exibir top-9 com nota. Top-10/20 e sacados **irreproduziveis**
por dado publico.

### tab_v.tab_v_b* -- nao ha bucket "ate 15 dias"
**Sintoma:** lamina Austin traz coluna "ate 15d" / "16-30d".
**Causa:** CVM comeca em 0-30 (b1).
**Mitigacao:** apresentar os 10 buckets nativos (30/60/.../>1080) com nota.

### Natureza dos DC (duplicata / cheque / CCB / NP) -- inexistente
**Sintoma:** Austin detalha tipo de titulo.
**Causa:** CVM tipifica DC por **setor economico** (`tab_ii`), nao por tipo
de titulo. Informacao so existe no administrador.
**Mitigacao:** mostrar composicao setorial como substituto diferente, nao replica.

### Rating de agencia, recompras/WOP, desempenho historico versus mercado
**Sintoma:** Austin inclui.
**Causa:** dado proprietario (agencia) ou operacional (admin).
**Mitigacao:** declarar na lista de limitacoes da Ficha.

## Consultando via MCP (postgres-gr)

Quando o Claude precisa inspecionar dados reais via MCP, usar o schema `cvm_remote`:

```sql
-- Listar campos de uma tabela
SELECT column_name, data_type FROM information_schema.columns
WHERE table_schema = 'cvm_remote' AND table_name = 'tab_x_2'
ORDER BY ordinal_position;

-- Snapshot de um fundo (chave: cnpj_fundo_classe -- formato "XX.XXX.XXX/XXXX-XX")
SELECT competencia, tab_x_classe_serie, tab_x_qt_cota, tab_x_vl_cota
FROM cvm_remote.tab_x_2
WHERE cnpj_fundo_classe = '13.805.152/0001-03'
ORDER BY competencia DESC LIMIT 12;

-- Verificar ocupacao de um campo opcional (quantos NULL vs preenchido)
SELECT
  COUNT(*) FILTER (WHERE tab_x_qt_cota IS NULL)     AS nulls,
  COUNT(*) FILTER (WHERE tab_x_qt_cota IS NOT NULL) AS preenchidos
FROM cvm_remote.tab_x_2;
```

Nao ha `tenant_id` -- dado publico. Proveniencia nas respostas do BI:
`source_type='public:cvm_fidc'`, `trust_level='high'`.

## Quando atualizar este dicionario

- **Nova versao do zip CVM** (muda sufixo `(N)` no filename):
  baixar, extrair em `docs/cvm-fidc/raw/v<N>/`, rodar o script, revisar diff.
- **Descobriu nova omissao em producao:** acrescentar entrada em `KNOWN_OMISSIONS`
  no script **e** nesta pagina (secao [Omissoes conhecidas](#omissoes-conhecidas-e-como-lidar)).
- **Novo uso cruzado (campo cita outro campo):** adicionar Q&A no topo.
- **Mudanca estrutural do CVM** (ex.: nova tabela -- Res.175 ja adicionou
  `tab_x_1_1` e renomeou varios `cnpj_fundo` -> `cnpj_fundo_classe`):
  atualizar `TABLE_DESCRIPTIONS` no script + texto desta pagina.
