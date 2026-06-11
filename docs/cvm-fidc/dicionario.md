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

### Como o ATIVO fecha (aritmetica validada em 2026-04, 4.102 fundos)
`tab_i_vl_ativo = tab_i1_vl_disp + tab_i2_vl_carteira + tab_i3_vl_posicao_deriv
+ tab_i4_vl_outro_ativo` (fecha em 4.100/4.102). A carteira (I.2) = soma dos 11
itens 2a..2j + outro (4.073/4.102). `tab_i2i_vl_cota_fidc_np` esta **100% NULL**
(pos-RCVM 175 colapsou em `tab_i2h_vl_cota_fidc`).

### Provisao (PDD) — onde esta e como funciona (REGRA DURA p/ indicadores)
`tab_i2a11_vl_reducao_recup` / `tab_i2b11_vl_reducao_recup` — nome oficial
"Provisao para Reducao no Valor de Recuperacao (-)". Tres fatos validados:
1. **Armazenada POSITIVA** (0 valores negativos no universo) apesar do "(-)" —
   quem consome SUBTRAI.
2. **Os subtotais (2a, 2b, carteira, ativo) ja vem LIQUIDOS de provisao**
   (3.975/4.102 fundos: `2a = soma(a1..a10) - a11`). Bruto = liquido + provisao.
3. **`tab_ii` (setorial) e o DC BRUTO**: `tab_ii_vl_carteira = (2a+a11)+(2b+b11)`
   — validado ao centavo no REALINVEST. KPI sobre bruto usa tab_ii ou
   liquido+provisao; sobre liquido usa tab_i direto.

### tab_v = DC COM risco em buckets; tab_vi = DC SEM risco (espelhos)
Validado no universo 2026-04: `tab_v_a+b+c = 2a BRUTO` (898/1.034 fundos com
2b>0; ZERO casos = 2a+2b) e **`tab_vi_a+b+c = 2b BRUTO`** (839/1.034). Apesar
do nome das colunas sugerir o contrario, `tab_vi` NAO e "passivo por prazo" —
e o espelho da `tab_v` para o bloco SEM aquisicao substancial de riscos.
**Inadimplencia/prazo TOTAL da carteira = tab_v + tab_vi** (mesmos 10 buckets).
Indicador que use so a tab_v ignora R$ 242,8 bi (no REALINVEST, 89% da carteira).

### Passivo e PL — aritmetica validada (2026-04, 4.102 fundos)
- **`tab_iv_a_vl_pl = tab_i_vl_ativo - tab_iii_vl_passivo` em 4.102/4.102** (ao
  centavo). `tab_iv_b_vl_pl_medio` = media dos ultimos 3 meses.
- **`tab_iii_vl_passivo = a_vl_pagar (curto+longo) + b_vl_posicao_deriv`** em
  4.102/4.102. Derivativos vendidos: termo/opcoes lancadas/ajustes futuros/swap.
- Universo: passivo R$ 24,9 bi vs PL R$ 932,9 bi (FIDC quase nao tem passivo —
  "valores a pagar" = despesas/taxas/obrigacoes operacionais).
- **REALINVEST 2026-04 (validacao interna):** passivo CVM 52.069,44 =
  `wh_cpr_movimento` Σ valor<0 (CPR a pagar) 52.068,82 — diff R$ 0,62 (mesmo
  residuo do DC). PL CVM 25.870.794,03 = ativo - passivo exato.

### PL por classe / subordinacao (tab_x_2 E o MEC)
`tab_x_2.tab_x_qt_cota * tab_x_vl_cota` por `tab_x_classe_serie`. Validado
REALINVEST 2026-04: quantidade, valor da cota e patrimonio **identicos ate a
8a casa decimal** ao `wh_mec_evolucao_cotas` (30/04) — a administradora reporta
o MEC literal. Soma das classes = PL total exato (Senior 11.721.444,60 + Mez
2.529.899,70 + Sub 11.619.449,73). **Subordinacao** = Σ classes
`%subord%`/PL — calculavel em 3.205/4.102 fundos na ultima competencia (897
sao mono-classe sem serie subordinada); cobertura de qt/vl em 2026-04 e 100%,
mas competencias historicas tem o NULL sistematico (ver Omissoes).

