"""Live data collection by direct web scraping (no third-party scraping services).

Every collector is best-effort: it returns (data, status) and never raises, so one blocked
source does not stop the analysis. Sources:
  - Google News RSS (news headlines)
  - Bing News RSS (fallback / additional headlines)
  - Reddit public JSON search (online community posts)
  - Yahoo Finance chart endpoint (share price, 1 year)
  - Google Play Store (app rating + recent reviews, via the google-play-scraper library)
  - Instagram public profile endpoint / page meta tags
  - X (Twitter) public syndication timeline
"""
import json
import re
import html
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlparse
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
MOBILE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
             "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
TIMEOUT = 12


def _get(url, headers=None, timeout=TIMEOUT):
    h = {"User-Agent": UA, "Accept-Language": "en-IN,en;q=0.9"}
    if headers:
        h.update(headers)
    return requests.get(url, headers=h, timeout=timeout)


def _iso(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


def handle_from_link(link, platform):
    """Accepts a full URL, @handle or plain handle; returns the bare handle."""
    if not link:
        return None
    link = link.strip()
    if link.startswith("@"):
        return link[1:]
    if "://" not in link and "/" not in link:
        return link
    if "://" not in link:
        link = "https://" + link
    path = [p for p in urlparse(link).path.split("/") if p]
    if not path:
        return None
    h = path[0]
    if h in ("i", "intent", "home", "explore", "p", "reel"):
        return None
    return h.lstrip("@")


def normalise_ticker(t):
    """'NSE:ETERNAL' -> 'ETERNAL.NS'; 'BSE:543320' -> '543320.BO'; otherwise unchanged."""
    if not t:
        return None
    t = t.strip().upper()
    if ":" in t:
        ex, sym = t.split(":", 1)
        suffix = {"NSE": ".NS", "BSE": ".BO", "LON": ".L", "TYO": ".T", "HKG": ".HK"}.get(ex, "")
        return sym + suffix
    return t


# ----------------------------------------------------------------- news
def parse_rss(xml_text, source_label):
    items = []
    root = ET.fromstring(xml_text)
    for it in root.iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        pub = it.findtext("pubDate")
        src = it.findtext("source") or ""
        date = None
        if pub:
            try:
                date = _iso(parsedate_to_datetime(pub))
            except Exception:
                date = None
        # Google News appends " - Publisher" to titles
        publisher = src.strip()
        if not publisher and " - " in title:
            publisher = title.rsplit(" - ", 1)[1]
        if publisher and title.endswith(" - " + publisher):
            title = title[: -len(" - " + publisher)]
        if title:
            items.append({"text": html.unescape(title), "url": link, "date": date,
                          "source": source_label, "publisher": publisher, "channel": "news"})
    return items


def google_news(company, days=180):
    q = quote_plus(f'"{company}" when:{days}d')
    url = f"https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        r = _get(url)
        r.raise_for_status()
        items = parse_rss(r.text, "Google News")
        return items, {"ok": True, "n": len(items)}
    except Exception as e:
        return [], {"ok": False, "error": str(e)[:160]}


def bing_news(company):
    url = f"https://www.bing.com/news/search?q={quote_plus(company)}&format=rss"
    try:
        r = _get(url)
        r.raise_for_status()
        items = parse_rss(r.text, "Bing News")
        return items, {"ok": True, "n": len(items)}
    except Exception as e:
        return [], {"ok": False, "error": str(e)[:160]}


# ----------------------------------------------------------------- reddit
def reddit(company, limit=100):
    url = f"https://www.reddit.com/search.json?q={quote_plus(chr(34) + company + chr(34))}&sort=new&t=year&limit={limit}"
    try:
        r = _get(url, headers={"User-Agent": "reptrak-live/1.0 (academic reputation research)"})
        r.raise_for_status()
        data = r.json()
        items = []
        for ch in data.get("data", {}).get("children", []):
            d = ch.get("data", {})
            text = (d.get("title") or "") + ". " + (d.get("selftext") or "")[:400]
            items.append({"text": text.strip(), "url": "https://www.reddit.com" + d.get("permalink", ""),
                          "date": _iso(datetime.fromtimestamp(d.get("created_utc", time.time()), tz=timezone.utc)),
                          "source": "Reddit", "publisher": "r/" + d.get("subreddit", ""), "channel": "social",
                          "engagement": d.get("score", 0) + d.get("num_comments", 0)})
        return items, {"ok": True, "n": len(items)}
    except Exception as e:
        return [], {"ok": False, "error": str(e)[:160]}


# ----------------------------------------------------------------- stock
def parse_yahoo_chart(data):
    res = data["chart"]["result"][0]
    ts = res.get("timestamp") or []
    closes = res["indicators"]["quote"][0].get("close") or []
    pts = [(datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"), round(c, 2))
           for t, c in zip(ts, closes) if c is not None]
    meta = res.get("meta", {})
    return {"symbol": meta.get("symbol"), "currency": meta.get("currency"), "series": pts}


def stock(ticker):
    if not ticker:
        return None, {"ok": False, "error": "no ticker given"}
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote_plus(ticker)}?range=1y&interval=1d"
    try:
        r = _get(url)
        r.raise_for_status()
        out = parse_yahoo_chart(r.json())
        if len(out["series"]) < 5:
            raise ValueError("too few price points")
        return out, {"ok": True, "n": len(out["series"])}
    except Exception as e:
        return None, {"ok": False, "error": str(e)[:160]}


# ----------------------------------------------------------------- play store
def play_store(company, country="in", n_reviews=150):
    try:
        from google_play_scraper import search, reviews, Sort, app as app_details
        hits = search(company, lang="en", country=country, n_hits=5) or []
        hits = [h for h in hits if h.get("appId")]
        if not hits:
            raise ValueError("no app found")
        cl = company.lower()
        hits.sort(key=lambda h: (cl not in (h.get("title") or "").lower(), cl not in (h.get("developer") or "").lower()))
        top = hits[0]
        det = app_details(top["appId"], lang="en", country=country)
        revs, _ = reviews(top["appId"], lang="en", country=country, sort=Sort.NEWEST, count=n_reviews)
        items = [{"text": rv.get("content") or "", "date": _iso(rv.get("at")), "source": "Google Play",
                  "publisher": det.get("title"), "channel": "reviews", "rating": rv.get("score")}
                 for rv in revs if rv.get("content")]
        stars = [rv.get("score") for rv in revs if rv.get("score")]
        summary = {"app": det.get("title"), "appId": top["appId"], "score": det.get("score"),
                   "ratings": det.get("ratings"),
                   "recent_avg": round(sum(stars) / len(stars), 2) if stars else None,
                   "one_star_share": round(sum(1 for s in stars if s == 1) / len(stars), 3) if stars else None}
        return {"summary": summary, "items": items}, {"ok": True, "n": len(items)}
    except Exception as e:
        return None, {"ok": False, "error": str(e)[:160]}


# ----------------------------------------------------------------- instagram
def parse_instagram_json(data):
    u = data["data"]["user"]
    edges = u.get("edge_owner_to_timeline_media", {}).get("edges", [])
    posts = []
    for e in edges[:12]:
        n = e.get("node", {})
        cap = ""
        ce = n.get("edge_media_to_caption", {}).get("edges", [])
        if ce:
            cap = ce[0].get("node", {}).get("text", "")
        posts.append({"likes": n.get("edge_liked_by", {}).get("count") or n.get("edge_media_preview_like", {}).get("count", 0),
                      "comments": n.get("edge_media_to_comment", {}).get("count", 0),
                      "caption": cap[:300],
                      "date": _iso(datetime.fromtimestamp(n.get("taken_at_timestamp", 0), tz=timezone.utc)) if n.get("taken_at_timestamp") else None})
    return {"followers": u.get("edge_followed_by", {}).get("count"),
            "following": u.get("edge_follow", {}).get("count"),
            "posts_total": u.get("edge_owner_to_timeline_media", {}).get("count"),
            "recent_posts": posts}


def parse_count(s):
    s = s.replace(",", "").strip().upper()
    m = re.match(r"([\d.]+)\s*([KMB]?)", s)
    if not m:
        return None
    v = float(m.group(1))
    return int(v * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)])


