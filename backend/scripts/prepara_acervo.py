# -*- coding: utf-8 -*-
"""Normaliza o acervo Portal FIDC para o CSV canonico da API QiTech.

Le manifest_acervo.csv (saida da triagem), abre cada arquivo escolhido e
gera staging/<data>.csv no layout EXATO do fidc-estoque da API (30 colunas
camelCase, `;`, decimal virgula, data dd/mm/yyyy, SIM/NAO) — para a VM
reusar map_fidc_estoque sem nenhuma mudanca.

Colunas ausentes no formato Portal: nomeGestor/docGestor (vazias) e
prazoAnual (vazia; PRAZO_ATUAL do Portal e outra semantica — dias ate
vencimento — e e DESCARTADO, documentado aqui).

Saida: staging/AAAA-MM-DD.csv + staging_manifest.csv + acervo_staging.zip
"""
import csv
import hashlib
import io
import os
import zipfile
from datetime import date

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
FOLDER = r"C:\Users\RicardoPimenta\A7 CREDIT SECURITIZADORA S.A\Repositório de documentos A7 - Repositório\REALINVEST\Controle de Carteira - Portal FIDC"
STAGING = os.path.join(HERE, "staging")
os.makedirs(STAGING, exist_ok=True)

HEADER = ["nomeFundo", "docFundo", "dataFundo", "nomeGestor", "docGestor",
          "nomeOriginador", "docOriginador", "nomeCedente", "docCedente",
          "nomeSacado", "docSacado", "seuNumero", "numeroDocumento",
          "tipoRecebivel", "valorNominal", "valorPresente", "valorAquisicao",
          "valorPdd", "faixaPdd", "dataReferencia", "dataVencimentoOriginal",
          "dataVencimentoAjustada", "dataEmissao", "dataAquisicao", "prazo",
          "prazoAnual", "situacaoRecebivel", "taxaCessao", "taxaRecebivel",
          "coobrigacao"]

MAPA = {  # coluna Portal -> coluna API (diretas)
    "NOME_FUNDO": "nomeFundo", "DOC_FUNDO": "docFundo", "DATA_FUNDO": "dataFundo",
    "NOME_ORIGINADOR": "nomeOriginador", "DOC_ORIGINADOR": "docOriginador",
    "NOME_CEDENTE": "nomeCedente", "DOC_CEDENTE": "docCedente",
    "NOME_SACADO": "nomeSacado", "DOC_SACADO": "docSacado",
    "SEU_NUMERO": "seuNumero", "NU_DOCUMENTO": "numeroDocumento",
    "TIPO_RECEBIVEL": "tipoRecebivel", "VALOR_NOMINAL": "valorNominal",
    "VALOR_PRESENTE": "valorPresente", "VALOR_AQUISICAO": "valorAquisicao",
    "VALOR_PDD": "valorPdd", "FAIXA_PDD": "faixaPdd",
    "DATA_REFERENCIA": "dataReferencia",
    "DATA_VENCIMENTO_ORIGINAL": "dataVencimentoOriginal",
    "DATA_VENCIMENTO_AJUSTADA": "dataVencimentoAjustada",
    "DATA_EMISSAO": "dataEmissao", "DATA_AQUISICAO": "dataAquisicao",
    "PRAZO": "prazo", "SITUACAO_RECEBIVEL": "situacaoRecebivel",
    "TAXA_CESSAO": "taxaCessao", "TX_RECEBIVEL": "taxaRecebivel",
    "COOBRIGACAO": "coobrigacao",
}
COLS_DATA = {"dataFundo", "dataReferencia", "dataVencimentoOriginal",
             "dataVencimentoAjustada", "dataEmissao", "dataAquisicao"}
COLS_NUM = {"valorNominal", "valorPresente", "valorAquisicao", "valorPdd",
            "taxaCessao", "taxaRecebivel"}


def le(path):
    fl = path.lower()
    if fl.endswith(".zip"):
        with zipfile.ZipFile(path) as z:
            inner = [n for n in z.namelist() if n.lower().endswith((".csv", ".xlsx"))][0]
            b = z.read(inner)
        if inner.lower().endswith(".csv"):
            return _le_csv_bytes(b)
        return pd.read_excel(io.BytesIO(b))
    if fl.endswith(".csv"):
        with open(path, "rb") as fh:
            return _le_csv_bytes(fh.read())
    return pd.read_excel(path)


