/**
 * Lamina FIDC -- documento de 3 paginas A4 (porte do handoff de design).
 *
 * MOTIVO: superficie de impressao/PDF (nao pagina BI interativa). Usa CSS
 * proprio escopado (`.lamina-print-root`) + estilos inline pontuais e SVG
 * inline (charts.tsx) -- coberto pelo MODO ITERACAO DE DESIGN (CLAUDE.md) e
 * pela natureza de "surface/documento". Cores = tokens Strata (calc.ts COL).
 * Todo numero vem de `LaminaResponse` (silver QiTech); display derivado em calc.ts.
 */

import * as React from "react"

import type { LaminaClasseSerie, LaminaResponse } from "@/lib/api-client"

import {
  AtivoChart,
  ConcHistChart,
  GarantiaChart,
  PLStackedChart,
  RentHistChart,
} from "./charts"
import {
  CLASSE_COLOR,
  CLASSE_SHORT,
  COL,
  compound,
  derive,
  fmt,
  fmtMi,
  p1,
  p2,
  pctCDI,
} from "./calc"

const LAMINA_CSS = `
.lamina-print-root{background:#aeb6bd;padding:24px 0 48px;font-family:'Inter',Arial,sans-serif;color:#111827}
.lamina-print-root .lam-page{position:relative;width:794px;min-height:1123px;background:#fff;margin:0 auto 24px;padding:0 0 64px;box-shadow:0 8px 30px rgba(10,25,45,.28)}
.lamina-print-root .lam-page::before{content:"";position:absolute;top:0;left:0;right:0;height:4px;background:linear-gradient(90deg,#1B2B4B 0%,#1B2B4B 72%,#E9D400 72%,#E9D400 100%)}
.lamina-print-root table{width:100%;border-collapse:collapse}
.lamina-print-root svg text{font-family:'Inter',Arial,sans-serif}
.lamina-print-root .lam-eyebrow{font-size:10px;font-weight:600;letter-spacing:.18em;text-transform:uppercase;color:#6B7280}
.lamina-print-root .lam-h1{font-size:25px;font-weight:700;letter-spacing:-.01em;color:#111827;line-height:1}
.lamina-print-root .lam-h1-sm{font-size:18px;font-weight:700;letter-spacing:-.01em;color:#111827;line-height:1}
.lamina-print-root .lam-sub{font-size:11px;color:#4B5563;margin-top:7px;font-variant-numeric:tabular-nums}
.lamina-print-root .lam-h2{font-size:13px;font-weight:600;color:#111827}
.lamina-print-root .lam-hint{font-size:10px;color:#6B7280}
.lamina-print-root .lam-secline{border-bottom:1px solid #D1D5DB;padding-bottom:7px;display:flex;align-items:baseline;gap:10px}
.lamina-print-root .lam-wordmark{font-size:20px;font-weight:800;letter-spacing:-.02em;color:#1B2B4B}
.lamina-print-root .lam-wordmark span{color:#E9D400;-webkit-text-stroke:.4px #1B2B4B}
.lamina-print-root .th{text-align:right;padding:6px 7px;font-size:9px;font-weight:600;letter-spacing:.05em;text-transform:uppercase;color:#6B7280;border-bottom:1px solid #D1D5DB;white-space:nowrap}
.lamina-print-root .thl{text-align:left}
.lamina-print-root .td{text-align:right;padding:5px 7px;font-size:10.5px;color:#111827;font-variant-numeric:tabular-nums;white-space:nowrap;border-bottom:1px solid #F3F4F6}
.lamina-print-root .tdl{text-align:left;color:#374151;font-weight:500}
.lamina-print-root .tdsub{text-align:left;padding:5px 7px;font-size:10px;color:#6B7280;border-bottom:1px solid #F3F4F6;white-space:nowrap}
.lamina-print-root .tot{text-align:right;padding:6px 7px;font-size:10.5px;font-weight:700;color:#1B2B4B;font-variant-numeric:tabular-nums;border-top:1.5px solid #1B2B4B;white-space:nowrap}
.lamina-print-root .totl{text-align:left}
.lamina-print-root .pTH{text-align:right;padding:5px 3px;font-size:8.5px;font-weight:600;text-transform:uppercase;color:#6B7280;border-bottom:1px solid #D1D5DB;white-space:nowrap}
.lamina-print-root .pTHL{text-align:left}
.lamina-print-root .pTD{text-align:right;padding:4px 3px;font-size:9.5px;color:#111827;font-variant-numeric:tabular-nums;white-space:nowrap;border-bottom:1px solid #F3F4F6}
.lamina-print-root .pTDL{text-align:left;color:#374151;font-weight:500;padding-left:0}
.lamina-print-root .pTDsub{text-align:left;padding:4px 6px 4px 3px;font-size:9px;color:#6B7280;border-bottom:1px solid #F3F4F6;white-space:nowrap}
.lamina-print-root .lam-foot{position:absolute;bottom:22px;left:44px;right:44px;display:flex;justify-content:space-between;font-size:9px;color:#9CA3AF;border-top:1px solid #EEF1F4;padding-top:8px}
.lamina-print-root .lam-tag{display:inline-flex;align-items:center;gap:6px}
.lamina-print-root .lam-tag i{width:8px;height:8px;border-radius:1px;flex:none;display:inline-block}
@media print{
  @page{size:A4 portrait;margin:0}
  body{background:#fff}
  body *{visibility:hidden}
  .lamina-print-root,.lamina-print-root *{visibility:visible}
  .lamina-print-root{position:absolute;left:0;top:0;width:100%;background:#fff;padding:0}
  .lamina-print-root .lam-page{margin:0;box-shadow:none;page-break-after:always;break-after:page}
  .lamina-print-root .lam-page:last-child{page-break-after:auto;break-after:auto}
}
`

