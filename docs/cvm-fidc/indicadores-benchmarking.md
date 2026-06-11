# Indicadores de Benchmarking FIDC — proposta (cesta inicial)

> Proposta 2026-06-11 (worktree `bench`). Cruzamento de: (a) praticas de
> mercado — relatorios de monitoramento de agencias (Austin, Liberum, S&P),
> guias de analise FIDC e levantamentos Uqbar; (b) o modelo CVM validado
> empiricamente no [`dicionario.md`](./dicionario.md) (4 grupos dominados:
> ativo, passivo/PL, cotas/fluxo, giro/qualidade). Todos os campos citados
> tem semantica VALIDADA — incluindo as pegadinhas (provisao positiva,
> tab_v+tab_vi, rentabilidade autoritativa, recompra=valor pago).
>
> STATUS: PROPOSTA — aguardando aprovacao do Ricardo. Nada implementado.

## Convencoes

- `DC_bruto` = `tab_ii_vl_carteira` (= 2a+2b brutos, validado ao centavo)
- `PDD` = `tab_i2a11_vl_reducao_recup + tab_i2b11_vl_reducao_recup` (positiva)
- `Inad` = `tab_v_b_vl_dircred_inad + tab_vi_b_vl_dircred_inad` (com+sem risco)
- Por-serie: `tab_x_2/x_3/x_4/x_6`, chave `tab_x_classe_serie`
- Tudo por `cnpj_fundo_classe x competencia`; comparaveis por porte/setor
  (`tab_ii`)/condominio/prazo (campos cadastrais do `tab_x`/registro)

## Nucleo (10)

| # | Indicador | Formula (campos CVM) | Leitura / pratica de mercado |
|---|---|---|---|
| 1 | **PL** (porte) | `tab_iv_a_vl_pl` (+ `tab_iv_b_vl_pl_medio` 3m) | Base de tudo: segmentacao por faixa de porte, denominador dos demais. Mediana e distribuicao do segmento |
| 2 | **Indice de Subordinacao** | `Σ tab_x_2(qt*vl) das series %Subordinada%` / PL (variantes: so Sub Jr; Sub+Mez) | Colchao de protecao da senior — O indicador de agencia. Mercado: >20% conservador, 10-20% moderado. Calculavel p/ 3.205/4.102 fundos |
| 3 | **Passivo / Ativo** | `tab_iii_vl_passivo / tab_i_vl_ativo` | Sanidade/outlier (FIDC quase nao tem passivo; universo 2,6%). Valor alto = obrigacao estrutural atipica |
| 4 | **% do Ativo em DC** | `(tab_i2a + tab_i2b) / tab_i_vl_ativo` (liquido) | "Pureza" do fundo: separa FIDC-de-carteira de FIDC-veiculo/distressed (os 60 fundos com I.4 dominante). Complemento: % alta liquidez + % outros |
| 5 | **Alta Liquidez / PL** ("caixa") | `(tab_i1_vl_disp + tab_i2d_titpub + tab_i2e_cdb + tab_i2f_comprom + tab_i2g_outro_rf + tab_i2c5_cota_fif + tab_i4a_vl_cprazo) / PL` | Eficiencia de alocacao (caixa alto = drag de rentabilidade; baixo = risco de liquidez p/ resgate/amortizacao). **Inclui I.4 SO curto prazo** (`tab_i4a` — no REALINVEST e o floating de liquidacao, vira caixa em dias); o I.4 longo prazo fica FORA (judicial/dacao, iliquido). Validacao alternativa: `tab_x_5` liquidez escalonada (visao do admin) |
| 6 | **Prazo medio da carteira** | media ponderada dos buckets `tab_v_a* + tab_vi_a*` (pontos medios 15/45/75/105/135/165/270/540/900/1260d) | Duration do lastro; agencia reporta em todo monitoramento. Faixa >1080 censurada (nota) |
| 7 | **Inadimplencia total** ("atraso normalizado") | `Inad / DC_bruto` + aging (>30/>90/>180d via buckets b1..b10) | O indicador Uqbar do segmento (mar/26: 11,3% mercado). DENOMINADOR BRUTO e numerador v+vi (so tab_v ignora 89% da carteira em fundos como o REALINVEST) |
| 8 | **Cobertura de PDD** | `PDD / Inad` | Coverage ratio: >100% bem provisionado (mercado: >150% forte). O gap atraso-vs-PDD e exatamente o que a CVM supervisiona nos administradores |
| 9 | **PDD / PL** (e PDD / DC_bruto) | `PDD / tab_iv_a_vl_pl` | Peso da perda esperada sobre o patrimonio (pedido Ricardo). A variante /DC_bruto e a "taxa de provisao" comparavel entre carteiras |
| 10 | **Taxa de Recompra** | `tab_vii_d_2_vl_recompra / DC_bruto` (mes; tambem acum. 12m) | **Proxy de write-off/suporte do cedente** — nao existe campo de WOP no informe; recompra e o observavel (validado = valor PAGO, ao centavo no REALINVEST). Pratica de agencia: analisar performance EXCLUINDO recompra, pois ela mascara inadimplencia (cedente recompra o podre). Recompra alta + inadimplencia baixa = red flag classico |

