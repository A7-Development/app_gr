"""Parse CVM FIDC metadata bundle into a structured YAML dictionary.

Reads the raw .txt files published by CVM under
`dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/META/meta_inf_mensal_fidc_txt.zip`
(one .txt per table -- tab_I, tab_II, ..., tab_X_7) and emits
`docs/cvm-fidc/dicionario.yaml`, the canonical field catalogue used by:

- Claude (dev workflow)  -- grep to answer "which table has field X?"
- Backend adapter         -- source of truth for column types / optionality
- Frontend tooltips       -- when/if we wire the dictionary into <InfoBadge>

Input files live in `docs/cvm-fidc/raw/<versao>/`. The version string (e.g. "v5")
tracks the `(N)` suffix CVM uses on the zip filename; bump it when a newer
dictionary is published.

Usage:
    python scripts/parse_cvm_metadata.py --versao v5

The script is stdlib-only (no PyYAML) so it runs on a clean checkout.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_ROOT = REPO_ROOT / "docs" / "cvm-fidc" / "raw"
OUTPUT_PATH = REPO_ROOT / "docs" / "cvm-fidc" / "dicionario.yaml"

# Curated short descriptions per table -- the CVM metadata files describe
# individual fields but don't have a table-level abstract. These are manually
# maintained so the generated YAML is readable on its own.
TABLE_DESCRIPTIONS: dict[str, str] = {
    "tab_i": (
        "Cabecalho do fundo + posicao da carteira em R$ "
        "(direitos creditorios, titulos publicos, disponibilidades, cotas de outros fundos). "
        "~112 colunas. Granularidade: 1 linha por cnpj_fundo_classe x competencia."
    ),
    "tab_ii": (
        "Composicao setorial dos direitos creditorios "
        "(industrial, comercial, servicos, agronegocio, financeiro, credito, factoring, "
        "setor publico, judicial, imobiliario, marca/IP). Valores em R$."
    ),
    "tab_iii": (
        "Direitos creditorios adquiridos no mes -- prazo medio, taxa media, valor total."
    ),
    "tab_iv": (
        "Patrimonio Liquido TOTAL do fundo/classe (sem quebra por subclasse) -- "
        "atual e medio dos ultimos tres meses."
    ),
    "tab_v": (
        "Direitos creditorios a vencer + inadimplentes + antecipados, "
        "escalonados em 10 buckets de prazo (30/60/90/120/150/180/360/720/1080/>1080 dias)."
    ),
    "tab_vi": (
        "Passivo/obrigacoes do fundo por prazo (mesma escala de tab_v)."
    ),
    "tab_vii": (
        "Informacoes complementares -- pagamento de despesas, provisoes."
    ),
    "tab_ix": (
        "Mercado secundario -- precos min/medio/max de compra e venda das cotas "
        "segmentados por intervalos de rentabilidade (40 colunas)."
    ),
    "tab_x": (
        "Distribuicao de SCR (Sistema de Informacoes de Credito) por rating "
        "AA/A/B/C/D/E/F/G/H -- separadamente por risco do devedor e risco da operacao."
    ),
    "tab_x_1": (
        "Numero de cotistas POR classe/serie (uma linha por "
        "tab_x_classe_serie x id_subclasse)."
    ),
    "tab_x_1_1": (
        "Numero de cotistas POR TIPO DE INVESTIDOR "
        "(banco, PF, PJ financeira/nao financeira, EAPC, EFPC, RPPS, InvNR, FII, "
        "clube, seguradora, corretora, capitalizacao, cota_fidc, outro_fi, outros) -- "
        "quebrado em Senior e Subordinada, NAO por serie."
    ),
    "tab_x_2": (
        "Quantidade e valor da cota POR classe/serie. "
        "PL por subclasse deriva de qt_cota x vl_cota -- UNICA fonte oficial. "
        "Campo tab_x_qt_cota vem frequentemente NULL (ver dicionario.md)."
    ),
    "tab_x_3": (
        "Rentabilidade apurada no mes (%) POR classe/serie."
    ),
    "tab_x_4": (
        "Movimentacoes do mes -- captacoes, resgates, resgates solicitados, "
        "amortizacoes -- valor em R$ e quantidade de cotas, POR classe/serie."
    ),
    "tab_x_5": (
        "Liquidez escalonada do ativo -- R$ liquidavel em 0/30/60/90/180/360/>360 dias."
    ),
    "tab_x_6": (
        "Desempenho percentual esperado vs realizado POR classe/serie."
    ),
    "tab_x_7": (
        "Garantias atreladas aos direitos creditorios -- valor (R$) e percentual."
    ),
}

# Fields that are OPTIONAL in CVM (admin pode omitir sem violar o schema) OR
# que sabidamente vem em branco para casos importantes. Registrar aqui faz
# o dicionario lembrar de caveats de qualidade no mundo real.
KNOWN_OMISSIONS: list[dict[str, str | list[str]]] = [
    {
        "campo": "tab_x_2.tab_x_qt_cota",
        "descricao": (
            "Quantidade de cotas por classe/serie. Campo opcional no preenchimento. "
            "Muitos administradores (ex.: QI Corretora pos-Res.175) deixam NULL. "
            "Sem qt_cota nao ha como derivar PL da subclasse (pl = qt * vl)."
        ),
        "casos_conhecidos": [
            "13.805.152/0001-03 (Puma FIDC NP Multissetorial) -- NULL em toda a serie 2025-02..2026-03",
        ],
        "mitigacao": (
            "Mostrar somente vl_cota + nr_cotst na UI; declarar na lista de limitacoes. "
            "Rateio por nr_cotst NAO e proxy valido."
        ),
    },
    {
        "campo": "tab_x_4.tab_x_qt_cota",
        "descricao": (
            "Quantidade de cotas movimentada (captacao/resgate/amortizacao). "
            "Mesmo padrao de omissao de tab_x_2.tab_x_qt_cota -- quando o admin nao "
            "preenche estoque, tambem nao preenche fluxo."
        ),
        "casos_conhecidos": [
            "13.805.152/0001-03 (Puma FIDC NP Multissetorial)",
        ],
        "mitigacao": (
            "Derivar fluxo em R$ via tab_x_vl_total (sempre populado). "
            "Quantidade de cotas movimentadas fica indisponivel."
        ),
    },
    {
        "campo": "tab_i.tab_i2a12_pr_cedente_{1..9}",
        "descricao": (
            "Concentracao dos 9 maiores cedentes (% do PL). CVM nao coleta top-10+ "
            "nem qualquer informacao dos SACADOS."
        ),
        "casos_conhecidos": ["Todos os FIDCs"],
        "mitigacao": (
            "Relatorios de agencias (Austin etc.) que citam top-10/20 e sacados usam "
            "fonte do ADMINISTRADOR, nao CVM -- irreproduzivel via dado publico."
        ),
    },
    {
        "campo": "tab_v.tab_v_b*_vl_inad_*",
        "descricao": (
            "Buckets de inadimplencia comecam em 0-30 dias. CVM NAO tem bucket 'ate 15d' "
            "(usado por Austin)."
        ),
        "casos_conhecidos": ["Esquema CVM -- limitacao estrutural"],
        "mitigacao": (
            "Ficha da UI apresenta os 10 buckets CVM (0-30..>1080) com nota inline."
        ),
    },
]


FIELD_BLOCK_RE = re.compile(
    r"-{5,}\s*\nCampo:\s*(?P<nome>\S+)\s*\n-{5,}\s*\n(?P<body>.*?)(?=-{5,}\s*\nCampo:|\Z)",
    re.DOTALL,
)
BODY_KEY_RE = re.compile(
    r"^\s*(?P<key>Descri\S+o|Dom\S+nio|Tipo Dados|Tamanho|Precis\S+o|Scale)\s*:\s*(?P<val>.*?)\s*$",
    re.MULTILINE,
)

KEY_ALIASES: dict[str, str] = {
    "descricao": "descricao",
    "dominio": "dominio",
    "tipo dados": "tipo",
    "tamanho": "tamanho",
    "precisao": "precisao",
    "scale": "scale",
}


def _norm_key(raw: str) -> str:
    cleaned = (
        raw.lower()
        .replace("ç", "c")
        .replace("ã", "a")
        .replace("á", "a")
        .replace("é", "e")
        .replace("í", "i")
        .replace("ó", "o")
        .replace("ú", "u")
    )
    # Stray mojibake (cp1252 saw as utf-8)
    for bad, good in (
        ("desi�o", "descricao"),
        ("dom�nio", "dominio"),
        ("precis�o", "precisao"),
    ):
        cleaned = cleaned.replace(bad, good)
    # Accent-less variants of the canonical names
    if cleaned.startswith("descr"):
        return "descricao"
    if cleaned.startswith("dom"):
        return "dominio"
    if cleaned.startswith("tipo"):
        return "tipo"
    if cleaned.startswith("tamanho"):
        return "tamanho"
    if cleaned.startswith("prec"):
        return "precisao"
    if cleaned.startswith("scale"):
        return "scale"
    return cleaned


def _read_meta_file(path: Path) -> str:
    """Read a CVM metadata .txt using the encoding CVM actually ships (cp1252)."""
    raw = path.read_bytes()
    # The files are cp1252 (Latin-1 superset). Fall back gracefully if they
    # ever switch to UTF-8.
    for enc in ("cp1252", "latin-1", "utf-8"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def parse_metadata_file(path: Path) -> list[dict[str, str | int]]:
    text = _read_meta_file(path)
    fields: list[dict[str, str | int]] = []
    for m in FIELD_BLOCK_RE.finditer(text):
        nome = m.group("nome").strip().lower()
        body = m.group("body")
        entry: dict[str, str | int] = {"nome": nome}
        for bm in BODY_KEY_RE.finditer(body):
            key = _norm_key(bm.group("key"))
            val = bm.group("val").strip()
            if not val:
                continue
            if key in ("tamanho", "precisao", "scale"):
                try:
                    entry[key] = int(val)
                    continue
                except ValueError:
                    pass
            entry[key] = val
        fields.append(entry)
    return fields


def table_name_from_filename(filename: str) -> str:
    """meta_inf_mensal_fidc_tab_X_1.txt -> tab_x_1"""
    stem = Path(filename).stem
    prefix = "meta_inf_mensal_fidc_"
    if stem.startswith(prefix):
        stem = stem[len(prefix) :]
    return stem.lower()


def _yaml_escape(value: str) -> str:
    needs_quote = any(ch in value for ch in ":#&*?|<>=!%@`'\"") or value.strip() != value
    if needs_quote or value == "":
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def _render_yaml(doc: dict) -> str:
    """Minimal YAML writer tailored to this dictionary's shape (no deps)."""
    lines: list[str] = []

    def emit_scalar(indent: int, key: str, value: object) -> None:
        prefix = " " * indent
        if value is None:
            lines.append(f"{prefix}{key}: null")
        elif isinstance(value, bool):
            lines.append(f"{prefix}{key}: {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{prefix}{key}: {value}")
        else:
            lines.append(f"{prefix}{key}: {_yaml_escape(str(value))}")

    def emit(indent: int, obj: object) -> None:
        prefix = " " * indent
        if isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(v, dict):
                    lines.append(f"{prefix}{k}:")
                    emit(indent + 2, v)
                elif isinstance(v, list):
                    if not v:
                        lines.append(f"{prefix}{k}: []")
                        continue
                    lines.append(f"{prefix}{k}:")
                    for item in v:
                        if isinstance(item, dict):
                            first = True
                            for ik, iv in item.items():
                                dash = "- " if first else "  "
                                first = False
                                if isinstance(iv, (dict, list)):
                                    lines.append(f"{prefix}  {dash}{ik}:")
                                    emit(indent + 4, iv)
                                else:
                                    rendered = (
                                        _yaml_escape(str(iv))
                                        if not isinstance(iv, (int, float, bool))
                                        and iv is not None
                                        else ("null" if iv is None else str(iv))
                                    )
                                    lines.append(f"{prefix}  {dash}{ik}: {rendered}")
                        else:
                            rendered = (
                                _yaml_escape(str(item))
                                if not isinstance(item, (int, float, bool))
                                and item is not None
                                else ("null" if item is None else str(item))
                            )
                            lines.append(f"{prefix}  - {rendered}")
                else:
                    emit_scalar(indent, k, v)
        elif isinstance(obj, list):
            for item in obj:
                lines.append(f"{prefix}- {_yaml_escape(str(item))}")

    emit(0, doc)
    return "\n".join(lines) + "\n"