function Wordmark({ h = 52 }: { h?: number }) {
  // Logo institucional A7 Credit (lockup vertical). Plain <img>: superficie de
  // impressao (next/image nao agrega aqui e atrapalha o print).
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img src="/a7-credit.png" alt="A7 Credit" style={{ height: h, width: "auto", display: "block", marginLeft: "auto" }} />
  )
}

function Tag({ s, small }: { s: LaminaClasseSerie; small?: boolean }) {
  return (
    <span className="lam-tag" style={small ? { fontSize: 8.5 } : undefined}>
      <i style={{ background: CLASSE_COLOR[s.classe] }} />
      {CLASSE_SHORT[s.classe]}
    </span>
  )
}

const cdiColor = (v: number | null): string | undefined =>
  v == null ? undefined : v >= 100 ? COL.pos : COL.neg

export function LaminaDocument({ data }: { data: LaminaResponse }) {
  const d = derive(data)
  const meses = data.meses
  const last = d.last
  const cdi = data.cdi
  const classes = data.classes // ordem sr, mez, sub
  // anoIdx: primeiro mes do ano da competencia (YTD).
  const yy = data.competencia.slice(2, 4)
  const anoIdx = Math.max(0, meses.findIndex((m) => m.endsWith(`/${yy}`)))

  return (
    <div className="lamina-print-root">
      <style dangerouslySetInnerHTML={{ __html: LAMINA_CSS }} />

      {/* ============ PAGINA 1 ============ */}
      <div className="lam-page">
        <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", padding: "30px 44px 18px" }}>
          <div>
            <div className="lam-eyebrow" style={{ marginBottom: 6 }}>Lâmina mensal do fundo</div>
            <div className="lam-h1">{data.fundo_nome}</div>
            <div className="lam-sub">
              CNPJ {formatCnpj(data.cnpj)}
              {data.gestor_nome ? ` · Gestao ${data.gestor_nome}` : ""}
            </div>
          </div>
          <div style={{ textAlign: "right" }}>
            <Wordmark />
            <div style={{ fontSize: 10.5, fontWeight: 600, color: "#1B2B4B", marginTop: 8 }}>{data.competencia_label}</div>
            <div style={{ fontSize: 9.5, color: "#6B7280", marginTop: 1 }}>posição {formatDate(data.posicao)}</div>
          </div>
        </header>

        {/* ficha discreta */}
        <div style={{ margin: "0 44px", padding: "9px 0 10px", borderTop: "1px solid #E5E7EB", borderBottom: "1px solid #E5E7EB", fontSize: 10, color: "#6B7280" }}>
          Administrador <strong style={{ color: "#4B5563", fontWeight: 500 }}>QiTech</strong>
          <span style={{ color: "#D1D5DB", margin: "0 7px" }}>·</span>
          Originador <strong style={{ color: "#4B5563", fontWeight: 500 }}>{data.originador_nome ?? "—"}</strong>
          <span style={{ color: "#D1D5DB", margin: "0 7px" }}>·</span>
          Classes <strong style={{ color: "#4B5563", fontWeight: 500 }}>{classes.map((c) => CLASSE_SHORT[c.classe]).join(" · ")}</strong>
        </div>

        {/* KPI hero */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(6,1fr)", margin: "0 44px", borderBottom: "1px solid #E5E7EB" }}>
          <Kpi label="PL total" value={`R$ ${fmtMi(d.kpi.plTotal)} mi`} sub={`${classes.length} classes · ${formatDate(data.posicao, true)}`} />
          <KpiClasse color={CLASSE_COLOR.sr} label="Sênior 12M" value={`${p1(d.kpi.sen12)}%`} cdi={d.kpi.sen12Cdi} />
          <KpiClasse color={CLASSE_COLOR.mez} label="Sub Mez 12M" value={`${p1(d.kpi.mez12)}%`} cdi={d.kpi.mez12Cdi} />
          <KpiClasse color={CLASSE_COLOR.sub} label="Sub Jr 12M" value={`${p1(d.kpi.sub12)}%`} cdi={d.kpi.sub12Cdi} valueColor="#1B2B4B" />
          <Kpi label="Subordinação" value={`${p1(d.kpi.razao)}%`} sub="Sub + Mez / PL" />
          <Kpi label="PDD / carteira" value={`${p2(d.kpi.pddCarteira)}%`} sub={meses[last]} last />
        </div>

        {/* performance mensal */}
        <div style={{ padding: "26px 44px 0" }}>
          <div className="lam-secline">
            <span className="lam-h2">Desempenho mensal por classe</span>
            <span className="lam-hint">rentabilidade % e % do CDI · {meses[0]} → {meses[last]}</span>
          </div>
          <div style={{ marginTop: 10 }}>
            <table>
              <thead>
                <tr>
                  <th className="pTH pTHL" />
                  <th className="pTH pTHL" />
                  {meses.map((m) => <th key={m} className="pTH">{m}</th>)}
                  <th className="pTH" style={{ borderBottomColor: "#1B2B4B" }}>Acum.</th>
                </tr>
              </thead>
              <tbody>
                {classes.map((c) => {
                  const acum = compound(c.var_mensal)
                  const acumK = d.c12 ? (acum / d.c12) * 100 : null
                  return (
                    <React.Fragment key={c.classe}>
                      <tr>
                        <td className="pTDL" rowSpan={2}><Tag s={c} small /></td>
                        <td className="pTDsub">Rent. %</td>
                        {c.var_mensal.map((v, i) => <td key={i} className="pTD">{p2(v)}</td>)}
                        <td className="pTD" style={{ fontWeight: 700, color: "#1B2B4B" }}>{p2(acum)}</td>
                      </tr>
                      <tr>
                        <td className="pTDsub">% CDI</td>
                        {c.var_mensal.map((v, i) => {
                          const k = pctCDI(v, cdi[i] ?? 0)
                          return <td key={i} className="pTD" style={{ color: cdiColor(k), fontWeight: k == null ? undefined : 600 }}>{p1(k)}</td>
                        })}
                        <td className="pTD" style={{ color: cdiColor(acumK), fontWeight: 600 }}>{p1(acumK)}</td>
                      </tr>
                    </React.Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div style={{ fontSize: 9.5, color: "#6B7280", marginTop: 7, fontStyle: "italic" }}>
            Classe constituída no meio do período não exibe o retorno do mês de constituição (período parcial).
          </div>
        </div>

        {/* acum + distrib */}
        <div style={{ display: "flex", gap: 34, padding: "24px 44px 0" }}>
          <div style={{ flex: 1.35, minWidth: 0 }}>
            <div className="lam-secline"><span className="lam-h2">Rentabilidade acumulada</span></div>
            <div style={{ marginTop: 10 }}>
              <table>
                <thead>
                  <tr>
                    <th className="th thl" /><th className="th thl" />
                    <th className="th">Mês</th><th className="th">6M</th><th className="th">12M</th>
                    <th className="th" style={{ borderBottomColor: "#1B2B4B" }}>{`20${yy}`}</th>
                  </tr>
                </thead>
                <tbody>
                  {classes.map((c) => {
                    const m = c.var_mensal[last]
                    const s6 = compound(c.var_mensal.slice(-6))
                    const s12 = compound(c.var_mensal)
                    const ano = compound(c.var_mensal.slice(anoIdx))
                    const k = (num: number, den: number) => (den ? (num / den) * 100 : null)
                    return (
                      <React.Fragment key={c.classe}>
                        <tr>
                          <td className="td tdl" rowSpan={2}><Tag s={c} /></td>
                          <td className="tdsub">Rent. %</td>
                          <td className="td">{p2(m)}</td><td className="td">{p2(s6)}</td><td className="td">{p2(s12)}</td>
                          <td className="td" style={{ fontWeight: 700, color: "#1B2B4B" }}>{p2(ano)}</td>
                        </tr>
                        <tr>
                          <td className="tdsub">% CDI</td>
                          <td className="td" style={{ color: cdiColor(pctCDI(m, cdi[last] ?? 0)) }}>{p1(pctCDI(m, cdi[last] ?? 0))}</td>
                          <td className="td" style={{ color: cdiColor(k(s6, compound(cdi.slice(-6)))) }}>{p1(k(s6, compound(cdi.slice(-6))))}</td>
                          <td className="td" style={{ color: cdiColor(k(s12, d.c12)) }}>{p1(k(s12, d.c12))}</td>
                          <td className="td" style={{ color: cdiColor(k(ano, compound(cdi.slice(anoIdx)))) }}>{p1(k(ano, compound(cdi.slice(anoIdx))))}</td>
                        </tr>
                      </React.Fragment>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="lam-secline"><span className="lam-h2">Distribuição de cotas</span></div>
            <div style={{ marginTop: 10 }}>
              <table>
                <thead>
                  <tr><th className="th thl">Classe</th><th className="th">Nº cotas</th><th className="th">PL (R$)</th><th className="th">% PL</th></tr>
                </thead>
                <tbody>
                  {classes.map((c) => (
                    <tr key={c.classe}>
                      <td className="td tdl"><Tag s={c} /></td>
                      <td className="td">{p2(c.quantidade)}</td>
                      <td className="td">{fmt(c.patrimonio[last])}</td>
                      <td className="td">{p1(d.kpi.plTotal ? (c.patrimonio[last] / d.kpi.plTotal) * 100 : null)}</td>
                    </tr>
                  ))}
                  <tr>
                    <td className="tot totl">Total</td><td className="tot" /><td className="tot">{fmt(d.kpi.plTotal)}</td><td className="tot">100,0</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* charts */}
        <div style={{ display: "flex", gap: 34, padding: "24px 44px 0" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#111827" }}>Rentabilidade histórica acumulada</div>
            <Legend items={[["Sub JR", COL.subLine, true], ["CDI", COL.cdiLine, true]]} />
            <RentHistChart meses={meses} varSub={d.byClasse.sub?.var_mensal ?? meses.map(() => null)} cdi={cdi} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#111827" }}>Evolução do patrimônio líquido</div>
            <Legend items={classes.map((c) => [CLASSE_SHORT[c.classe], CLASSE_COLOR[c.classe], false] as [string, string, boolean])} />
            <PLStackedChart meses={meses} classes={classes} />
          </div>
        </div>

        <Footer left={`A7 Credit · FIDC Analytics — ${data.fundo_nome}`} page="Página 1 de 3" />
      </div>

      {/* ============ PAGINA 2 ============ */}
      <div className="lam-page">
        <PageHeader fundo={data.fundo_nome} subtitle="Estrutura de capital · qualidade da carteira" />

        <div style={{ padding: "26px 44px 0" }}>
          <div className="lam-secline" style={{ justifyContent: "space-between" }}>
            <span style={{ display: "flex", alignItems: "baseline", gap: 10 }}>
              <span className="lam-h2">Razão de garantia</span>
              <span className="lam-hint">(PL Subordinada + Mezanino) / PL total · {meses[0]} → {meses[last]}</span>
            </span>
            <span style={{ fontSize: 11, fontWeight: 600, color: "#1B2B4B" }}>{p1(d.kpi.razao)}% atual</span>
          </div>
          <Legend items={[...classes.map((c) => [`% PL ${CLASSE_SHORT[c.classe]}`, CLASSE_COLOR[c.classe], false] as [string, string, boolean]), ["Razão de garantia (Sub+Mez)", COL.alert, true]]} />
          <GarantiaChart meses={meses} classes={classes} totals={d.totals} razao={d.razaoMensal} />
          <div style={{ marginTop: 10 }}>
            <table>
              <thead><tr><th className="th thl">% PL</th>{meses.map((m) => <th key={m} className="th">{m}</th>)}</tr></thead>
              <tbody>
                {classes.map((c) => (
                  <tr key={c.classe}>
                    <td className="td tdl"><Tag s={c} /></td>
                    {c.patrimonio.map((v, i) => <td key={i} className="td">{p1(d.totals[i] ? (v / d.totals[i]) * 100 : null)}</td>)}
                  </tr>
                ))}
                <tr>
                  <td className="tot totl">Razão de garantia</td>
                  {d.razaoMensal.map((v, i) => <td key={i} className="tot">{p1(v)}</td>)}
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ padding: "26px 44px 0" }}>
          <div className="lam-secline"><span className="lam-h2">Evolução do ativo</span><span className="lam-hint">a vencer · vencido · caixa, com PDD sobre a carteira</span></div>
          <Legend items={[["Direitos a vencer", CLASSE_COLOR.mez, false], ["Direitos vencidos", COL.vencido, false], ["Caixa", COL.caixa, false], ["PDD / carteira", COL.alert, true]]} />
          <AtivoChart meses={meses} aVencer={data.aging.a_vencer} vencido={data.aging.vencido} caixa={data.aging.caixa} pddPct={d.pddCarteiraPct} />
          <div style={{ marginTop: 10 }}>
            <table>
              <thead><tr><th className="th thl">R$ mi</th>{meses.map((m) => <th key={m} className="th">{m}</th>)}</tr></thead>
              <tbody>
                <tr><td className="td tdl">A vencer</td>{data.aging.a_vencer.map((v, i) => <td key={i} className="td">{fmtMi(v)}</td>)}</tr>
                <tr><td className="td tdl">Vencido</td>{data.aging.vencido.map((v, i) => <td key={i} className="td">{fmtMi(v)}</td>)}</tr>
                <tr><td className="td tdl">PDD / carteira %</td>{d.pddCarteiraPct.map((v, i) => <td key={i} className="td">{p1(v)}</td>)}</tr>
              </tbody>
            </table>
          </div>
        </div>

        <div style={{ padding: "26px 44px 0" }}>
          <div className="lam-secline"><span className="lam-h2">Resumo por série</span><span className="lam-hint">valor da cota e rentabilidade</span></div>
          <div style={{ marginTop: 10 }}>
            <table>
              <thead>
                <tr><th className="th thl">Cota</th><th className="th">Valor da cota</th><th className="th">Rent. 12M</th><th className="th">% CDI 12M</th></tr>
              </thead>
              <tbody>
                {classes.map((c) => {
                  const r12 = compound(c.var_mensal)
                  const k = d.c12 ? (r12 / d.c12) * 100 : null
                  return (
                    <tr key={c.classe}>
                      <td className="td tdl"><Tag s={c} /></td>
                      <td className="td">{p2(c.valor_cota)}</td>
                      <td className="td">{p2(r12)}</td>
                      <td className="td" style={{ color: cdiColor(k) }}>{p1(k)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>

        <Footer left="Aging reconcilia: a vencer + vencido = estoque total. Sem papéis baixados no estoque." page="Página 2 de 3" />
      </div>

      {/* ============ PAGINA 3 ============ */}
      <div className="lam-page">
        <PageHeader fundo={data.fundo_nome} subtitle="Concentração de cedentes e sacados" />

        <div style={{ display: "flex", gap: 34, padding: "26px 44px 0" }}>
          <ConcTable title="Cedentes" prefix="Cedente" items={data.concentracao.cedentes} plTotal={d.kpi.plTotal} posicao={formatDate(data.posicao, true)} />
          <ConcTable title="Sacados" prefix="Sacado" items={data.concentracao.sacados} plTotal={d.kpi.plTotal} posicao={formatDate(data.posicao, true)} />
        </div>

        <div style={{ display: "flex", gap: 34, padding: "26px 44px 0" }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#111827" }}>Histórico de concentração — cedentes</div>
            <Legend items={[["Maior cedente", CLASSE_COLOR.sub, false], ["10 maiores", CLASSE_COLOR.sr, false]]} />
            <ConcHistChart meses={meses} maior={data.concentracao.historico.cedente_maior} top10={data.concentracao.historico.cedente_top10} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 600, color: "#111827" }}>Histórico de concentração — sacados</div>
            <Legend items={[["Maior sacado", CLASSE_COLOR.sub, false], ["10 maiores", CLASSE_COLOR.sr, false]]} />
            <ConcHistChart meses={meses} maior={data.concentracao.historico.sacado_maior} top10={data.concentracao.historico.sacado_top10} />
          </div>
        </div>

        <div style={{ padding: "22px 44px 0" }}>
          <div style={{ fontSize: 8.5, color: "#9CA3AF", lineHeight: 1.5 }}>
            Proveniência: warehouse silver (adapter QiTech) — evolução de cotas, rentabilidade, estoque e saldo de conta
            corrente. Posição {formatDate(data.posicao)}. Campos cadastrais de regulamento (rating, subordinação mínima,
            benchmark-alvo, taxas de adm./perf.) não disponíveis na fonte.
          </div>
        </div>

        <Footer left="Rentabilidade passada não representa garantia de rentabilidade futura. Material meramente informativo." page="Página 3 de 3" />
      </div>
    </div>
  )
}

// ── sub-componentes ──────────────────────────────────────────────────────────
function Kpi({ label, value, sub, last }: { label: string; value: string; sub: string; last?: boolean }) {
  return (
    <div style={{ padding: last ? "16px 0 16px 16px" : "16px 16px", borderLeft: label === "PL total" ? undefined : "1px solid #E5E7EB", paddingLeft: label === "PL total" ? 0 : 16 }}>
      <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: "#6B7280" }}>{label}</div>
      <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: "-.02em", color: "#111827", marginTop: 6, fontVariantNumeric: "tabular-nums" }}>{value}</div>
      <div style={{ fontSize: 10, color: "#4B5563", marginTop: 3 }}>{sub}</div>
    </div>
  )
}

function KpiClasse({ color, label, value, cdi, valueColor }: { color: string; label: string; value: string; cdi: number | null; valueColor?: string }) {
  return (
    <div style={{ padding: "16px 16px", borderLeft: "1px solid #E5E7EB" }}>
      <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: ".08em", textTransform: "uppercase", color: "#6B7280" }}>
        <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: 1, background: color, marginRight: 5, verticalAlign: 1 }} />{label}
      </div>
      <div style={{ fontSize: 20, fontWeight: 700, letterSpacing: "-.02em", color: valueColor ?? "#111827", marginTop: 6, fontVariantNumeric: "tabular-nums" }}>{value}</div>
      <div style={{ fontSize: 10, color: COL.pos, marginTop: 3, fontVariantNumeric: "tabular-nums" }}>{cdi == null ? "—" : `${p1(cdi)}% do CDI`}</div>
    </div>
  )
}

function PageHeader({ fundo, subtitle }: { fundo: string; subtitle: string }) {
  return (
    <header style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", padding: "30px 44px 18px", borderBottom: "1px solid #EEF1F4" }}>
      <div>
        <div className="lam-h1-sm">{fundo}</div>
        <div style={{ fontSize: 10, color: "#6B7280", marginTop: 5 }}>{subtitle}</div>
      </div>
      <Wordmark h={38} />
    </header>
  )
}

function Legend({ items }: { items: [string, string, boolean][] }) {
  return (
    <div style={{ display: "flex", gap: 16, fontSize: 9.5, color: "#4B5563", margin: "5px 0 2px", flexWrap: "wrap" }}>
      {items.map(([label, color, line], i) => (
        <span key={i}>
          <span style={line
            ? { display: "inline-block", width: 14, height: 3, background: color, verticalAlign: 2, marginRight: 5, borderRadius: 2 }
            : { display: "inline-block", width: 9, height: 9, background: color, verticalAlign: -1, marginRight: 5, borderRadius: 1 }} />
          {label}
        </span>
      ))}
    </div>
  )
}

function ConcTable({ title, prefix, items, plTotal, posicao }: { title: string; prefix: string; items: { posicao: number; financeiro: number }[]; plTotal: number; posicao: string }) {
  const soma = items.reduce((a, b) => a + b.financeiro, 0)
  return (
    <div style={{ flex: 1, minWidth: 0 }}>
      <div className="lam-secline"><span className="lam-h2">{title}</span><span className="lam-hint">10 maiores · {posicao}</span></div>
      <div style={{ marginTop: 10 }}>
        <table>
          <thead><tr><th className="th thl">{title}</th><th className="th">Financeiro</th><th className="th">% PL</th></tr></thead>
          <tbody>
            {items.map((it) => (
              <tr key={it.posicao}>
                <td className="td tdl">{prefix} {it.posicao}</td>
                <td className="td">{fmt(it.financeiro)}</td>
                <td className="td">{p1(plTotal ? (it.financeiro / plTotal) * 100 : null)}</td>
              </tr>
            ))}
            <tr>
              <td className="tot totl">10 maiores</td>
              <td className="tot">{fmt(soma)}</td>
              <td className="tot">{p1(plTotal ? (soma / plTotal) * 100 : null)}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Footer({ left, page }: { left: string; page: string }) {
  return (
    <div className="lam-foot">
      <span>{left}</span>
      <span>{page}</span>
    </div>
  )
}

// ── formatadores locais ──────────────────────────────────────────────────────
function formatCnpj(cnpj: string): string {
  const c = (cnpj ?? "").replace(/\D/g, "").padStart(14, "0")
  if (c.length !== 14) return cnpj
  return `${c.slice(0, 2)}.${c.slice(2, 5)}.${c.slice(5, 8)}/${c.slice(8, 12)}-${c.slice(12)}`
}

function formatDate(iso: string, short = false): string {
  // iso = "YYYY-MM-DD"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  return short ? `${m[3]}/${m[2]}` : `${m[3]}/${m[2]}/${m[1]}`
}
