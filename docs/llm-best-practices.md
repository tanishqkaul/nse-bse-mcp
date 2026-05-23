# LLM Best Practices for NSE/BSE MCP

This guide is written **for language models** using this MCP server. Follow these rules
to produce accurate, token-efficient, and actionable responses about Indian stocks.

---

## 1. Always Filter with `fields_to_return`

Every tool accepts `fields_to_return`. This is the single most important practice.
**Never call a tool without it unless you genuinely need every field.**

```json
// BAD — dumps 40+ fields, wastes 800 tokens
{
  "name": "nse_bse_get_quote",
  "arguments": { "symbol": "RELIANCE", "exchange": "NSE" }
}

// GOOD — returns exactly what the user asked for
{
  "name": "nse_bse_get_quote",
  "arguments": {
    "symbol": "RELIANCE",
    "exchange": "NSE",
    "fields_to_return": ["price", "change_pct", "pe_ratio", "market_cap_crore"]
  }
}
```

### Available `fields_to_return` by tool

| Tool | Key filterable fields |
|------|-----------------------|
| `get_quote` | `price`, `change`, `change_pct`, `pe_ratio`, `pb_ratio`, `market_cap_crore`, `eps`, `dividend_yield`, `beta`, `sector`, `week52_high`, `week52_low`, `isin` |
| `get_historical` (per row) | `date`, `open`, `high`, `low`, `close`, `volume`, `daily_return_pct` |
| `get_fundamentals` | `revenue`, `gross_margin`, `net_margin`, `roe`, `debt_equity`, `eps_ttm`, `recommendation`, `target_mean` |
| `get_options` (per row) | `strike`, `last_price`, `bid`, `ask`, `implied_volatility`, `open_interest`, `volume`, `in_the_money` |
| `compare_stocks` (per stock) | `symbol`, `price`, `change_pct`, `market_cap_cr`, `pe`, `pb`, `roe_pct`, `npm_pct`, `beta`, `sector` |
| `get_index` | `level`, `change_pct`, `period_return_pct`, `week52_high`, `week52_low` |
| `get_news` | `title`, `publisher`, `link`, `published_at` |
| `sector_snapshot` | `name`, `level`, `change_pct`, `direction` |
| `get_esg` | `total_esg`, `environment_score`, `social_score`, `governance_score` |

---

## 2. Use Limiting Parameters for Large Datasets

When the tool has a `limit_*` or `top_n` parameter, always set it.

```json
// Options chain: only the 5 strikes above and below ATM
{
  "name": "nse_bse_get_options",
  "arguments": {
    "symbol": "RELIANCE",
    "expiry": "2026-06-25",
    "option_type": "calls",
    "fields_to_return": ["strike", "last_price", "implied_volatility", "open_interest"],
    "limit_strikes_near_atm": 5
  }
}

// Shareholders: top 5 only
{
  "name": "nse_bse_get_shareholders",
  "arguments": {
    "symbol": "TCS",
    "top_n": 5,
    "include_mutualfunds": false
  }
}

// News: 5 headlines only
{
  "name": "nse_bse_get_news",
  "arguments": {
    "symbol": "INFY",
    "limit": 5,
    "fields_to_return": ["title", "publisher", "published_at"]
  }
}
```

---

## 3. Chain Tools for Research Workflows

Don't try to answer everything with a single tool call. Chain tools in a logical sequence.

### Research Workflow Example: "Is TCS a good buy right now?"

**Step 1 — Quick pulse check**
```json
{ "name": "nse_bse_get_quote",
  "arguments": { "symbol": "TCS", "fields_to_return": ["price","change_pct","pe_ratio","week52_high","week52_low"] } }
```

**Step 2 — Technicals**
```json
{ "name": "nse_bse_get_technicals",
  "arguments": { "symbol": "TCS", "indicators": ["rsi","macd","supertrend"] } }
```

**Step 3 — Analyst consensus**
```json
{ "name": "nse_bse_get_analyst_view",
  "arguments": { "symbol": "TCS", "include": ["price_targets","recommendations_summary"] } }
```

**Step 4 — News sentiment**
```json
{ "name": "nse_bse_get_news",
  "arguments": { "symbol": "TCS", "limit": 5, "fields_to_return": ["title","publisher","published_at"] } }
```

Then synthesize all four results into a single, structured answer.

---

## 4. Know When to Use Each Tool

| User Ask | Primary Tool | Secondary Tool |
|----------|-------------|----------------|
| "What is X trading at?" | `get_quote` (fields: price, change_pct) | — |
| "Is X a good buy technically?" | `get_technicals` | `get_quote` (price) |
| "Compare X and Y" | `compare_stocks` | — |
| "What's the F&O situation for X?" | `get_options` (list expiries first) | `get_quote` (price) |
| "What do analysts say about X?" | `get_analyst_view` | — |
| "Show me X's financial health" | `get_fundamentals` | `get_financials` (quarterly) |
| "What's the market doing today?" | `sector_snapshot` | `get_index` (NIFTY50) |
| "Is promoter buying or selling X?" | `get_insider_activity` | — |
| "What's my portfolio worth?" | `portfolio_analysis` | — |
| "Any dividends coming for X?" | `get_dividends` | `get_earnings` (calendar) |

