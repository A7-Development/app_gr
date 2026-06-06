"""Re-rotula o banco/layout do bronze CNAB pelo HEADER (nao pelo nome).

Os arquivos foram ingeridos com `banco` derivado de um detector antigo que
mapeava codigos errado (274 -> "grafeno", 310 -> "desconhecido"). O header CNAB
declara a identidade real (274=BMP, 310=Vortx). Este oneshot re-roda o detector
ATUAL (`detectar_banco`, header-based) sobre o `conteudo` de cada
`wh_cnab_raw_arquivo` e corrige `banco` + `layout` onde divergir.

Header-driven e idempotente: re-rodar nao muda nada se ja estiver certo. Nao
reprocessa nem toca silver -- so corrige o rotulo do bronze.

Uso:
    python -m scripts.relabel_cnab_banco              # DRY-RUN (todos os tenants)
    python -m scripts.relabel_cnab_banco --apply      # aplica os updates
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.integracoes.adapters.cobranca.detect import detectar_banco
from app.warehouse.cnab_raw_arquivo import BANCO_DESCONHECIDO, CnabRawArquivo

_LAYOUT_DESCONHECIDO = "desconhecido"


async def _main(apply: bool) -> None:
    mudancas: Counter[str] = Counter()
    total = 0
    async with AsyncSessionLocal() as db:
        rows = (
            await db.execute(
                select(
                    CnabRawArquivo.id,
                    CnabRawArquivo.banco,
                    CnabRawArquivo.layout,
                    CnabRawArquivo.conteudo,
                )
            )
        ).all()
        total = len(rows)
        for rid, banco_atual, layout_atual, conteudo in rows:
            det = detectar_banco(conteudo)
            banco_novo = det.banco if det else BANCO_DESCONHECIDO
            layout_novo = det.layout if det else _LAYOUT_DESCONHECIDO
            if banco_novo == banco_atual and layout_novo == layout_atual:
                continue
            mudancas[f"{banco_atual}/{layout_atual} -> {banco_novo}/{layout_novo}"] += 1
            if apply:
                obj = await db.get(CnabRawArquivo, rid)
                if obj is not None:
                    obj.banco = banco_novo
                    obj.layout = layout_novo
        if apply:
            await db.commit()

    print(f"[relabel] arquivos={total} mode={'APPLY' if apply else 'DRY-RUN'}")
    if not mudancas:
        print("  nenhuma mudanca (tudo ja correto).")
    for k, v in sorted(mudancas.items(), key=lambda kv: kv[1], reverse=True):
        print(f"  {v:5d}  {k}")
    if not apply and mudancas:
        print("[relabel] DRY-RUN — nada gravado. Use --apply para aplicar.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-rotula banco/layout do bronze CNAB (header-based)")
    parser.add_argument("--apply", action="store_true", help="Aplica os updates (sem isso, DRY-RUN).")
    args = parser.parse_args()
    asyncio.run(_main(args.apply))


if __name__ == "__main__":
    main()