### I.4 "Outros Ativos" — o que e na pratica
Schema so abre curto/longo prazo (`tab_i4a/tab_i4b`). Empiricamente (2026-04,
R$ 22,3 bi): **dois mundos** — (a) residual contabil em 2.748 fundos (mediana
0,03% do ativo); (b) posicao DOMINANTE (>=50% do ativo) em 60 fundos / R$ 9,1
bi, quase todos FIDC-NP de credito judicial/distressed (Latache Legal Claims
86%, AZO/CITY/LUSO/MN I = 100% do ativo) — esses fundos ficam INVISIVEIS nas
lentes de lastro (tab_ii/tab_v vazias). Caso BTG Consignados II (R$ 2,4 bi
curto prazo) = floating operacional. **No REALINVEST: I.4 = CPR Contas a
Receber (floating de liquidacao + diferidos) — bate ao centavo com a QiTech.**

### Mapeamento CVM <-> QiTech (validado REALINVEST, competencia 2026-04, ao centavo)
| CVM | QiTech (silver, posicao do ultimo dia util) |
|---|---|
| DC bruto (`tab_ii_vl_carteira`) | `wh_posicao_cota_fundo` "REALINVEST A VENCER"+"VENCIDOS" **+ `wh_posicao_renda_fixa` NCPX** (notas comerciais vao DENTRO do DC na CVM; campo I.2.c.3 "NP Comercial" fica 0) |
| Provisao (a11+b11) | `wh_posicao_outros_ativos` (que E a PDD com sinal negativo — por isso o balanco estrutural a exclui) |
| Cotas FIF (I.2.c.5) | `wh_posicao_cota_fundo` externos (ITAU SOBERANO REF SI) |
| Titulos Publicos (I.2.d) | `wh_posicao_renda_fixa` NTN-B |
| Outros Ativos (I.4 curto) | `wh_cpr_movimento` Σ valor>0 (CPR a receber) |
| Disponibilidades (I.1) | tesouraria+conta corrente (residuo R$ 349,74 nao mapeado, imaterial) |

Base de check mensal automatico CVM x posicao interna (candidato a Conferencia).

### Cotas e fluxo — semantica validada (2026-04 + REALINVEST x MEC)
- **`tab_x_4` (movimentacao)**: 4 `tab_x_tp_oper` — Captacoes no Mes /
  Resgates no Mes / Amortizacoes / Resgates Solicitados (fila, nao fluxo).
  Universo abril: 27,3 / 5,9 / 1,2 / 0,1 bi -> captacao liquida = capt - resg
  - amort = +20,2 bi. **Validado REALINVEST: CVM = MEC ao centavo**, com
  mapeamento `Captacoes = wh_mec_evolucao_cotas.entradas` e `Resgates =
  .saidas` (as colunas `aporte`/`retirada` do MEC ficam zeradas).
- **`tab_x_3` (rentabilidade) e AUTORITATIVA — Δcota NAO e proxy**: REALINVEST
  = MEC `variacao_mensal` arredondado a 2 casas (4,2743 -> 4,27). No universo,
  rentab so bate com `Δ tab_x_2.vl_cota` em 68% das series (5.489/8.044 a
  2bps); das 2.096 que divergem >50bps, 63% tem amortizacao/resgate no mes
  (cota cai sem ser rentabilidade negativa) e 782 divergem sem movimento
  (ruido de reporte). Indicador de rentabilidade usa tab_x_3, nunca Δcota.
- **`tab_x_6` (desempenho)**: `pr_desemp_esperado` = META da serie;
  serie com taxa-alvo atingida reporta esperado = real (REALINVEST Senior
  1,44/1,44, Mez 1,56/1,56); **Subordinada reporta esperado = 0** (recebe o
  residual — nao tem meta). Spread real-esperado so faz sentido p/ series
  com meta > 0.
