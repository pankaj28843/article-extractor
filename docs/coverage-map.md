# Documentation Coverage Map

**Audience**: Maintainers, technical writers, and contributors deciding where new content belongs.  
**Prerequisites**: Familiarity with the Divio quadrants described in [notes.md](https://github.com/pankaj28843/article-extractor/blob/main/notes.md) and the docsRealityCheck workflow.  
**Purpose**: Guarantee that the README plus every page under `docs/` stays mutually exclusive and collectively exhaustive (MECE) for Article Extractor.

## Scenario Routing Table

| Persona / Need | Primary Location | Why | Related Pages |
| --- | --- | --- | --- |
| Prospective user evaluating the project | [README](https://github.com/pankaj28843/article-extractor/blob/main/README.md) | Short pitch, badges, supported surfaces | [Explanations](explanations/why.md), [coverage checklist](coverage-map.md#page-checklist) |
| Engineer running a first extraction via CLI | [Tutorial: CLI in 2 Minutes](tutorials/cli.md) | End-to-end instructions with verification + sample output | [How-To: Networking](how-to/networking.md) |
| Team deploying the Docker server | [Tutorial: Docker in 5 Minutes](tutorials/docker.md) | Container workflow + health checks | [How-To: Cache & Playwright](how-to/cache-playwright.md), [Reference: Configuration](reference/configuration.md) |
| Developer embedding the library | [Tutorial: Python in 5 Minutes](tutorials/python.md) | Sample code + outputs | [Reference: Runtime Interfaces](reference/runtime.md) |
| Operator tuning caches, storage, or fetcher preferences | [How-To: Cache & Playwright Storage](how-to/cache-playwright.md) | Step-by-step overrides + verification | [Reference: Configuration](reference/configuration.md#playwright-storage-queue) |
| Operator configuring proxies, user-agents, headed browsers | [How-To: Networking Controls](how-to/networking.md) | Recipes for CLI/server overrides | [Tutorials](tutorials/index.md), [Reference: Runtime Interfaces](reference/runtime.md#fastapi-server) |
| SRE enabling diagnostics and metrics | [How-To: Diagnostics & Metrics](how-to/diagnostics.md) | Logging and StatsD instructions with sample output | [Release Engineering](release-engineering/index.md) |
| Architect comparing trade-offs and heuristics | [Explanations: How It Works](explanations/how-it-works.md) | Pipeline rationale, scoring math | [Explanations: Why](explanations/why.md), [Reference](reference/index.md) |
| Contributor editing docs or code | [Contributing Guide](contributing/index.md) | Validation loop + docsRealityCheck enforcement | [Development Workflow](contributing/development.md), [Release Engineering](release-engineering/index.md) |
| Release manager shipping Docker/docs | [Release Engineering](release-engineering/index.md) | GitHub Pages + docker smoke harness | [Contributing](contributing/index.md) |

## Page Checklist

This table tracks MECE compliance for every Markdown page. ✅ means the page explicitly covers audience, prerequisites, estimated time, verification, troubleshooting, and next steps per [notes.md](https://github.com/pankaj28843/article-extractor/blob/main/notes.md) and [docsRealityCheck.prompt.md](https://github.com/pankaj28843/article-extractor/blob/main/.github/prompts/docsRealityCheck.prompt.md).

| Page | Quadrant | Audience Declared | Prereqs Listed | Time/Scope | Verification | Troubleshooting/Next Steps |
| --- | --- | --- | --- | --- | --- | --- |
| README | Landing | ✅ | ✅ | ✅ | ✅ (links to tutorials) | ✅ |
| docs/index.md | Home | ✅ | ✅ | n/a | n/a | ✅ |
| coverage-map.md | Index | ✅ | ✅ | n/a | ✅ | ✅ |
| tutorials/cli.md | Tutorial | ✅ | ✅ | ✅ | ✅ | ✅ |
| tutorials/docker.md | Tutorial | ✅ | ✅ | ✅ | ✅ | ✅ |
| tutorials/python.md | Tutorial | ✅ | ✅ | ✅ | ✅ | ✅ |
| how-to/cache-playwright.md | How-To | ✅ | ✅ | ✅ | ✅ | ✅ |
| how-to/networking.md | How-To | ✅ | ✅ | n/a | ✅ | ✅ |
| how-to/diagnostics.md | How-To | ✅ | ✅ | n/a | ✅ | ✅ |
| reference/configuration.md | Reference | ✅ | n/a | n/a | ✅ (link to diagnostics) | ✅ |
| reference/runtime.md | Reference | ✅ | n/a | n/a | ✅ | ✅ |
| explanations/why.md | Explanation | ✅ | ✅ | n/a | n/a | ✅ |
| explanations/how-it-works.md | Explanation | ✅ | ✅ | n/a | n/a | ✅ |
| contributing/index.md | How-To | ✅ | ✅ | n/a | ✅ | ✅ |
| contributing/development.md | How-To | ✅ | ✅ | n/a | ✅ | ✅ |
| release-engineering/index.md | How-To | ✅ | ✅ | n/a | ✅ | ✅ |

> Keep this table updated whenever new pages land or scope changes. If a column would be marked ❌, fix the page immediately before merging.
