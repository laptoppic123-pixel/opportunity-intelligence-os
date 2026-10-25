"""Bounded, owner-authorized network access shared by all research/model adapters."""

from datetime import datetime, timedelta, timezone
import time
from urllib.parse import urlsplit
import httpx
from .safety import public_url
from .providers import ProviderRegistry
from .ai_reliability import response_deferral, defer, FREE_ROUTER


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
        max_attempts = (
            1
            if model or source["name"] == "openrouter" or (source.get("config") or {}).get("allowance")
            else 3
        )
        for attempt in range(max_attempts):
            if self.requests >= self.store.settings.max_requests:
                raise PermissionError("Run request bound reached")
            if time.monotonic() - self.started >= self.store.settings.max_seconds:
                raise PermissionError("Run time bound reached")
            request_id = self.registry.reserve(source, estimate=estimate, run_id=self.run_id)
            self.requests += 1
            try:
                options = {}
                if source["name"] == "openrouter":
                    left = self.store.settings.max_seconds - (time.monotonic() - self.started)
                    options["timeout"] = max(0.1, min(40, left))
                response = self.client.request(
                    method, url, params=params, json=payload, headers=headers, **options
                )
                if len(response.content) > 2_000_000:
                    raise ValueError("Response size limit")
                if source["name"] == "openrouter":
                    body = {}
                    if "json" in response.headers.get("content-type", ""):
                        body = response.json()
                    api_error = isinstance(body, dict) and body.get("error") and not body.get("choices")
                    if response.status_code >= 300 or api_error:
                        actual = (body.get("usage") or {}).get("cost") if isinstance(body, dict) else None
                        self.store.settle(
                            request_id,
                            actual if actual is not None else (0 if float(estimate) == 0 else None),
                        )
                        if actual is not None and float(actual) > float(estimate):
                            raise defer(
                                self.store,
                                source,
                                (payload or {}).get("model", "catalog"),
                                "free_price_guard_exceeded",
                                provider_wide=True,
                                review=True,
                            )
                        raise response_deferral(
                            self.store, source, (payload or {}).get("model", "catalog"), response
                        )
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
                        attempt + 1 < max_attempts
                        and time.monotonic() - self.started + 2**attempt < self.store.settings.max_seconds
                    ):
                        time.sleep(2**attempt)
                        continue
                if response.status_code >= 300:
                    self.store.settle(request_id, 0 if float(estimate) == 0 else None)
                    if response.status_code in {401, 402, 403}:
                        self.store.update(
                            "source_registry",
                            source["id"],
                            {
                                "failure_count": 3,
                                "last_error": f"HTTP {response.status_code}: credential/access/credit unavailable; no paid fallback",
                            },
                        )
                        source["failure_count"] = 3
                    raise PermissionError(f"Provider HTTP {response.status_code}")
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
                if actual is None and (source.get("config") or {}).get("allowance"):
                    self.store.update(
                        "source_registry",
                        source["id"],
                        {
                            "failure_count": 3,
                            "last_error": "Promotional charge unknown; reservation held for review",
                        },
                    )
                    source["failure_count"] = 3
                    raise PermissionError("Credit provider stopped: charge unknown")
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
                if source["name"] == "openrouter":
                    model_id = (payload or {}).get("model", "catalog")
                    raise defer(
                        self.store,
                        source,
                        model_id,
                        "free_transport_unavailable",
                        provider_wide=model_id in {FREE_ROUTER, "catalog"},
                    ) from None
                if attempt + 1 < max_attempts and float(estimate) == 0:
                    time.sleep(2**attempt)
                    continue
                self.registry.failure(source, type(exc).__name__)
                raise RuntimeError("Provider transport failed; inspect source health") from None
        self.registry.failure(source, "transient errors exhausted")
        raise RuntimeError("Provider retry bound reached")
