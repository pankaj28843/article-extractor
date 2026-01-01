# GitHub CLI (gh) Non-Interactive Usage Instructions

> **CRITICAL: Always use non-interactive mode when automating gh commands in scripts or agent workflows.**

## The Problem: Interactive Pagers

By default, `gh` commands open interactive pagers (less/more) that require manual intervention:
- User must press `q` to exit
- Blocks automated workflows
- Cannot capture output programmatically
- Terminal hangs waiting for user input

**NEVER run bare `gh` commands without piping to head/tail!**

## The Solution: Pipe to head/tail

**ALWAYS pipe gh output to `head` or `tail` with `-n` flag:**

```bash
# BAD: Opens interactive pager
gh run list --limit 5

# GOOD: Non-interactive, shows first 10 lines
gh run list --limit 5 | head -n 10

# GOOD: Non-interactive, shows last 50 lines
gh run view --log-failed | tail -n 50
```

## Core Patterns

### 1. List Workflow Runs

```bash
# Show recent runs (first 10 lines)
gh run list --limit 5 | head -n 10

# Show specific workflow
gh run list --workflow="CI" --limit 3 | head -n 5

# JSON output for programmatic parsing
gh run list --limit 3 --json conclusion,status,workflowName,createdAt | head -n 20
```

### 2. View Workflow Logs

```bash
# Show failure logs (last 100 lines most useful)
gh run view <run_id> --log-failed | tail -n 100

# Show all logs (first 50 lines for overview)
gh run view <run_id> --log | head -n 50
```

### 3. Repository Operations

```bash
# Check repo visibility
gh repo view --json visibility,isPrivate | head -n 5

# View repo details
gh repo view --json name,description,isPrivate,url | head -n 10
```

### 4. Re-running Workflows

```bash
# Re-run failed workflow (no output expected)
gh run rerun <run_id> | head -n 5

# Re-run all failed jobs
gh run rerun <run_id> --failed | head -n 5

# Watch workflow progress (limit output)
gh run watch <run_id> | head -n 50
```

## When to Use head vs tail

| Command Type | Use | Reason |
|--------------|-----|--------|
| `gh run list` | `head -n 10` | Most recent runs at top, need overview |
| `gh run view --log-failed` | `tail -n 100` | Error messages typically at end of logs |
| `gh run view --log` | `head -n 50` | Overview of execution, or `tail` for errors |
| `gh api` | `head -n 20` | JSON responses, need complete structure |
| `gh repo view` | `head -n 10` | Compact output, shows all needed info |

## Always Check gh help First

**Before guessing gh command syntax, ALWAYS consult help:**

```bash
# Get command-specific help
gh run list --help | head -n 50
gh api --help | head -n 40

# Discover available flags
gh run view --help | grep -E "^\s+--" | head -n 30
```

## Common Pitfalls

### ❌ Anti-Pattern 1: Bare gh Commands
```bash
gh run list  # Opens pager, blocks workflow
gh run view --log  # User must press 'q' to continue
```

### ✅ Correct Pattern
```bash
gh run list | head -n 10  # Non-interactive, shows overview
gh run view --log | tail -n 50  # Non-interactive, shows errors
```

### ❌ Anti-Pattern 2: Assuming Silent Success
```bash
gh run rerun 12345  # Did it work? No output to verify
```

### ✅ Correct Pattern
```bash
gh run rerun 12345 | head -n 5  # Pipe even if no output expected
sleep 5 && gh run list --limit 1 | head -n 3  # Verify it started
```

## Validation Checklist

Before committing any script using gh CLI:

- [ ] All `gh` commands pipe to `head` or `tail`
- [ ] Tested command with `--help` flag first
- [ ] JSON output uses `--json` flag explicitly
- [ ] Error logs use `tail -n 100` (errors at end)
- [ ] List commands use `head -n 10` (overview at top)
- [ ] Sleep added between dependent operations
- [ ] No bare `gh` commands without pipes

---

**Remember: When in doubt, run `gh <command> --help | head -n 50` first!**
