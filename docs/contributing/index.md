# Contributing to the Docs

**Audience & Prereqs**: Contributors in the Contributing lane of the [Docs Coverage Map](../coverage-map.md#scenario-routing-table); assume familiarity with the validation loop, GitHub PR workflow, and the docsRealityCheck process.

## Validation Checklist

Documentation changes follow the same validation discipline as code:

1. `uv run ruff format . && uv run ruff check --fix .`
2. `PYTHONPATH=src uv run pytest tests/ --cov=src/article_extractor --cov-report=term-missing`
3. `uv run article-extractor --help` plus a sample URL request
4. `uv run mkdocs build --strict` (fails on missing anchors or nav drift per #techdocs mkdocs/user-guide/configuration.md)

## Docs Author Workflow

- Use `uv sync --extra docs` once to pull the MkDocs toolchain, then `uv run mkdocs serve --no-livereload --dev-addr 127.0.0.1:4000` for local previews.
- Keep prose active and concise as stressed in [notes.md lines 29-130](https://github.com/pankaj28843/article-extractor/blob/main/notes.md#L29-L130), and slot new material into the Tutorials / How-To / Reference / Explanation buckets already represented in the docs navigation.
- Cite authoritative sources (TechDocs, MkDocs manual, GitHub Pages docs) whenever you describe tooling behavior, following the workflow in [.github/instructions/techdocs.instructions.md](https://github.com/pankaj28843/article-extractor/blob/main/.github/instructions/techdocs.instructions.md).
- Update the [Documentation Coverage Map](../coverage-map.md) whenever you add, remove, or significantly change a page so the MECE checklist stays accurate.
- Pair code changes with documentation whenever behavior or validation steps change.

## GitHub Pages Automation

The `.github/workflows/docs.yml` pipeline mirrors the official Pages guidance (#techdocs https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site/):

1. Every push to `main`, pull request, or manual dispatch runs checkout → uv sync → `uv run mkdocs build --strict` → `actions/upload-pages-artifact`.
2. Pushes to `main` continue with `actions/deploy-pages`, targeting the auto-created `github-pages` environment.
3. Inspect deployments with non-interactive GitHub CLI commands (see [gh-cli instructions](https://github.com/pankaj28843/article-extractor/blob/main/.github/instructions/gh-cli.instructions.md)):

	```bash
	gh api repos/:owner/:repo/pages | head -n 20
	gh run list --workflow docs --limit 1 | head -n 10
	gh run view <run_id> --log | tail -n 50
	```

4. Switch the publishing source to "GitHub Actions" when required:

	```bash
	gh api --method PATCH repos/:owner/:repo/pages \
		  -F build_type=workflow -F source.branch=gh-pages -F source.path=/ | head -n 20
	```

## Manual Fallbacks

- Follow [Development Workflow](development.md) for local setup and validation.
- If automation fails, deploy directly with `uv run mkdocs gh-deploy --remote-branch gh-pages` and note in the PR that the fallback path was used (#techdocs mkdocs/user-guide/deploying-your-docs.md). The next workflow run will overwrite the manual deploy, so re-enable automation immediately.
