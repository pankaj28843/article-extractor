---
title: Comment Intent Audit (Code Cleanup)
description: Systematically audit and clean code comments to remove bloat and keep only intent-explaining comments
applyTo:
  - "src/**/*.py"
---

# Comment Intent Audit Prompt

## Goal
Systematically audit all comments in a Python module and classify them as DELETE (noise), KEEP (explains intent), or ADD_MISSING (complex logic needs documentation).

## When to Use
- Module accumulated AI-generated comment bloat
- Refactor left behind redundant docstrings or TODOs
- Preparing a file for feature work and want the comment surface clean

**Docs-only issues? Use `alignDocsSection.prompt.md` or `docsRewrite.prompt.md`.**

## Philosophy
From `.github/copilot-instructions.md`: comments explain **why**, not **what**. Intent lives in comments; mechanics belong in code/identifiers.

### DELETE These
- Restatements of obvious code (`# increment i`)
- Placeholder TODOs with no owner/issue
- Docstrings that add zero information beyond the function name

### KEEP These
- Trade-offs, invariants, magic numbers
- References to known bugs with issue IDs
- Non-obvious heuristics (density thresholds, tokenization quirks)

### ADD MISSING
- Complex algorithms (candidate scoring, DOM traversal)
- Non-trivial environment contracts (storage-state assumptions)
- Magic constants controlling heuristics

## Instructions
1. **Gather context** – Identify file/scope (full module or specific class/function).
2. **Scan comments** – Inline `#`, block strings, docstrings. Categorize each entry using the decision tree:

```
Does it explain WHY?
├─ YES → Is that intent obvious now?
│  ├─ YES → DELETE
│  └─ NO  → KEEP
└─ NO  → Is it restating WHAT?
   ├─ YES → DELETE
   └─ NO  → Is it actionable TODO/FIXME?
       ├─ YES with owner/issue → KEEP
       └─ otherwise → DELETE
```

3. **Identify gaps** – Flag complex logic lacking comments.
4. **Prepare audit table** – Include line numbers and justification for DELETE/KEEP/ADD_MISSING.
5. **Apply edits** – Use `apply_patch`/`multi_replace_string_in_file` to remove noise or add concise intent comments.
6. **Validate** – `uv run ruff check <file>` and `uv run pytest tests/ -v -k <area>` if structural edits touched behavior.

## Output Templates

### 1. Audit Report (Markdown)
```
# Comment Audit: src/article_extractor/extractor.py

## DELETE (noise) – 4 comments
| Line | Comment | Reason |
|------|---------|--------|
| 45 | "# increment counter" | Restates code |

## KEEP (intent) – 2 comments
| Line | Comment | Why |
|------|---------|-----|
| 120 | "# Density heuristic penalizes ads" | Explains scoring intent |

## ADD_MISSING (needs comment) – 1 location
| Line | Code | Why |
|------|------|-----|
| 210 | `if score < 0.05:` | Explain noise filter |
```

### 2. Code Changes
Use `multi_replace_string_in_file` or `apply_patch` to remove noise and add intent comments inline.

## Related Files
- `.github/copilot-instructions.md` – Comment intent guidance, AI-bloat rules
- `.github/instructions/validation.instructions.md` – Commands to re-run after editing python files