- **`tab_x_1` / `tab_x_1_1` (cotistas)**: por serie (REALINVEST: 7 Senior /
  4 Mez / 6 Sub) e por tipo de investidor (15 tipos x Senior|Subord — sem
  abertura por serie).

### Giro e qualidade (tab_vii / tab_x SCR / tab_x_7) — semantica validada
- **`tab_vii` = negocios do MES**, 4 blocos: `a*` AQUISICOES por tipo (com/sem
  risco, a vencer ad/inad, **ja inadimplentes** — a5 identifica compra
  distressed: 147 fundos / R$ 640 mi em abril); `b*` ALIENACOES (vendas) por
  contraparte (cedente+relacionadas / prestadores / terceiros) com valor de
  venda E valor contabil (desagio da venda = vl - vl_contab); `c` substituicao;
  `d` RECOMPRA. Universo abril: aquisicoes R$ 150,4 bi (1.603 fundos),
  recompras R$ 1,97 bi (453 fundos — proxy de "WOP/recompra" do mercado).
- **`tab_vii_d` recompra = valor PAGO, validado AO CENTAVO no REALINVEST**:
  269.089,44 = `wh_liquidacao_recebivel` abril (BAIXA POR RECOMPRA 248.737,98
  + RECOMPRA PARCIAL SEM ADIANTAMENTO 20.351,46, Σ valor_pago).
- **Aquisicoes NAO conciliam direto com a QiTech**: CVM 20,33 mi vs
  `wh_aquisicao_recebivel` abril 16,15 mi (valor_compra) / 16,67 mi (face).
  O gap ≈ bloco "com risco" (2,74 mi — provavelmente notas comerciais NCPX,
  que nao passam pelo relatorio de aquisicao da QiTech) + residuo ~0,9 mi a
  investigar. Nao usar como check ao-centavo sem resolver a base.
- **`tab_x` SCR: 100% dos fundos reportam** (devedor E operacao, AA..H) —
  colunas TEXT com string numerica ("24941894.33"), parse direto. REALINVEST:
  AA 24,94 mi + H 243.050,36. Unica visao de rating da carteira por dado
  publico.
- **`tab_x_7` garantias: campo RARO** — 29/4.102 fundos (R$ 7,7 bi). Nao
  serve de indicador transversal; so flag pontual.

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

### XML protocolado (FNET IFP) = dataset, 100% (validado 2026-06-11)
Cruzamos o XML IFP v6.6 do REALINVEST (abril/26) campo a campo contra o
`cvm_remote`: **identico em tudo** — o dataset reproduz o protocolo sem perda.
XML e o formato preferido p/ conferencias pontuais (estruturado; PDF
desnecessario). Bonus do cruzamento:
- **A regua SCR fecha o DC bruto AO CENTAVO**: AA+C+G+H = tab_ii_vl_carteira
  (REALINVEST: 24.941.894,33 + 432.365,71 + 111.664,88 + 243.050,36 =
  25.728.975,28). O SCR carrega ARRASTO (a vencer de devedor em atraso entra
  no nivel do devedor) — por isso C+G+H (787k) > vencidos (480k). Consultar
  TODAS as letras, nao so AA/H.
- **Recompra tem 2 valores**: pago (`d_2`=269.089,44) vs contabil
  (`d_3`=269.567,11) — o delta (477,67) e a perda/desconto realizado na
  recompra. Indicador fino: desagio de recompra = d_3 - d_2.

### DC de cedentes com divida ativa da Uniao (tab_x_debito_tribut)
`(X.9.1) Valor total dos DC cedidos por cedentes que possuem debitos
tributarios inscritos em divida ativa da Uniao` (no XML: `REG_TRIB_CED`).
REALINVEST abr/26: **R$ 3.737.489,57 = 14,5% do DC bruto**. Indicador de
risco de FRAUDE/PENHORA de lastro (cedente devedor da Uniao -> risco de
constricao judicial dos recebiveis). Candidato a indicador da cesta —
ninguem do mercado publica isso agregado.

