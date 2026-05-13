.PHONY: help deploy deploy-check deploy-yes deploy-backend deploy-logs status

# Host de produção (.26 dentro da LAN/VPN). Override: PROD_HOST=root@host make deploy
PROD_HOST ?= root@192.168.100.26

help:
	@echo "GR app deploy targets — wrappers de gr-deploy em $(PROD_HOST)"
	@echo ""
	@echo "  make deploy-check     dry-run: lista commits, arquivos, plano (não aplica)"
	@echo "  make deploy           aplica com prompt de confirmação"
	@echo "  make deploy-yes       aplica direto, sem prompt (CI / quick fix)"
	@echo "  make deploy-backend   backend-only (skip rebuild do frontend)"
	@echo "  make deploy-logs      tail do log de deploys no servidor"
	@echo "  make status           status systemd dos services gr-api / gr-frontend"
	@echo ""
	@echo "Pré-requisito: SSH com chave configurado para $(PROD_HOST)."
	@echo "Override host: PROD_HOST=root@<host> make <target>"

deploy-check:
	@ssh $(PROD_HOST) gr-deploy --check

deploy:
	@ssh -t $(PROD_HOST) gr-deploy

deploy-yes:
	@ssh $(PROD_HOST) gr-deploy -y

deploy-backend:
	@ssh -t $(PROD_HOST) gr-deploy --no-build

deploy-logs:
	@ssh $(PROD_HOST) "tail -100 /var/log/gr-api/deploy.log"

status:
	@ssh $(PROD_HOST) "systemctl status gr-api gr-frontend --no-pager | head -25"
