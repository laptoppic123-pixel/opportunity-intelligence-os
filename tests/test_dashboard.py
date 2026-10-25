from streamlit.testing.v1 import AppTest
from opportunity_intelligence.config import ROOT


def test_offline_dashboard_pages_and_queue_control(tmp_path, monkeypatch):
    monkeypatch.setenv("OI_DEMO_MODE", "true")
    monkeypatch.setenv("OI_DATA_DIR", str(tmp_path))
    app = AppTest.from_file(str(ROOT / "dashboard/app.py"), default_timeout=30).run()
    assert not app.exception
    pages = [
        "Explore / Search",
        "Opportunity Detail",
        "Speculative Gems",
        "Idea Comparison",
        "Research Queue",
        "Source / API Health",
        "Usage & Budget",
        "Favorites / Owner Notes",
        "Export Center",
    ]
    for page in pages:
        app.sidebar.radio[0].set_value(page).run()
        assert not app.exception, (page, [e.message for e in app.exception])
    app.sidebar.radio[0].set_value("Research Queue").run()
    app.text_area[0].set_value("Offline UI fixture: investigate this buyer")
    next(b for b in app.button if b.label == "Queue research").click().run()
    assert not app.exception
    from opportunity_intelligence.config import Settings
    from opportunity_intelligence.store import Store

    store = Store(Settings(demo=True, data_dir=tmp_path))
    assert store.list("research_queue", query="Offline UI fixture: investigate this buyer")
