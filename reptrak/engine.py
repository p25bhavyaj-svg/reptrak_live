"""Scoring engine: turns scraped items into a RepTrak-style reputation profile and
toolkit actionables.

Method (transparent and reproducible):
  1. Every text item (headline, post, review, tweet) gets a sentiment score in [-1, 1]
     (VADER with a business/finance lexicon extension).
  2. Items are tagged to the 7 RepTrak dimensions, 8 toolkit stakeholders and media frames by
     keyword rules. One item can carry several tags.
  3. Dimension score (1-5) = 3 + 2 x mean sentiment x n/(n+4)  (shrinks small samples to neutral).
     Performance blends media tone with share-price momentum; Products & Services blends media
     tone with app-store rating.
  4. RepTrak score = weighted mean of dimensions; Pulse = esteem, admire, trust, feel-good.
  5. Stakeholder index uses the toolkit scorecard weights; triggers from the playbook generate
     prioritised actionables, with SCCT crisis classification of negative issues.
"""
import re
from collections import defaultdict, Counter
from statistics import mean, pstdev

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from .toolkit import STAKEHOLDERS, SCCT, RECOMMENDATIONS

_an = SentimentIntensityAnalyzer()
_an.lexicon.update({
    "surge": 2.0, "surges": 2.0, "soars": 2.2, "soar": 2.0, "jumps": 1.6, "jump": 1.2, "rally": 1.6, "rallies": 1.6,
    "zooms": 1.8, "upgrade": 1.6, "upgrades": 1.6, "beats": 1.4, "record": 1.0, "outperform": 1.5, "bullish": 1.8,
    "profit": 0.8, "profitable": 1.4, "feasible": 1.2, "dismisses": 2.4, "dismissed": 2.2, "junks": 2.0, "growth": 0.9, "expansion": 0.7, "wins": 1.5, "upside": 1.2,
    "plunge": -2.4, "plunges": -2.4, "slump": -2.0, "slumps": -2.0, "tanks": -2.2, "tank": -1.8, "falls": -1.3,
    "fall": -1.0, "slips": -1.1, "drops": -1.2, "cut": -0.9, "cuts": -1.0, "probe": -1.6, "penalty": -1.8,
    "strike": -1.6, "strikes": -1.4, "suspended": -2.0, "suspends": -2.0, "layoffs": -2.2, "layoff": -2.2,
    "lawsuit": -1.6, "ban": -1.4, "bans": -0.6, "misses": -1.6, "downgrade": -1.8, "backlash": -2.2, "boycott": -2.2,
    "violation": -2.0, "violations": -2.0, "fraud": -3.0, "outage": -1.6, "glitch": -1.3, "expired": -1.6,
    "cockroach": -2.6, "cockroaches": -2.6, "unhygienic": -2.4, "exploitation": -2.6, "exploited": -2.4,
    "miscreants": -1.8, "notice": -0.6, "demand": -0.3, "hike": -0.8, "hikes": -0.8, "levies": -0.8,
    "withdrawn": -1.0, "shuts": -1.4, "shut": -1.2, "job": 0.0, "shortage": -1.4, "low": -0.8, "worst": -2.5, "scam": -2.8, "refund": -0.6,
})

DIMENSIONS = {
    "Products & Services": (0.16, ["product", "products", "service", "quality", "delivery", "deliveries", "order",
                                   "orders", "price", "fee", "fees", "refund", "rating", "review", "hygiene",
                                   "food safety", "expired", "outage", "glitch", "customer", "app", "menu", "dish"]),
    "Innovation": (0.13, ["launch", "launches", "innovation", "innovative", "ai", "technology", "tech", "feature",
                          "pilot", "patent", "new service", "drone", "wearable", "first-of-its-kind", "platform"]),
    "Workplace": (0.14, ["employee", "employees", "staff", "layoff", "layoffs", "jobs", "hiring", "union", "strike",
                         "gig", "rider", "riders", "delivery partner", "delivery partners", "wages", "salary",
                         "workplace", "workers", "worker", "esop", "culture", "attrition"]),
    "Governance": (0.14, ["board", "governance", "audit", "sebi", "probe", "cci", "fraud", "compliance",
                          "disclosure", "resign", "resigns", "steps down", "tax", "gst", "penalty", "lawsuit",
                          "court", "antitrust", "regulator", "notice", "price parity", "ethics", "transparency"]),
    "Citizenship": (0.15, ["csr", "esg", "sustainab", "climate", "carbon", "electric", "ev", "community",
                           "donat", "charity", "social", "environment", "plastic", "emission", "feeding",
                           "healthy", "safety of", "welfare"]),
    "Leadership": (0.14, ["ceo", "founder", "chairman", "leadership", "management", "vision", "strategy",
                          "chief executive", "md", "vice chairman", "succession"]),
    "Performance": (0.14, ["profit", "revenue", "earnings", "quarter", "q1", "q2", "q3", "q4", "ebitda", "margin",
                           "shares", "stock", "market cap", "valuation", "target price", "brokerage", "growth",
                           "loss", "results", "buy rating", "rating", "upside"]),
}

