.PHONY: deps bootstrap setup seed reset-data doctor run-agent run-agent-docker run-mcp-docker smoke-test smoke-test-docker bake-build bake-push stop clean logs status

deps:
	bash scripts/install_deps.sh

bootstrap: deps setup

setup:
	bash scripts/setup.sh

seed:
	pip3 install -q -r scripts/requirements-seed.txt
	python3 scripts/seed_data.py

reset-data:
	bash scripts/reset_data.sh

doctor:
	bash scripts/doctor.sh

run-agent:
	python3 agent/main.py

run-agent-docker:
	docker compose --profile app run --rm agent

run-mcp-docker:
	docker compose --profile app run --rm mcp_server

smoke-test:
	python3 scripts/test_mvp_queries.py

smoke-test-docker:
	docker compose --profile app run --rm agent scripts/test_mvp_queries.py

bake-build:
	docker buildx bake -f deploy/docker-bake.hcl images

bake-push:
	docker buildx bake -f deploy/docker-bake.hcl release --push

stop:
	bash -c "docker compose down 2>/dev/null || docker-compose down"

clean:
	bash -c "docker compose down -v 2>/dev/null || docker-compose down -v"
	rm -rf infra/nginx/certs

logs:
	bash -c "docker compose logs -f 2>/dev/null || docker-compose logs -f"

status:
	bash -c "docker compose ps 2>/dev/null || docker-compose ps"
