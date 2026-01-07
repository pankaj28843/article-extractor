# Operations Runbook

Five Arrange/Act/Assert recipes keep cache tuning, networking, diagnostics, validation, and release automation in one place so you can work through incidents without hopping across multiple files.

**Audience**: Operators and contributors maintaining production deployments.  
**Prerequisites**: Working CLI or Docker deployment and access to logs.  
**Time**: ~15-30 minutes for a single workflow.  
**What you'll learn**: How to tune caches, manage storage, and validate releases.

## Cache and Playwright Storage

**Arrange**
- Running CLI or Docker deployment.
- Optional host directory when you want persistence (default runs remain ephemeral), e.g., `$HOME/.article-extractor`.

**Act**

```bash
mkdir -p $HOME/.article-extractor
export AE_STORAGE=$HOME/.article-extractor/storage_state.json

ARTICLE_EXTRACTOR_CACHE_SIZE=2000 \
ARTICLE_EXTRACTOR_THREADPOOL_SIZE=8 \
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia \
  --output text \
  --storage-state "$AE_STORAGE" | head -n 5

docker run --rm -d -p 3001:3000 --name article-extractor-tuned \
  -e ARTICLE_EXTRACTOR_CACHE_SIZE=2000 \
  -e ARTICLE_EXTRACTOR_THREADPOOL_SIZE=8 \
  -e ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT=true \
  -e ARTICLE_EXTRACTOR_STORAGE_STATE_FILE=/data/storage_state.json \
  -v $HOME/.article-extractor:/data \
  ghcr.io/pankaj28843/article-extractor:latest

curl -s -XPOST http://localhost:3001/ \
  -H "Content-Type: application/json" \
  -d '{"url":"https://en.wikipedia.org/wiki/Wikipedia"}' | jq '.title, .word_count'
ls -R $HOME/.article-extractor | head
docker stop article-extractor-tuned
```

> Skip `--storage-state`, `ARTICLE_EXTRACTOR_STORAGE_STATE_FILE`, and the `--volume` flag when you prefer the default ephemeral Playwright session. See the [Docker CLI reference](https://docs.docker.com/reference/cli/docker/container/run/#options) for volume/env semantics.

**Assert**
- CLI logs show the increased cache size; Docker logs show Playwright fetching with persisted storage.
- POST response returns the same title/word count as the CLI tutorial.
- `storage_state.json` plus a `storage_state.json.changes/processed/` tree exist under the mounted directory.
- Adjust queue thresholds via `ARTICLE_EXTRACTOR_STORAGE_QUEUE_*` when logs warn about backlog; values are listed in the [Reference](reference.md#configuration).
- `uv run scripts/debug_docker_deployment.py --disable-storage --skip-build` mimics the default ephemeral behavior, while the default harness run continues to verify persistence.

## Networking Controls

**Arrange**
- Proxy credentials if required.
- Playwright extras installed for headed sessions.

**Act**

```bash
export HTTPS_PROXY=https://proxy.example.com:8443
export NO_PROXY=localhost,127.0.0.1

uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia \
  --output text --prefer-playwright | head -n 4

(uv run uvicorn article_extractor.server:app --host 127.0.0.1 --port 3002 \
  > ./tmp/uvicorn.log 2>&1 & echo $! > ./tmp/uvicorn.pid) && sleep 3 && \
  curl -s -XPOST http://127.0.0.1:3002/ \
       -H "Content-Type: application/json" \
       -d '{"url":"https://example.com","prefer_playwright":false,"network":{"user_agent":"DocsSample/1.0","random_user_agent":false,"headed":false,"proxy":null,"proxy_bypass":["metadata.internal"],"storage_state":null,"user_interaction_timeout":0}}' \
       | jq '{title, word_count, warnings}' && \
  kill $(cat ./tmp/uvicorn.pid) && rm ./tmp/uvicorn.pid
```

**Assert**
- CLI banner shows `Fetched with Playwright` (diagnostics) or prints the expected word count even when a proxy is active.
- Server response returns `"Example Domain"` with `word_count: 19` and `warnings: null`.
- `./tmp/uvicorn.log` includes a JSON line logging the resolved proxy, matching the overrides you posted.
- Unset `HTTPS_PROXY`/`NO_PROXY` after debugging to avoid surprises.

## Diagnostics and Metrics

**Arrange**
- CLI or Docker runtime.
- Optional StatsD endpoint (defaults to UDP 8125 locally).

**Act**

```bash
ARTICLE_EXTRACTOR_LOG_LEVEL=info \
ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1 \
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia --output text 2>&1 | head -n 10

docker run --rm -d -p 3002:3000 --name article-extractor-diag \
  -e ARTICLE_EXTRACTOR_LOG_LEVEL=info \
  -e ARTICLE_EXTRACTOR_LOG_FORMAT=json \
  -e ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1 \
  ghcr.io/pankaj28843/article-extractor:latest

docker logs --tail 8 article-extractor-diag

docker stop article-extractor-diag

ARTICLE_EXTRACTOR_METRICS_ENABLED=1 \
ARTICLE_EXTRACTOR_METRICS_SINK=statsd \
ARTICLE_EXTRACTOR_METRICS_STATSD_HOST=127.0.0.1 \
ARTICLE_EXTRACTOR_METRICS_STATSD_PORT=8125 \
ARTICLE_EXTRACTOR_METRICS_NAMESPACE=article_extractor \
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia --output text | head -n 3
```

**Assert**
- CLI diagnostics show structured JSON with `request_id`, cache hints, and fetcher selection.
- Docker logs stream the same fields for every HTTP request until you stop the container.
- Enabling StatsD emits UDP packets (use `tcpdump -i lo udp port 8125` if you need proof) containing counters like `article_extractor.cli_extractions.success`.
- Reset `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=0` and `LOG_LEVEL=warning` after collection to reduce noise.

## Development Workflow and Validation

**Arrange**
- Cloned repo plus `uv sync --all-extras`.
- Follow `.github/instructions/validation.instructions.md` to the letter.

**Act**

```bash
uv run ruff format .
uv run ruff check --fix .
PYTHONPATH=src uv run pytest tests/ --cov=src/article_extractor --cov-report=term-missing
uv run article-extractor --help
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia
uv run mkdocs build --strict
uv run mkdocs build --strict --clean
```

Add `uv run scripts/debug_docker_deployment.py --skip-build --tail-lines 120` whenever Docker or Playwright behavior changes.

**Assert**
- Coverage stays ≥93%.
- CLI help exits 0 and prints the latest options.
- MkDocs builds succeed without nav/anchor warnings.

## Release Automation

**Arrange**
- Access to GitHub Actions plus `gh` CLI (always pipe output; see `.github/instructions/gh-cli.instructions.md`).
- Docker installed if you need to run the smoke harness locally.

**Act**

```bash
uv run uvicorn article_extractor.server:app --host 0.0.0.0 --port 3000 &
sleep 2
curl -sf http://localhost:3000/health
kill %1

uv run scripts/debug_docker_deployment.py --skip-build --tail-lines 120

gh run list --workflow docs --limit 1 | head -n 10
gh api repos/:owner/:repo/pages | head -n 20

uv run mkdocs gh-deploy --remote-branch gh-pages
```

**Assert**
- Local server health check succeeds before tagging.
- Smoke harness logs `Docker validation harness completed successfully` and HTTP 200s.
- `gh run list` shows the latest docs workflow green; `gh api repos/:owner/:repo/pages` confirms Actions-based publishing.
- `mkdocs gh-deploy` serves as the documented fallback. Record the fallback in the PR description so the workflow can resume control on the next push.