### Garantias
`cvm_remote.tab_x_7.tab_x_vl_garantia_dircred` (R$) e `tab_x_pr_garantia_dircred` (% do DC).

### Taxa de aquisicao dos DC (taxa de desconto / juros praticadas no mes)
`cvm_remote.tab_ix` — **NAO e "mercado secundario"** (4a descricao corrigida).
Sao as TAXAS praticadas nos negocios do fundo no mes, em **% ANUAL decimal**
(ex.: `80.77` = 80,77% a.a.), por classe de ativo:

- Blocos: `a`=DC com risco · `b`=DC sem risco · `c`=Valores Mobiliarios ·
  `d`=Titulos Publicos · `e`=CDB · `f`=Outras RF
- Sub-blocos: `1`=Taxa de DESCONTO (da aquisicao) · `2`=Taxa de JUROS (do DC)
- Dimensoes: Compra|Venda x Minima|**Media (PONDERADA)**|Maxima
- Ex.: `tab_ix_a1_1_2_compra_media` = taxa de desconto media ponderada de
  COMPRA dos DC com risco.

**Conversao p/ mes**: `taxa_am = (1 + taxa_aa/100)^(1/12) - 1`. REALINVEST
abr/26 (DC com risco, compra): min 53,79 / media 80,77 / max 130,94 % a.a.
(= 3,65% / 5,06% / 7,22% a.m.); sem risco media 93,89% a.a. O campo interno
`wh_liquidacao_recebivel.taxa_aquisicao` tambem e ANUAL (media simples abril
63,5 vs CVM ponderada 80,77 — mesma ordem; cuidado com outliers de prazo
curtissimo anualizado, max observado 201.943%). Taxa de juros (a2/b2) vem 0
no REALINVEST (FAT/desconto puro — juros so em credito com fluxo).

**Indicador candidato**: "taxa media de aquisicao" comparavel entre fundos do
mesmo setor (tab_ii) — o PRICING do mercado, unico lugar publico onde aparece.

**Ocupacao (2026-04, 4.102 fundos) + gotchas**: colunas sao TEXT (parse como o
SCR). Preenchem: a1 desconto-compra DC risco **1.074** fundos (mediana do
mercado **28,5% a.a.** ≈ 2,11% a.m.); a2 juros-compra **480** (credito com
fluxo — consignado/CCB reportam JUROS em vez de desconto: olhar a1 E a2);
b1 sem-risco 727; b2 243; vendas raras (38); TPF 307 / outras RF 146 / VM 37 /
**CDB 0**. GOTCHAS de qualidade: outliers de anualizacao de prazo curtissimo
(REALINVEST b1 max 7.008% a.a.) e valores residuais tipo 0,05/0,1 em TPF/venda
— winsorizar (ex.: cap p99 ou filtrar > ~500% a.a.) antes de agregar.

**LIMITACAO ESTRUTURAL (2026-06-11, validada pelo Ricardo com dado do fundo):
o NIVEL da taxa na tab_ix NAO e confiavel.** A taxa REAL do REALINVEST em
abril, calculada da carteira adquirida (2.608 recebiveis, desagio 3,23% /
prazo ponderado 28d), e **3,47% a.m. = 51,46% a.a.** — a CVM publica 80,77.
Causa: as administradoras anualizam POR TITULO e tiram media — anualizar
duplicata de dias e matematicamente invalido (a media ponderada por titulo da
mesma carteira da 343.092% a.a.; o proprio max publicado de 7.008% prova o
metodo). Alem disso os blocos a/b cobrem subconjuntos (com/sem risco), nao a
carteira inteira. Tentativas de reproduzir o numero da Singulare (agregacao
por dia: 53,31; por dia x cedente: 85,80) chegam perto mas nao fecham — cada
admin tem corte proprio. **Uso aceitavel: ordinal/comparativo entre fundos de
perfil de prazo parecido, com winsorizacao e ressalva; nivel absoluto NAO.**
A formula defensavel (carteira agregada): `taxa_am = (Σface/Σcompra)^(30/
prazo_pond) - 1` — p/ tenant proprio, usar o interno (taxa final operacoes5).

