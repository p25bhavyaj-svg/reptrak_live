"""Builds data/eternal_demo.json by running the live engine on an offline snapshot of
Eternal Limited evidence compiled for the CCR live project (Dec 2025 - Nov 2026).

Snapshot contents (all from public reporting gathered for the project):
  - 58 dated news headlines (Business Standard topic pages, Inc42, Business Today, Deccan Herald,
    Siasat, The News Minute, YourStory, ThePrint, Outlook Business)
  - Google Play summary for Zomato: 4.57 stars, 14.1m ratings, ~17.8% 1-star share on recent builds (Quash, Sep 2026)
  - Indicative NSE share-price points reported in the press (Aug/Sep values derived from
    '+56%' and '+60% from March low' reports)
Instagram and X were not captured in the offline snapshot; run the live analysis for those.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reptrak.engine import analyze  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
SNAP = os.path.join(HERE, "eternal_snapshot.json")
OUT = os.path.join(os.path.dirname(HERE), "data", "eternal_demo.json")

snap = json.load(open(SNAP, encoding="utf-8"))
news = [{"text": n["h"], "date": n["date"], "source": "Google News", "publisher": n.get("pub", ""),
         "url": None, "channel": "news"} for n in snap["headlines"]]
bundle = {
    "inputs": {"company": "Eternal (Zomato / Blinkit)", "ticker": "ETERNAL.NS", "instagram": "zomato", "x": "zomato"},
    "collected_at": "2026-11-25 (offline snapshot)",
    "demo": True,
    "note": ("Saved demo: offline snapshot of 58 dated headlines (Dec-25 to Nov-26), Google Play summary and "
             "indicative share-price points compiled for the CCR live project. Instagram and X were not captured "
             "offline; press 'Run live analysis' for current data from all sources."),
    "raw": {
        "google_news": news, "bing_news": [], "reddit": [],
        "stock": {"symbol": "ETERNAL.NS", "currency": "INR", "indicative": True, "series": snap["stock_points"]},
        "play_store": {"summary": snap["play_summary"], "items": []},
        "instagram": None, "x": None,
    },
    "status": {
        "google_news": {"ok": True, "n": len(news), "note": "offline snapshot"},
        "bing_news": {"ok": False, "error": "not used in offline snapshot"},
        "reddit": {"ok": False, "error": "not captured in offline snapshot"},
        "stock": {"ok": True, "n": len(snap["stock_points"]), "note": "indicative press-reported points"},
        "play_store": {"ok": True, "n": 0, "note": "summary only (rating, 1-star share)"},
        "instagram": {"ok": False, "error": "not captured in offline snapshot"},
        "x": {"ok": False, "error": "not captured in offline snapshot"},
    },
}
res = analyze(bundle)
json.dump(res, open(OUT, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("RepTrak", res["reptrak"]["score"], "Pulse", res["pulse"]["score"], "Stakeholder index", res["stakeholder_index"],
      "items", res["n_items"], "actionables", len(res["actionables"]))
for d, v in res["reptrak"]["dimensions"].items():
    print(f"  {d:22s} {v['score']}  n={v['n']}")
for s in res["stakeholders"]:
    print(f"  {s['name']:28s} {s['status']:6s} tone={s['tone']} n={s['n']} {s['reasons']}")
