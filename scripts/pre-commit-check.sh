#!/bin/bash
# Pre-commit check script for article-extractor
# Run this before committing: ./scripts/pre-commit-check.sh

set -e

echo "🔍 Running pre-commit checks..."

echo ""
echo "📝 Formatting code with Ruff..."
uv run ruff format .

echo ""
echo "🔧 Linting code with Ruff..."
uv run ruff check --fix .

echo ""
echo "🧪 Running tests with coverage..."
uv run pytest --cov=src/article_extractor --cov-report=term-missing -v

echo ""
echo "📊 Checking coverage threshold (94%+)..."
COVERAGE=$(uv run coverage report --format=total 2>/dev/null || echo "0")
echo "Coverage: $COVERAGE%"

if [ "$COVERAGE" -lt 94 ]; then
    echo "❌ Coverage $COVERAGE% is below threshold 94%"
    exit 1
fi

echo ""
echo "✅ All pre-commit checks passed!"
echo ""
echo "You can now commit your changes."