FRAMES = {
    "Financial/Market": ["profit", "revenue", "earnings", "shares", "stock", "target", "brokerage", "q1", "q2", "q3",
                         "q4", "ebitda", "valuation", "market cap", "rally", "results"],
    "Regulation/Legal": ["cci", "court", "probe", "gst", "tax", "notice", "penalty", "ministry", "rules", "regulator",
                         "parity", "law", "sebi", "antitrust"],
    "Labour/Workforce": ["gig", "rider", "riders", "strike", "union", "workers", "delivery partner", "layoff",
                         "jobs", "employees", "wages"],
    "ESG/Purpose": ["esg", "ev", "electric", "climate", "sustainab", "csr", "healthy", "feeding", "carbon"],
    "Leadership/Governance": ["ceo", "founder", "steps down", "board", "chairman", "governance"],
    "Consumer/Pricing": ["fee", "fees", "price", "pricing", "customers", "refund", "cash on delivery", "subscription"],
    "Product safety": ["fda", "fssai", "hygiene", "expired", "cockroach", "food safety", "licence", "license", "recall"],
    "Competition": ["competition", "competitive", "rival", "swiggy", "zepto", "amazon", "flipkart", "market share"],
}
FINANCIAL_FRAMES = {"Financial/Market"}


def _has(text, kw):
    """Word-start match; short keywords (<=4 chars) also need a word end, longer ones allow stems/plurals."""
    kw = kw.lower().strip()
    end = r"(?![a-z0-9])" if len(kw) <= 4 else ""
    return re.search(r"(?<![a-z0-9])" + re.escape(kw) + end, text) is not None


def sentiment(text):
    return _an.polarity_scores(text)["compound"]


def tag(item):
    t = " " + (item.get("text") or "").lower() + " "
    item["dims"] = [d for d, (_, kws) in DIMENSIONS.items() if any(_has(t, k) for k in kws)]
    item["stakeholders"] = [s["id"] for s in STAKEHOLDERS if any(_has(t, k) for k in s["keywords"])]
    fr = [f for f, kws in FRAMES.items() if any(_has(t, k) for k in kws)]
    item["frame"] = fr[0] if fr else "Other"
    item["frames"] = fr
    cl = None
    for cluster in ("victim", "preventable", "accidental"):
        if item["sentiment"] <= -0.05 and any(_has(t, c) for c in SCCT[cluster]["cues"]):
            cl = cluster
            break
    item["crisis"] = cl
    return item


def shrink_score(vals, k=4):
    if not vals:
        return None
    n = len(vals)
    return max(1.0, min(5.0, 3 + 2 * mean(vals) * n / (n + k)))


def stock_metrics(stock):
    if not stock or not stock.get("series"):
        return None
    from datetime import date, timedelta
    pts = [(date.fromisoformat(d), p) for d, p in stock["series"]]
    s = [p for _, p in pts]
    last_d, last = pts[-1]

    def price_at(days_back):
        target = last_d - timedelta(days=days_back)
        prior = [p for d, p in pts if d <= target]
        return prior[-1] if prior else pts[0][1]
    r1y = last / pts[0][1] - 1
    r3m = last / price_at(91) - 1
    r1m = last / price_at(30) - 1
    dd = last / max(s) - 1
    daily = [s[i] / s[i - 1] - 1 for i in range(1, len(s))]
    vol = pstdev(daily) * (252 ** 0.5) if len(daily) > 20 else None
    score = 3 + max(-1.0, min(1.0, r1y / 0.5)) + 0.6 * max(-1.0, min(1.0, r3m / 0.25))
    return {"last": last, "last_date": last_d.isoformat(), "r1y": round(r1y, 4), "r3m": round(r3m, 4),
            "r1m": round(r1m, 4), "drawdown_from_peak": round(dd, 4), "volatility": round(vol, 3) if vol else None,
            "market_score": round(max(1.0, min(5.0, score)), 2), "currency": stock.get("currency"),
            "indicative": stock.get("indicative", False)}


