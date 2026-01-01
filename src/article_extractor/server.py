"""FastAPI HTTP server for article extraction.

This server provides a drop-in replacement for readability-js-server with
the same API but using pure Python instead of Node.js.

Example:
    Run the server:
        uvicorn article_extractor.server:app --host 0.0.0.0 --port 3000

    Query the server:
        curl -XPOST http://localhost:3000/ \\
            -H "Content-Type: application/json" \\
            -d'{"url": "https://en.wikipedia.org/wiki/Wikipedia"}'
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, HttpUrl

from .extractor import extract_article_from_url
from .types import ExtractionOptions

logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Article Extractor Server",
    description="Pure-Python article extraction service - Drop-in replacement for readability-js-server",
    version="0.1.2",
    docs_url="/docs",
    redoc_url="/redoc",
)


# Request/Response models
class ExtractionRequest(BaseModel):
    """Request model for article extraction."""

    url: Annotated[HttpUrl, Field(description="URL to extract article content from")]


class ExtractionResponse(BaseModel):
    """Response model matching readability-js-server format."""

    url: str = Field(description="Original URL")
    title: str = Field(description="Extracted article title")
    byline: str | None = Field(default=None, description="Article author")
    dir: str = Field(default="ltr", description="Text direction (ltr/rtl)")
    content: str = Field(description="Extracted HTML content")
    length: int = Field(description="Character length of content")
    excerpt: str = Field(description="Short text excerpt")
    siteName: str | None = Field(default=None, description="Site name (if available)")

    # Additional fields from article-extractor
    markdown: str = Field(description="Markdown version of content")
    word_count: int = Field(description="Word count of content")
    success: bool = Field(description="Whether extraction succeeded")


@app.get("/", status_code=status.HTTP_200_OK)
async def root() -> dict:
    """Health check endpoint."""
    return {
        "service": "article-extractor-server",
        "status": "running",
        "version": "0.1.2",
        "description": "Pure-Python replacement for readability-js-server",
    }


@app.post("/", response_model=ExtractionResponse, status_code=status.HTTP_200_OK)
async def extract_article_endpoint(request: ExtractionRequest) -> ExtractionResponse:
    """Extract article content from URL.

    This endpoint provides the same interface as readability-js-server.

    Args:
        request: Extraction request with URL

    Returns:
        Extracted article content in readability-js-server compatible format

    Raises:
        HTTPException: If extraction fails
    """
    try:
        url = str(request.url)
        logger.info(f"Extracting article from: {url}")

        # Extract article using default options
        result = await extract_article_from_url(
            url,
            options=ExtractionOptions(
                min_word_count=150,
                min_char_threshold=500,
                include_images=True,
                include_code_blocks=True,
                safe_markdown=True,
            ),
        )

        if not result.success:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Failed to extract article: {result.error or 'Unknown error'}",
            )

        # Convert to readability-js-server compatible response
        return ExtractionResponse(
            url=result.url,
            title=result.title,
            byline=result.author,
            dir="ltr",  # Could be extracted from HTML lang/dir attributes
            content=result.content,
            length=len(result.content),
            excerpt=result.excerpt,
            siteName=None,  # Could be extracted from meta tags if needed
            markdown=result.markdown,
            word_count=result.word_count,
            success=result.success,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Unexpected error extracting article from {request.url}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {e!s}",
        ) from e


@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check() -> dict:
    """Kubernetes/Docker health check endpoint."""
    return {"status": "healthy"}


# Error handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException) -> JSONResponse:
    """Handle HTTP exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "url": str(request.url)},
    )


@app.exception_handler(Exception)
async def general_exception_handler(_request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.exception("Unexpected error")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error", "error": f"{exc!s}"},
    )
