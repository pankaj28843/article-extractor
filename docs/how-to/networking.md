# Networking Controls

**Audience & Prereqs**: Operators in the How-To lane of the [Docs Coverage Map](../coverage-map.md#scenario-routing-table); assume a working CLI/server deployment, proxy credentials (if required), and the Playwright extras for headed browsing.  
**Goal**: Configure proxies, force fetchers, tweak user-agents, and send overrides through the FastAPI server with confidence.

## 1. Prep Environment Variables

Export proxy settings once and reuse them across CLI/server invocations:

```bash
export HTTPS_PROXY=https://proxy.example.com:8443
export NO_PROXY=localhost,127.0.0.1
```

(`unset HTTPS_PROXY NO_PROXY` returns you to direct networking.) Docker injects the same env vars via `-e NAME=value` (#techdocs https://docs.docker.com/reference/cli/docker/container/run/#env).

## 2. CLI Flags for Networking

| Flag | Effect |
| --- | --- |
| `--proxy=http://user:pass@proxy:8080` | Override env vars for a single run. |
| `--prefer-playwright` / `--prefer-httpx` | Force a fetcher when both are available. |
| `--headed --user-interaction-timeout 30` | Launch Chromium visibly for CAPTCHA/manual auth (requires `[all]` extra + `playwright install`). |
| `--storage-state PATH` | Persist cookies to disk (pair with [cache & storage how-to](cache-playwright.md)). |
| `--user-agent`, `--random-user-agent` | Pin or randomize headers via `fake-useragent` (install `[all]`). |

Example run (2026-01-03):

```bash
uv run article-extractor https://en.wikipedia.org/wiki/Wikipedia --output text --prefer-playwright | head -n 4
```

Output:

```text
Title: Wikipedia - Wikipedia
Author: Unknown
Words: 33414
```

Use the same flags through `ExtractionOptions` when embedding inside Python.

## 3. FastAPI Overrides

Send overrides in the JSON body. This example pinches the user-agent, disables Playwright, and bypasses metadata hosts:

```bash
(uv run uvicorn article_extractor.server:app --host 127.0.0.1 --port 3002 > ./tmp/uvicorn.log 2>&1 & echo $! > ./tmp/uvicorn.pid) \
  && sleep 3 \
  && curl -s -XPOST http://127.0.0.1:3002/ \
       -H "Content-Type: application/json" \
        -d '{"url":"https://example.com","prefer_playwright":false,"network":{"user_agent":"DocsSample/1.0","random_user_agent":false,"headed":false,"proxy":null,"proxy_bypass":["metadata.internal"],"storage_state":null,"user_interaction_timeout":0}}' \
        | jq '{title, word_count, warnings}' \
      && kill $(cat ./tmp/uvicorn.pid) && rm ./tmp/uvicorn.pid
```

Sample response:

```json
{
  "title": "Example Domain",
  "word_count": 19,
  "warnings": null
}
```

Log excerpt (`./tmp/uvicorn.log`):

```text
{"message": "Extracting article", "url": "https://example.com/", "request_id": "17b0982f33904f2a96a7c9624fb27bfd"}
{"message": "Fetched with httpx", "status_code": 200, "via_proxy": false}
```

The compound command starts `uv run uvicorn …` in the background, stores its PID in `./tmp/uvicorn.pid`, and kills it after the `curl` finishes so you do not leave stray FastAPI workers running.

All POST fields map directly to `FetchPreferences` in `src/article_extractor/types.py`.

## 4. Verification Checklist

- CLI runs exit 0 and print the banner/title even when you force a fetcher.
- Server responses include `warnings` when a proxy/storage override fails—treat non-empty warnings as actionable.
- Logs show the resolved proxy, user-agent, and headed flags, which confirms overrides propagated through the fetcher layer.

## Troubleshooting

- **Proxy auth failures**: URL-encode usernames/passwords or prefer env vars so shells don’t mangle special characters.
- **Playwright missing**: `--headed` silently falls back to httpx without Chromium. Install `[all]` and rerun `playwright install`.
- **Storage path missing**: Responses list warnings describing permission/IO errors. Fix the mount or follow [Override Cache & Playwright Storage](cache-playwright.md).
- **403s from strict sites**: Try `--prefer-playwright --headed` to mimic browsers, rotate user-agents, or route via a residential proxy.
