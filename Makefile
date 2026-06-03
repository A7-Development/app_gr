.PHONY: help deploy deploy-check deploy-yes deploy-backend deploy-logs status

# Host de produção (VM26). Default usa o alias `gr-vm26` do ~/.ssh/config
# (resolve HostName 192.168.100.26 + User outstand + IdentityFile).
# Override: PROD_HOST=outstand@host make deploy
PROD_HOST ?= gr-vm26

# gr-deploy precisa de sudo (git pull em /opt/app_gr é de app_gr + systemctl
# restart). O user outstand tem sudo NOPASSWD pra gr-deploy/systemctl, então
# não há prompt de senha — mas o gr-deploy sem -y ainda pede confirmação.

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
	@echo "Override host: PROD_HOST=outstand@<host> make <target>"

deploy-check:
	@ssh $(PROD_HOST) sudo gr-deploy --check

deploy:
	@ssh -t $(PROD_HOST) sudo gr-deploy

deploy-yes:
	@ssh $(PROD_HOST) sudo gr-deploy -y

deploy-backend:
	@ssh -t $(PROD_HOST) sudo gr-deploy --no-build

deploy-logs:
	@ssh $(PROD_HOST) "tail -100 /var/log/gr-api/deploy.log"

status:
	@ssh $(PROD_HOST) "systemctl status gr-api gr-frontend --no-pager | head -25"
