# speedrr maintenance tasks.
#
# Python work runs through `uv run` so the locked environment is used rather
# than whatever happens to be on PATH. Container and tower targets deliberately
# do not, since they must work before `uv sync` has run.
#
# `check` mirrors ci.yml's five steps (sync, lint, fmt-check, typecheck, test),
# in that order. Its recipe issues them as sequential $(MAKE) calls rather than
# as a prerequisite list: recipe lines within a single target always run one
# after another, regardless of -j, whereas prerequisites of one target are
# fair game for `make -j` to run concurrently. That matters here because each
# step invokes `uv run`, which implicitly syncs the venv against uv.lock -
# several of those firing at once against the same .venv would race.

SHELL         := bash
.SHELLFLAGS   := -o pipefail -c

IMAGE   ?= ghcr.io/Baine/speedrr
VERSION ?= dev
TOWER   ?= tower.local

.PHONY: help sync lint fmt fmt-check typecheck test check build load verify release clean

help: ## Show this help
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

sync: ## Install the locked dependencies
	uv sync --frozen

lint: ## Lint with ruff
	uv run ruff check .

fmt: ## Format with ruff
	uv run ruff format .

fmt-check: ## Fail if anything is unformatted
	uv run ruff format --check .

typecheck: ## Type check with pyright
	uv run pyright

test: ## Run the test suite
	uv run pytest -q

check: ## Everything CI runs, in the same order, sequentially
	$(MAKE) sync
	$(MAKE) lint
	$(MAKE) fmt-check
	$(MAKE) typecheck
	$(MAKE) test

build: ## Build the image (override VERSION to tag it)
	podman build -t $(IMAGE):$(VERSION) .

load: ## Side-load the locally built image onto tower
	@# `docker load`'s own "Loaded image: <name>" line is the only reliable
	@# signal that *this* transfer actually landed an image - a stale image
	@# already present under the target tag must not be mistaken for success.
	@# `docker load` normally preserves a fully-qualified tag (ours includes the
	@# registry, ghcr.io/..., so it does). If IMAGE is ever overridden to a bare
	@# name, docker load lands it as localhost/<name> instead - retag only then.
	podman save --format docker-archive $(IMAGE):$(VERSION) | gzip -1 | \
		ssh $(TOWER) 'set -u -o pipefail; \
			out=$$(gunzip | docker load 2>&1); status=$$?; \
			echo "$$out"; \
			if [ $$status -ne 0 ]; then exit $$status; fi; \
			loaded=$$(printf "%s\n" "$$out" | sed -n "s/^Loaded image: //p" | tail -1); \
			if [ -z "$$loaded" ]; then \
				echo "load: no \"Loaded image:\" line in docker load output - transfer failed" >&2; \
				exit 1; \
			fi; \
			[ "$$loaded" = "$(IMAGE):$(VERSION)" ] || docker tag "$$loaded" $(IMAGE):$(VERSION)'

verify: ## Run the live qBittorrent check on tower
	scp scripts/verify_qbt.py $(TOWER):/tmp/verify_qbt.py
	ssh $(TOWER) 'docker run --rm --network mux \
		-v /mnt/user/appdata/speedrr:/data \
		-v /tmp/verify_qbt.py:/tmp/verify_qbt.py:ro \
		$(IMAGE):$(VERSION) python /tmp/verify_qbt.py'
	ssh $(TOWER) 'rm -f /tmp/verify_qbt.py'

release: check ## Tag VERSION and push it; CI builds and publishes
	@test "$(VERSION)" != "dev" || \
		(echo "set VERSION, e.g. make release VERSION=v1.3.0" && exit 1)
	git tag $(VERSION)
	git push origin $(VERSION)

clean: ## Remove local build and cache artifacts
	rm -rf .venv .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