---

## 5. Handle `"N/A"` and `null` Values Gracefully

Yahoo Finance data is not always complete for Indian stocks. Many fields will be `null` or `"N/A"`.

**Do:**
- Acknowledge when a field is unavailable: *"P/B ratio data is not available for this stock."*
- Continue the analysis with available fields.
- Suggest the user check the BSE/NSE website for official data.

**Don't:**
- Treat `null` as `0`.
- Say a company has "0% dividend yield" when the field is `null`.
- Silently skip unavailable data without telling the user.

---

## 6. Respect Rate Limits

Yahoo Finance rate-limits heavy API usage. If you get an error like:
> `"Error: Rate limit hit. Wait a few seconds and retry."`

Wait before retrying. Prefer broad queries over rapid repeated calls.

**Patterns that cause rate limits:**
- Calling `compare_stocks` with 10 symbols back-to-back repeatedly
- Fetching `sector_snapshot` every few seconds
- Calling `get_financials` for many stocks in rapid succession

**Mitigation:** The server has a 5-minute in-memory cache. Identical calls within 5 minutes are served from cache.

---

## 7. NSE vs BSE — When to Use Which

Most liquid large-cap stocks trade on **both** NSE and BSE. Use:

- **NSE** (default) — for most queries; better liquidity, NSE is the primary exchange for most instruments
- **BSE** — for companies listed only on BSE, or to cross-verify a quote

If a symbol returns no data on NSE, try BSE:
```json
{ "symbol": "SOMESTOCK", "exchange": "BSE" }
```

---

## 8. Options Data Limitations

Yahoo Finance has **limited options data** for Indian stocks. The most reliable coverage is for:
- `RELIANCE`, `INFY`, `TCS`, `HDFCBANK`, `ICICIBANK`

**Always call `get_options` without an expiry first** to check available expiry dates before fetching a chain:

```json
// Step 1: check available expiries
{ "name": "nse_bse_get_options", "arguments": { "symbol": "RELIANCE" } }
// Returns: { "available_expiries": ["2026-06-25", "2026-07-31", ...] }

// Step 2: fetch the chain for a specific expiry
{ "name": "nse_bse_get_options",
  "arguments": { "symbol": "RELIANCE", "expiry": "2026-06-25",
                 "option_type": "both", "limit_strikes_near_atm": 5,
                 "fields_to_return": ["strike","last_price","implied_volatility","open_interest"] } }
```

---

## 9. Quarterly vs Annual Financials

Use the right frequency for the question:

| Question | `frequency` |
|----------|-------------|
| "Is X's revenue growing year over year?" | `annual` |
| "How did X do last quarter?" | `quarterly` |
| "What's X's trailing 12-month revenue?" | `ttm` |

And always filter statements:
```json
{
  "name": "nse_bse_get_financials",
  "arguments": {
    "symbol": "WIPRO",
    "frequency": "quarterly",
    "statements": ["income_statement"]
  }
}
```

---

## 10. Formatting Responses for Users

When presenting Indian financial data to users:

- **Market Cap**: Say "₹50,000 Cr" not "₹500,000,000,000"
- **Margins**: Present as percentages: "Net margin: 20%" not "0.2"
- **Price targets**: Always mention the number of analysts: "₹1,750 mean target (22 analysts)"
- **52W range**: Give context: "Currently at 83% of its 52-week high"
- **Technicals**: Don't just say "RSI: 65" — interpret: "RSI at 65 suggests mild bullishness but not yet overbought territory"

---

## 11. ESG Data Coverage Warning

ESG data from Yahoo Finance is primarily available for **global large-cap stocks**.
Coverage for Indian-listed stocks is sparse. If `get_esg` returns a `"message"` field
instead of scores, tell the user this data isn't available and suggest checking:
- NSE Sustainability Index
- CRISIL ESG ratings
- Sustainalytics (for dual-listed companies)

---

## Quick Reference: Minimum Viable Calls

```json
// Fastest quote
{ "name": "nse_bse_get_quote",
  "arguments": { "symbol": "X", "fields_to_return": ["price","change_pct"] } }

// Market pulse
{ "name": "nse_bse_sector_snapshot",
  "arguments": { "indices": ["NIFTY50","NIFTYBANK","NIFTYIT","INDIAVIX"],
                 "fields_to_return": ["name","level","change_pct"] } }

// Technical signal only
{ "name": "nse_bse_get_technicals",
  "arguments": { "symbol": "X", "indicators": ["rsi","macd","supertrend"] } }

// Analyst view only
{ "name": "nse_bse_get_analyst_view",
  "arguments": { "symbol": "X", "include": ["price_targets","recommendations_summary"] } }
```
