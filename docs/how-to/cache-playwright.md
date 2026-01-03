# Override Cache & Playwright Storage

**Audience & Prereqs**: Operators in the How-To lane of the [Docs Coverage Map](../coverage-map.md#scenario-routing-table); start from a running CLI or Docker deployment, writable storage path, Docker 24+ (if containerized), and comfort with env vars.  
**Time**: ~10 minutes including container restart and verification.  
**Goal**: Tune cache/threadpool limits, persist cookies between runs, and confirm the storage queue is healthy.

## 1. Pick Cache & Threadpool Sizes

- `ARTICLE_EXTRACTOR_CACHE_SIZE` (default `1000`): raise it for reuse-heavy workloads, lower it to conserve RAM.
- `ARTICLE_EXTRACTOR_THREADPOOL_SIZE` (default `0`): pin it when you want deterministic CPU usage (set to number of logical cores you allocate).

Set them inline when launching the CLI or server:

```bash
ARTICLE_EXTRACTOR_CACHE_SIZE=2000 \
ARTICLE_EXTRACTOR_THREADPOOL_SIZE=8 \
uv run article-extractor https://example.com --output text
```

## 2. Persist Playwright Session State

1. Choose a host directory (here we use `$HOME/.article-extractor`) and ensure it exists:

   ```bash
   mkdir -p $HOME/.article-extractor
   ```

2. Set `ARTICLE_EXTRACTOR_STORAGE_STATE_FILE=/data/storage_state.json` so Chromium writes cookies inside the mounted path. Keep the `storage_state.json.changes/` queue on the same volume to avoid corruption.

## 3. Run Docker with Overrides

```bash
docker run --rm -d -p 3001:3000 --name article-extractor-tuned \
  -e ARTICLE_EXTRACTOR_CACHE_SIZE=2000 \
  -e ARTICLE_EXTRACTOR_THREADPOOL_SIZE=8 \
  -e ARTICLE_EXTRACTOR_STORAGE_STATE_FILE=/data/storage_state.json \
  -e ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT=true \
  -v $HOME/.article-extractor:/data \
  ghcr.io/pankaj28843/article-extractor:latest
```

Sample excerpt (2026-01-03):

```text
$ docker logs --tail 4 article-extractor-tuned
INFO:     Waiting for application startup.
INFO:     Application startup complete.
{"timestamp": "2026-01-03T14:13:14.008738+00:00", "component": "server", "path": "/health", "status_code": 200, ...}
```

Post a URL through the tuned container to warm the cache and storage:

```bash
curl -s -XPOST http://localhost:3001/ \
  -H "Content-Type: application/json" \
  -d '{"url":"https://en.wikipedia.org/wiki/Wikipedia"}' | jq '.title, .word_count'
```

Output:

```text
"Wikipedia - Wikipedia"
33414
```

## 4. Monitor the Storage Queue

List the mounted directory to confirm both the storage file and the change queue update after each headed/browser interaction:

```text
$ ls -R $HOME/.article-extractor | head
/home/pankaj/.article-extractor:
storage_state.json
storage_state.json.changes

.../processed:
1767449315581301290-870d9c2f78724e38801830c0e1b63939.json
```

Tune queue env vars from the [Configuration Reference](../reference/configuration.md#playwright-storage-queue) when you see logs about backlog or retention.

## Verification Checklist

- `docker ps` shows `article-extractor-tuned` running with your env overrides.
- `curl` responses return HTTP 200 plus title/word count while the logs confirm request IDs.
- `storage_state.json` and `storage_state.json.changes/processed/` update on disk after solving a challenge or handling authenticated flows.

## Troubleshooting

- **Queue backlog warnings**: Increase `ARTICLE_EXTRACTOR_STORAGE_QUEUE_MAX_ENTRIES` or share the storage volume across workers so they flush in parallel.
- **Permission errors writing storage**: Ensure the host directory is writable or use `--user $(id -u):$(id -g)` when running Docker.
- **Cache misses**: Gradually increase `ARTICLE_EXTRACTOR_CACHE_SIZE` while observing `docker stats` to keep RAM under control.
- **Prefer Playwright not honored**: Confirm the Playwright extra is installed inside your runtime; without Chromium the server falls back to httpx regardless of the env var.

Stop the tuned container when you're done:

```bash
docker stop article-extractor-tuned
```