def parse_instagram_meta(page_html):
    soup = BeautifulSoup(page_html, "html.parser")
    tag = soup.find("meta", attrs={"property": "og:description"}) or soup.find("meta", attrs={"name": "description"})
    if not tag:
        raise ValueError("no profile meta found")
    d = tag.get("content", "")
    m = re.search(r"([\d.,]+[KMB]?)\s+Followers,\s*([\d.,]+[KMB]?)\s+Following,\s*([\d.,]+[KMB]?)\s+Posts", d, re.I)
    if not m:
        raise ValueError("profile counts not in meta")
    return {"followers": parse_count(m.group(1)), "following": parse_count(m.group(2)),
            "posts_total": parse_count(m.group(3)), "recent_posts": []}


def instagram(handle):
    if not handle:
        return None, {"ok": False, "error": "no handle given"}
    try:
        r = _get(f"https://i.instagram.com/api/v1/users/web_profile_info/?username={handle}",
                 headers={"x-ig-app-id": "936619743392459", "User-Agent": MOBILE_UA})
        if r.status_code == 200:
            out = parse_instagram_json(r.json())
            return out, {"ok": True, "n": len(out["recent_posts"]), "method": "profile endpoint"}
    except Exception:
        pass
    try:
        r = _get(f"https://www.instagram.com/{handle}/")
        r.raise_for_status()
        out = parse_instagram_meta(r.text)
        return out, {"ok": True, "n": 0, "method": "page meta"}
    except Exception as e:
        return None, {"ok": False, "error": "Instagram blocked anonymous access (" + str(e)[:100] + ")"}