def build_dictionary(raw_dir: Path, versao: str) -> dict:
    tabelas: dict[str, dict] = {}
    for txt in sorted(raw_dir.glob("*.txt")):
        tabela = table_name_from_filename(txt.name)
        campos = parse_metadata_file(txt)
        tabelas[tabela] = {
            "descricao": TABLE_DESCRIPTIONS.get(tabela, ""),
            "arquivo_cvm_meta": txt.name,
            "quantidade_campos": len(campos),
            "campos": campos,
        }

    return {
        "fonte": "cvm",
        "dataset": "inf_mensal_fidc",
        "versao_dicionario": versao,
        "data_geracao": date.today().isoformat(),
        "schema_fdw": "cvm_remote",
        "url_fonte": (
            "https://dados.cvm.gov.br/dados/FIDC/DOC/INF_MENSAL/META/"
            "meta_inf_mensal_fidc_txt.zip"
        ),
        "observacao": (
            "Gerado por scripts/parse_cvm_metadata.py a partir dos .txt brutos em "
            "docs/cvm-fidc/raw/<versao>/. Nao editar este arquivo manualmente -- "
            "ajustes editoriais vao em docs/cvm-fidc/dicionario.md."
        ),
        "tabelas": tabelas,
        "omissoes_observadas": KNOWN_OMISSIONS,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--versao",
        default="v5",
        help="Sufixo do diretorio em docs/cvm-fidc/raw/ (ex.: v5, v6).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_PATH,
        help="Caminho de saida do YAML (default: docs/cvm-fidc/dicionario.yaml).",
    )
    args = parser.parse_args()

    raw_dir = RAW_ROOT / args.versao
    if not raw_dir.is_dir():
        print(f"ERRO: diretorio nao encontrado: {raw_dir}", file=sys.stderr)
        print(
            "Baixe o zip da CVM, extraia para docs/cvm-fidc/raw/<versao>/ e rode de novo.",
            file=sys.stderr,
        )
        return 2

    doc = build_dictionary(raw_dir, args.versao)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(_render_yaml(doc), encoding="utf-8")

    total_fields = sum(t["quantidade_campos"] for t in doc["tabelas"].values())
    print(
        f"OK: {len(doc['tabelas'])} tabelas / {total_fields} campos -> {args.output}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
