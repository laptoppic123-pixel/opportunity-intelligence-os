"""Bounded, owner-authorized network access shared by all research/model adapters."""

from datetime import datetime, timedelta, timezone
import time
from urllib.parse import urlsplit
import httpx
from .safety import public_url
from .providers import ProviderRegistry


class Transport:
    def __init__(self, store, *, run_id=None, client=None):
        self.store = store
        self.registry = ProviderRegistry(store)
        self.run_id = run_id
        self.requests = 0
        self.started = time.monotonic()
        self.client = client or httpx.Client(
            timeout=15,
            follow_redirects=False,
            headers={"User-Agent": "OpportunityIntelligenceOS/2.0 (bounded public API research)"},
        )

    def close(self):
        self.client.close()

    def request(
        self, source, method, url, *, params=None, payload=None, headers=None, estimate=None, model=False
    ):
        self.store.settings.require_live()
        public_url(url)
        if urlsplit(url).scheme != "https":
            raise PermissionError("Research transport requires HTTPS")
        if (
            self.requests >= self.store.settings.max_requests
            or time.monotonic() - self.started > self.store.settings.max_seconds
        ):
            raise PermissionError("Run request/time bound reached")
        # No redirects: API credentials must never be forwarded to another host.
        estimate = source["estimated_cost"] if estimate is None else estimate
        for attempt in range(3):
            if self.requests >= self.store.settings.max_requests:
                raise PermissionError("Run request bound reached")
            request_id = self.registry.reserve(source, estimate=estimate, run_id=self.run_id)
            self.requests += 1
            try:
                response = self.client.request(method, url, params=params, json=payload, headers=headers)
                if len(response.content) > 2_000_000:
                    raise ValueError("Response size limit")
                if response.status_code in {429, 502, 503, 504}:
                    self.store.settle(request_id, 0 if float(estimate) == 0 else None)
                    # A provider's retry-after is persisted, not ignored by immediate retries.
                    retry = response.headers.get("Retry-After")
                    if retry:
                        try:
                            seconds = min(86400, max(1, int(retry)))
                        except ValueError:
                            seconds = 3600
                        cfg = {
                            **source["config"],
                            "blocked_until": (
                                datetime.now(timezone.utc) + timedelta(seconds=seconds)
                            ).isoformat(),
                        }
                        source["config"] = cfg
                        self.store.update("source_registry", source["id"], {"config": cfg})
                        raise PermissionError("Provider requested backoff; retrieval deferred")
                    if (
                        attempt < 2
                        and time.monotonic() - self.started + 2**attempt < self.store.settings.max_seconds
                    ):
                        time.sleep(2**attempt)
                        continue
                if response.status_code >= 300:
                    self.store.settle(request_id, 0 if float(estimate) == 0 else None)
                    raise PermissionError(
                        f"API unavailable (HTTP {response.status_code}); no scraping fallback"
                    )
                is_json = "json" in response.headers.get("content-type", "")
                data = response.json() if is_json else response.text
                if model:
                    usage = data.get("usage", {}) if isinstance(data, dict) else {}
                    actual = usage.get("cost")
                    if actual is None and float(estimate) == 0:
                        actual = 0
                    self.store.settle(request_id, actual, tokens=usage.get("total_tokens"))
                else:
                    actual = 0 if float(estimate) == 0 else None
                    if isinstance(data, dict):
                        reported = data.get("costDollars")
                        if isinstance(reported, dict):
                            reported = reported.get("total")
                        if reported is None:
                            reported = (data.get("usage") or {}).get("cost")
                        if reported is not None:
                            actual = float(reported)
                    self.store.settle(request_id, actual)
                if actual is not None and float(actual) > float(estimate):
                    source["failure_count"] = 3
                    self.store.update(
                        "source_registry",
                        source["id"],
                        {
                            "failure_count": 3,
                            "last_error": "Actual charge exceeded the authorized estimate; review required",
                        },
                    )
                    raise PermissionError("Provider stopped: actual charge exceeded the authorized estimate")
                self.registry.success(source)
                return data
            except (httpx.HTTPError, ValueError) as exc:
                self.store.settle(request_id, 0 if float(estimate) == 0 else None)
                if attempt < 2 and float(estimate) == 0:
                    time.sleep(2**attempt)
                    continue
                self.registry.failure(source, type(exc).__name__)
                raise RuntimeError("Provider transport failed; inspect source health") from None
        self.registry.failure(source, "transient errors exhausted")
        raise RuntimeError("Provider retry bound reached")
