# Docs Voice & Style

> **Problem**: Tone drift and redundant prose crept in as pages multiplied.  \
> **Why**: Matching the matter-of-fact cadence in the Python tutorial, FastAPI guides, uv docs, and Pytest assert examples (#techdocs https://docs.python.org/3.13/tutorial/index.html, #techdocs https://fastapi.tiangolo.com/advanced/settings/, #techdocs https://docs.astral.sh/uv/guides/, #techdocs https://docs.pytest.org/en/stable/how-to/assert.html) keeps every page terse and verifiable.  \
> **Outcome**: Consistent Problem/Why/Outcome intros, Arrange/Act/Assert bodies, and command blocks backed by real output.

## Tone & Sentence Rules

- Open with the reader’s question in ≤75 words using the Python tutorial’s “This page teaches you…” pattern.
- Write in second-person, active voice; FastAPI’s settings doc shows how to give crisp instructions without fluff.
- Cap sentences around 25 words and delete filler per A Philosophy of Software Design’s “eliminate complexity” warning (#techdocs file:///home/pankaj/Personal/Code/docs-mcp-server/mcp-data/a-philosophy-of-software-design/06-2-the-nature-of-complexity.md).

## Structural Patterns

- Every page starts with a **Problem / Why / Outcome** blockquote.
- Tutorials, operations recipes, and runbooks must use **Arrange / Act / Assert** subheadings so readers can skim prerequisites, commands, and verification steps, mirroring Pytest’s arrange/assert narrative.
- Explanations stick to short theses plus numbered or bulleted lists—no walls of prose.

## Tables, Links, and References

- Format knobs like Docker’s option tables: one row per flag, explicit defaults, and hyperlinks to the authoritative spec (#techdocs https://docs.docker.com/reference/cli/docker/buildx/build/).
- When you mention `.env` precedence or FastAPI wiring, cite the FastAPI settings article so readers know where the behavior comes from.
- README and landing pages should link to anchors (`tutorials.md#cli-fast-path`, `operations.md#diagnostics-and-metrics`) instead of restating procedures.

## Commands & Proof

- Never invent sample output. Run the command, trim with `head`/`tail`, and paste the real lines (per `.github/instructions/validation.instructions.md`).
- Mention the exact `uv run`, proxy, or Playwright flags so operators can grep logs for the same text.
- When referencing GitHub Actions or Docker CLI syntax, cite the official docs (#techdocs https://docs.github.com/en/actions/concepts/workflows-and-actions/, #techdocs https://docs.docker.com/reference/cli/docker/container/run/#env).

## Math & Callouts

- Keep inline math within `$…$`; wrap multi-line expressions in `$$` so KaTeX renders correctly.
- Use blockquotes for callouts and Problem/Why/Outcome sections; reserve admonitions for troubleshooting steps that require extra scrolling.

## Bad vs Good Hero Copy

| Version | Copy |
| --- | --- |
| **Bloated** | “Article Extractor is an innovative, world-class content extraction platform providing numerous capabilities for a wide variety of global customers.” |
| **Target Style** | “Article Extractor turns arbitrary HTML into deterministic Markdown. Problem: brittle scrapers fail on paywalls. Why: ingestion pipelines need reproducible text. Outcome: one scorer shared by the CLI, FastAPI server, and Python API.” |

Write every hero (README, docs landing pages, tutorial introductions) using the target style so visitors immediately know whether they are in the right place.
