# Token Efficiency Guide

Token efficiency is not a nice-to-have — it is the difference between an MCP server
that works well inside an LLM context window and one that blows it up in three calls.
This guide explains how to keep every tool call lean.

---

## Why This Matters

A typical `get_quote` call without filtering returns ~40 fields ≈ **600–800 tokens**.
A `get_financials(frequency="annual")` without statement filtering can return **8,000–15,000 tokens**.

If your workflow makes 5–10 tool calls, that is your entire 4K context gone before you've written a word.

---

## Token Budget Estimates Per Tool

| Tool | No filter (tokens) | With `fields_to_return` (tokens) |
|------|--------------------|----------------------------------|
| `get_quote` | ~700 | ~80–150 |
| `get_historical` (100 rows) | ~5,000 | ~500–800 (close+date only) |
| `get_fundamentals` | ~900 | ~150–300 |
| `get_financials` (annual, all stmts) | ~8,000–15,000 | ~500–2,000 |
| `compare_stocks` (5 stocks) | ~2,000 | ~400–600 |
| `get_options` (full chain) | ~10,000+ | ~300–800 (ATM filter + field filter) |
| `get_news` (10 articles) | ~1,500 | ~400–600 (title+publisher only) |
| `sector_snapshot` (all indices) | ~3,000 | ~600 (name+change_pct only) |
| `get_technicals` (all indicators) | ~800 | ~200–400 (rsi+macd only) |
| `portfolio_analysis` (10 stocks) | ~4,000 | ~800 (summary+allocation only) |
| `get_analyst_view` (all sections) | ~2,000 | ~400 (price_targets only) |

---

## The Most Expensive Calls and How to Fix Them

### 1. `get_financials` without statement filter

```json
// EXPENSIVE — fetches all 3 statements × 4 years = potentially 15,000 tokens
{ "name": "nse_bse_get_financials", "arguments": { "symbol": "RELIANCE" } }

// EFFICIENT — only what you need
{ "name": "nse_bse_get_financials",
  "arguments": {
    "symbol": "RELIANCE",
    "frequency": "quarterly",
    "statements": ["income_statement"]
  }
}
```

### 2. `get_historical` without `max_records`

```json
// EXPENSIVE — 500 rows of daily data for 2 years = ~25,000 tokens
{ "name": "nse_bse_get_historical",
  "arguments": { "symbol": "TCS", "period": "2y" } }

// EFFICIENT — last 20 days, close price only
{ "name": "nse_bse_get_historical",
  "arguments": {
    "symbol": "TCS",
    "period": "1mo",
    "max_records": 20,
    "fields_to_return": ["date", "close"]
  }
}
```

### 3. `get_options` without ATM filter

```json
// EXPENSIVE — full chain with 50+ strikes × 2 sides = ~10,000 tokens
{ "name": "nse_bse_get_options",
  "arguments": { "symbol": "RELIANCE", "expiry": "2026-06-25" } }

// EFFICIENT — ±5 strikes around ATM, key metrics only
{ "name": "nse_bse_get_options",
  "arguments": {
    "symbol": "RELIANCE",
    "expiry": "2026-06-25",
    "option_type": "calls",
    "limit_strikes_near_atm": 5,
    "fields_to_return": ["strike", "last_price", "implied_volatility", "open_interest"]
  }
}
```

---

## Caching: Free Token Savings

The server has a **5-minute TTL in-memory cache** for `ticker.info`. If you call
`get_quote` and then `get_fundamentals` on the same stock within 5 minutes,
the second call uses cached data — no extra latency or Yahoo Finance quota.

**Implication:** It is cheaper to make two narrow calls than one large call.

```
Call 1: get_quote(symbol="TCS", fields_to_return=["price","change_pct"])   → ~80 tokens
Call 2: get_fundamentals(symbol="TCS", fields_to_return=["pe_ratio","roe"]) → ~100 tokens (cached info)

vs.

Call 1: get_quote(symbol="TCS") → ~700 tokens (all fields)
```

---

## Parallelism: `compare_stocks` vs Multiple `get_quote` Calls

`compare_stocks` fetches all stocks concurrently using `asyncio.gather`. This is
**2–5× faster** than calling `get_quote` N times.

```
# Slow: 5 sequential calls
get_quote("RELIANCE")   → 1.2s
get_quote("TCS")        → 1.2s
get_quote("INFY")       → 1.2s
get_quote("HDFCBANK")   → 1.2s
get_quote("ICICIBANK")  → 1.2s
Total: ~6 seconds

# Fast: 1 parallel call
compare_stocks(["RELIANCE","TCS","INFY","HDFCBANK","ICICIBANK"]) → ~1.5 seconds
```

Use `compare_stocks` for any multi-stock comparison. Use `sector_snapshot` for
all-index snapshots (also parallel).

---

## Choosing `period` for `get_technicals`

Technical indicators require a minimum number of data points:

| Indicator | Minimum days | Recommended `period` |
|-----------|-------------|----------------------|
| RSI (14) | 28 | `3mo` |
| MACD (26) | 52 | `3mo` |
| Bollinger Bands (20) | 40 | `3mo` |
| ATR (14) | 28 | `3mo` |
| Supertrend (10) | 20 | `3mo` |
| MA 200d | 200 | `1y` |

Use `6mo` (default) to safely cover all indicators except MA-200. Use `1y` only
if you need `moving_averages.ma_200d`.

---

## Field Grouping Patterns

### For a trading decision
```json
"fields_to_return": ["price","change_pct","week52_high","week52_low","pe_ratio","beta"]
```

### For a valuation screen
```json
"fields_to_return": ["symbol","pe_ratio","pb_ratio","roe_pct","npm_pct","market_cap_cr"]
```

### For a dividend income investor
```json
"fields_to_return": ["symbol","price","dividend_yield","eps","payout_ratio"]
```

### For a technical trader
```json
// compare_stocks fields
"fields_to_return": ["symbol","price","change_pct","beta"]
// + separate get_technicals with indicators=["rsi","macd","supertrend"]
```

---

## Anti-Patterns to Avoid

| Anti-pattern | Fix |
|--------------|-----|
| Calling `get_quote` then `get_fundamentals` without filters | Add `fields_to_return` to both |
| Fetching 2 years of daily history for a simple trend check | Use `period="3mo"` and `max_records=50` |
| Getting all 6 analyst sections when user only asked about targets | `include=["price_targets"]` |
| Fetching full options chain to show 3 strikes | `limit_strikes_near_atm=3` |
| Calling `get_financials` for all 3 statements when user asked about margins | `statements=["income_statement"]` |
| Getting news then not using the links | `fields_to_return=["title","publisher","published_at"]` |
| Ignoring `null` values and treating them as 0 in calculations | Always check for `null` before arithmetic |
