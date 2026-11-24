"""Offline tests: parsers against sample payloads in each source's real format, plus the
engine and Flask endpoints with network calls stubbed. Run: python -m pytest -q tests"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reptrak import scrapers  # noqa: E402
from reptrak.engine import analyze  # noqa: E402

RSS = """<?xml version="1.0" encoding="UTF-8"?><rss version="2.0"><channel>
<item><title>Eternal Q2 profit jumps 92% to Rs 125 crore - Business Standard</title><link>https://news.google.com/a</link>
<pubDate>Wed, 21 Oct 2026 10:00:00 GMT</pubDate><source url="https://bs.com">Business Standard</source></item>
<item><title>Blinkit store licence suspended after cockroaches found - Inc42</title><link>https://news.google.com/b</link>
<pubDate>Tue, 11 Aug 2026 10:00:00 GMT</pubDate><source url="https://inc42.com">Inc42</source></item>
<item><title>Gig workers call strike against Zomato over pay - The Hindu</title><link>https://news.google.com/c</link>
<pubDate>Wed, 24 Dec 2025 10:00:00 GMT</pubDate><source url="https://thehindu.com">The Hindu</source></item>
</channel></rss>"""

YAHOO = {"chart": {"result": [{"meta": {"symbol": "ETERNAL.NS", "currency": "INR"},
                               "timestamp": [1735689600 + 86400 * i for i in range(300)],
                               "indicators": {"quote": [{"close": [200 + i * 0.4 for i in range(300)]}]}}]}}

IG_JSON = {"data": {"user": {"edge_followed_by": {"count": 1200000}, "edge_follow": {"count": 50},
                             "edge_owner_to_timeline_media": {"count": 3000, "edges": [
                                 {"node": {"edge_liked_by": {"count": 5000}, "edge_media_to_comment": {"count": 120},
                                           "taken_at_timestamp": 1790000000,
                                           "edge_media_to_caption": {"edges": [{"node": {"text": "Happy new year from all of us!"}}]}}}]}}}}

IG_META = '<html><head><meta property="og:description" content="1.2M Followers, 50 Following, 3,000 Posts - See Instagram photos"></head></html>'

X_HTML = ('<html><script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": {"timeline": {"entries": [
    {"content": {"tweet": {"full_text": "We are proud of our delivery partners", "created_at": "Thu Jan 01 10:00:00 +0000 2026",
                           "favorite_count": 900, "reply_count": 300, "retweet_count": 50, "user": {"followers_count": 2500000}}}}]}}}}) + "</script></html>")


def test_rss():
    items = scrapers.parse_rss(RSS, "Google News")
    assert len(items) == 3
    assert items[0]["publisher"] == "Business Standard"
    assert items[0]["text"].endswith("125 crore")
    assert items[0]["date"] == "2026-10-21"


def test_yahoo():
    out = scrapers.parse_yahoo_chart(YAHOO)
    assert out["symbol"] == "ETERNAL.NS" and len(out["series"]) == 300


def test_instagram():
    a = scrapers.parse_instagram_json(IG_JSON)
    assert a["followers"] == 1200000 and a["recent_posts"][0]["likes"] == 5000
    b = scrapers.parse_instagram_meta(IG_META)
    assert b["followers"] == 1200000 and b["posts_total"] == 3000


def test_x():
    out = scrapers.parse_x_syndication(X_HTML)
    assert out["followers"] == 2500000 and out["tweets"][0]["likes"] == 900


def test_handles_and_ticker():
    assert scrapers.handle_from_link("https://www.instagram.com/zomato/", "instagram") == "zomato"
    assert scrapers.handle_from_link("https://x.com/zomato?lang=en", "x") == "zomato"
    assert scrapers.handle_from_link("@blinkit", "x") == "blinkit"
    assert scrapers.normalise_ticker("NSE:ETERNAL") == "ETERNAL.NS"
    assert scrapers.normalise_ticker("eternal.ns") == "ETERNAL.NS"


def _bundle():
    return {"inputs": {"company": "Eternal", "ticker": "ETERNAL.NS", "instagram": "zomato", "x": "zomato"},
            "collected_at": "test",
            "raw": {"google_news": scrapers.parse_rss(RSS, "Google News"), "bing_news": [], "reddit": [],
                    "stock": scrapers.parse_yahoo_chart(YAHOO),
                    "play_store": {"summary": {"app": "Zomato", "score": 4.5, "ratings": 100, "recent_avg": 3.1, "one_star_share": 0.31},
                                   "items": [{"text": "Refund not given, worst support", "rating": 1, "date": "2026-11-01", "source": "Google Play", "channel": "reviews"}]},
                    "instagram": scrapers.parse_instagram_json(IG_JSON), "x": scrapers.parse_x_syndication(X_HTML)},
            "status": {k: {"ok": True, "n": 1} for k in ["google_news", "bing_news", "reddit", "stock", "play_store", "instagram", "x"]}}


def test_engine():
    r = analyze(_bundle())
    assert 1 <= r["reptrak"]["score"] <= 5
    assert set(r["pulse"]["items"]) == {"Esteem", "Admire", "Trust", "Feel-good"}
    ids = {s["id"]: s for s in r["stakeholders"]}
    assert ids["frontline"]["status"] == "fired"
    assert ids["customers"]["status"] == "fired"  # 1-star share > 20%
    assert ids["operations"]["status"] == "fired"
    assert r["actionables"][0]["rank"] == 1
    assert any(c["cluster"] == "preventable" for c in r["crisis_radar"])
    assert r["digital"]["instagram"]["followers"] == 1200000


def test_api(monkeypatch):
    import app as webapp
    monkeypatch.setattr(webapp, "collect", lambda *a, **k: _bundle())
    c = webapp.app.test_client()
    assert c.get("/health").json["ok"]
    assert c.get("/").status_code == 200
    d = c.get("/api/demo").json
    assert d["demo"] and d["n_items"] == 58
    r = c.post("/api/analyze", json={"company": "Eternal", "ticker": "NSE:ETERNAL"})
    assert r.status_code == 200 and r.json["reptrak"]["score"]
    assert c.post("/api/analyze", json={"company": ""}).status_code == 400
