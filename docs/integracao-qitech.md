# Integracao QiTech (Singulare) — inventario + arquitetura

## Contexto

QiTech e o novo nome da Singulare — administradora/custodiante de FIDC que
o GR integra para ingerir dados canonicos (posicoes, movimentacoes, cadastros).
A base URL `api-portal.singulare.com.br` continua ativa durante a transicao
de marca.

O sistema e multi-tenant: cada tenant tem seu proprio contrato com a QiTech
e portanto suas proprias credenciais, URL base e ambiente (sandbox vs
producao). Tudo vive em `tenant_source_config` cifrado por envelope
(Fernet). Zero hardcode.

## Localizacao

- Adapter: [backend/app/modules/integracoes/adapters/admin/qitech/](../backend/app/modules/integracoes/adapters/admin/qitech/)
- Enum: `SourceType.ADMIN_QITECH` = `"admin:qitech"`
- Catalogo: linha seedada via migration [b1d9a2f7c4e8](../backend/alembic/versions/b1d9a2f7c4e8_seed_qitech_source_catalog.py)

## Auth — HTTP Basic para emissao + `x-api-key` para uso

Auth em dois passos **com headers diferentes**:

1. **Emissao do token** — HTTP Basic com `base64(client_id:client_secret)`.
2. **Chamadas subsequentes** — header customizado `x-api-key: <apiToken>`.

A QiTech/Singulare **nao usa** `Authorization: Bearer` apesar do token
parecer OAuth. Validado em 2026-04-24 contra
`/v2/netreport/report/market/outros-fundos/{data}`:

- `Authorization: Bearer <token>` → `500 {"message":"A solicitacao nao
  pode ser concluida."}` — mensagem generica, dificil de debugar.
- `x-api-key: <token>` → `200` + payload canonico.

Armadilha anti-debug conhecida — se algum dia um endpoint passar a
responder 500 generico depois de refactor, **primeiro suspeito** e o
header de auth.

O adapter cacheia o `apiToken` emitido em memoria por
`(tenant_id, environment)` — isolamento multi-tenant estrito.

### Endpoint de emissao

```
POST https://api-portal.singulare.com.br/v2/painel/token/api
Authorization: Basic <base64(client_id:client_secret)>
```

Sem body. O par `client_id` / `client_secret` vem de
`tenant_source_config.config` (cifrado por envelope Fernet).

### Resposta

```json
{ "apiToken": "0LfLwwwfRjn6tl5Ux6we_YwyVF0rszAz4_CqwtiWcZLvmyMuhq" }
```

Status code observado: **201 Created** (nao 200). Nosso parser aceita
qualquer 2xx que traga `apiToken`.

### Uso subsequente

```
GET /v2/netreport/report/market/{tipo-de-mercado}/{data}
x-api-key: <apiToken>
```

Emissao via `httpx.BasicAuth(client_id, client_secret)`; uso via
`request.headers["x-api-key"] = token` no `_ApiKeyAuth.async_auth_flow`
de `connection.py`.

### TTL

Nao confirmado pela QiTech — default assumido: **3600s** (1h), com skew
de refresh de 60s para evitar race conditions. Configuravel por tenant
via `token_ttl_seconds` no config.

## Inventario de endpoints (em construcao)

| Area | Metodo | Path | Status | Observacoes |
|---|---|---|---|---|
| Auth | POST | `/v2/painel/token/api` | **implementado** | Basic Auth → `apiToken` |
| Relatorios: Mercado | GET | `/v2/netreport/report/market/{tipo-de-mercado}/{data}` | **fetch implementado** | Ativos com quebra por carteira. Auth via `x-api-key` (nao Bearer). HTTP 400 com `{"relatórios":{}, "message":"Não há resultados..."}` e **dado valido** (tenant sem portfolio no mercado), tratado como sucesso-vazio pelo adapter. Parsing canonico pendente. |

### Tipos de mercado (path param `tipo-de-mercado`)

Valores literais do vendor, sempre lowercase com hifen quando multi-palavra.
Catalogo canonico vive em `reports.py::TIPOS_DE_MERCADO_CONHECIDOS` (23 tipos).

**Carteiras / ativos**

| Codigo | Descricao |
|---|---|
| `outros-fundos` | Outros fundos |
| `rf` | Renda fixa |
| `rv` | Renda variavel |
| `rv-opcoes` | RV opcoes |
| `rv-opcoes-flexiveis` | RV opcoes flexiveis |
| `rv-emprestimo-acoes` | RV emprestimo acoes |
| `rv-emprestimo-acoes-inadimplentes` | RV emprestimo acoes inadimplentes |
| `rf-fidc` | RF FIDC |
| `rf-compromissadas` | RF compromissadas |

