up: ## Docker compose up, start container
	docker compose up -d --build
down: ## Docker compose down
	docker compose down --remove-orphans
shell: ## Shell into container
	docker compose exec rebalance-lnd sh
test: ## Run tests
	docker compose exec rebalance-lnd python -m unittest discover tests/ -v

.PHONY: help
help:
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

.DEFAULT_GOAL := help
