#!/usr/bin/env bash
# gr-deploy — atualiza app_gr a partir de origin/main
# Uso: gr-deploy [--check|-n] [--no-build] [--yes|-y]
# Politica: NUNCA roda alembic; apenas avisa se tem migration nova.
#
# Deploy idempotente: pull do origin/main, opcional pip/npm install,
# build de frontend se necessario, restart de servico afetado, smoke test.
#
# Fonte versionada em scripts/ops/gr-deploy.sh do repo (single source of truth).
# Copia operacional em /usr/local/bin/gr-deploy. Para sincronizar:
#   sudo install -m 0755 /opt/app_gr/scripts/ops/gr-deploy.sh /usr/local/bin/gr-deploy

set -euo pipefail

REPO=/opt/app_gr
USR=app_gr
LOG=/var/log/gr-api/deploy.log

CHECK=0; NO_BUILD=0; YES=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -n|--check)   CHECK=1 ;;
    --no-build)   NO_BUILD=1 ;;
    -y|--yes)     YES=1 ;;
    -h|--help)
      sed -n '2,5p' "$0" | sed 's/^# //'
      exit 0 ;;
    *) echo "flag desconhecida: $1" >&2; exit 1 ;;
  esac
  shift
done

[[ $EUID -eq 0 ]] || { echo 'precisa ser root (pra systemctl)' >&2; exit 1; }

# log everything
exec > >(tee -a "$LOG") 2>&1
echo
echo '=================================='
echo "gr-deploy @ $(date -Iseconds)"
echo '=================================='

# Falha visivel: trap que imprime mensagem ALTA quando o script morre.
# Sem isso, com `set -e` o script simplesmente exit 1 e o user pode pensar
# que so um warning passou. O trap garante "ERRO" na tela em qualquer falha.
fail() {
  local code=$?
  echo
  echo '#####################################################'
  echo "# ERRO: gr-deploy abortou (exit $code) em linha $1"
  echo '# Servico NAO foi restartado. Build (se houve) pode estar corrompida.'
  echo "# Log completo: $LOG"
  echo '#####################################################'
  exit "$code"
}
trap 'fail $LINENO' ERR

echo
echo '==> git fetch origin main'
sudo -u $USR git -C $REPO fetch origin main --quiet

OLD=$(sudo -u $USR git -C $REPO rev-parse HEAD)
NEW=$(sudo -u $USR git -C $REPO rev-parse origin/main)

if [[ "$OLD" == "$NEW" ]]; then
  echo "OK: ja em $OLD — nada a fazer"
  exit 0
fi

echo
echo "==> commits a aplicar (${OLD:0:7}..${NEW:0:7}):"
sudo -u $USR git -C $REPO log --oneline "$OLD..$NEW"
echo
echo '==> arquivos alterados:'
sudo -u $USR git -C $REPO diff --stat "$OLD..$NEW" | tail -30

CHANGED=$(sudo -u $USR git -C $REPO diff --name-only "$OLD..$NEW")
echo "$CHANGED" | grep -qE '^backend/(pyproject\.toml|uv\.lock)$'      && PY=1     || PY=0
echo "$CHANGED" | grep -qE '^frontend/(package\.json|package-lock\.json)$' && NPM=1  || NPM=0
echo "$CHANGED" | grep -qE '^frontend/'                                   && FRONT=1  || FRONT=0
echo "$CHANGED" | grep -qE '^backend/'                                    && BACK=1   || BACK=0
echo "$CHANGED" | grep -qE '^backend/alembic/versions/'                   && ALEMBIC=1 || ALEMBIC=0

[[ $NO_BUILD == 1 ]] && BUILD=0 || BUILD=$FRONT

echo
echo '==> plano:'
printf '   %-13s %s\n' 'pip install:' "$([[ $PY     == 1 ]] && echo YES || echo skip)"
printf '   %-13s %s\n' 'npm install:' "$([[ $NPM    == 1 ]] && echo YES || echo skip)"
printf '   %-13s %s\n' 'npm build:'   "$([[ $BUILD  == 1 ]] && echo YES || echo skip)"
printf '   %-13s %s\n' 'restart:'     "$([[ $BACK   == 1 ]] && echo -n 'gr-api '; [[ $BUILD == 1 ]] && echo gr-frontend; [[ $BACK == 0 && $BUILD == 0 ]] && echo skip)"

