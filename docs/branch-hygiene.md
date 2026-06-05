# Higiene de branches & worktrees — App GR

> Guia operacional para sessões paralelas (Claude Code e humanos) no monorepo
> `app_gr`. Criado em 2026-06-05 após dois incidentes evitáveis (ver §0).
> **Objetivo:** nunca mais reverter trabalho alheio num merge, nunca editar o
> checkout errado, e manter o número de branches sob controle.

---

## 0. Por que este guia existe (dois sustos reais, 2026-06-05)

1. **Merge de base velha (quase-reversão).** Um branch foi criado a partir de um
   `origin/main` antigo. Enquanto a sessão trabalhava, outras sessões mergearam
   (refactor do `FilterBar`, conciliação). Ao tentar mergear, o diff `origin/main
   ..HEAD` mostrava **8 arquivos** — o branch teria **revertido** o trabalho das
   outras sessões. Pego na conferência do diff, refeito com branch fresco +
   cherry-pick (diff de 1 arquivo).
2. **Edição no checkout errado.** Arquivos de backend foram escritos em
   `C:\app_gr` (checkout do `main`) em vez da worktree da sessão, ficando como
   alterações soltas na working tree do `main`. Corrigido movendo para a worktree
   e restaurando o checkout principal.

Ambos têm a mesma raiz: **muitas sessões + muitas worktrees + branches de vida
longa**. As regras abaixo eliminam os dois.

---

## 1. As 4 regras de ouro (válidas para toda sessão)

### Regra 1 — Branch sempre de `origin/main` FRESCO
```bash
git fetch origin main
git switch -c <nome-do-branch> origin/main
```
Nunca crie branch a partir de outro branch, de um `main` local possivelmente
desatualizado, ou de uma base "que já estava aqui". Sempre `origin/main` recém-
buscado.

### Regra 2 — Antes de TODO merge, confira o diff (3 pontos)
```bash
git fetch origin main
git diff --stat origin/main...HEAD     # 3 pontos = a partir do merge-base
```
O resultado tem que listar **apenas os arquivos que você mexeu**. Se aparecer
arquivo de outra área (ex.: `FilterBar`, `conciliacao_*`), seu branch está
**desatualizado** e o merge vai **reverter** o trabalho dos outros.

**Conserto:** rebase na base atual e re-confira.
```bash
git rebase origin/main
git diff --stat origin/main...HEAD     # agora deve ser só o seu
```
> `...` (três pontos) compara contra o **merge-base** — é o que importa.
> `..` (dois pontos) pode enganar quando a base divergiu.

### Regra 3 — Uma sessão = uma worktree = um branch
- Trabalhe **somente** dentro da worktree da sua sessão
  (`C:\app_gr\.claude\worktrees\<sessao>`).
- **Nunca** edite arquivos em `C:\app_gr` diretamente — esse é o checkout do
  `main`, compartilhado. Editar lá deixa lixo na working tree do `main` e pode
  ser commitado por engano.
- Confira onde você está antes de editar: `git rev-parse --show-toplevel`.

### Regra 4 — Merge = squash + delete imediato
```bash
gh pr merge <n> --squash --delete-branch
```
Se o `--delete-branch` falhar porque o `main` está em outra worktree, apague o
remoto na mão: `git push origin --delete <branch>`. PRs pequenos e curtos.

---

## 2. Como saber se um branch "pode ser deletado"

**Não use `git branch --merged`.** Com squash-merge o commit ganha um SHA novo,
então o branch original aparece como "não mergeado" mesmo já estando no `main`.

Use **um** destes critérios confiáveis:

| Critério | Comando | "Pode deletar" quando |
|---|---|---|
| Estado do PR | `gh pr view <branch> --json state` | `state == "MERGED"` |
| Conteúdo no main | `git diff origin/main...<branch>` | saída **vazia** (tudo já está no main) |

E **nunca** delete um branch que está **checked-out numa worktree ativa** — isso
quebra a sessão que o usa. Confira com `git worktree list`.

---

## 3. Procedimento de limpeza (rodar com as sessões FECHADAS)

> Faça com calma, com dry-run, e **só depois** que as sessões paralelas
> terminaram. Classifique cada branch em 3 baldes.

### Inventário
```bash
git fetch --prune                                 # remove refs remotos mortos
git worktree list                                 # quais worktrees existem
gh pr list --state open --limit 50 --json number,headRefName,title

# Para cada branch remoto, ver se o conteúdo já está no main:
for b in $(git ls-remote --heads origin | sed 's#.*refs/heads/##'); do
  if [ -z "$(git diff origin/main...origin/$b 2>/dev/null)" ]; then
    echo "[mergeado]  $b"
  else
    echo "[tem trabalho fora do main]  $b"
  fi
done
```

### Os 3 baldes
- **Balde A — mergeado + sem worktree ativa → deletar.**
  ```bash
  git branch -D <b> 2>/dev/null
  git push origin --delete <b>
  ```
- **Balde B — mergeado mas checked-out numa worktree → fechar a worktree antes.**
  ```bash
  git worktree remove <path>        # fecha a worktree
  git branch -D <b> && git push origin --delete <b>
  ```
- **Balde C — tem trabalho fora do main (WIP/stale) → NÃO deletar sem confirmar
  com o dono.** Branch antigo sem PR pode estar superseded ou pode ser trabalho
  vivo. Pergunte antes.

### Prune final
```bash
git fetch --prune
git worktree prune                  # remove registros de worktrees fantasma
git remote prune origin
```

---

## 4. Worktrees — disciplina

- Uma worktree por sessão, sob `C:\app_gr\.claude\worktrees\<nome>`.
- Ao terminar a sessão **e** mergear o branch: `git worktree remove <path>`.
- `git worktree list` deve refletir só as sessões realmente ativas + o checkout
  `C:\app_gr` (main).
- Não criar worktree sobre um branch de outra sessão.

---

## 5. Checklist rápido (cole no início/fim da sessão)

**Início:**
- [ ] `git fetch origin main` e branch novo de `origin/main` (Regra 1).
- [ ] Estou na worktree da sessão? (`git rev-parse --show-toplevel`).

**Antes de mergear:**
- [ ] `git fetch origin main` + `git diff --stat origin/main...HEAD` lista **só
      meus arquivos**? (Regra 2). Se não, `git rebase origin/main`.
- [ ] Build/lint verdes.

**Depois de mergear:**
- [ ] `gh pr merge --squash --delete-branch` (ou apagar remoto na mão).
- [ ] `git worktree remove` quando a sessão fechar.
