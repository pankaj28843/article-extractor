"""Test fixtures for article extractor tests."""

import pytest


@pytest.fixture
def simple_article_html() -> str:
    """Simple blog post HTML for testing."""
    return """<!DOCTYPE html>
<html>
<head>
    <title>Test Article Title | Example Site</title>
    <meta property="og:title" content="Test Article Title">
</head>
<body>
    <header>
        <nav>
            <a href="/">Home</a>
            <a href="/about">About</a>
        </nav>
    </header>
    <main>
        <article class="post-content">
            <h1>Test Article Title</h1>
            <p>This is the first paragraph of the article. It contains enough
            text to be considered content, with commas, periods, and other
            punctuation marks that indicate real prose.</p>
            <p>Here is another paragraph with more content. The article extractor
            should recognize this as the main content area because it has
            substantial text content and proper paragraph structure.</p>
            <p>A third paragraph continues the article with additional information.
            This helps ensure the content passes minimum word count thresholds
            that are used to filter out navigation and boilerplate text.</p>
            <pre><code>def example():
    return "code block"</code></pre>
            <p>The conclusion wraps up the article with final thoughts.</p>
        </article>
    </main>
    <aside class="sidebar">
        <h3>Related Posts</h3>
        <ul>
            <li><a href="/post1">Post 1</a></li>
            <li><a href="/post2">Post 2</a></li>
        </ul>
    </aside>
    <footer>
        <p>Copyright 2025</p>
    </footer>
</body>
</html>"""


@pytest.fixture
def minimal_html() -> str:
    """Minimal HTML with very little content."""
    return """<!DOCTYPE html>
<html>
<head><title>Minimal</title></head>
<body>
    <p>Just one short paragraph.</p>
</body>
</html>"""


@pytest.fixture
def code_heavy_html() -> str:
    """Documentation page with lots of code blocks."""
    return """<!DOCTYPE html>
<html>
<head>
    <title>Installation Guide | Docs</title>
    <meta property="og:title" content="Installation Guide">
</head>
<body>
    <nav>
        <a href="/">Docs</a>
        <a href="/guide">Guide</a>
    </nav>
    <main>
        <article>
            <h1>Installation Guide</h1>
            <p>Follow these steps to install the package.</p>
            <h2>Requirements</h2>
            <p>Python 3.10 or higher is required.</p>
            <pre><code>pip install example-package</code></pre>
            <h2>Configuration</h2>
            <p>Configure the settings as shown below:</p>
            <pre><code>
import example
example.configure(
    setting1="value1",
    setting2="value2"
)
            </code></pre>
            <p>You can also use environment variables for configuration.</p>
        </article>
    </main>
    <footer>
        <p>Documentation licensed under MIT</p>
    </footer>
</body>
</html>"""


@pytest.fixture
def navigation_heavy_html() -> str:
    """HTML with heavy navigation, typical of docs sites."""
    return """<!DOCTYPE html>
<html>
<head>
    <title>Main Article | Site</title>
    <meta property="og:title" content="Main Article">
</head>
<body>
    <nav class="top-nav">
        <ul>
            <li><a href="/">Home</a></li>
            <li><a href="/docs">Docs</a></li>
            <li><a href="/api">API</a></li>
            <li><a href="/examples">Examples</a></li>
            <li><a href="/about">About</a></li>
        </ul>
    </nav>
    <div class="sidebar">
        <nav>
            <ul>
                <li><a href="/section1">Section 1</a></li>
                <li><a href="/section2">Section 2</a></li>
                <li><a href="/section3">Section 3</a></li>
            </ul>
        </nav>
    </div>
    <main>
        <article>
            <h1>Main Article</h1>
            <p>This is the main content area. It should be extracted despite
            the heavy navigation around it. The extractor should identify this
            as the primary content because of the article tag and the text density.</p>
            <p>Additional paragraphs provide more content signals to the extractor.
            Commas, periods, and sentence structure indicate real article content.</p>
        </article>
    </main>
    <aside class="related">
        <h3>Related Articles</h3>
        <ul>
            <li><a href="/related1">Related 1</a></li>
            <li><a href="/related2">Related 2</a></li>
        </ul>
    </aside>
    <footer>
        <nav>
            <a href="/privacy">Privacy</a>
            <a href="/terms">Terms</a>
        </nav>
    </footer>
</body>
</html>"""
