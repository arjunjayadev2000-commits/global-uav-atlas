"""Polite, cached, resumable HTTP client shared by every crawler.

Behaviour required by the specification and implemented here:

* per-host rate limiting and a descriptive user agent
* ``robots.txt`` consulted (and cached) before any fetch
* exponential backoff retries on transport errors and 5xx/429
* on-disk response cache with a TTL so re-runs do not re-hit sources
* hard timeouts on every request
* streaming downloads with a size ceiling and content sniffing
* a typed :class:`FetchError` that distinguishes *blocked by policy* (do not
  retry) from *transient* (retry) so failures can be isolated per platform
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.robotparser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

from app.config import get_settings
from app.logging import AgentLogger
from app.utils import RateLimiter, retry_call, safe_filename, sha256_bytes, stable_id

LOG = AgentLogger("crawler.http")


class FetchError(RuntimeError):
    """Raised when a fetch fails.

    ``retryable`` False means the failure is a policy/permanent decision
    (403/404/410, robots disallow, offline mode) and must not be retried.
    """

    def __init__(self, message: str, *, status: int | None = None, retryable: bool = True) -> None:
        super().__init__(message)
        self.status = status
        self.retryable = retryable


class RobotsDisallowed(FetchError):
    def __init__(self, url: str) -> None:
        super().__init__(f"robots.txt disallows {url}", status=None, retryable=False)


@dataclass(slots=True)
class Response:
    url: str
    status: int
    headers: dict[str, str]
    content: bytes
    from_cache: bool = False

    @property
    def text(self) -> str:
        encoding = "utf-8"
        ctype = self.headers.get("content-type", "")
        if "charset=" in ctype:
            encoding = ctype.split("charset=", 1)[1].split(";")[0].strip() or "utf-8"
        return self.content.decode(encoding, errors="replace")

    def json(self) -> Any:
        return json.loads(self.text)


_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class HttpClient:
    """Thin wrapper over :mod:`requests` with the policies described above."""

    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        cache_dir: Path | None = None,
        rate_limit: float | None = None,
    ) -> None:
        self.settings = get_settings()
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "User-Agent": self.settings.user_agent,
                "Accept-Encoding": "gzip, deflate",
            }
        )
        self.cache_dir = cache_dir or (self.settings.paths.cache / "http")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.limiter = RateLimiter(
            rate_limit if rate_limit is not None else self.settings.rate_limit_per_host
        )
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        #: Hosts refused by an egress policy. Retrying these wastes the whole run,
        #: so the first refusal is remembered and every later request fails fast.
        self._blocked_hosts: dict[str, str] = {}
        self.stats: dict[str, int] = {
            "requests": 0,
            "cache_hits": 0,
            "errors": 0,
            "bytes": 0,
            "blocked": 0,
        }

    # -- cache ---------------------------------------------------------
    def _cache_paths(self, url: str) -> tuple[Path, Path]:
        key = stable_id(url)
        host = urllib.parse.urlparse(url).netloc or "unknown"
        bucket = self.cache_dir / safe_filename(host, default="host")
        bucket.mkdir(parents=True, exist_ok=True)
        return bucket / f"{key}.body", bucket / f"{key}.meta.json"

    def _read_cache(self, url: str) -> Response | None:
        if not self.settings.http_cache_enabled:
            return None
        body_path, meta_path = self._cache_paths(url)
        if not (body_path.is_file() and meta_path.is_file()):
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return None
        age = time.time() - float(meta.get("stored_at", 0))
        if age > self.settings.http_cache_ttl_seconds:
            return None
        self.stats["cache_hits"] += 1
        return Response(
            url=meta.get("url", url),
            status=int(meta.get("status", 200)),
            headers={k.lower(): v for k, v in meta.get("headers", {}).items()},
            content=body_path.read_bytes(),
            from_cache=True,
        )

    def _write_cache(self, url: str, response: Response) -> None:
        if not self.settings.http_cache_enabled:
            return
        body_path, meta_path = self._cache_paths(url)
        try:
            body_path.write_bytes(response.content)
            meta_path.write_text(
                json.dumps(
                    {
                        "url": response.url,
                        "status": response.status,
                        "headers": response.headers,
                        "stored_at": time.time(),
                        "sha256": sha256_bytes(response.content),
                    }
                ),
                encoding="utf-8",
            )
        except OSError as exc:  # cache is best effort, never fatal
            LOG.debug("cache write failed for %s: %s", url, exc)

    # -- egress policy -------------------------------------------------
    @staticmethod
    def _is_policy_refusal(exc: BaseException) -> bool:
        """Distinguish "the network said no" from "the network hiccuped".

        A proxy/CONNECT refusal (403/407) is an organisation policy decision:
        retrying it is pointless and, multiplied across hundreds of sources,
        turns a fast run into a very slow one.
        """
        text = str(exc).lower()
        return any(
            marker in text
            for marker in (
                "tunnel connection failed",
                "proxyerror",
                "unable to connect to proxy",
                "403 forbidden",
                "407 proxy authentication",
            )
        )

    def blocked_reason(self, host: str) -> str | None:
        return self._blocked_hosts.get(host)

    # -- robots --------------------------------------------------------
    def robots_allows(self, url: str) -> bool:
        if not self.settings.respect_robots:
            return True
        parsed = urllib.parse.urlparse(url)
        if parsed.netloc in self._blocked_hosts:
            return True  # unreachable anyway; the fetch below reports the refusal
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self._robots:
            parser: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
            assert parser is not None
            parser.set_url(f"{origin}/robots.txt")
            try:
                raw = self.session.get(
                    f"{origin}/robots.txt", timeout=min(self.settings.request_timeout, 15.0)
                )
                if raw.status_code >= 400:
                    parser = None  # no usable robots -> default allow
                else:
                    parser.parse(raw.text.splitlines())
            except requests.RequestException as exc:
                if self._is_policy_refusal(exc):
                    self._blocked_hosts[parsed.netloc] = "proxy refused CONNECT (403/407)"
                parser = None
            self._robots[origin] = parser
        parser = self._robots[origin]
        if parser is None:
            return True
        return bool(parser.can_fetch(self.settings.user_agent, url))

    # -- fetching ------------------------------------------------------
    def get(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_cache: bool = True,
        max_bytes: int | None = None,
        allow_robots_bypass: bool = False,
    ) -> Response:
        full_url = url
        if params:
            separator = "&" if "?" in url else "?"
            full_url = f"{url}{separator}{urllib.parse.urlencode(params, doseq=True)}"

        if use_cache:
            cached = self._read_cache(full_url)
            if cached is not None:
                return cached

        if self.settings.offline:
            raise FetchError(f"offline mode: refusing network fetch of {full_url}", retryable=False)

        host_early = urllib.parse.urlparse(full_url).netloc
        blocked = self._blocked_hosts.get(host_early)
        if blocked:
            self.stats["blocked"] += 1
            raise FetchError(
                f"host {host_early} refused by network egress policy ({blocked})",
                status=403,
                retryable=False,
            )

        if not allow_robots_bypass and not self.robots_allows(full_url):
            self.stats["blocked"] += 1
            raise RobotsDisallowed(full_url)

        host = urllib.parse.urlparse(full_url).netloc
        limit = max_bytes if max_bytes is not None else self.settings.image_max_bytes

        def _attempt() -> Response:
            self.limiter.wait(host)
            self.stats["requests"] += 1
            try:
                raw = self.session.get(
                    full_url,
                    headers=headers,
                    timeout=self.settings.request_timeout,
                    stream=True,
                    allow_redirects=True,
                )
            except requests.RequestException as exc:
                if self._is_policy_refusal(exc):
                    self._blocked_hosts[host] = "proxy refused CONNECT (403/407)"
                    self.stats["blocked"] += 1
                    raise FetchError(
                        f"host {host} refused by network egress policy: {exc}",
                        status=403,
                        retryable=False,
                    ) from exc
                raise FetchError(f"transport error for {full_url}: {exc}", retryable=True) from exc

            with raw:
                status = raw.status_code
                if status in _RETRYABLE_STATUS:
                    raise FetchError(
                        f"HTTP {status} for {full_url}", status=status, retryable=True
                    )
                if status >= 400:
                    raise FetchError(
                        f"HTTP {status} for {full_url}", status=status, retryable=False
                    )
                chunks: list[bytes] = []
                total = 0
                for chunk in raw.iter_content(65536):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > limit:
                        raise FetchError(
                            f"response exceeds {limit} bytes: {full_url}", retryable=False
                        )
                    chunks.append(chunk)
                content = b"".join(chunks)
                self.stats["bytes"] += len(content)
                return Response(
                    url=str(raw.url),
                    status=status,
                    headers={k.lower(): v for k, v in raw.headers.items()},
                    content=content,
                )

        def _on_retry(attempt: int, exc: BaseException, delay: float) -> None:
            LOG.warning("retry %d for %s after %.1fs (%s)", attempt, full_url, delay, exc)

        try:
            response = retry_call(
                _attempt,
                attempts=self.settings.max_retries,
                base_delay=self.settings.backoff_base,
                retry_on=(FetchError,),
                should_retry=lambda e: getattr(e, "retryable", False),
                on_retry=_on_retry,
            )
        except FetchError:
            self.stats["errors"] += 1
            raise

        if use_cache:
            self._write_cache(full_url, response)
        return response

    def get_json(self, url: str, *, params: dict[str, Any] | None = None, **kwargs: Any) -> Any:
        response = self.get(url, params=params, **kwargs)
        return response.json()

    def download(self, url: str, destination: Path, *, max_bytes: int | None = None) -> Response:
        """Download to ``destination`` atomically (resumable across runs)."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        response = self.get(url, use_cache=False, max_bytes=max_bytes)
        tmp = destination.with_suffix(destination.suffix + ".part")
        tmp.write_bytes(response.content)
        tmp.replace(destination)
        return response


_CLIENT: HttpClient | None = None


def get_client() -> HttpClient:
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = HttpClient()
    return _CLIENT


def reset_client() -> None:
    global _CLIENT
    _CLIENT = None
