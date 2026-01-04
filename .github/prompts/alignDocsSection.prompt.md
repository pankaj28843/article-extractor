---
title: Align Documentation Section (Surgical Fix)
description: Fix a specific section of a documentation file to comply with Divio-style guidance and repo writing rules
applyTo:
  - "README.md"
  - "docs/**/*.md"
---

# Align Documentation Section Prompt

## Goal
Surgically fix a specific section of a documentation file without rewriting the entire document. Use when most of the doc is solid but one section violates the standards captured in `.github/copilot-instructions.md` (Divio, real commands, active voice).

## When to Use
- A section uses passive voice or filler
- Missing runnable examples or verification steps
- Wrong Divio quadrant (Tutorial content inside Reference, etc.)
- Code comments in the doc restate obvious mechanics
- Cross-references are missing for a single section

**Need a full rewrite? Use `docsRewrite.prompt.md` instead.**

## Inputs
1. **File path** – documentation file to fix
2. **Section identifier** – heading or line range (e.g., "## Installation" or "lines 45-67")
3. **Issue description** – e.g., "passive voice", "missing example", "needs cross-reference"

## Workflow

### Step 1: Locate the Section
- Read the target file and find the section by heading or range
- Capture surrounding context (heading before/after) so replacements are unambiguous

### Step 2: Diagnose the Issue

| Issue | Diagnosis | Fix |
|-------|-----------|-----|
| Passive voice | "The extractor can be run" | Change to active "Run the extractor" |
| Missing example | Describes behavior only | Add runnable command with actual output |
| No cross-reference | Mentions related topic sans link | Link to existing doc/README anchor |
| Wrong quadrant | Tutorial contains huge reference table | Move table to Reference doc, link back |
| Comment bloat | Code block repeats obvious steps | Delete or reduce to intent-only comments |

### Step 3: Apply Fix Using Guidelines
- Active voice + second person
- Copy-pasteable commands preceded by prerequisites/time estimates when relevant
- Use bullet lists for multi-step instructions; include verification command at the end
- Cite other docs/sections via relative links (`[CLI usage](#cli)`).

### Step 4: Preserve Context
- Do **not** modify adjacent sections unless broken
- Maintain heading levels; keep anchors stable unless the user approved a change
- Keep working examples that already meet standards

### Step 5: Validate
1. Section-level checks: active voice, runnable example, cross-reference, verification command
2. File-level checks: `uv run mkdocs build --strict` (if docs/ exist) or ensure README anchors render in Markdown preview
3. If commands changed, re-run them locally and paste actual output

## Output Format
Use `replace_string_in_file` (or `apply_patch`) with enough surrounding context to make the change deterministic. Example:

```python
replace_string_in_file(
    filePath="README.md",
    oldString="## Installation\n\nYou can install the dependencies using uv.",
    newString="## Installation\n\nInstall dependencies with uv:\n\n```bash\nuv sync --locked --all-extras --dev\nuv sync --upgrade --all-extras --dev```\n\nThis installs all extras and dev dependencies from pyproject.toml."
)
```

## Related Resources
- `.github/copilot-instructions.md` – Divio expectations, command verification rules
- README.md – Source of truth for env vars, Docker usage, CLI examples
- `.github/instructions/validation.instructions.md` – Commands to re-run when docs describe tooling
