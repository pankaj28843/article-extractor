## What is PRP?

Product Requirement Prompt (PRP)

## In short

A PRP is PRD + curated codebase intelligence + agent/runbook—the minimum viable packet an AI needs to plausibly ship production-ready code on the first pass.

Product Requirement Prompt (PRP) is a structured prompt methodology first established in summer 2024 with context engineering at heart. A PRP supplies an AI coding agent with everything it needs to deliver a vertical slice of working software—no more, no less.

### How PRP Differs from Traditional PRD

A traditional PRD clarifies what the product must do and why customers need it, but deliberately avoids how it will be built.

A PRP keeps the goal and justification sections of a PRD yet adds three AI-critical layers:

### Context

Precise file paths and content, library versions and library context, code snippets examples. LLMs generate higher-quality code when given direct, in-prompt references instead of broad descriptions.

## Creating Effective PRP Plans

### When to Create a PRP Plan

Create a detailed PRP plan for **non-trivial** tasks that require:
- **Multiple actions** across several files or modules
- **Complex logic** that needs careful analysis before implementation
- **Refactoring** that impacts existing functionality
- **Integration** between multiple systems or services
- **Testing strategy** that spans multiple layers (unit, integration)

**Skip PRP planning for trivial tasks** like:
- Single file edits or bug fixes
- Adding simple options to CLI
- Basic configuration changes
- Straightforward documentation updates

### PRP Plan Structure

A comprehensive PRP plan should include:

#### 1. Goal (What & Why)
- **What**: Clear, specific description of what needs to be built/changed
- **Why**: Business justification and value proposition
- **Success Criteria**: Measurable outcomes and acceptance criteria

#### 2. Current State Analysis
- **Existing Code Review**: Detailed analysis of current implementation
- **Dependencies**: What systems/modules are involved
- **Constraints**: Technical limitations or requirements
- **Risk Assessment**: What could go wrong and mitigation strategies

#### 3. Implementation Blueprint
- **Phased Approach**: Break work into logical, sequential phases
- **File-by-File Changes**: Specific files that need modification
- **Testing Strategy**: What needs to be tested and how

#### 4. Context & Anti-Patterns
- **Known Gotchas**: Project-specific patterns and pitfalls to avoid
- **Code Quality Standards**: Style guides and quality requirements

#### 5. Validation Loop
- **Level 1**: Syntax, imports, and basic compilation
- **Level 2**: Unit tests (`uv run pytest tests/ -v`)
- **Level 3**: CLI testing (`uv run docs-html-screenshot --help`)
- **Level 4**: Docker build and test

### Anti-Patterns in PRP Planning

**Avoid These Planning Mistakes**:

**Over-Planning Trivial Tasks**:
- Don't create 50-line PRPs for single-method changes
- Skip formal planning for obvious implementations
- Use judgment - if it's a 5-minute fix, just do it

**Under-Analyzing Complex Changes**:
- Don't start coding complex refactors without understanding current state
- Always analyze existing patterns before introducing new ones
- Map out dependencies and integration points first

**Generic Implementation Blueprints**:
- Avoid vague steps like "update the CLI" or "add tests"
- Include specific file paths, method names, and code patterns
- Reference existing code examples and conventions

## article-extractor Specific Context

### Key Files to Reference
```yaml
- file: .github/copilot-instructions.md
  sections: "Core Philosophy, Prime Directives, Validation"
  why: Prime directives and quality gates

- file: src/article_extractor/extractor.py
  why: Core extraction logic with Readability-style scoring

- file: src/article_extractor/server.py
  why: FastAPI HTTP server

- file: src/article_extractor/cli.py
  why: CLI entry point

- file: pyproject.toml
  why: Project configuration, dependencies, entry points
```

### Validation Commands
```bash
# Format and lint
uv run ruff format . && uv run ruff check --fix .

# Run tests
uv run pytest tests/ -v

# CLI testing
uv run article-extractor --help

# Server testing
uv run uvicorn article_extractor.server:app --reload --port 3000

# Docker build
docker build -t article-extractor .
docker run --rm -p 3000:3000 article-extractor
```
