# RepTrak Live

A web app that scores a company's corporate reputation from live public web data on the seven
RepTrak dimensions and the RepTrak Pulse, then turns the result into prioritised actionables using
the stakeholder reputation toolkit (playbook + scorecard) built for the CCR live project.

**Inputs:** company name, stock ticker, Instagram link, X link.
**Saved demo:** "Load saved Eternal demo" shows a stored analysis of Eternal Limited (Zomato, Blinkit).

## What it does

| Step | Detail |
|---|---|
| Collect (direct scraping, no paid scraping services) | Google News RSS and Bing News RSS (last 6 months), Reddit public search, Yahoo Finance daily prices (1 year), Google Play rating and newest reviews, Instagram public profile, X public timeline |
| Score | VADER sentiment with a business/finance lexicon; keyword tagging to RepTrak dimensions, stakeholders and media frames; dimension score = 3 + 2 × mean tone × n/(n+4) |
| Blend with operating proxies | Performance = media tone + share-price momentum; Products & Services = media tone + app-store rating |
| Pulse | Esteem, Admire, Trust (penalised for preventable-crisis coverage), Feel-good |
| Toolkit | 8 stakeholders with scorecard weights, channels, frames, early-warning triggers and response rules; weighted stakeholder index; SCCT crisis radar (victim / accidental / preventable) with prescribed responses; prioritised actionables linked to recommendations R1-R4 |
| Outputs | KPI tiles, source status, RepTrak radar, Pulse, two-track coverage (financial vs non-financial), dimension evidence, actionables, scorecard, crisis radar, media frames, monthly tone, share price, digital presence, reputation-vs-reality check, filterable evidence explorer, JSON download |

## Deploy on Render

1. Put this folder in a GitHub repository (it is ready as-is; `render.yaml` is included).
2. In Render: **New → Blueprint**, select the repository, and confirm. Render reads `render.yaml`.
   - Or **New → Web Service**: Runtime *Python*, Build command `pip install -r requirements.txt`,
     Start command `gunicorn app:app --workers 2 --threads 4 --timeout 120 --bind 0.0.0.0:$PORT`.
3. Open the service URL. The first live run takes about 15-30 seconds; results are cached for 30 minutes
   (`CACHE_TTL` environment variable).

## Run locally

```bash
pip install -r requirements.txt
python app.py            # http://localhost:5000
python -m pytest -q tests  # offline parser, engine and API tests
python scripts/build_demo.py   # rebuilds data/eternal_demo.json from scripts/eternal_snapshot.json
```

## Ticker format

Yahoo Finance symbols: `ETERNAL.NS` (NSE), `543320.BO` (BSE), `AAPL`. `NSE:ETERNAL` and `BSE:543320`
are converted automatically.

## Limitations

- Instagram and X frequently block anonymous requests from cloud servers. When blocked, the app
  shows them as unavailable and scores the remaining sources. Reddit may also rate-limit cloud IPs.
- Keyword tagging and lexicon sentiment are approximations (e.g. negations and sarcasm). Scores show
  direction and relative strength; they are not a licensed RepTrak® survey score.
- The saved Eternal demo is built from an offline snapshot: 58 dated headlines (Dec 2025-Nov 2026),
  a Google Play summary and indicative press-reported share prices. Instagram and X are not in the
  snapshot.
