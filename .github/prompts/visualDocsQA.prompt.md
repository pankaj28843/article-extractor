---
description: Capture rendered docs screenshots and analyze them with vision capabilities
---

# Visual Documentation QA Prompt

## Goal
Screenshot the rendered documentation site (MkDocs or README preview) and **use LLM vision capabilities to analyze each screenshot**. The objective is visual reasoning—identify issues visible only after rendering.

## Vision-First Analysis
1. **Visually inspect each screenshot PNG**
   - Option A: If your environment can load images directly (e.g., `#file:` reference), open the screenshot.
   - Option B: If you cannot self-load images, ask the user to attach generated screenshots to the chat.
2. **Describe what you see** before listing issues.
3. **Use visual reasoning** to detect layout problems, spacing issues, broken diagrams, code block formatting, etc.
4. **Do NOT rely solely on markdown source.** Only rendered output surfaces many defects.

## Prerequisites
- Docs built locally (`uv run mkdocs build --strict --clean`) or README rendered via the MkDocs site.
- Screenshot tool (Docker image `ghcr.io/pankaj28843/docs-html-screenshot:latest` or `docs-html-screenshot` via `uv tool install`).

## Workflow

### Step 1: Build Documentation
```bash
uv run mkdocs build --strict --clean
```
If build fails, fix errors before proceeding.

### Step 2: Capture Screenshots
Store images in `tmp/screenshots/` using flat filenames for easy `#filename` references.

```bash
rm -rf tmp/screenshots && mkdir -p tmp/screenshots

docker run --rm --init --ipc=host \
  -v "$PWD/site:/input:ro" \
  -v "$PWD/tmp/screenshots:/output" \
  ghcr.io/pankaj28843/docs-html-screenshot:latest \
  --input /input --output /output --allow-http-errors
```

(Alt) `uv tool run docs-html-screenshot --input site --output tmp/screenshots --allow-http-errors`

### Step 3: Analyze Screenshots with Vision
1. `ls tmp/screenshots/*.png` to list files.
2. Load each PNG (via `#filename` or user attachment).
3. For every image, describe layout + note issues.

**Output format**:
```
### #docs/filename.md ✅ PASS | ⚠️ ISSUES

**Visual description**: …

**Issues found**: None | [List]
```

### Step 4: Fix Issues
- Map screenshot back to source (`docs/*.md`, README).
- Categorize issues (Mermaid errors, spacing, table alignment, missing links).
- Apply fixes using `apply_patch`/`replace_string_in_file`.
- Rebuild docs and regenerate screenshots.

### Step 5: Validation Loop
```bash
uv run mkdocs build --strict --clean
rm -rf tmp/screenshots && mkdir -p tmp/screenshots
# rerun screenshot command
timeout 60 uv run pytest tests/ -m unit --no-cov -q  # optional quick sanity check
```

## Visual Inspection Checklist
**Structure**
- [ ] Clear heading hierarchy, consistent spacing
- [ ] Navigation sidebar shows active section
- [ ] Code blocks render with syntax highlighting
- [ ] Tables align and remain legible
- [ ] Admonitions render with icons/colors
- [ ] No horizontal scroll on desktop width

**Content Quality**
- [ ] Audience, prerequisites, and time estimate (where relevant)
- [ ] Real code examples/commands
- [ ] Bulleted lists for multi-step instructions
- [ ] Active voice

**Error Detection**
- [ ] No console errors or missing assets in screenshot tool output
- [ ] No 404 pages or blank sections
- [ ] Diagrams (Mermaid) render properly

## Iteration Strategy
Default to **three** passes:
1. Baseline capture + high-severity issues
2. Formatting polish (spacing, alignment)
3. Final check + validation rerun

## Output
- Screenshots saved in `tmp/screenshots/`
- Visual analysis notes per page
- Summary of fixes + validation status

## Related
- `.github/copilot-instructions.md` – Documentation standards
- README.md / docs/ – Source markdown to patch
- `.github/instructions/validation.instructions.md` – Commands to re-run when docs mention tooling