**DERIVACAO CORRETA so com dados CVM — "Yield efetivo da carteira"
(2026-06-11):** a taxa nao e invertivel da tab_ix (CVM nao publica face x
preco; media de anualizadas nao desfaz por Jensen), mas o RESULTADO e:

    yield_am = Σ(rentab_classe x PL_classe) / DC_bruto_medio
             = (tab_x_3 x tab_x_2) / tab_ii

E o retorno LIQUIDO que a carteira entregou (apos custos/PDD/caixa) — piso
honesto da taxa praticada. Validado REALINVEST abr/26: derivado 2,81% a.m. vs
taxa bruta real interna 3,47% (gap = custos+PDD+drag de caixa). Escala:
calculavel p/ 3.036 fundos; mercado abr/26 mediana 1,40% a.m. (p25 0,09 /
p75 2,24). E o indicador de pricing RECOMENDADO da cesta (tab_ix vira
secundario/ordinal). Bracket auxiliar: converter tab_ix p/ mensal
((1+tx/100)^(30/365)-1) da o intervalo [conv(min), conv(media)] que contem a
taxa real (REALINVEST: [2,39%, 5,59%] ∋ 3,47%).

### Custos operacionais do fundo — NAO existem em dado aberto (verificado 2026-06-11)
O Informe Mensal nao tem NENHUM campo de despesa (catalogo varrido). O
balancete mensal e protocolado na CVM (XML COFI via CVMWeb) mas NAO e
publicado como dado aberto para FIDC: `fi-doc-balancete` (150MB/mes) contem
apenas TP_FUNDO_CLASSE in (FI, CLASSES-FIF) — REALINVEST ausente (testado
2026-04); `fie-doc-balancete` cobre FAPI/FIIM/FMAI/FMP; em
`dados.cvm.gov.br/dados/FIDC/DOC/` so existe `INF_MENSAL/`. Consequencias:
1. **Yield bruto NAO e derivavel com precisao** de dado publico — o yield
   efetivo (liquido) e o teto do que da pra medir cross-fund.
2. Ponte APROXIMADA: `yield_bruto ≈ yield_efetivo + taxa_adm/12 + ΔPDD/DC`
   — ΔPDD ja temos (provisao m vs m-1); taxa_adm contratual viria do
   `registro_fundo_classe.zip` (ja no radar, gated). Residuo = demais
   despesas (custodia/consultoria/auditoria — relevantes em fundo pequeno).
3. Custos REALIZADOS por fundo: so nas DFs anuais do FNET (PDF, nao
   estruturado) ou, p/ fundos proprios, no interno (CPR/DRE).

## Resumo por tabela

| Tabela | Granularidade | Serve para... |
|---|---|---|
| `tab_i` | fundo/classe x mes | Cabecalho + posicao carteira R$ (~109 campos) |
| `tab_ii` | fundo/classe x mes | Composicao setorial DC |
| `tab_iii` | fundo/classe x mes | PASSIVO: valores a pagar (curto/longo) + derivativos vendidos (NAO e "DC adquiridos") |
| `tab_iv` | fundo/classe x mes | PL total + PL medio trimestral |
| `tab_v` | fundo/classe x mes | DC **COM risco** a vencer / inadimplente / antecipado por bucket de prazo |
| `tab_vi` | fundo/classe x mes | DC **SEM risco** por bucket — espelho da tab_v (NAO e "passivo por prazo") |
| `tab_vii` | fundo/classe x mes | Negocios do mes: qt/vl de DC + aquisicoes por origem (cedente/prestador/terceiro, com vl contabil) + substituicoes + RECOMPRAS (proxy de WOP do mercado) |
| `tab_ix` | fundo/classe x mes | TAXAS praticadas (desconto da aquisicao + juros, % a.a., min/media/max, compra/venda) por classe de ativo — NAO e "mercado secundario" |
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