def analyze(bundle):
    company = bundle["inputs"]["company"]
    raw = bundle["raw"]
    status = bundle["status"]

    # ---------- assemble items
    items, seen = [], set()
    for key in ("google_news", "bing_news"):
        for it in raw.get(key) or []:
            k = re.sub(r"\W+", " ", it["text"].lower()).strip()[:90]
            if k in seen:
                continue
            seen.add(k)
            items.append(it)
    for it in raw.get("reddit") or []:
        items.append(it)
    play = raw.get("play_store") or {}
    for it in (play.get("items") or []):
        it["channel"] = "reviews"
        items.append(it)
    xr = raw.get("x") or {}
    for tw in (xr.get("tweets") or []):
        items.append({"text": tw["text"], "date": tw.get("date"), "source": "X", "publisher": "@" + (bundle["inputs"].get("x") or ""),
                      "channel": "owned_social", "engagement": tw.get("likes", 0) + tw.get("replies", 0)})
    ig = raw.get("instagram") or {}
    for p in (ig.get("recent_posts") or []):
        if p.get("caption"):
            items.append({"text": p["caption"], "date": p.get("date"), "source": "Instagram",
                          "publisher": "@" + (bundle["inputs"].get("instagram") or ""), "channel": "owned_social",
                          "engagement": (p.get("likes") or 0) + (p.get("comments") or 0)})
    for it in items:
        it["sentiment"] = round(sentiment(it["text"]), 3)
        tag(it)

    earned = [i for i in items if i["channel"] in ("news", "social")]
    reviews = [i for i in items if i["channel"] == "reviews"]
    owned = [i for i in items if i["channel"] == "owned_social"]

    # ---------- RepTrak dimensions (earned media + community + reviews; owned posts excluded)
    judged = earned + reviews
    dim_out = {}
    sm = stock_metrics(raw.get("stock"))
    for d, (w, _) in DIMENSIONS.items():
        vals = [i["sentiment"] for i in judged if d in i["dims"]]
        media = shrink_score(vals)
        score, basis = media, "media & community tone"
        if d == "Performance" and sm:
            score = sm["market_score"] if media is None else 0.5 * media + 0.5 * sm["market_score"]
            basis = "media tone (50%) + share-price momentum (50%)"
        if d == "Products & Services" and play.get("summary", {}).get("score"):
            rating = play["summary"].get("recent_avg") or play["summary"]["score"]
            score = rating if media is None else 0.5 * media + 0.5 * rating
            basis = "media tone (50%) + app-store rating (50%)"
        ev = sorted([i for i in judged if d in i["dims"]], key=lambda x: x["sentiment"])
        dim_out[d] = {"score": round(score, 2) if score is not None else None, "weight": w, "n": len(vals),
                      "tone": round(mean(vals), 3) if vals else None, "basis": basis,
                      "worst": [_brief(x) for x in ev[:3]], "best": [_brief(x) for x in ev[-3:][::-1]]}
    avail = {d: v for d, v in dim_out.items() if v["score"] is not None}
    wsum = sum(v["weight"] for v in avail.values()) or 1
    rep = round(sum(v["score"] * v["weight"] for v in avail.values()) / wsum, 2) if avail else None

    # ---------- Pulse
    def dscore(d):
        return dim_out[d]["score"] if dim_out[d]["score"] is not None else 3.0
    crisis_items = [i for i in judged if i["crisis"]]
    prev_share = sum(1 for i in crisis_items if i["crisis"] == "preventable") / max(1, len(judged))
    social_vals = [i["sentiment"] for i in items if i["channel"] in ("social", "reviews")]
    pulse = {
        "Esteem": rep if rep is not None else 3.0,
        "Admire": round(mean([dscore("Performance"), dscore("Innovation"), dscore("Leadership")]), 2),
        "Trust": round(max(1.0, mean([dscore("Governance"), dscore("Workplace"), dscore("Citizenship")]) - 2 * prev_share), 2),
        "Feel-good": round(shrink_score(social_vals) or 3.0, 2),
    }
    pulse_score = round(mean(pulse.values()), 2)

    # ---------- frames & two-track
    fr = defaultdict(lambda: [0, 0, 0])
    for i in earned:
        idx = 0 if i["sentiment"] <= -0.05 else (2 if i["sentiment"] >= 0.05 else 1)
        fr[i["frame"]][idx] += 1
    fin = [i for i in earned if i["frame"] in FINANCIAL_FRAMES]
    nonfin = [i for i in earned if i["frame"] not in FINANCIAL_FRAMES and i["frame"] != "Other"]
    two_track = {
        "financial_n": len(fin), "nonfinancial_n": len(nonfin),
        "financial_positive_share": round(sum(1 for i in fin if i["sentiment"] >= 0.05) / len(fin), 3) if fin else None,
        "nonfinancial_negative_share": round(sum(1 for i in nonfin if i["sentiment"] <= -0.05) / len(nonfin), 3) if nonfin else None,
        "financial_tone": round(mean([i["sentiment"] for i in fin]), 3) if fin else None,
        "nonfinancial_tone": round(mean([i["sentiment"] for i in nonfin]), 3) if nonfin else None,
    }

    # ---------- monthly tone
    mt = defaultdict(list)
    for i in earned:
        if i.get("date"):
            mt[i["date"][:7]].append(i["sentiment"])
    monthly = [{"month": m, "tone": round(mean(v), 3), "n": len(v)} for m, v in sorted(mt.items())]

    # ---------- stakeholders & toolkit
    stake = []
    for s in STAKEHOLDERS:
        its = [i for i in judged if s["id"] in i["stakeholders"]]
        vals = [i["sentiment"] for i in its]
        tone = mean(vals) if vals else None
        score = shrink_score(vals) or 3.0
        neg = sorted([i for i in its if i["sentiment"] <= -0.05], key=lambda x: x["sentiment"])
        crisis_hits = [i for i in its if any(w in i["text"].lower() for w in s["crisis_words"]) and i["sentiment"] < 0]
        fired, reasons = _trigger(s, its, tone, crisis_hits, sm, play, two_track)
        status_s = "fired" if fired else ("watch" if (tone is not None and tone < 0) else "ok")
        stake.append({"id": s["id"], "name": s["name"], "example": s["example"], "salience": s["salience"],
                      "weight": s["weight"], "n": len(its), "tone": round(tone, 3) if tone is not None else None,
                      "score": round(score, 2), "status": status_s, "reasons": reasons,
                      "channel": s["channel"], "message": s["message"], "trigger": s["trigger"],
                      "response": s["response"], "kpi": s["kpi"], "owner": s["owner"],
                      "recommendation": RECOMMENDATIONS.get(s["id"]),
                      "evidence": [_brief(x) for x in neg[:4]]})
    stake_index = round(sum(x["score"] * x["weight"] for x in stake) / 100, 2)

    # ---------- crisis radar (SCCT)
    clusters = defaultdict(list)
    for i in crisis_items:
        clusters[i["crisis"]].append(i)
    radar = []
    for cl in ("preventable", "accidental", "victim"):
        its = sorted(clusters.get(cl, []), key=lambda x: x["sentiment"])
        if its:
            radar.append({"cluster": cl, "n": len(its), "response": SCCT[cl]["response"], "posture": SCCT[cl]["posture"],
                          "items": [_brief(x) for x in its[:6]]})

    # ---------- actionables (prioritised)
    sev = {"fired": 3, "watch": 1.5, "ok": 0}
    acts = []
    for x in stake:
        if x["status"] == "ok":
            continue
        cl = None
        for c in ("preventable", "accidental", "victim"):
            if any(e["text"] in [y["text"] for y in clusters.get(c, [])] for e in x["evidence"]):
                cl = c
                break
        pr = round(x["weight"] * sev[x["status"]] * (1 + max(0, -(x["tone"] or 0))), 1)
        acts.append({"stakeholder": x["name"], "status": x["status"], "priority": pr,
                     "why": "; ".join(x["reasons"]) or f"net tone {x['tone']}",
                     "do": x["response"], "channel": x["channel"], "frame": x["message"],
                     "scct": cl, "scct_response": SCCT[cl]["response"] if cl else None,
                     "kpi": x["kpi"], "owner": x["owner"], "recommendation": x["recommendation"],
                     "evidence": x["evidence"][:2]})
    acts.sort(key=lambda a: -a["priority"])
    for k, a in enumerate(acts):
        a["rank"] = k + 1
        a["horizon"] = "0-30 days" if a["status"] == "fired" and k < 3 else ("1-3 months" if a["status"] == "fired" else "3-6 months")

    # ---------- reality check: perception (media/community) vs operating proxies
    reality = []
    if sm:
        reality.append({"proxy": "Share-price momentum", "value": sm["market_score"],
                        "perception": dim_out["Performance"]["score"]})
    if play.get("summary", {}).get("score"):
        reality.append({"proxy": "App-store rating", "value": play["summary"].get("recent_avg") or play["summary"]["score"],
                        "perception": dim_out["Products & Services"]["score"]})

    # ---------- digital presence
    digital = {}
    if ig:
        posts = ig.get("recent_posts") or []
        eng = [(p.get("likes") or 0) + (p.get("comments") or 0) for p in posts]
        digital["instagram"] = {"followers": ig.get("followers"), "posts_total": ig.get("posts_total"),
                                "avg_engagement": round(mean(eng)) if eng else None,
                                "engagement_rate": round(mean(eng) / ig["followers"], 5) if eng and ig.get("followers") else None,
                                "caption_tone": round(mean([sentiment(p["caption"]) for p in posts if p.get("caption")]), 3) if posts else None}
    if xr:
        tw = xr.get("tweets") or []
        digital["x"] = {"followers": xr.get("followers"), "tweets_sampled": len(tw),
                        "avg_engagement": round(mean([t.get("likes", 0) + t.get("replies", 0) + t.get("retweets", 0) for t in tw])) if tw else None,
                        "tone": round(mean([sentiment(t["text"]) for t in tw]), 3) if tw else None}

    counts = Counter(i["source"] for i in items)
    return {
        "company": company, "inputs": bundle["inputs"], "collected_at": bundle.get("collected_at"),
        "demo": bundle.get("demo", False), "note": bundle.get("note"),
        "status": status, "counts": dict(counts), "n_items": len(items),
        "reptrak": {"score": rep, "band": _band(rep), "dimensions": dim_out},
        "pulse": {"score": pulse_score, "items": pulse, "band": _band(pulse_score)},
        "stakeholder_index": stake_index, "stakeholders": stake, "actionables": acts,
        "crisis_radar": radar, "frames": {k: {"negative": v[0], "neutral": v[1], "positive": v[2]} for k, v in fr.items()},
        "two_track": two_track, "monthly_tone": monthly, "stock": sm,
        "stock_series": (raw.get("stock") or {}).get("series", []), "play": play.get("summary"),
        "digital": digital, "reality_check": reality,
        "items": [_brief(i, full=True) for i in sorted(items, key=lambda x: x.get("date") or "", reverse=True)[:250]],
    }


