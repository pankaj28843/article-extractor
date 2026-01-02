---
description: Completely rewrite a documentation file to follow Divio-style guidance and repo standards
---

# Documentation Rewrite Prompt

## Goal
Completely rewrite a documentation file to be clear, user-centric, and compliant with the Divio quadrants (Tutorial, How-To, Reference, Explanation) referenced in `.github/copilot-instructions.md`.

## When to Use
- Doc is outdated or incorrect
- Content belongs to the wrong Divio quadrant
- Writing violates style guidelines (passive voice, no examples, unclear audience)
- File needs complete restructuring rather than a surgical fix

## Inputs
1. **Target file path** – documentation file to rewrite
2. **Current content** – portion being replaced
3. **Desired quadrant** – Tutorial, How-To, Reference, or Explanation (optional; infer if not provided)

## Step 1: Analyze Current State
- Identify the current quadrant, target audience, and violations
- Note missing info, outdated commands, or dead links

## Step 2: Determine Correct Quadrant
Use Divio decision tree:
1. Learning journey? → Tutorial
2. Solve specific task? → How-To
3. Fact lookup? → Reference
4. Explain why/how? → Explanation

If the file mixes quadrants, split into multiple docs or keep primary quadrant + link to others.

## Step 3: Gather Context
- Read related code (CLI, server, extractor modules)
- Check README and notes for existing examples
- Run every command you plan to document; copy actual output

## Step 4: Rewrite Using Templates

**Tutorial Template**
```markdown
# Tutorial: [Learning Goal]

**Time**: ~X minutes  
**Prerequisites**: [Requirements]  
**What You'll Learn**: [Specific outcomes]

## Step 1: [Action]
```bash
uv run article-extractor https://example.com
```

**Expected output**:
```
…
```

## Verification
Run `uv run article-extractor --help` and confirm exit code 0.

## Next Steps
- How-To: [Link]
- Reference: [Link]
```

**How-To Template**
```markdown
# How-To: [Problem]

**Goal**: [Outcome]  
**Prerequisites**: [Requirements]

## Steps
1. **[Action]**
   ```bash
   uv run article-extractor https://…
   ```
2. **[Action]**

## Troubleshooting
**Symptom**: [Error]
**Fix**: [Solution]

## Related
- Reference: [Config options]
- Explanation: [Why]
```

**Reference Template**
```markdown
# Reference: [Component]

## CLI Commands
### `article-extractor`
**Synopsis**: `uv run article-extractor [OPTIONS] URL`

## Settings
| Env Var | Type | Default | Description |
|---------|------|---------|-------------|
| `ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT` | bool | true | Prefer Playwright fetcher |
```

**Explanation Template**
```markdown
# Explanation: [Concept]

## Problem
[Context]

## Our Approach
[Why we chose this design]

## Alternatives Considered
| Option | Pros | Cons | Reason |
|--------|------|------|--------|
```

## Step 5: Apply Style Guidelines
- Active voice, second person
- Short paragraphs (≤3 sentences)
- Real commands + outputs
- Cross-reference other docs using relative links

## Step 6: Validate
1. `uv run mkdocs build --strict --clean` (if docs/ used) or preview README
2. Run every documented command (CLI, curl, Docker)
3. Update `mkdocs.yml` navigation if file added/renamed

## Output
- Replace entire file content with rewritten version
- Mention nav updates if required

## Related
- `.github/copilot-instructions.md` – Divio + documentation standards
- README.md – Canonical env var + CLI guidance
- `.github/instructions/validation.instructions.md` – Commands to re-run when docs mention tooling