# ----------------------------------------------------------------- x / twitter
def parse_x_syndication(page_html):
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', page_html, re.S)
    if not m:
        raise ValueError("timeline data not found")
    data = json.loads(m.group(1))
    entries = data["props"]["pageProps"]["timeline"]["entries"]
    tweets, followers = [], None
    for e in entries:
        tw = (e.get("content") or {}).get("tweet")
        if not tw:
            continue
        user = tw.get("user", {})
        followers = followers or user.get("followers_count")
        created = None
        try:
            created = _iso(datetime.strptime(tw.get("created_at", ""), "%a %b %d %H:%M:%S %z %Y"))
        except Exception:
            pass
        tweets.append({"text": tw.get("full_text") or tw.get("text") or "", "date": created,
                       "likes": tw.get("favorite_count", 0), "replies": tw.get("reply_count", 0),
                       "retweets": tw.get("retweet_count", 0)})
    return {"followers": followers, "tweets": tweets}


def x_profile(handle):
    if not handle:
        return None, {"ok": False, "error": "no handle given"}
    try:
        r = _get(f"https://syndication.twitter.com/srv/timeline-profile/screen-name/{handle}")
        r.raise_for_status()
        out = parse_x_syndication(r.text)
        return out, {"ok": True, "n": len(out["tweets"])}
    except Exception as e:
        return None, {"ok": False, "error": "X blocked anonymous access (" + str(e)[:100] + ")"}


def x_mentions_via_news(company):
    """Fallback: public conversation about the company on X as indexed by Google News."""
    return google_news(f"{company} twitter OR X post", days=60)


# ----------------------------------------------------------------- orchestrator
def collect(company, ticker=None, instagram_link=None, x_link=None):
    from concurrent.futures import ThreadPoolExecutor
    ig_handle = handle_from_link(instagram_link, "instagram")
    x_handle = handle_from_link(x_link, "x")
    yticker = normalise_ticker(ticker)
    jobs = {
        "google_news": (google_news, (company,)),
        "bing_news": (bing_news, (company,)),
        "reddit": (reddit, (company,)),
        "stock": (stock, (yticker,)),
        "play_store": (play_store, (company,)),
        "instagram": (instagram, (ig_handle,)),
        "x": (x_profile, (x_handle,)),
    }
    out, status = {}, {}
    with ThreadPoolExecutor(max_workers=7) as ex:
        futs = {k: ex.submit(f, *a) for k, (f, a) in jobs.items()}
        for k, f in futs.items():
            try:
                out[k], status[k] = f.result(timeout=40)
            except Exception as e:
                out[k], status[k] = None, {"ok": False, "error": str(e)[:160]}
    return {"inputs": {"company": company, "ticker": yticker, "instagram": ig_handle, "x": x_handle},
            "raw": out, "status": status,
            "collected_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}
