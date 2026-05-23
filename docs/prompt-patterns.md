# Prompt Patterns for NSE/BSE MCP

Reusable tool-call recipes for common financial research workflows.
Each pattern lists the exact sequence of tool calls with parameters.

---

## Pattern 1: Quick Stock Check

**User ask:** "What's Infosys trading at?"

```json
{
  "name": "nse_bse_get_quote",
  "arguments": {
    "symbol": "INFY",
    "exchange": "NSE",
    "fields_to_return": ["price", "change", "change_pct", "direction", "volume", "pe_ratio"]
  }
}
```

**Response synthesis:** State price, directional change, and one contextual metric (P/E vs sector average).

---

## Pattern 2: Full Buy/Sell Research

**User ask:** "Should I buy HDFC Bank right now?"

**Step 1 — Price context**
```json
{ "name": "nse_bse_get_quote",
  "arguments": { "symbol": "HDFCBANK",
                 "fields_to_return": ["price","change_pct","week52_high","week52_low","pe_ratio","pb_ratio","beta"] } }
```

**Step 2 — Technical signal**
```json
{ "name": "nse_bse_get_technicals",
  "arguments": { "symbol": "HDFCBANK", "indicators": ["rsi","macd","supertrend","bollinger_bands"] } }
```

**Step 3 — Analyst view**
```json
{ "name": "nse_bse_get_analyst_view",
  "arguments": { "symbol": "HDFCBANK", "include": ["price_targets","recommendations_summary"] } }
```

**Step 4 — Recent news**
```json
{ "name": "nse_bse_get_news",
  "arguments": { "symbol": "HDFCBANK", "limit": 5, "fields_to_return": ["title","publisher","published_at"] } }
```

**Response synthesis:** Synthesize across all four: current price vs 52W range, technical signal (BUY/SELL/NEUTRAL), analyst consensus and upside to mean target, and any material recent news.

---

## Pattern 3: Sector Rotation Check

**User ask:** "Which sectors are leading the market today?"

```json
{
  "name": "nse_bse_sector_snapshot",
  "arguments": {
    "indices": ["NIFTY50","NIFTYBANK","NIFTYIT","NIFTYPHARMA","NIFTYAUTO",
                "NIFTYMETAL","NIFTYENERGY","NIFTYFMCG","NIFTYREALTY","INDIAVIX"],
    "fields_to_return": ["name", "level", "change_pct", "direction"]
  }
}
```

**Response synthesis:** Rank sectors by `change_pct`. Note INDIAVIX level separately — high VIX (>20) signals fear, low VIX (<14) signals complacency.

---

## Pattern 4: Peer Comparison (Banking Sector)

**User ask:** "Compare the top private banks on valuation."

```json
{
  "name": "nse_bse_compare_stocks",
  "arguments": {
    "symbols": ["HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "INDUSINDBK"],
    "exchange": "NSE",
    "fields_to_return": ["symbol","price","change_pct","market_cap_cr","pe","pb","roe_pct","div_yield_pct"]
  }
}
```

**Response synthesis:** Present as a ranked table. Highlight which bank has the lowest P/E vs highest ROE (value quality combination).

---

## Pattern 5: Options Strategy Research

**User ask:** "Show me the RELIANCE options chain for next month."

**Step 1 — Find available expiries**
```json
{ "name": "nse_bse_get_options",
  "arguments": { "symbol": "RELIANCE", "exchange": "NSE" } }
// Returns: { "available_expiries": ["2026-06-25", "2026-07-31", "2026-08-28"] }
```

**Step 2 — Fetch ATM ±5 strikes with key metrics**
```json
{ "name": "nse_bse_get_options",
  "arguments": {
    "symbol": "RELIANCE",
    "expiry": "2026-06-25",
    "option_type": "both",
    "limit_strikes_near_atm": 5,
    "fields_to_return": ["strike","last_price","bid","ask","implied_volatility","open_interest","in_the_money"]
  }
}
```

**Response synthesis:** Present calls and puts in a table. Highlight the ATM strike (where `in_the_money` flips). Note highest OI strikes as key support/resistance levels for the market.

---

## Pattern 6: Portfolio Review

**User ask:** "How is my portfolio doing?" (holdings provided in context)

```json
{
  "name": "nse_bse_portfolio_analysis",
  "arguments": {
    "holdings": [
      { "symbol": "RELIANCE", "quantity": 50,  "avg_buy_price": 2400.0 },
      { "symbol": "TCS",      "quantity": 20,  "avg_buy_price": 3500.0 },
      { "symbol": "ITC",      "quantity": 200, "avg_buy_price": 380.0  },
      { "symbol": "HDFCBANK", "quantity": 75,  "avg_buy_price": 1700.0 }
    ],
    "fields_to_return": ["summary", "per_stock", "sector_allocation", "risk_metrics"]
  }
}
```

