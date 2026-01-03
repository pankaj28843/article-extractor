# Release Engineering

**Audience & Prereqs**: Maintainers in the Release Engineering lane of the [Docs Coverage Map](../coverage-map.md#scenario-routing-table); require GitHub Actions access, Docker 24+, and the validation loop described in [Development Workflow](../contributing/development.md).

Operational runbooks for publishing docs, validating the FastAPI service, and shipping Docker images.

## GitHub Pages Workflow

Docs deploy via GitHub Actions following the official guidance (#techdocs https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site/):

1. Every push to `main` triggers `.github/workflows/docs.yml`.
2. The workflow runs `actions/checkout`, installs the locked docs extra via `uv sync --extra docs`, builds with `uv run mkdocs build --strict`, uploads artifacts via `actions/upload-pages-artifact`, and deploys with `actions/deploy-pages` into the auto-created `github-pages` environment.
3. Pull requests run the same build/upload steps and keep the preview artifact available in the Checks tab without deploying.
4. The repository’s GitHub Pages site is already configured for Actions builds via `gh api --method POST repos/:owner/:repo/pages -F build_type=workflow` (REST API doc: https://docs.github.com/en/rest/pages/pages?apiVersion=2022-11-28#create-a-github-pages-site).
5. To inspect state with `gh` (always pipe output):

	```bash
	gh api repos/:owner/:repo/pages | head -n 20
	gh run list --workflow docs --limit 1 | head -n 10
	gh run view <run_id> --log | tail -n 50
	```

6. Switch the publishing source to Actions if needed:

	```bash
	gh api --method PATCH repos/:owner/:repo/pages \
		 -F build_type=workflow -F source.branch=gh-pages -F source.path=/ | head -n 20
	```

## FastAPI Health Check

Before tagging a release, confirm the HTTP service boots and responds:

```bash
uv run uvicorn article_extractor.server:app --host 0.0.0.0 --port 3000 &
sleep 2
curl -sf http://localhost:3000/health
kill %1
```

Add `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1` when you need deeper traces (see [Diagnostics & Metrics](../how-to/diagnostics.md)).

## Docker Smoke Harness

Validates the Docker image plus Playwright storage queue end-to-end.

**Prerequisites**: Docker 24+, uv, and the optional `httpx` extra for the harness.  
**Verification**: Harness exits 0 and logs `Docker validation harness completed successfully`.

1. Run the harness (skip the rebuild during local edits):

	```bash
	uv run scripts/debug_docker_deployment.py --skip-build --tail-lines 120
	```

2. Inspect the tail for HTTP 200s and queue statistics. Rerun with `--retries 2` or point `--urls-file` at a custom corpus when a URL flakes.
3. Pass env vars (e.g., `ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS=1`) through `uv run` to debug Playwright state handling.

## Fallback Deploy (`mkdocs gh-deploy`)

If Pages automation is unavailable, deploy manually per MkDocs' GitHub Pages guide (#techdocs mkdocs/user-guide/deploying-your-docs.md):

```bash
uv run mkdocs gh-deploy --remote-branch gh-pages
```

Never edit the `gh-pages` branch directly—the next deploy overwrites manual changes. After running the fallback, re-enable the workflow so future commits use the automated path again.
