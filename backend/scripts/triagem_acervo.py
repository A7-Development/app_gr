# -*- coding: utf-8 -*-
"""Triagem do acervo Portal FIDC: data interna, dedupe, manifesto.

Abre cada candidato a snapshot de estoque (xlsx/csv/xls/zip), le
DATA_REFERENCIA de dentro, valida unicidade, e escolhe 1 arquivo por data
(criterio: mais linhas; empate -> mtime mais recente). Gera:
  manifest_acervo.csv  (data;arquivo;formato;linhas;vp_total;flags)
  triagem_resumo.txt
"""
import csv as csvmod
import io
import os
import re
import zipfile
from collections import defaultdict
from datetime import datetime

import pandas as pd

FOLDER = r"C:\Users\RicardoPimenta\A7 CREDIT SECURITIZADORA S.A\Repositório de documentos A7 - Repositório\REALINVEST\Controle de Carteira - Portal FIDC"
OUT = os.path.dirname(os.path.abspath(__file__))

COLS_ESPERADAS = {"NOME_FUNDO", "DOC_CEDENTE", "VALOR_PRESENTE", "DATA_REFERENCIA"}


def data_do_nome(f):
    for n in re.findall(r"\d{8}", f):
        dd, mm, yy = int(n[:2]), int(n[2:4]), int(n[4:])
        if 1 <= dd <= 31 and 1 <= mm <= 12 and 2020 <= yy <= 2026:
            return f"{yy:04d}-{mm:02d}-{dd:02d}"
    return None


def parse_csv_bytes(b):
    for enc in ("utf-8-sig", "latin1"):
        try:
            df = pd.read_csv(io.BytesIO(b), sep=";", encoding=enc, decimal=",",
                             dtype=str)
            if df.shape[1] >= 20:
                return df
        except Exception:
            continue
    return None


def le_arquivo(path):
    """Retorna (df, formato) ou (None, motivo)."""
    fl = path.lower()
    try:
        if fl.endswith(".zip"):
            with zipfile.ZipFile(path) as z:
                inner = [n for n in z.namelist() if n.lower().endswith((".csv", ".xlsx"))]
                if not inner:
                    return None, "zip_sem_planilha"
                b = z.read(inner[0])
                if inner[0].lower().endswith(".csv"):
                    df = parse_csv_bytes(b)
                    return (df, "zip/csv") if df is not None else (None, "zip_csv_ilegivel")
                return pd.read_excel(io.BytesIO(b), dtype=str), "zip/xlsx"
        if fl.endswith(".csv"):
            with open(path, "rb") as fh:
                df = parse_csv_bytes(fh.read())
            return (df, "csv") if df is not None else (None, "csv_ilegivel")
        if fl.endswith((".xlsx", ".xls")):
            return pd.read_excel(path, dtype=str), "xlsx"
        return None, "extensao_nao_suportada"
    except Exception as e:
        return None, f"erro:{type(e).__name__}"


def main():
    candidatos = []
    for f in os.listdir(FOLDER):
        fl = f.lower()
        if ("stoque" in fl) and fl.endswith((".xlsx", ".xls", ".csv", ".zip")):
            candidatos.append(f)
    print(f"candidatos: {len(candidatos)}")

    registros = []   # dicts
    problemas = []
    for i, f in enumerate(candidatos, 1):
        path = os.path.join(FOLDER, f)
        df, fmt = le_arquivo(path)
        if df is None:
            problemas.append((f, fmt))
            continue
        df.columns = [str(c).strip().upper() for c in df.columns]
        if not COLS_ESPERADAS.issubset(df.columns):
            problemas.append((f, "layout_inesperado:" + ",".join(list(df.columns)[:5])))
            continue
        # Dois formatos no acervo: ISO "%Y-%m-%d %H:%M:%S" (xlsx, celula
        # datetime lida como str) e "%d/%m/%Y" (csv). Nunca usar dayfirst
        # em string ISO — pandas troca dia/mes (ex.: 2023-03-06 -> 03/jun).
        raw_ref = df["DATA_REFERENCIA"].astype(str).str.strip()
        if raw_ref.str.match(r"^\d{4}-").any():
            parsed = pd.to_datetime(raw_ref, format="ISO8601", errors="coerce")
        else:
            parsed = pd.to_datetime(raw_ref, format="%d/%m/%Y", errors="coerce")
        refs = parsed.dt.date.dropna().unique()
        if len(refs) != 1:
            problemas.append((f, f"datas_internas={len(refs)}"))
            continue
        ref = refs[0].isoformat()
        vp = pd.to_numeric(
            df["VALOR_PRESENTE"].str.replace(".", "", regex=False).str.replace(",", ".", regex=False)
            if df["VALOR_PRESENTE"].dtype == object and df["VALOR_PRESENTE"].str.contains(",", na=False).any()
            else df["VALOR_PRESENTE"], errors="coerce").sum()
        nome_dt = data_do_nome(f)
        registros.append({
            "data": ref, "arquivo": f, "formato": fmt, "linhas": len(df),
            "vp_total": round(float(vp), 2),
            "mtime": datetime.fromtimestamp(os.path.getmtime(path)).isoformat(timespec="seconds"),
            "flag_nome_diverge": (nome_dt is not None and nome_dt != ref),
        })
        if i % 100 == 0:
            print(f"  ... {i}/{len(candidatos)}")

    por_data = defaultdict(list)
    for r in registros:
        por_data[r["data"]].append(r)

    manifest = []
    duplicatas = 0
    for d in sorted(por_data):
        regs = sorted(por_data[d], key=lambda r: (r["linhas"], r["mtime"]), reverse=True)
        escolhido = regs[0]
        escolhido["flag_duplicatas"] = len(regs) - 1
        duplicatas += len(regs) - 1
        manifest.append(escolhido)

    with open(os.path.join(OUT, "manifest_acervo.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csvmod.DictWriter(fh, fieldnames=list(manifest[0].keys()), delimiter=";")
        w.writeheader()
        w.writerows(manifest)

    anos = defaultdict(int)
    for m in manifest:
        anos[m["data"][:4]] += 1
    divergentes = [m for m in manifest if m["flag_nome_diverge"]]

    resumo = []
    resumo.append(f"candidatos lidos: {len(candidatos)}")
    resumo.append(f"snapshots validos: {len(registros)}")
    resumo.append(f"datas distintas: {len(manifest)}")
    resumo.append(f"duplicatas descartadas: {duplicatas}")
    resumo.append(f"problemas ({len(problemas)}):")
    for f, m in problemas:
        resumo.append(f"  - {f}: {m}")
    resumo.append(f"datas por ano: {dict(sorted(anos.items()))}")
    resumo.append(f"nome diverge do conteudo ({len(divergentes)}):")
    for m in divergentes[:20]:
        resumo.append(f"  - {m['arquivo']} -> conteudo={m['data']}")
    txt = "\n".join(resumo)
    with open(os.path.join(OUT, "triagem_resumo.txt"), "w", encoding="utf-8") as fh:
        fh.write(txt)
    print(txt)


if __name__ == "__main__":
    main()