**Derivativos e cambio**

| Codigo | Descricao |
|---|---|
| `futuros` | Futuros |
| `opcoes-futuro` | Opcoes futuro |
| `swap` | Swap |
| `termo` | Termo |
| `termo-rv` | Termo RV |
| `cambio` | Cambio |

**Tesouraria / contabeis**

| Codigo | Descricao |
|---|---|
| `tesouraria` | Tesouraria |
| `conta-corrente` | Conta corrente |
| `cpr` | CPR (Contas a Pagar e Receber) |
| `demonstrativo-caixa` | Demonstrativo caixa |
| `outros-ativos` | Outros ativos |
| `outros-emprestimos` | Outros emprestimos |

**Relatorios agregados**

| Codigo | Descricao |
|---|---|
| `rentabilidade` | Rentabilidade |
| `mec` | MEC (mapa evolutivo de cotas) |

*(tabela cresce conforme novos endpoints entrem. Cada endpoint novo
documenta schema de response + rate limit + mapping para modelo canonico.)*

## Modelo de config por tenant

`tenant_source_config.config` (decifrado) para `source_type=admin:qitech`:

```json
{
  "base_url": "https://api-portal.singulare.com.br",
  "client_id": "exemplo-client-id",
  "client_secret": "exemplo-client-secret",
  "token_ttl_seconds": 3600,
  "token_refresh_skew_seconds": 60
}
```

- **`base_url`** — opcional; default `https://api-portal.singulare.com.br`.
  Permite que um tenant aponte para homologacao sem tocar codigo.
- **`client_id`** / **`client_secret`** — obrigatorios. Emitidos pela
  QiTech ao tenant. Cifrados em repouso via envelope (Fernet).
- **`token_ttl_seconds`** / **`token_refresh_skew_seconds`** — opcionais.

**Retrocompat:** `QiTechConfig.from_dict` ainda aceita o formato antigo
`{"credentials": {"client_id": "...", "client_secret": "..."}}` por
seguranca — configs gravadas antes de 2026-04-24 continuam validas.
Top-level `client_id`/`client_secret` ganham prioridade sobre o dict aninhado.

## Arquitetura

```
adapters/admin/qitech/
├── __init__.py       docstring + mapa do pacote
├── version.py        ADAPTER_VERSION (semver)
├── config.py         QiTechConfig (dataclass frozen, from_dict)
├── endpoints.py      catalogo de (metodo, path) — relativo a base_url
├── errors.py         QiTechAdapterError + AuthError + HttpError
├── auth.py           get_api_token + cache TTL por (tenant_id, env)
├── connection.py     build_async_client(httpx.AsyncClient + _BearerAuth)
├── adapter.py        adapter_ping / adapter_sync (entrypoints do runner)
└── bootstrap.py      CLI para ping manual por tenant
```

Fluxo de uma request de dominio (futuro):

```
sync_runner.run_sync_one(tenant_id, ADMIN_QITECH)
   -> decrypt_config(tenant_source_config.config)
   -> adapter.adapter_sync(tenant_id, cfg_dict)
       -> QiTechConfig.from_dict(cfg_dict)
       -> build_async_client(tenant_id, env, config)
           -> _BearerAuth.async_auth_flow
               -> get_api_token(tenant_id, env, config)   ← cache ou POST
               -> Authorization: Bearer <token>
               -> yield request
               -> (se 401) invalidate + refetch + retry 1x
       -> client.get("/custody/...")  ← etl.py (ainda nao existe)
       -> map para canonico -> persist -> decision_log
```

## Tests

`backend/tests/modules/integracoes/adapters/qitech/`:

- **`test_auth.py`** — token fetch, cache TTL, isolamento por tenant,
  rejeicao em 401/5xx, payload sem `apiToken`.
- **`test_connection.py`** — bearer injection via MockTransport, retry
  automatico em 401.

Cobertura dos cenarios multi-tenant:
- Tenant A e tenant B batem o endpoint com credenciais diferentes → dois
  tokens distintos, nenhum contaminacao.
- Token expirado de tenant A nao afeta cache do tenant B.

## Roadmap

1. **[DONE]** auth + cache + ping → usuario cadastra credenciais pela UI e
   clica "Testar" → 200.
2. Primeiro endpoint de dominio (TBD com base no que o usuario priorizar).
   Criar mapper → modelo canonico → persist + decision_log.
3. Webhook receiver (se a QiTech emitir) — Fase 5 do plano geral.