## Complementares (5)

| # | Indicador | Formula | Leitura |
|---|---|---|---|
| 11 | **Captacao liquida / PL** | `(Captacoes - Resgates - Amortizacoes) / PL` (`tab_x_4`) + fila `Resgates Solicitados` | Crescimento organico e pressao de saida. Universo abr/26: +20,2 bi |
| 12 | **Giro da carteira** | `tab_vii_a(1+2) aquisicoes / DC_bruto` | Velocity do lastro (FAT gira ~1x/mes; consignado quase nao gira). Contextualiza inadimplencia e prazo. ATENCAO: aquisicoes CVM nao conciliam 1:1 com QiTech (base inclui notas) |
| 13 | **Rentabilidade da Subordinada** | `tab_x_3` da serie Sub (mes + acum 12m) | O retorno do "equity" do fundo — onde o resultado aparece primeiro. SEMPRE tab_x_3 (Δcota nao e proxy — amortizacao distorce) |
| 14 | **Atingimento de meta** | `tab_x_6: pr_desemp_real - pr_desemp_esperado` (so series com esperado>0) | Consistencia das series senior/mez vs benchmark prometido (tracking). Sub fica fora (esperado=0, residual) |
| 15 | **Mix SCR de risco** | `Σ tab_x_scr_risco_oper_{d..h} / Σ tab_x_scr_risco_oper_*` (parse text; usar TODAS as letras — ha arrasto) | Qualidade da carteira na visao BACEN (AA..H) — 100% dos fundos reportam; unica lente de rating publica. A regua AA..H soma o DC bruto exato |
| 16 | **Yield efetivo da carteira** | `Σ(tab_x_3.rentab x tab_x_2.PL_classe) / tab_ii.DC_bruto medio` | Retorno LIQUIDO entregue pela carteira (piso da taxa praticada) — derivavel p/ 3.036 fundos; mercado abr/26: mediana 1,40% a.m. Validado REALINVEST: 2,81% vs taxa bruta real 3,47%. Substitui a tab_ix como indicador de pricing (tab_ix = ordinal secundario; nivel nao confiavel) |
| 17 | **DC de cedentes em Divida Ativa** | `tab_x_debito_tribut / DC_bruto` | Risco de constricao judicial do lastro (penhora de recebivel de cedente devedor da Uniao). REALINVEST: 14,5%. Ninguem publica isso agregado |

## Notas de desenho

1. **Denominadores conscientes**: inadimplencia sobre BRUTO (tab_ii);
   subordinacao sobre PL; liquidez sobre PL. Documentar em cada KPI (tooltip
   de proveniencia, §14).
2. **Recompra como write-off**: rotular como "proxy" — write-off contabil
   nao e campo do informe. Para o proprio tenant, o numero interno
   (wh_liquidacao_recebivel) e a verdade; CVM serve p/ comparar com o mercado.
3. **Comparabilidade**: todo indicador ganha contexto como percentil do peer
   group (mesmo porte/setor tab_ii), nao numero solto — e o formato dos
   relatorios de agencia.
4. **Casos especiais**: fundos "% DC" baixo (item 4) saem dos rankings de
   inadimplencia/prazo (lastro nao representativo) — flag em vez de numero.
5. **Concentracao top-9 cedentes** (`tab_i2a12_pr_*`) ja existe no benchmark
   atual — mantem-se como esta (nao re-listada na cesta).

## Fontes de mercado

- FIDCs.com.br — guia de analise e indicadores (benchmarks de subordinacao,
  inadimplencia, coverage, liquidez D+0/D+30)
- Uqbar / InvestNews / InfoMoney — "atraso normalizado" do mercado (11,3%
  mar/26), salto de 32% nos vencidos
- Relatorios de monitoramento Austin/Liberum/S&P (Pine, Quata, Leme) —
  pratica de excluir recompras da performance, prazo medio, atraso/PL
- ANBIMA Guia Tecnico de PDD + CVM metodologia de supervisao de provisoes
