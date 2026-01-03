# Documentation Reality Check Prompt

## Purpose
Prevent documentation drift by enforcing reality-grounded workflows. This is an internal developer process—verification artifacts should not appear in published docs.

## Workflow

1. **Before editing docs**: Run every command you plan to document (CLI, FastAPI, Docker) in your current environment.
2. **Capture output**: Copy-paste actual terminal output into docs. Trim secrets, but keep real prompts + exit codes.
3. **Use repo-local temp storage**: Write verification artifacts, logs, and scratch files to `./tmp/...` (gitignored) so you never rely on `/tmp` permissions that might differ per host.
4. **Never invent outputs**: If you have not run it, do not document it.
5. **Clean up**: Do not leave verification notes or TODOs in published docs—keep them in notes.md if needed.

## Checklist (All Must Pass)

### Command Verification
- [ ] Every shell command added/modified in the diff was executed on this machine within the last 7 days
- [ ] Outputs are copy-pasted from real runs (including `uv run article-extractor …`, Docker commands, curl health checks)
- [ ] Long-running commands (>10s) include duration or expectation
- [ ] Destructive commands warn about side effects (cache clears, docker volume wipes)

### Audience Clarity
- [ ] Doc declares target audience in the first paragraph
- [ ] Prerequisites stated explicitly (tools, knowledge, access)
- [ ] Time estimate provided for tutorials/how-tos
- [ ] “What you’ll learn” listed concretely, not vaguely

### How & Why Balance
- [ ] Procedures provide numbered/bulleted steps (HOW)
- [ ] Explanations include rationale/trade-offs (WHY)
- [ ] Troubleshooting section references real error messages
- [ ] Every multi-step workflow ends with a verification command/output

### Anti-Bloat
- [ ] No filler phrases (“simply”, “feel free”, “as mentioned”)
- [ ] Every sentence teaches something non-obvious
- [ ] Code comments explain intent (WHY), not mechanics (WHAT)
- [ ] Cross-references use links rather than repeating content

### Divio Compliance
- [ ] Tutorials = learning-oriented, numbered steps, verification at end
- [ ] How-To = problem-oriented, concise recipe, prerequisites + verification
- [ ] Reference = fact lookup (tables, options) without opinions
- [ ] Explanation = concept-focused, diagrams/trade-offs discussed

## Failure Actions
If any checkbox fails:
1. Re-run commands and capture actual output.
2. Rewrite sections violating clarity/anti-bloat rules.
3. Add missing How/Why content and cross-references.
4. Ask for review before merging if uncertainty remains.

## Related
- `.github/copilot-instructions.md` – Divio guidance, command verification rules
- README.md / notes.md – Source of truth for env vars, Docker usage, and scratch validations
- `.github/instructions/validation.instructions.md` – Mandatory command list for CLI/server/Docker workflows