def _trigger(s, its, tone, crisis_hits, sm, play, two_track):
    reasons = []
    sid = s["id"]
    if tone is not None and tone < -0.2 and len(its) >= 3:
        reasons.append(f"net tone {tone:+.2f} across {len(its)} items")
    if sid == "frontline" and any(re.search(r"strike|protest|union", i["text"].lower()) for i in its):
        reasons.append("strike / protest / union coverage")
    if sid == "customers" and play.get("summary", {}).get("one_star_share") and play["summary"]["one_star_share"] > 0.2:
        reasons.append(f"1-star share {play['summary']['one_star_share']:.0%} of recent reviews")
    if sid == "operations" and crisis_hits:
        reasons.append(f"{len(crisis_hits)} safety / inspection items")
    if sid == "investors" and sm and sm["r3m"] < -0.15:
        reasons.append(f"share price {sm['r3m']:+.0%} over 3 months")
    if sid == "regulators" and len([i for i in its if i["sentiment"] < 0]) >= 2:
        reasons.append(f"{len([i for i in its if i['sentiment'] < 0])} negative regulatory items")
    if sid == "media" and two_track.get("nonfinancial_tone") is not None and two_track["nonfinancial_tone"] < -0.3:
        reasons.append(f"non-financial tone {two_track['nonfinancial_tone']:+.2f}")
    if sid == "employees" and any(re.search(r"layoff|lay off|job cuts", i["text"].lower()) for i in its):
        reasons.append("layoff / job-cut coverage")
    if sid == "partners" and any(re.search(r"boycott|antitrust|cci|parity|commission", i["text"].lower()) for i in its if i["sentiment"] < 0):
        reasons.append("boycott / antitrust / commission dispute")
    if len(crisis_hits) >= 2 and (tone or 0) < 0 and sid != "operations" and not reasons:
        reasons.append(f"{len(crisis_hits)} crisis-cue items")
    return bool(reasons), reasons


def _band(x):
    if x is None:
        return "insufficient data"
    if x >= 4.0:
        return "Strong"
    if x >= 3.5:
        return "Robust"
    if x >= 3.0:
        return "Average"
    if x >= 2.5:
        return "Weak"
    return "Poor"


def _brief(i, full=False):
    b = {"text": i["text"][:220], "date": i.get("date"), "source": i.get("source"),
         "publisher": i.get("publisher"), "url": i.get("url"), "sentiment": i.get("sentiment")}
    if full:
        b.update({"dims": i.get("dims"), "stakeholders": i.get("stakeholders"), "frame": i.get("frame"),
                  "crisis": i.get("crisis"), "channel": i.get("channel")})
    return b