if [[ $ALEMBIC == 1 ]]; then
  echo
  echo '#####################################################'
  echo '# ATENCAO: novas migrations alembic detectadas:'
  echo "$CHANGED" | grep '^backend/alembic/versions/' | sed 's/^/#   /'
  echo '# POLITICA: NAO rodar automaticamente. Confirmar com Ricardo.'
  echo '#####################################################'
fi

if [[ $CHECK == 1 ]]; then
  echo
  echo '(dry-run, nada aplicado)'
  exit 0
fi

if [[ $YES == 0 ]]; then
  echo
  read -rp 'Aplicar? [y/N] ' ans </dev/tty
  [[ "$ans" =~ ^[Yy]$ ]] || { echo 'abortado'; exit 1; }
fi

# stash override + ff merge + pop
echo
echo '==> merge'
STASHED=0
if ! sudo -u $USR git -C $REPO diff --quiet -- frontend/next.config.mjs; then
  sudo -u $USR git -C $REPO stash push -m 'gr-deploy:next.config' -- frontend/next.config.mjs
  STASHED=1
fi
sudo -u $USR git -C $REPO merge --ff-only origin/main
if [[ $STASHED == 1 ]]; then
  if ! sudo -u $USR git -C $REPO stash pop; then
    echo 'ERRO: stash pop conflitou — resolver manualmente em /opt/app_gr'
    exit 1
  fi
fi

if [[ $PY == 1 ]]; then
  echo; echo '==> pip install'
  sudo -u $USR $REPO/backend/.venv/bin/pip install -e "$REPO/backend[dev]" --quiet
fi

if [[ $NPM == 1 ]]; then
  echo; echo '==> npm install'
  sudo -u $USR -- bash -lc "cd $REPO/frontend && npm install --silent"
fi

if [[ $BUILD == 1 ]]; then
  echo; echo '==> npm run build'
  # Saida completa vai pro $LOG via tee global. Aqui mostramos tudo no stdout
  # tambem (sem `| tail -10`) pra que erros de lint/typecheck/build apareçam
  # visiveis na sessao interativa. Antes, com tail -10, o output util era
  # cortado e a falha passava despercebida — processo antigo continuava
  # rodando, novo build nunca era servido. Ver fix de 2026-05-20.
  sudo -u $USR -- bash -lc "cd $REPO/frontend && NODE_ENV=production npm run build"

  # Defesa em profundidade: build pode ter exit 0 com .next/ incompleto
  # em casos patologicos (cancelado por sinal entre stages, OOM no final).
  # BUILD_ID e escrito como ultimo passo de `next build` — sua presenca
  # e o unico sinal confiavel de "build terminou".
  if [[ ! -s $REPO/frontend/.next/BUILD_ID ]]; then
    echo
    echo '#####################################################'
    echo '# ERRO: build terminou sem BUILD_ID em .next/'
    echo '# Provavel build interrompida/parcial. NAO restartando frontend.'
    echo "# Investigar: ls -la $REPO/frontend/.next/ ; tail -200 $LOG"
    echo '#####################################################'
    exit 1
  fi
fi

# restart
echo; echo '==> systemctl restart'
declare -a SVCS=()
[[ $BACK  == 1 ]] && SVCS+=(gr-api)
[[ $BUILD == 1 ]] && SVCS+=(gr-frontend)
if [[ ${#SVCS[@]} -gt 0 ]]; then
  systemctl restart "${SVCS[@]}"
  sleep 4
  for s in "${SVCS[@]}"; do printf '   %-15s %s\n' "$s" "$(systemctl is-active $s)"; done
fi

# smoke
echo; echo '==> smoke test'
curl -sI --max-time 8 https://callback.strataai.com.br/health | head -1 || echo '(callback n/a — talvez NAT loopback; teste do workstation)'

echo
echo "OK: ${OLD:0:7} -> ${NEW:0:7}"
