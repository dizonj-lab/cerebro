# CEREBRO — container and Kubernetes workflow.
#
#   make up        build images, load them into the cluster, deploy, wait
#   make urls      how to reach it
#   make down      remove everything
#
# Kubernetes is the primary target. `make compose-up` is the simpler fallback.

SHELL := /bin/bash
API_IMAGE := cerebro-api:0.1.0
WEB_IMAGE := cerebro-web:0.1.0
NS := cerebro

# Host port for the app. Override when something else already owns it:
#   make compose-up WEB_PORT=3100
#   make port-forward WEB_PORT=3100
# For compose you can instead set CEREBRO_WEB_PORT in a .env file (see
# .env.example), which compose picks up on its own.
WEB_PORT ?= 3000

.DEFAULT_GOAL := help
.PHONY: help build load deploy up down status logs wait urls port-forward validate diagrams \
        compose-up compose-down compose-logs test-backend test-e2e

help: ## Show available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-16s\033[0m %s\n", $$1, $$2}'

## --- Kubernetes ------------------------------------------------------------

build: ## Build both container images
	docker build -t $(API_IMAGE) backend
	docker build -t $(WEB_IMAGE) frontend

load: ## Make the built images visible to the cluster
	./scripts/k8s-load-images.sh

deploy: ## Apply the manifests
	kubectl apply -k k8s/

wait: ## Block until the workloads are ready
	kubectl -n $(NS) rollout status statefulset/cerebro-postgres --timeout=180s
	kubectl -n $(NS) rollout status deployment/cerebro-api --timeout=180s
	kubectl -n $(NS) rollout status deployment/cerebro-web --timeout=180s

up: build load deploy wait urls ## Build, load, deploy and wait

urls: ## Show how to reach the running app
	@echo
	@echo "  make port-forward   ->  http://localhost:$(WEB_PORT)   (no extra setup)"
	@echo "  With ingress-nginx  ->  http://cerebro.localhost"
	@echo

port-forward: ## Serve the app locally without an ingress controller (WEB_PORT=3000)
	@echo "App on http://localhost:$(WEB_PORT) — fully functional, including sign-in:"
	@echo "the web pod proxies /api to the API service."
	kubectl -n $(NS) port-forward svc/cerebro-web $(WEB_PORT):3000

status: ## Show workload status
	kubectl -n $(NS) get pods,svc,ingress,pvc

logs: ## Tail API and web logs
	kubectl -n $(NS) logs -l app.kubernetes.io/part-of=cerebro --tail=100 -f --max-log-requests=6

down: ## Delete everything, including the database volume
	-kubectl delete -k k8s/
	-kubectl delete pvc -n $(NS) -l app.kubernetes.io/name=cerebro-postgres

validate: ## Render and schema-check the manifests (no cluster needed)
	@kubectl kustomize k8s/ > /dev/null && echo "kustomize render: OK"
	@if command -v kubeconform >/dev/null 2>&1; then \
		kubectl kustomize k8s/ | kubeconform -strict -summary -kubernetes-version 1.31.0; \
	else \
		echo "SKIPPED schema validation: kubeconform is not installed."; \
		echo "  Only the kustomize render was checked above."; \
		echo "  Install it for a full offline schema check:"; \
		echo "    https://github.com/yannh/kubeconform#installation"; \
		echo "  Or, with a cluster reachable:  kubectl apply -k k8s/ --dry-run=server"; \
	fi

## --- Docker Compose (simpler alternative) ----------------------------------

compose-up: ## Run the whole stack with docker compose (WEB_PORT=3000)
	CEREBRO_WEB_PORT=$(WEB_PORT) docker compose up --build -d
	@echo "App on http://localhost:$(WEB_PORT)"

compose-down: ## Stop compose and remove the database volume
	docker compose down -v

compose-logs: ## Tail compose logs
	docker compose logs -f

## --- Architecture ----------------------------------------------------------

diagrams: ## Regenerate the C4 diagrams from the Structurizr model
	structurizr.sh validate -w architecture/structurizr/workspace.dsl
	structurizr.sh export -w architecture/structurizr/workspace.dsl \
		-f mermaid -o architecture/diagrams
	@cd architecture/diagrams && for f in structurizr-*.mmd; do \
		mv "$$f" "$${f#structurizr-}"; \
	done
	@cd architecture/diagrams && for f in *.mmd; do \
		mmdc -i "$$f" -o "$${f%.mmd}.png" -b white -w 2200; \
	done
	@echo "Regenerated. Requires structurizr-cli and @mermaid-js/mermaid-cli on PATH."

## --- Tests -----------------------------------------------------------------

test-backend: ## Run backend tests (needs a local PostgreSQL)
	cd backend && . .venv/bin/activate && pytest -q

test-e2e: ## Run end-to-end tests against an already-running stack (WEB_PORT=3000)
	cd frontend && E2E_BASE_URL=http://localhost:$(WEB_PORT) npm run test:e2e
