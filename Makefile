SHELL := /bin/bash

ROOT ?= $(WORKSPACE)
TASK ?=
MODEL ?=
HARNESS_ARGS ?=

.PHONY: help up down logs pull chat harness supervise dashboard test hygiene gate \
	install hooks clean

help:
	@echo "Qaymark — local AI code-generation factory"
	@echo
	@echo "  make up                        Start Ollama + Open WebUI and pull the model"
	@echo "  make down                      Stop the stack"
	@echo "  make logs                      Follow container logs"
	@echo "  make install                   Install the qaymark CLI (pip install -e .)"
	@echo "  make hooks                     Enable the pre-commit hygiene hook"
	@echo "  make chat PROMPT=\"...\"          One-off prompt via the Ollama API"
	@echo "  make harness TASK=\"...\" \\"
	@echo "       WORKSPACE=/path/to/dir     Run the guardrailed code harness once"
	@echo "  make supervise TASK=\"...\" \\"
	@echo "       WORKSPACE=/path/to/dir     Build then rebuild on every dashboard feedback"
	@echo "  make dashboard ROOT=/path       Serve the signed-in control plane"
	@echo "  make test                      Run the harness unit tests"
	@echo "  make gate                      Run the strict hygiene gate on the repo"
	@echo "  make hygiene PATH_ARG=dir      Run slop-be-gone against a path (needs sbg)"
	@echo "  make clean                     Remove the tool cache"

up:
	./scripts/bootstrap.sh

down:
	docker compose down --remove-orphans

logs:
	docker compose logs -f

pull:
	docker compose exec -T ollama ollama pull "$(if $(MODEL),$(MODEL),qwen2.5-coder:3b)"

chat:
	@test -n "$(PROMPT)" || { echo "Usage: make chat PROMPT=\"your prompt\""; exit 1; }
	./scripts/chat.sh "$(PROMPT)"

harness:
	@test -n "$(TASK)" || { echo "Usage: make harness TASK=\"...\" WORKSPACE=/path"; exit 1; }
	@test -n "$(WORKSPACE)" || { echo "Set WORKSPACE=/path/to/dir"; exit 1; }
	python3 scripts/code_harness.py \
		--task "$(TASK)" \
		--workspace "$(WORKSPACE)" \
		$(if $(MODEL),--model $(MODEL),) \
		$(HARNESS_ARGS)

supervise:
	@test -n "$(TASK)" || { echo "Usage: make supervise TASK=\"...\" WORKSPACE=/path"; exit 1; }
	@test -n "$(WORKSPACE)" || { echo "Set WORKSPACE=/path/to/dir"; exit 1; }
	python3 scripts/code_harness.py \
		--task "$(TASK)" \
		--workspace "$(WORKSPACE)" \
		--supervise \
		$(if $(MODEL),--model $(MODEL),) \
		$(HARNESS_ARGS)

dashboard:
	@test -n "$(ROOT)" || { echo "Usage: make dashboard ROOT=/path"; exit 1; }
	DASHBOARD_PASSWORD="$${DASHBOARD_PASSWORD:?set DASHBOARD_PASSWORD}" \
	python3 scripts/dashboard.py "$(ROOT)" $(if $(PORT),--port $(PORT),)

test:
	PYTHONPATH="$(CURDIR)" python3 -m unittest discover -s tests -t . -v

hygiene:
	@test -n "$(PATH_ARG)" || { echo "Usage: make hygiene PATH_ARG=dir"; exit 1; }
	python3 -m sbg.cli check "$(PATH_ARG)" --strict --manifest "$(CURDIR)/sbg_manifest.json"

gate:
	python3 scripts/hygiene_gate.py --path "$(CURDIR)"

install:
	pip install -e .

hooks:
	git config core.hooksPath .githooks
	@echo "pre-commit hygiene hook enabled (core.hooksPath = .githooks)"

clean:
	rm -rf "$${HARNESS_CACHE_DIR:-$$HOME/.cache/local-coding-harness}"
