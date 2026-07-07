# Strata Collector

Agente de coleta de arquivos da plataforma Strata ("forwarder"). Roda como
**servico do Windows** no servidor do cliente, vigia pastas configuradas
remotamente e empurra arquivos novos (CNAB, XML, zips diarios) por **HTTPS
outbound** para o File Gateway (`/api/v1/filedrop/upload`).

Principios (plano Landing Zone Multi-tenant, CLAUDE.md §sobre filedrop):

- **O agente e burro.** Pastas vigiadas, globs, labels e intervalo moram na
  `watch_config` da credencial (tabela `agent_credential`) e chegam via
  `GET /filedrop/ping`. Trocar a politica de coleta de um cliente = editar a
  config no Strata; nada muda na maquina do cliente.
- **Arquivos sobem como estao.** Cliente que zipa por dia tem o `.zip`
  enviado intacto (marque `container: "zip"` na watch pra sinalizar o
  consumidor no servidor). O agente nunca descompacta.
- **Trafego 100% outbound.** Nunca entramos na LAN do cliente; o agente
  empurra. Fronteira de confianca = o gateway.
- **Dedup em duas camadas.** State local (`state.json`) evita reenvio; o
  servidor deduplica por sha256 dentro de (tenant, source_label) — perder o
  state local e inofensivo (reenvio volta como `duplicate`).
- Arquivo **modificado** (CNAB regravado, zip do dia que cresceu) e detectado
  por size+mtime e re-enviado — vira NOVA linha no registry (sha novo),
  preservando as duas versoes no bronze.
- Arquivo "quente" (mtime < `min_age_seconds`, default 60s) espera o proximo
  ciclo — nao sobe CNAB pela metade.

## Layout na maquina do cliente

| Caminho | Conteudo |
|---|---|
| `C:\Program Files\Strata Collector\strata-collector.exe` | binario (unico, sem dependencias) |
| `%PROGRAMDATA%\StrataCollector\config.json` | `server_url` + `token` (escrito pelo instalador) |
| `%PROGRAMDATA%\StrataCollector\state.json` | o que ja subiu (path -> size/mtime/sha/status) |
| `%PROGRAMDATA%\StrataCollector\logs\collector.log` | log (rotacao simples em ~5MB) |

## CLI

```
strata-collector run              roda em console (debug)
strata-collector run -once        executa UM ciclo e sai (smoke test)
strata-collector run -config X    config.json explicito
strata-collector install|uninstall|start|stop    controla o servico Windows
strata-collector version
```

## Build

Requer Go >= 1.26 (sem CGO, sem toolchain extra):

```
cd collector
go build -ldflags="-s -w" -o strata-collector.exe .
```

Cross-compile de qualquer SO: `GOOS=windows GOARCH=amd64 go build ...`.

## Instalador

[`installer/strata-collector.iss`](./installer/strata-collector.iss) (Inno
Setup 6). O wizard pede **apenas** URL do servidor + token; escreve o
`config.json`, registra o servico e inicia. Compilar:

```
go build -ldflags="-s -w" -o strata-collector.exe .
ISCC installer\strata-collector.iss
# -> installer/Output/StrataCollectorSetup-<versao>.exe
```

**Assinatura de codigo:** o setup/exe sem assinatura dispara SmartScreen no
Windows. Para distribuicao a clientes, assinar com certificado OV/EV
(decisao de compra pendente — ver memoria do projeto).

## Provisionamento de um cliente novo

1. Criar `agent_credential` para o tenant (token e exibido UMA vez):
   token plaintext `strata_agt_*` -> guarda-se so o sha256.
2. Definir `watch_config`, ex.:

   ```json
   {
     "scan_interval_minutes": 5,
     "watches": [
       {"path": "C:/Bitfin/Retorno", "glob": "*.RET", "source_label": "cobranca_cnab"},
       {"path": "C:/Bitfin/XML", "glob": "*.zip", "source_label": "bitfin_xml_operacoes", "container": "zip"}
     ]
   }
   ```

3. Rodar o instalador na maquina do cliente com URL + token.
4. Conferir heartbeat (`agent_credential.last_seen_at` + `agent_version`) e
   as primeiras linhas em `file_landing`.

Revogacao: `revoked_at` na credencial — o agente passa a receber 401 e loga
erro critico; nenhum acesso a infra do cliente e necessario.

## Versionamento

`Version` em [`main.go`](./main.go) (enviada em `X-Agent-Version`, visivel em
`agent_credential.agent_version`). Bump a cada release + `AppVersion` no
`.iss`.
