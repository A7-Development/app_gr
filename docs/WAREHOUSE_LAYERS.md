# Warehouse: camadas raw (bronze) → canônico (silver)

Referência detalhada para §13.2 do CLAUDE.md.

## Schema mínimo da raw

```python
class <Vendor>Raw<Entidade>(Base):
    __tablename__ = "wh_<vendor>_raw_<entidade>"
    # Partição lógica: tenant + tipo (se houver múltiplos endpoints) + data.
    tenant_id: UUID          # NOT NULL
    tipo: String             # NOT NULL (ex: "relatorio_posicao")
    data_referencia: Date    # NOT NULL
    # UQ composto: (tenant_id, tipo, data_referencia)

    payload: JSONB           # body cru, sem fragmentar
    payload_sha256: String(64)  # detecta re-fetch redundante
    http_status: Integer     # 200 ou 400-com-shape (sem dados)
    fetched_at: DateTime     # quando rodou o sync
    fetched_by_version: String  # versão do adapter (ex: "qitech_adapter_v1.0.0")
```

Raw **não usa o mixin `Auditable`** — ela é a fonte, não referencia outra fonte upstream.

## Fluxo ETL (orquestrado em `etl.py` do adapter)

```
fetch_<endpoint>()                  -> dict (response cru)
  -> grava 1 linha em wh_<vendor>_raw_<entidade>  (idempotente por UQ)
  -> map_<endpoint>(payload, ...)   -> list[dict]
  -> upsert em wh_<entidade>        (idempotente por tenant_id + source_id)
  -> registra entry em decision_log (sync metrics)
```

## Exceções (raw NÃO obrigatória)

- **Fontes federadas via postgres_fdw** (§13.1) — o "raw" é o DB federado em si.
- **`self_declared` / `internal_note`** — operador digita direto no canônico via UI.
- **Adapters legados pré-regra (ex.: Bitfin atual)** — dívida técnica documentada; retrofitar na próxima evolução significativa do adapter.

## Convenção de nomes

- Raw **inclui o vendor**: `wh_qitech_raw_outros_fundos`, `wh_serasa_refinho_raw_consulta`
- Canônico **não inclui vendor**: `wh_posicao_cota_fundo`, `wh_titulo`