def _le_csv_bytes(b):
    for enc in ("utf-8-sig", "latin1"):
        try:
            df = pd.read_csv(io.BytesIO(b), sep=";", encoding=enc, dtype=str)
            if df.shape[1] >= 20:
                return df
        except Exception:
            continue
    raise ValueError("csv ilegivel")


def fmt_data(v):
    if pd.isna(v) or v is None or str(v).strip() == "":
        return ""
    s = str(v).strip()
    if "/" in s:  # ja dd/mm/yyyy
        return s[:10]
    d = pd.to_datetime(s, format="ISO8601", errors="coerce")
    return "" if pd.isna(d) else d.strftime("%d/%m/%Y")


def fmt_num(v):
    if pd.isna(v) or v is None or str(v).strip() == "":
        return ""
    s = str(v).strip()
    if "," in s:  # ja BR
        return s
    try:
        f = float(s)
    except ValueError:
        return s
    out = f"{f:.10f}".rstrip("0")
    if out.endswith("."):
        out += "00"
    return out.replace(".", ",")


def main():
    manifest_in = os.path.join(HERE, "manifest_acervo.csv")
    rows = list(csv.DictReader(open(manifest_in, encoding="utf-8"), delimiter=";"))
    print(f"manifesto: {len(rows)} datas")

    out_manifest = []
    erros = []
    for i, r in enumerate(rows, 1):
        d, arq = r["data"], r["arquivo"]
        try:
            df = le(os.path.join(FOLDER, arq))
            df.columns = [str(c).strip().upper() for c in df.columns]
            out = pd.DataFrame()
            for src, dst in MAPA.items():
                out[dst] = df[src] if src in df.columns else ""
            out["nomeGestor"] = ""
            out["docGestor"] = ""
            out["prazoAnual"] = ""  # PRAZO_ATUAL (dias ate vcto) descartado
            out = out[HEADER]
            for c in COLS_DATA:
                out[c] = out[c].map(fmt_data)
            for c in COLS_NUM:
                out[c] = out[c].map(fmt_num)
            out["seuNumero"] = out["seuNumero"].map(
                lambda v: str(v).strip().removesuffix(".0") if pd.notna(v) else "")
            out["prazo"] = out["prazo"].map(
                lambda v: str(v).strip().removesuffix(".0") if pd.notna(v) else "0")
            out["coobrigacao"] = out["coobrigacao"].map(
                lambda v: "SIM" if str(v).strip().upper() == "SIM" else "NAO")
            # sanity: dataReferencia unica e igual a data do manifesto
            refs = {x for x in out["dataReferencia"] if x}
            esperado = date.fromisoformat(d).strftime("%d/%m/%Y")
            if refs != {esperado}:
                raise ValueError(f"dataReferencia {refs} != {esperado}")
            buf = io.StringIO()
            out.to_csv(buf, sep=";", index=False, lineterminator="\n")
            txt = buf.getvalue()
            dest = os.path.join(STAGING, f"{d}.csv")
            with open(dest, "w", encoding="utf-8", newline="") as fh:
                fh.write(txt)
            out_manifest.append({
                "data": d, "arquivo_origem": arq, "linhas": len(out),
                "sha256": hashlib.sha256(txt.encode()).hexdigest()[:16],
            })
        except Exception as e:
            erros.append((d, arq, f"{type(e).__name__}: {e}"))
        if i % 100 == 0:
            print(f"  ... {i}/{len(rows)}")

    with open(os.path.join(HERE, "staging_manifest.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["data", "arquivo_origem", "linhas", "sha256"], delimiter=";")
        w.writeheader()
        w.writerows(out_manifest)

    zpath = os.path.join(HERE, "acervo_staging.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        for m in out_manifest:
            z.write(os.path.join(STAGING, f"{m['data']}.csv"), f"{m['data']}.csv")
        z.write(os.path.join(HERE, "staging_manifest.csv"), "staging_manifest.csv")

    print(f"ok: {len(out_manifest)} datas normalizadas | erros: {len(erros)}")
    for e in erros:
        print("  ERRO", *e)
    print("zip:", zpath, f"{os.path.getsize(zpath)//1024//1024} MB")


if __name__ == "__main__":
    main()
