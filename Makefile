.PHONY: setup web discover collect check up down logs docker-discover docker-collect
ARGS ?=
.PHONY: annotate
annotate:
	uv run --locked python scripts/run_annotation.py
.PHONY: youtube-labeling youtube-validation
youtube-labeling:
	uv run --locked python scripts/youtube/validate_comments.py prepare $(ARGS)
youtube-validation:
	uv run --locked python scripts/youtube/validate_comments.py evaluate $(ARGS)
COMPOSE = docker compose $(if $(filter 1,$(GPU)),-f compose.yaml -f compose.gpu.yaml,)
.PHONY: classify docker-classify classify-wykop docker-classify-wykop
classify:
	uv run --locked python scripts/classify_comments.py $(ARGS)
docker-classify:
	$(COMPOSE) run --rm classifier scripts/classify_comments.py $(ARGS)
classify-wykop:
	uv run --locked python scripts/wykop/classify_entries.py $(ARGS)
docker-classify-wykop:
	$(COMPOSE) run --rm classifier scripts/wykop/classify_entries.py $(ARGS)
setup:
	uv sync --locked
web:
	uv run --locked python scripts/run_web.py
discover:
	uv run --locked python scripts/youtube/discover_videos.py $(ARGS)
collect:
	uv run --locked python scripts/youtube/collect_comments.py $(ARGS)
check:
	uv run --locked ruff check .
	uv run --locked ruff format --check .
	uv run --locked python -m unittest discover -s tests
up:
	$(COMPOSE) up --build -d web
down:
	$(COMPOSE) down
logs:
	$(COMPOSE) logs -f web model-init
docker-discover:
	$(COMPOSE) run --rm --entrypoint /app/.venv/bin/python collector scripts/youtube/discover_videos.py $(ARGS)
docker-collect:
	$(COMPOSE) run --rm --entrypoint /app/.venv/bin/python collector scripts/youtube/collect_comments.py $(ARGS)
