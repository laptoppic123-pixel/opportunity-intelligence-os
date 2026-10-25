from opportunity_intelligence.sources import SourceAdapters
import pytest


class FixtureTransport:
    def __init__(self, store, responses):
        self.store = store
        self.responses = iter(responses)
        self.calls = []

    def request(self, source, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return next(self.responses)


def provider(store, name):
    return store.list("source_registry", name=name)[0]


def test_keyless_hn_algolia_parser(store):
    t = FixtureTransport(
        store,
        [
            {
                "hits": [
                    {
                        "objectID": "123",
                        "title": "Fictional fixture",
                        "comment_text": "<p>Manual reporting pain</p>",
                        "created_at_i": 1700000000,
                        "author": "fixture-author",
                    }
                ]
            }
        ],
    )
    rows = SourceAdapters(t).fetch(provider(store, "hn_algolia"), "reporting")
    assert len(rows) == 1 and rows[0].url == "https://news.ycombinator.com/item?id=123"
    assert "<p>" not in rows[0].excerpt and rows[0].author_hash != "fixture-author"


def test_official_hn_and_github_public_query(store):
    t = FixtureTransport(
        store, [[1], {"title": "Reporting problem", "text": "Manual export", "time": 1700000000}]
    )
    assert SourceAdapters(t).fetch(provider(store, "hn_official"), "reporting")
    t = FixtureTransport(
        store,
        [
            {
                "items": [
                    {
                        "id": 1,
                        "html_url": "https://github.com/example/tool/issues/1",
                        "title": "Need reporting",
                        "body": "Manual work",
                        "created_at": "2026-01-01T00:00:00Z",
                        "user": {"id": 7},
                    }
                ]
            }
        ],
    )
    assert SourceAdapters(t).fetch(provider(store, "github"), "reporting")
    assert "is:public" in t.calls[0][2]["params"]["q"]


def test_stackexchange_attribution(store):
    t = FixtureTransport(
        store,
        [
            {
                "items": [
                    {
                        "question_id": 5,
                        "link": "https://stackoverflow.com/questions/5",
                        "title": "Fixture",
                        "body": "Export issue",
                        "creation_date": 1700000000,
                        "owner": {"user_id": 2, "link": "https://stackoverflow.com/users/2"},
                    }
                ]
            }
        ],
    )
    row = SourceAdapters(t).fetch(provider(store, "stackexchange"), "export")[0]
    assert "CC BY-SA" in row.license and row.metadata["attribution_url"]


def test_optional_search_payloads_are_bounded(store):
    for name in ["exa", "tavily"]:
        t = FixtureTransport(
            store,
            [
                {
                    "results": [
                        {
                            "id": "fixture",
                            "url": "https://example.com/fixture",
                            "title": "Fixture",
                            "content": "Unknown buyer demand",
                            "highlights": ["Public excerpt"],
                        }
                    ]
                }
            ],
        )
        assert SourceAdapters(t).fetch(provider(store, name), "workflow", limit=3)
        payload = t.calls[0][2]["payload"]
        assert payload.get("max_results", payload.get("numResults")) == 3


def test_extraction_requires_reviewed_domain_and_price(store):
    t = FixtureTransport(store, [{"results": []}])
    src = provider(store, "tavily")
    with pytest.raises(PermissionError):
        SourceAdapters(t).extract(src, ["https://example.com/page"])
    assert not t.calls
    src["config"].update(extract_allowed_domains=["example.com"], extract_estimated_cost=0)
    SourceAdapters(t).extract(src, ["https://example.com/page"])
    assert t.calls[0][1] == "https://api.tavily.com/extract"
