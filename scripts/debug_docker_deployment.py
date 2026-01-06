#!/usr/bin/env python3
"""Docker debug harness rewritten in Python with parallel smoke requests."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

try:
    import httpx
except ImportError as exc:  # pragma: no cover - defensive guard for local tooling
    raise SystemExit(
        "scripts/debug_docker_deployment.py requires httpx>=0.28. "
        "Install the optional 'httpx' extra (uv pip install httpx) before rerunning."
    ) from exc

LOG_PREFIX = "[docker-debug]"
MOUNT_TARGET = "/var/article-extractor/storage"
DEFAULT_URLS: tuple[str, ...] = (
    "https://en.wikipedia.org/wiki/Wikipedia",
    "https://en.wikipedia.org/wiki/Machine_learning",
    "https://en.wikipedia.org/wiki/Space_exploration",
    "https://developer.mozilla.org/en-US/docs/Web/JavaScript",
    "https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API",
    "https://www.bbc.com/news/technology",
    "https://www.theguardian.com/science",
    "https://www.npr.org/sections/technology/",
    "https://www.cnn.com/business",
    "https://blog.cloudflare.com/",
    "https://aws.amazon.com/blogs/aws/",
    "https://engineering.atspotify.com/",
    "https://dropbox.tech/",
    "https://netflixtechblog.com/",
    "https://openai.com/blog/",
    "https://about.google/stories/",
    "https://blogs.microsoft.com/",
    "https://devblogs.microsoft.com/dotnet/",
    "https://engineering.linkedin.com/blog",
    "https://www.theverge.com/tech",
)


class HarnessError(Exception):
    """Raised when the debug harness encounters a recoverable failure."""


@dataclass
class HarnessArgs:
    image_tag: str
    container_name: str
    container_port: int
    concurrency: int
    retries: int
    urls_file: Path | None
    skip_build: bool
    keep_container: bool
    diagnostics_flag: str
    tail_lines: int
    health_timeout: int
    disable_storage: bool


@dataclass
class UrlResult:
    url: str
    status_code: int | None
    elapsed: float
    excerpt: str | None
    error: str | None


def log(message: str) -> None:
    sys.stdout.write(f"{LOG_PREFIX} {message}\n")


def parse_args() -> HarnessArgs:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild the Docker image, start the FastAPI service, and fire parallel smoke "
            "requests to validate Playwright storage behavior."
        )
    )
    parser.add_argument(
        "--image-tag",
        default="article-extractor:local",
        help="Docker image tag to build/run.",
    )
    parser.add_argument(
        "--container-name",
        default="article-extractor-smoke",
        help="Name of the temporary Docker container.",
    )
    parser.add_argument(
        "--container-port",
        type=int,
        default=13005,
        help="Internal container port exposed by the FastAPI app.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=6,
        help="Maximum concurrent POST requests to issue against the server.",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=1,
        help="Number of additional attempts per URL when the first POST fails.",
    )
    parser.add_argument(
        "--urls-file",
        type=Path,
        help="Optional file containing newline-separated URLs (comments starting with # are ignored).",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip rebuilding the Docker image and reuse the current tag.",
    )
    parser.add_argument(
        "--keep-container",
        action="store_true",
        help="Leave the smoke container running after the harness exits.",
    )
    parser.add_argument(
        "--diagnostics-flag",
        default=os.environ.get("ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS", "0"),
        help="Value for ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS passed into the container (defaults to env value).",
    )
    parser.add_argument(
        "--tail-lines",
        type=int,
        default=80,
        help="Number of log lines to stream from the container after the run completes.",
    )
    parser.add_argument(
        "--health-timeout",
        type=int,
        default=60,
        help="Seconds to wait for /health to report ready before failing the harness.",
    )
    parser.add_argument(
        "--disable-storage",
        action="store_true",
        help="Skip mounting Playwright storage so the harness mimics the default ephemeral runtime (persistence remains the default)",
    )
    args = parser.parse_args()
    if args.concurrency <= 0:
        parser.error("--concurrency must be a positive integer")
    if args.retries < 0:
        parser.error("--retries cannot be negative")
    if args.tail_lines <= 0:
        parser.error("--tail-lines must be positive")
    if args.container_port <= 0:
        parser.error("--container-port must be positive")
    if args.health_timeout <= 0:
        parser.error("--health-timeout must be positive")
    return HarnessArgs(
        image_tag=args.image_tag,
        container_name=args.container_name,
        container_port=args.container_port,
        concurrency=args.concurrency,
        retries=args.retries,
        urls_file=args.urls_file,
        skip_build=args.skip_build,
        keep_container=args.keep_container,
        diagnostics_flag=str(args.diagnostics_flag),
        tail_lines=args.tail_lines,
        health_timeout=args.health_timeout,
        disable_storage=bool(args.disable_storage),
    )


def ensure_command(name: str) -> None:
    if shutil.which(name) is None:
        raise HarnessError(f"Required command '{name}' is not available on PATH")


def run_cmd(
    args: Sequence[str], *, capture_output: bool = False, check: bool = True
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - commands are constructed from trusted arguments
        args,
        text=True,
        capture_output=capture_output,
        check=check,
    )


def allocate_port(min_port: int = 20000) -> int:
    for _ in range(64):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("", 0))
            candidate = sock.getsockname()[1]
            if candidate >= min_port:
                return candidate
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return sock.getsockname()[1]


def build_image(image_tag: str, project_root: Path) -> None:
    log(f"Building Docker image {image_tag} ...")
    run_cmd(["docker", "build", "-t", image_tag, str(project_root)])


def reset_storage(storage_dir: Path) -> Path:
    if storage_dir.exists():
        shutil.rmtree(storage_dir)
    storage_dir.mkdir(parents=True, exist_ok=True)
    log(f"Seeding Playwright storage under {storage_dir} ...")
    run_cmd([sys.executable, "-m", "article_extractor.storage", str(storage_dir)])
    return storage_dir / "storage_state.json"


def container_exists(name: str) -> bool:
    result = run_cmd(
        ["docker", "ps", "-aq", f"--filter=name=^{name}$"], capture_output=True
    )
    return result.stdout.strip() != ""


def stop_container(name: str) -> None:
    if container_exists(name):
        log(f"Removing container {name} ...")
        run_cmd(["docker", "rm", "-f", name], check=False)


def start_container(
    image_tag: str,
    container_name: str,
    container_port: int,
    host_port: int,
    storage_dir: Path | None,
    diagnostics_flag: str,
) -> str:
    log(
        f"Starting container {container_name} on host port {host_port} -> {container_port} ..."
    )
    cmd = [
        "docker",
        "run",
        "-d",
        "--name",
        container_name,
        "--publish",
        f"{host_port}:{container_port}",
    ]
    if storage_dir is not None:
        cmd.extend(["--volume", f"{storage_dir}:{MOUNT_TARGET}"])
    else:
        log("Starting container without persistent storage; contexts remain ephemeral")
    cmd.extend(
        [
            "-e",
            "TZ=UTC",
            "-e",
            "HOST=0.0.0.0",
            "-e",
            f"PORT={container_port}",
            "-e",
            "ARTICLE_EXTRACTOR_CACHE_SIZE=512",
            "-e",
            "ARTICLE_EXTRACTOR_THREADPOOL_SIZE=12",
            "-e",
            "ARTICLE_EXTRACTOR_PREFER_PLAYWRIGHT=true",
        ]
    )
    if storage_dir is not None:
        cmd.extend(
            [
                "-e",
                f"ARTICLE_EXTRACTOR_STORAGE_STATE_FILE={MOUNT_TARGET}/storage_state.json",
            ]
        )
    cmd.extend(
        [
            "-e",
            f"ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS={diagnostics_flag}",
            image_tag,
        ]
    )
    try:
        result = run_cmd(cmd, capture_output=True)
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.strip() if exc.stderr else "unknown error"
        raise HarnessError(f"Docker failed to start the container: {stderr}") from exc
    container_id = result.stdout.strip()
    if not container_id:
        raise HarnessError("Docker did not return a container ID")
    if diagnostics_flag != "0":
        log(
            "Diagnostics logging is enabled inside the container "
            f"(ARTICLE_EXTRACTOR_LOG_DIAGNOSTICS={diagnostics_flag})."
        )
    return container_id


def wait_for_health(base_url: str, timeout: int) -> None:
    log(f"Waiting for {base_url}/health (timeout {timeout}s) ...")
    deadline = time.time() + timeout
    with httpx.Client(timeout=5.0) as client:
        while time.time() < deadline:
            try:
                response = client.get(f"{base_url}/health")
                if response.status_code == 200:
                    log("Health check succeeded")
                    return
            except httpx.HTTPError:
                pass
            time.sleep(1)
    raise HarnessError("Server did not become healthy before the timeout expired")


def load_urls(urls_file: Path | None) -> list[str]:
    if urls_file is None:
        return list(DEFAULT_URLS)
    if not urls_file.exists():
        raise HarnessError(f"Provided URLs file {urls_file} does not exist")
    urls: list[str] = []
    for raw_line in urls_file.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    deduped = list(dict.fromkeys(urls))
    if not deduped:
        raise HarnessError("URLs file was empty after removing blanks/comments")
    return deduped


def clean_excerpt(text: str, limit: int = 160) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= limit:
        return collapsed
    return f"{collapsed[:limit]}…"


async def fire_requests(
    base_url: str,
    urls: list[str],
    concurrency: int,
    retries: int,
) -> list[UrlResult]:
    semaphore = asyncio.Semaphore(concurrency)
    timeout = httpx.Timeout(35.0, read=75.0)
    results: list[UrlResult] = []

    async with httpx.AsyncClient(timeout=timeout) as client:

        async def issue_request(target: str) -> UrlResult:
            attempts = retries + 1
            last_excerpt: str | None = None
            last_error: str | None = None
            last_status: int | None = None
            last_elapsed = 0.0
            for attempt in range(attempts):
                start = time.perf_counter()
                try:
                    response = await client.post(f"{base_url}/", json={"url": target})
                    last_elapsed = time.perf_counter() - start
                    last_status = response.status_code
                    last_excerpt = clean_excerpt(response.text)
                    if response.status_code < 400:
                        return UrlResult(
                            target,
                            response.status_code,
                            last_elapsed,
                            last_excerpt,
                            None,
                        )
                    last_error = f"HTTP {response.status_code}"
                except httpx.HTTPError as exc:
                    last_elapsed = time.perf_counter() - start
                    last_error = str(exc)
                if attempt < attempts - 1:
                    await asyncio.sleep(1 + attempt)
            return UrlResult(
                target,
                last_status,
                last_elapsed,
                last_excerpt,
                last_error or "Request failed",
            )

        async def worker(target_url: str) -> None:
            async with semaphore:
                results.append(await issue_request(target_url))

        await asyncio.gather(*(worker(url) for url in urls))
    return results


def summarize_results(results: Iterable[UrlResult]) -> None:
    success = 0
    failures: list[UrlResult] = []
    for result in results:
        status = result.status_code if result.status_code is not None else "--"
        outcome = "ok" if result.error is None else f"FAIL ({result.error})"
        elapsed = f"{result.elapsed:0.2f}s" if result.elapsed else "--"
        log(f"[{status}] {elapsed:>7} {outcome:>12} :: {result.url}")
        if result.error:
            failures.append(result)
            if result.excerpt:
                log(f"    excerpt: {result.excerpt}")
        else:
            success += 1
    total = success + len(failures)
    log(f"Completed {success}/{total} URLs successfully")
    if failures:
        first = failures[0]
        snippet = first.excerpt or "(no body excerpt available)"
        raise HarnessError(
            f"{len(failures)} URLs failed during smoke execution. "
            f"First failure {first.url} -> {first.error}. Excerpt: {snippet}"
        )


def validate_storage(storage_file: Path) -> None:
    if not storage_file.exists():
        raise HarnessError(f"Expected storage file {storage_file} was not created")
    size = storage_file.stat().st_size
    if size <= 0:
        raise HarnessError(f"Storage file {storage_file} is empty")
    data = json.loads(storage_file.read_text())
    origins = data.get("origins", [])
    cookies = data.get("cookies", [])
    if not origins:
        raise HarnessError("Storage file did not capture any origins")
    if not cookies:
        raise HarnessError("Storage file did not capture any cookies")
    sample_origin = origins[0].get("origin", "unknown origin")
    log(
        f"Playwright storage ready at {storage_file} :: {len(origins)} origins, "
        f"{len(cookies)} cookies (sample origin: {sample_origin})"
    )


def print_container_logs(name: str, tail_lines: int) -> None:
    log(f"Container logs (tail {tail_lines}):")
    run_cmd(["docker", "logs", name, "--tail", str(tail_lines)], check=False)


def ready_curl_snippet(base_url: str, url: str) -> None:
    snippet = f"curl -X POST {base_url}/ \\\n       -H 'Content-Type: application/json' \\\n       --data '{{\"url\":\"{url}\"}}'"
    log("Ready-to-run curl command:")
    sys.stdout.write(f"  {snippet}\n")


def main() -> None:
    args = parse_args()
    ensure_command("docker")
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "tmp" / "docker-smoke-data"
    storage_dir: Path | None = None
    storage_file: Path | None = None
    if args.disable_storage:
        log(
            "Disable-storage flag set; harness will mimic the default ephemeral behavior"
        )
    else:
        storage_dir = data_dir
        storage_file = reset_storage(data_dir)
    urls = load_urls(args.urls_file)
    log(
        f"Running Docker harness with {len(urls)} URLs, concurrency {args.concurrency}, "
        f"retries {args.retries}"
    )
    if not args.skip_build:
        build_image(args.image_tag, project_root)
    host_port = allocate_port()
    log(f"Allocated host port {host_port}")

    if container_exists(args.container_name):
        stop_container(args.container_name)

    start_container(
        args.image_tag,
        args.container_name,
        args.container_port,
        host_port,
        storage_dir,
        args.diagnostics_flag,
    )
    logs_dumped = False
    base_url = f"http://localhost:{host_port}"
    try:
        wait_for_health(base_url, args.health_timeout)
        results = asyncio.run(
            fire_requests(base_url, urls, args.concurrency, args.retries)
        )
        summarize_results(results)
        if storage_file is not None:
            validate_storage(storage_file)
        print_container_logs(args.container_name, args.tail_lines)
        logs_dumped = True
        ready_curl_snippet(base_url, urls[0])
    except Exception:
        if container_exists(args.container_name) and not logs_dumped:
            print_container_logs(args.container_name, args.tail_lines)
        raise
    finally:
        if not args.keep_container:
            stop_container(args.container_name)

    log("Docker validation harness completed successfully")


if __name__ == "__main__":
    try:
        main()
    except HarnessError as exc:
        log(f"ERROR: {exc}")
        sys.exit(1)
    except KeyboardInterrupt:
        log("Interrupted by user")
        sys.exit(1)
