import json
import os
import time
import threading

from flask import Flask, jsonify, render_template, request

from reptrak.scrapers import collect
from reptrak.engine import analyze
from reptrak.toolkit import STAKEHOLDERS, SCCT

app = Flask(__name__)
BASE = os.path.dirname(os.path.abspath(__file__))
DEMO_PATH = os.path.join(BASE, "data", "eternal_demo.json")
CACHE_TTL = int(os.environ.get("CACHE_TTL", 1800))
_cache, _lock = {}, threading.Lock()


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/api/demo")
def demo():
    with open(DEMO_PATH, encoding="utf-8") as f:
        return jsonify(json.load(f))


@app.get("/api/toolkit")
def toolkit():
    return jsonify({"stakeholders": [{k: v for k, v in s.items() if k not in ("keywords", "crisis_words")} for s in STAKEHOLDERS],
                    "scct": {k: {"response": v["response"], "posture": v["posture"]} for k, v in SCCT.items()}})


@app.post("/api/analyze")
def run():
    body = request.get_json(force=True, silent=True) or {}
    company = (body.get("company") or "").strip()
    if len(company) < 2:
        return jsonify({"error": "Enter a company name."}), 400
    key = json.dumps([company.lower(), (body.get("ticker") or "").upper(), body.get("instagram"), body.get("x")])
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_TTL:
            return jsonify(hit[1])
    bundle = collect(company, body.get("ticker"), body.get("instagram"), body.get("x"))
    result = analyze(bundle)
    if result["n_items"] == 0:
        result["warning"] = ("No items could be collected. The sources may be blocking this server, "
                             "or the company name returned no coverage. Check the source status panel.")
    with _lock:
        _cache[key] = (time.time(), result)
    return jsonify(result)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=False)
