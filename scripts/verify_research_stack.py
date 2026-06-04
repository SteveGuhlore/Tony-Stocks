"""Pre-open smoke test for the Research Funnel stack: validates FMP / Finnhub /
Twelve Data API keys with real read-only calls, then runs the funnel end-to-end.

Run: python scripts/verify_research_stack.py
Exit code 0 only if every configured provider returns usable data. Research only.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta

from trading_bot.settings import load_dotenv_if_present
from trading_bot.data.research_providers import build_providers_from_env, gather_funnel_signals
from trading_bot.data.research_funnel import FunnelStageConfig, build_funnel

load_dotenv_if_present()

TEST = ["AAPL", "NVDA", "TSLA", "HOOD", "DAL"]
today = date.today()
ok = True


def check(label: str, value, good: bool) -> None:
    global ok
    mark = "PASS" if good else "FAIL"
    if not good:
        ok = False
    print(f"  [{mark}] {label}: {value}")


providers = build_providers_from_env()
fmp, finnhub, twelve = providers["fmp"], providers["finnhub"], providers["twelve"]

print("=== Key presence ===")
print(f"  FMP_API_KEY: {'set' if fmp.available else 'MISSING'}")
print(f"  FINNHUB_API_KEY: {'set' if finnhub.available else 'MISSING'}")
print(f"  TWELVE_DATA_API_KEY: {'set' if twelve.available else 'MISSING'}")

print("\n=== FMP (live) ===")
if fmp.available:
    screen = fmp.screen(limit=25)
    check("screen() returned tickers", f"{len(screen)} symbols (e.g. {screen[:5]})", len(screen) > 0)
    cal = fmp.earnings_calendar(today, today + timedelta(days=14))
    check("earnings_calendar()", f"{len(cal)} symbols with earnings in 14d", isinstance(cal, dict))
    rg = fmp.revenue_growth("AAPL")
    check("revenue_growth(AAPL)", rg, rg is not None)
else:
    check("FMP key", "missing", False)

print("\n=== Finnhub (live) ===")
if finnhub.available:
    s = finnhub.news_sentiment("AAPL")
    check("news_sentiment(AAPL)", s, s is not None)
    r = finnhub.recommendation("AAPL")
    check("recommendation(AAPL)", r, r is not None)
else:
    check("Finnhub key", "missing", False)

print("\n=== Twelve Data (live) ===")
if twelve.available:
    q = twelve.quote("AAPL")
    check("quote(AAPL)", q, q is not None)
else:
    check("Twelve key", "missing", False)

print("\n=== Funnel end-to-end (real enrichment on 5 symbols) ===")
signals = gather_funnel_signals(
    TEST, today=today, fmp=fmp, finnhub=finnhub, enrich_limit=5, earnings_blackout_days=14,
)
for sym in TEST:
    s = signals[sym]
    print(f"  {sym}: sentiment={s.news_sentiment} rec={s.recommendation_score} earnings={s.earnings_date}")
res = build_funnel(TEST, signals, FunnelStageConfig(), today)
check("build_funnel shortlist", res.shortlist, len(res.shortlist) > 0)
print(f"  stage_counts: {res.to_dict()['stage_counts']}")

print("\n=== RESULT:", "ALL GOOD ===" if ok else "SOME CHECKS FAILED ===")
sys.exit(0 if ok else 1)
