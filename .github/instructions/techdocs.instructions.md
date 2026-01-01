# TechDocs MCP Instructions

> **Summary**: TechDocs provides instant access to authoritative documentation sources—FastAPI, Python, Docker, and more. Use it to ground decisions in official docs rather than guessing.

---

## Quick Reference

| Tool | When to Use | Example |
|------|-------------|---------|
| `list_tenants` | Discover available docs, confirm tenant exists | **Start every research session here** |
| `describe_tenant` | Get test_queries, source_type, url_prefixes | Before searching—reveals good query patterns |
| `root_search` | Find relevant pages by keyword/phrase | `query="fastapi dependency injection"` |
| `root_fetch` | Read full document content | After search returns a high-score result |
| `root_browse` | Navigate filesystem/git tenants | For local docs or git-synced repos |

---

## Recommended Workflow

**Always follow this discovery pattern:**

```python
# 1. List available tenants (they change over time)
mcp_techdocs_list_tenants()

# 2. Describe the tenant to get query hints
mcp_techdocs_describe_tenant(codename="fastapi")

# 3. Search using test_queries as inspiration
mcp_techdocs_root_search(tenant_codename="fastapi", query="dependency injection")

# 4. Fetch the most relevant result
mcp_techdocs_root_fetch(tenant_codename="fastapi", uri="https://fastapi.tiangolo.com/...")
```

**Why this order matters:**
- `list_tenants` reveals what's available—tenants are added frequently
- `describe_tenant` returns `test_queries` that show which terms work well
- Searching without describe_tenant often leads to poor results

---

## Core Tenants for article-extractor

### Python Stack
| Codename | Scope | Sample Queries |
|----------|-------|----------------|
| `python` | Stdlib, async, pathlib, http.server | `async def`, `pathlib`, `dataclasses` |
| `pytest` | Fixtures, async tests, mocking | `@pytest.fixture`, `pytest-asyncio`, `tmp_path` |
| `fastapi` | HTTP endpoints, dependency injection | `APIRouter`, `dependency injection`, `middleware` |

### DevOps
| Codename | Scope | Sample Queries |
|----------|-------|----------------|
| `docker` | Dockerfile, multi-stage builds, ENTRYPOINT | `dockerfile`, `ENTRYPOINT`, `COPY` |
| `github-platform` | GitHub Actions, GHCR, workflows | `workflow`, `ghcr`, `docker build push` |
| `github-copilot` | Custom instructions, prompt files | `copilot-instructions`, `custom instructions` |

---

## Search Strategy

### DO
- **Start with `list_tenants`** at session start—new docs appear regularly
- **Use `describe_tenant`** to discover optimal query patterns from `test_queries`
- **Try multiple query variations** if initial searches miss (3-5 attempts)
- **Fetch only high-score (>50) results** to avoid noise
- **Cite sources** in code comments when patterns come from docs

### DON'T
- Skip `describe_tenant`—the `test_queries` often have the exact term you need
- Assume you know what's available—tenants are added frequently
- Give up after one search—try alternate phrasings
- Fetch low-score results hoping for relevance

---

## Troubleshooting

| Issue | Action |
|-------|--------|
| No hits for a term | Run `describe_tenant` and search for related terms from `test_queries` |
| Need implementation examples | Fetch the doc and look for code blocks |
| Research feels stale | `list_tenants` to confirm tenant exists and check for updates |
| Unsure which tenant to use | Start with `list_tenants`, filter by topic area |
