from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
import os
from urllib.parse import urlsplit
import feedparser
from .safety import clean, digest, public_url


@dataclass
class Observation:
    item_id: str
    url: str
    title: str
    excerpt: str
    published_at: str | None = None
    author_hash: str | None = None
    license: str = "unknown; reference and excerpt only"
    metadata: dict = field(default_factory=dict)


def stamp(epoch):
    return datetime.fromtimestamp(epoch, timezone.utc).isoformat() if epoch else None


def author(value):
    return digest(str(value)) if value else None


class SourceAdapters:
    def __init__(self, transport):
        self.t = transport

    def extract(self, source, urls):
        """Optional bounded extraction, only for explicitly reviewed domains and prices."""
        if source["name"] not in {"tavily", "exa"}:
            raise PermissionError("Provider does not support extraction")
        cfg = source["config"]
        allowed = set(cfg.get("extract_allowed_domains", []))
        if not urls or len(urls) > 2:
            raise PermissionError("Extraction is limited to two reviewed URLs")
        for url in urls:
            public_url(url)
            if urlsplit(url).hostname not in allowed:
                raise PermissionError("Domain lacks explicit extraction permission")
        estimate = cfg.get("extract_estimated_cost")
        if estimate is None:
            raise PermissionError("Extraction worst-case price is unknown")
        key = os.getenv(cfg.get("key_env") or "", "")
        tavily = source["name"] == "tavily"
        data = self.t.request(
            source,
            "POST",
            "https://api.tavily.com/extract" if tavily else "https://api.exa.ai/contents",
            headers={"Authorization": "Bearer " + key} if tavily else {"x-api-key": key},
            estimate=estimate,
            payload={"urls": urls, "extract_depth": "basic", "include_images": False, "format": "text"}
            if tavily
            else {"ids": urls, "text": {"maxCharacters": 700}},
        )
        return [
            Observation(
                str(h.get("id") or h.get("url")),
                h["url"],
                clean(h.get("title")),
                clean(h.get("raw_content") or h.get("text")),
                metadata={"retrieval": "permitted bounded extraction"},
            )
            for h in data.get("results", [])
            if h.get("url")
        ]

    def fetch(self, source, query, *, since=None, limit=5, page=0):
        name = source["name"]
        spec = source["config"]
        key = os.getenv(spec.get("key_env") or "", "")
        if name == "hn_algolia":
            params = {"query": query, "tags": "(story,comment)", "hitsPerPage": min(limit, 10), "page": page}
            if since:
                params["numericFilters"] = "created_at_i>" + str(
                    int(datetime.fromisoformat(since).timestamp())
                )
            data = self.t.request(
                source, "GET", "https://hn.algolia.com/api/v1/search_by_date", params=params
            )
            return [
                Observation(
                    str(h["objectID"]),
                    "https://news.ycombinator.com/item?id=" + str(h["objectID"]),
                    clean(h.get("title") or h.get("story_title")),
                    clean(h.get("comment_text") or h.get("story_text") or h.get("title")),
                    stamp(h.get("created_at_i")),
                    author(h.get("author")),
                    metadata={"original_link": h.get("url")},
                )
                for h in data.get("hits", [])
            ][:limit]
        if name == "hn_official":
            ids = self.t.request(source, "GET", "https://hacker-news.firebaseio.com/v0/newstories.json")
            rows = []
            for item in ids[: min(limit, 3)]:
                h = self.t.request(
                    source, "GET", f"https://hacker-news.firebaseio.com/v0/item/{int(item)}.json"
                )
                if (
                    h
                    and not h.get("deleted")
                    and not h.get("dead")
                    and any(
                        w.lower() in (h.get("title", "") + h.get("text", "")).lower() for w in query.split()
                    )
                ):
                    rows.append(
                        Observation(
                            str(item),
                            f"https://news.ycombinator.com/item?id={item}",
                            clean(h.get("title")),
                            clean(h.get("text") or h.get("title")),
                            stamp(h.get("time")),
                            author(h.get("by")),
                            metadata={"original_link": h.get("url")},
                        )
                    )
            return rows
        if name == "github":
            headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
            if key:
                headers["Authorization"] = "Bearer " + key
            q = query + " is:issue is:public"
            if since:
                q += " updated:>=" + since[:10]
            data = self.t.request(
                source,
                "GET",
                "https://api.github.com/search/issues",
                params={"q": q, "sort": "updated", "per_page": min(limit, 10), "page": page + 1},
                headers=headers,
            )
            return [
                Observation(
                    str(h["id"]),
                    h["html_url"],
                    clean(h["title"]),
                    clean(h.get("body")),
                    h.get("created_at"),
                    author(h.get("user", {}).get("id")),
                )
                for h in data.get("items", [])
                if "pull_request" not in h
            ][:limit]
        if name == "stackexchange":
            params = {
                "q": query,
                "site": "stackoverflow",
                "sort": "activity",
                "order": "desc",
                "pagesize": min(limit, 10),
                "filter": "withbody",
                "page": page + 1,
            }
            if key:
                params["key"] = key
            if since:
                params["fromdate"] = int(datetime.fromisoformat(since).timestamp())
            data = self.t.request(
                source, "GET", "https://api.stackexchange.com/2.3/search/advanced", params=params
            )
            if data.get("backoff"):
                config = {
                    **spec,
                    "blocked_until": (
                        datetime.now(timezone.utc) + timedelta(seconds=int(data["backoff"]))
                    ).isoformat(),
                }
                source["config"] = config
                self.t.store.update("source_registry", source["id"], {"config": config})
            if data.get("quota_remaining") == 0:
                self.t.registry.failure(source, "API quota exhausted; wait for reset")
            return [
                Observation(
                    str(h["question_id"]),
                    h["link"],
                    clean(h["title"]),
                    clean(h.get("body")),
                    stamp(h.get("creation_date")),
                    author(h.get("owner", {}).get("user_id")),
                    "CC BY-SA; original author/page attribution required",
                    {"attribution_url": h.get("owner", {}).get("link")},
                )
                for h in data.get("items", [])
            ][:limit]
        if name == "rss":
            rows = []
            for url in spec.get("feeds", [])[:2]:
                public_url(url)
                data = self.t.request(source, "GET", url)
                feed = feedparser.parse(data)
                for h in feed.entries[:limit]:
                    if not h.get("link"):
                        continue
                    excerpt = clean(h.get("summary") or h.get("title"))
                    if any(w.lower() in (h.get("title", "") + excerpt).lower() for w in query.split()):
                        rows.append(
                            Observation(
                                str(h.get("id") or h.link),
                                h.link,
                                clean(h.get("title")),
                                excerpt,
                                stamp(__import__("calendar").timegm(h.published_parsed))
                                if h.get("published_parsed")
                                else None,
                                metadata={"feed_url": url, "feed_title": clean(feed.feed.get("title"))},
                            )
                        )
            return rows[:limit]
        if name in {"exa", "tavily", "serper"}:
            endpoint = {
                "exa": "https://api.exa.ai/search",
                "tavily": "https://api.tavily.com/search",
                "serper": "https://google.serper.dev/search",
            }[name]
            payload = (
                {
                    "query": query,
                    "numResults": min(limit, 5),
                    "type": "auto",
                    "contents": {"highlights": True},
                }
                if name == "exa"
                else (
                    {
                        "query": query,
                        "max_results": min(limit, 5),
                        "search_depth": "basic",
                        "include_answer": False,
                        "include_raw_content": False,
                    }
                    if name == "tavily"
                    else {"q": query, "num": min(limit, 5)}
                )
            )
            headers = (
                {"x-api-key": key}
                if name == "exa"
                else ({"Authorization": "Bearer " + key} if name == "tavily" else {"X-API-KEY": key})
            )
            data = self.t.request(source, "POST", endpoint, payload=payload, headers=headers)
            items = data.get("organic" if name == "serper" else "results", [])
            return [
                Observation(
                    str(h.get("id") or h.get("url") or h.get("link")),
                    h.get("url") or h.get("link"),
                    clean(h.get("title")),
                    clean(" ".join(h.get("highlights", [])) or h.get("content") or h.get("snippet")),
                    h.get("publishedDate"),
                )
                for h in items
            ][:limit]
        if name == "youtube":
            data = self.t.request(
                source,
                "GET",
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "key": key,
                    "q": query,
                    "part": "snippet",
                    "type": "video",
                    "maxResults": min(limit, 5),
                },
            )
            return [
                Observation(
                    h["id"]["videoId"],
                    "https://www.youtube.com/watch?v=" + h["id"]["videoId"],
                    clean(h["snippet"]["title"]),
                    clean(h["snippet"].get("description")),
                    h["snippet"].get("publishedAt"),
                    metadata={"evidence_limit": "video metadata only; no transcript or buyer interview"},
                )
                for h in data.get("items", [])
            ]
        if name == "openalex":
            params = {"search": query, "per-page": min(limit, 5)}
            if key:
                params["api_key"] = key
            data = self.t.request(source, "GET", "https://api.openalex.org/works", params=params)
            return [
                Observation(
                    h["id"],
                    h.get("doi") or h["id"],
                    clean(h.get("display_name")),
                    clean(h.get("display_name")),
                    h.get("publication_date"),
                    metadata={"evidence_limit": "research trend, not demonstrated customer demand"},
                )
                for h in data.get("results", [])
            ]
        if name == "procurement":
            url = spec.get("base_url")
            if not url:
                raise PermissionError("Reviewed procurement endpoint is not configured")
            headers = {"Authorization": "Bearer " + key} if key else {}
            data = self.t.request(
                source, "GET", url, params={"q": query, "limit": min(limit, 5)}, headers=headers
            )
            items = data
            for segment in spec.get("result_path", "results").split("."):
                items = items.get(segment, [])
            mapping = spec.get(
                "field_mapping", {"id": "id", "url": "url", "title": "title", "excerpt": "description"}
            )
            return [
                Observation(
                    str(h[mapping["id"]]),
                    h[mapping["url"]],
                    clean(h[mapping["title"]]),
                    clean(h.get(mapping["excerpt"])),
                )
                for h in items[:limit]
            ]
        raise PermissionError("Provider has no permitted retrieval capability")
