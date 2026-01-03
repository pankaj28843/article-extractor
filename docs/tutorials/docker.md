# Docker Tutorial: Ship the Server in 5 Minutes

**Audience & Prereqs**: Engineers/SREs following the Tutorials lane in the [Docs Coverage Map](../coverage-map.md#scenario-routing-table); require Docker 24+, outbound pulls from GHCR, and permission to bind an exposed port.  
**Time**: ~5 minutes including the initial image pull.  
**What you'll learn**: Running the published container, verifying `/health`, posting a URL, and inspecting logs.

## 1. Run the Published Image

```bash
docker run --rm -d -p 3000:3000 --name article-extractor-docs ghcr.io/pankaj28843/article-extractor:latest
```

Sample pull (2026-01-03):

```text
Unable to find image 'ghcr.io/pankaj28843/article-extractor:latest' locally
latest: Pulling from pankaj28843/article-extractor
26f63b369c6c: Pull complete
...
Digest: sha256:fd9f0649e6c749b32cf6fab5dd756dc60e412bf4fc8bff3166f8ca42302c5702
Status: Downloaded newer image for ghcr.io/pankaj28843/article-extractor:latest
a138b10d07be7b93a4df93c71f42d870d3950d94f26e23e443d16afc9796ec0e
```

Follow the logs to confirm uvicorn is listening:

```text
$ docker logs --tail 8 article-extractor-docs
INFO:     Uvicorn running on http://0.0.0.0:3000 (Press CTRL+C to quit)
INFO:     Started server process [8]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
```

## 2. Verify `/health`

```bash
curl -sf http://localhost:3000/health
```

Logs show the JSON health probe:

```text
{"timestamp": "2026-01-03T14:11:41.669770+00:00", "level": "INFO", ... "path": "/health", "status_code": 200}
```

## 3. POST a URL

```bash
curl -s -XPOST http://localhost:3000/ \
  -H "Content-Type: application/json" \
  -d '{"url":"https://en.wikipedia.org/wiki/Wikipedia"}' | jq '.title, .word_count'
```

Sample output:

```text
"Wikipedia - Wikipedia"
33414
```

## 4. Stop the Container

```bash
docker stop article-extractor-docs
```

Add `--rm` (as shown above) so Docker cleans up automatically.

## Verification Checklist

- `docker run …` stays in the `running` state (check via `docker ps`) and logs the uvicorn banner.
- `curl /health` returns HTTP 200.
- The POST request returns a title + positive word count and logs a matching request ID.

## Common Extensions

1. **Persistent Playwright state**: Mount host storage and set `ARTICLE_EXTRACTOR_STORAGE_STATE_FILE` per [Override Cache & Playwright Storage](../how-to/cache-playwright.md#2-persist-playwright-session-state).
2. **Prefer Playwright or httpx**: Toggle `ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT` or pass `prefer_playwright` in the POST body.
3. **Diagnostics**: Export `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1` or enable StatsD as in [Diagnostics & Metrics](../how-to/diagnostics.md).

## Troubleshooting

- **Port conflicts**: Map to another host port: `-p 8080:3000`.
- **Proxy requirements**: Export `HTTPS_PROXY` / `NO_PROXY` or pass `--env HTTPS_PROXY=…` (Docker CLI docs: #techdocs https://docs.docker.com/reference/cli/docker/container/run/#env). Combine with [Networking Controls](../how-to/networking.md#1-prep-environment-variables).
- **Container exits immediately**: Run `docker logs article-extractor-docs` for the traceback and re-run with `ARTICLE_EXTRACTOR_LOG_LEVEL=debug`.

## Next Steps

- Persist storage and tune cache sizes via [How-To: Cache & Playwright Storage](../how-to/cache-playwright.md).
- Wire diagnostics and StatsD sinks with [How-To: Diagnostics & Metrics](../how-to/diagnostics.md).
- Automate GitHub Pages + release tasks per [Release Engineering](../release-engineering/index.md).