**Response synthesis:** Lead with total P&L (₹ and %). List each stock with individual P&L. Show sector concentration. Interpret beta: >1.2 = aggressive, <0.8 = defensive.

---

## Pattern 7: Dividend Income Research

**User ask:** "Which of these stocks pays the best dividend? TCS, Infosys, Wipro, HCL Tech."

**Step 1 — Compare dividend yield**
```json
{ "name": "nse_bse_compare_stocks",
  "arguments": {
    "symbols": ["TCS","INFY","WIPRO","HCLTECH"],
    "fields_to_return": ["symbol","price","div_yield_pct","eps","market_cap_cr"]
  }
}
```

**Step 2 — Deep dive on the highest yielder (say INFY)**
```json
{ "name": "nse_bse_get_dividends",
  "arguments": { "symbol": "INFY" } }
```

**Response synthesis:** Rank by `div_yield_pct`. Add total dividends paid in last 5 years for context. Note payout sustainability via EPS vs dividend ratio.

---

## Pattern 8: Pre-Earnings Research

**User ask:** "TCS results are coming up. What should I know?"

**Step 1 — Earnings calendar**
```json
{ "name": "nse_bse_get_earnings",
  "arguments": { "symbol": "TCS", "include": ["earnings_dates","calendar","earnings_history"], "limit": 4 } }
```

**Step 2 — Analyst EPS estimates**
```json
{ "name": "nse_bse_get_analyst_view",
  "arguments": { "symbol": "TCS", "include": ["earnings_estimates","price_targets","recommendations_summary"] } }
```

**Step 3 — Historical surprise pattern (from earnings_history)**
Already fetched in Step 1.

**Response synthesis:** State next earnings date, expected EPS (from analyst estimates), historical beat/miss rate, current analyst consensus and price target, and how the stock has historically moved post-results.

---

## Pattern 9: Promoter Confidence Check

**User ask:** "Are promoters buying or selling in Adani Ports?"

```json
{
  "name": "nse_bse_get_insider_activity",
  "arguments": {
    "symbol": "ADANIPORTS",
    "include": ["transactions", "roster"],
    "limit": 15,
    "transaction_type": null
  }
}
```

**Response synthesis:** Summarize net buy/sell over last 6 months. If more buying than selling → bullish signal. List top 3 transactions by value. Show current promoter holding from roster.

---

## Pattern 10: Multi-Year Financial Trend

**User ask:** "How has Bajaj Finance's revenue and profit grown over 4 years?"

```json
{
  "name": "nse_bse_get_financials",
  "arguments": {
    "symbol": "BAJFINANCE",
    "frequency": "annual",
    "statements": ["income_statement"]
  }
}
```

**Response synthesis:** Extract Revenue and Net Income rows across 4 years. Calculate CAGR. Present as a growth table. Note if margins are expanding or contracting.

---

## Pattern 11: Technical Screener (Multiple Stocks)

**User ask:** "Which of these IT stocks is technically the strongest right now?"

```json
// Call get_technicals for each — or compare on price momentum first
{ "name": "nse_bse_compare_stocks",
  "arguments": {
    "symbols": ["TCS","INFY","WIPRO","HCLTECH","TECHM"],
    "fields_to_return": ["symbol","price","change_pct","beta","sector"]
  }
}
```

Then for the top 2 performers:
```json
{ "name": "nse_bse_get_technicals",
  "arguments": { "symbol": "TCS", "indicators": ["rsi","macd","supertrend"] } }
{ "name": "nse_bse_get_technicals",
  "arguments": { "symbol": "INFY", "indicators": ["rsi","macd","supertrend"] } }
```

**Response synthesis:** Rank by `signal_summary.score` descending. Present a 2-line technical summary per stock.

---

## Pattern 12: Market Opening Brief

**User ask:** "Give me a quick market brief."

```json
// 1. Broad market
{ "name": "nse_bse_sector_snapshot",
  "arguments": {
    "indices": ["NIFTY50","SENSEX","NIFTYBANK","INDIAVIX"],
    "fields_to_return": ["name","level","change_pct","direction"]
  }
}

// 2. Top movers (manually known or from user's watchlist)
{ "name": "nse_bse_compare_stocks",
  "arguments": {
    "symbols": ["RELIANCE","TCS","HDFCBANK","ICICIBANK","INFY"],
    "fields_to_return": ["symbol","price","change_pct","direction"]
  }
}
```

**Response synthesis:** Open with NIFTY50 level and % change. Note VIX. Then list top movers sorted by absolute change. Keep it to 5–6 lines.
