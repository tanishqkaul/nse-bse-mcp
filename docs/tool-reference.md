# Tool Reference — NSE/BSE MCP v2.0

Complete parameter reference for all 19 tools. All tools return JSON.

---

## Market Data Tools

### `nse_bse_get_quote`
Get a real-time quote with price, valuation metrics, and company info.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Bare symbol, e.g. `RELIANCE` |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |
| `fields_to_return` | string[] | all | Subset of response fields |

**Response fields:** `symbol`, `exchange`, `name`, `price`, `change`, `change_pct`, `direction`,
`open`, `high`, `low`, `prev_close`, `volume`, `avg_volume`, `week52_high`, `week52_low`,
`ma_50d`, `ma_200d`, `market_cap`, `market_cap_crore`, `pe_ratio`, `forward_pe`, `pb_ratio`,
`eps`, `forward_eps`, `dividend_yield`, `beta`, `sector`, `industry`, `currency`, `isin`

```json
{
  "name": "nse_bse_get_quote",
  "arguments": {
    "symbol": "HDFCBANK",
    "exchange": "NSE",
    "fields_to_return": ["price", "change_pct", "pe_ratio", "market_cap_crore", "sector"]
  }
}
```

---

### `nse_bse_get_historical`
Get OHLCV price history. Supports both `period=` and `start_date`/`end_date`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |
| `period` | string | `3mo` | `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y`, `2y`, `5y`, `10y`, `ytd`, `max` |
| `start_date` | string | — | `YYYY-MM-DD` (alternative to period) |
| `end_date` | string | today | `YYYY-MM-DD` |
| `interval` | string | `1d` | `1m`, `5m`, `15m`, `1h`, `1d`, `1wk`, `1mo` |
| `max_records` | int | `100` | Max rows returned (1–500) |
| `fields_to_return` | string[] | all | Per-row fields |

**Per-row fields:** `date`, `open`, `high`, `low`, `close`, `volume`, `daily_return_pct`

**Notes:**
- Intraday intervals (`1m`–`1h`) only available for the last 60 days
- Use `start_date`/`end_date` for event-driven backtesting (e.g. around earnings)

```json
{
  "name": "nse_bse_get_historical",
  "arguments": {
    "symbol": "RELIANCE",
    "start_date": "2025-01-01",
    "end_date": "2025-06-01",
    "interval": "1wk",
    "fields_to_return": ["date", "close", "volume"]
  }
}
```

---

### `nse_bse_get_index`
Get current level and period performance for an Indian market index.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `index` | string | required | See `nse_bse_list_indices` for full list |
| `period` | string | `1d` | `1d`, `5d`, `1mo`, `3mo`, `6mo`, `1y` |
| `fields_to_return` | string[] | all | Subset of response fields |

**Response fields:** `index`, `yahoo_ticker`, `level`, `change`, `change_pct`, `direction`,
`week52_high`, `week52_low`, `ma_50d`, `ma_200d`, `period_return_pct`, `period_high`, `period_low`

---

### `nse_bse_list_indices`
List all 25 supported Indian market indices. No parameters.

---

### `nse_bse_sector_snapshot`
Parallel fetch of levels and % change for all or selected indices.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `indices` | string[] | all | Specific index names to fetch |
| `fields_to_return` | string[] | all | `name`, `level`, `change`, `change_pct`, `direction`, `week52_high`, `week52_low` |

Results are **sorted by `change_pct` descending** (best performers first).

```json
{
  "name": "nse_bse_sector_snapshot",
  "arguments": {
    "indices": ["NIFTYIT", "NIFTYBANK", "NIFTYPHARMA", "NIFTYAUTO"],
    "fields_to_return": ["name", "change_pct", "direction"]
  }
}
```

---

## Fundamental Analysis Tools

### `nse_bse_get_fundamentals`
Deep fundamental metrics: revenue, margins, balance sheet, per-share data, analyst targets.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |
| `fields_to_return` | string[] | all | Subset of fields |

**Available fields:**
`symbol`, `exchange`, `name`, `revenue`, `gross_profit`, `ebitda`, `operating_income`,
`net_income`, `gross_margin`, `operating_margin`, `net_margin`, `roe`, `roa`,
`total_assets`, `total_debt`, `cash`, `book_value`, `debt_equity`, `current_ratio`,
`quick_ratio`, `eps_ttm`, `forward_eps`, `revenue_per_share`, `cash_per_share`,
`dividend_per_share`, `payout_ratio`, `earnings_growth`, `revenue_growth`,
`target_mean`, `target_high`, `target_low`, `recommendation`, `analyst_count`, `description`

> All ₹ values (revenue, profit, assets, etc.) are in **Indian Crore**.
> Margin and growth fields are **decimals** (e.g. `0.20` = 20%).

---

### `nse_bse_get_financials`
Raw financial statements (income statement, balance sheet, cash flow).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |
| `frequency` | `annual`\|`quarterly`\|`ttm` | `annual` | Time granularity |
| `statements` | string[] | all | `income_statement`, `balance_sheet`, `cash_flow` |

```json
{
  "name": "nse_bse_get_financials",
  "arguments": {
    "symbol": "WIPRO",
    "frequency": "quarterly",
    "statements": ["income_statement", "cash_flow"]
  }
}
```

---

### `nse_bse_compare_stocks`
Side-by-side comparison of 2–10 stocks. Uses **parallel async fetch**.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbols` | string[] | required | 2–10 stock symbols |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange (same for all) |
| `fields_to_return` | string[] | all | Per-stock fields |

**Per-stock fields:** `symbol`, `name`, `price`, `change_pct`, `direction`,
`market_cap_cr`, `pe`, `pb`, `roe_pct`, `npm_pct`, `div_yield_pct`, `beta`, `sector`

---

## Options & Derivatives

### `nse_bse_get_options`
Options chain data. Call without `expiry` first to get available dates.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |
| `expiry` | string | `null` | `YYYY-MM-DD`. Omit to get available expiry list |
| `option_type` | `calls`\|`puts`\|`both` | `both` | Which side to return |
| `fields_to_return` | string[] | all | Per-contract fields |
| `limit_strikes_near_atm` | int (1–20) | `null` | N strikes above and below ATM |

**Per-contract fields:** `contract_symbol`, `strike`, `last_price`, `bid`, `ask`,
`change`, `change_pct`, `volume`, `open_interest`, `implied_volatility`, `in_the_money`, `expiry`

> Yahoo Finance options coverage for Indian stocks is limited. Best coverage:
> RELIANCE, INFY, TCS, HDFCBANK, ICICIBANK.

```json
{
  "name": "nse_bse_get_options",
  "arguments": {
    "symbol": "RELIANCE",
    "expiry": "2026-06-25",
    "option_type": "calls",
    "limit_strikes_near_atm": 5,
    "fields_to_return": ["strike", "last_price", "implied_volatility", "open_interest", "volume"]
  }
}
```

---

## Technical Analysis

### `nse_bse_get_technicals`
Compute technical indicators from daily OHLCV data. Includes composite signal.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |
| `indicators` | string[] | all | `rsi`, `macd`, `bollinger_bands`, `atr`, `moving_averages`, `volume_trend`, `supertrend` |
| `period` | string | `6mo` | Historical period for computation |

**Response structure:**
```json
{
  "rsi": { "value": 58.3, "period": 14, "signal": "neutral" },
  "macd": { "macd_line": 12.4, "signal_line": 9.8, "histogram": 2.6, "crossover": "bullish" },
  "bollinger_bands": { "upper": 1620, "middle": 1550, "lower": 1480, "pct_b": 0.71, "signal": "neutral" },
  "atr": { "value": 28.5, "period": 14 },
  "moving_averages": { "ma_20d": 1540, "ma_50d": 1495, "ma_200d": 1380, "price_vs_ma50": "above", "price_vs_ma200": "above" },
  "volume_trend": { "avg_volume_5d": 1200000, "avg_volume_20d": 1000000, "ratio_5d_vs_20d": 1.2, "signal": "high" },
  "supertrend": { "direction": "bullish", "value": 1480.0 },
  "signal_summary": { "signal": "BUY", "score": 2, "reasons": ["MACD bullish crossover", "Supertrend bullish"] }
}
```

**Signal levels:** `STRONG_BUY` (+3 or more), `BUY` (+1 to +2), `NEUTRAL` (0), `SELL` (-1 to -2), `STRONG_SELL` (-3 or less)

---

## Corporate Actions & Events

### `nse_bse_get_dividends`
Full dividend payout history.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |

Returns last 20 dividends (newest first) + 5-year total.

---

### `nse_bse_get_corporate_actions`
Unified timeline: splits + dividends + capital gains.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |

---

### `nse_bse_get_earnings`
Earnings dates, calendar, EPS history, quarterly trend.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |
| `include` | string[] | all | `earnings_dates`, `calendar`, `earnings_history`, `quarterly_earnings` |
| `limit` | int (1–20) | `8` | Max quarterly records |

---

## Ownership & Governance

### `nse_bse_get_shareholders`
Major, institutional, and mutual fund holders.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |
| `include_mutualfunds` | bool | `true` | Include MF holder data |
| `top_n` | int (1–50) | `15` | Max holders per category |

---

### `nse_bse_get_insider_activity`
Promoter/insider buy-sell transactions.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |
| `include` | string[] | all | `transactions`, `purchases`, `roster` |
| `limit` | int (1–50) | `20` | Max transaction records |
| `transaction_type` | `buy`\|`sell`\|null | `null` | Filter by type |

---

## Research & Analyst

### `nse_bse_get_analyst_view`
Ratings, upgrades/downgrades, price targets, EPS/revenue estimates.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |
| `include` | string[] | all | `recommendations_summary`, `upgrades_downgrades`, `price_targets`, `earnings_estimates`, `revenue_estimates`, `growth_estimates` |
| `limit_upgrades` | int (1–50) | `10` | Max rating change records |

---

### `nse_bse_get_news`
Recent news articles from Yahoo Finance.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |
| `limit` | int (1–25) | `10` | Number of articles |
| `fields_to_return` | string[] | all | `title`, `publisher`, `link`, `published_at`, `related_tickers` |

---

## Portfolio & ESG

### `nse_bse_portfolio_analysis`
P&L, sector allocation, and risk metrics for a portfolio.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `holdings` | PortfolioHolding[] | required | List of holdings (max 30) |
| `fields_to_return` | string[] | all | `summary`, `per_stock`, `sector_allocation`, `risk_metrics` |

**PortfolioHolding fields:** `symbol` (string), `quantity` (float, > 0), `avg_buy_price` (float, > 0), `exchange` (`NSE`\|`BSE`)

```json
{
  "name": "nse_bse_portfolio_analysis",
  "arguments": {
    "holdings": [
      { "symbol": "RELIANCE", "quantity": 50,  "avg_buy_price": 2400.0, "exchange": "NSE" },
      { "symbol": "TCS",      "quantity": 20,  "avg_buy_price": 3500.0, "exchange": "NSE" },
      { "symbol": "HDFCBANK", "quantity": 100, "avg_buy_price": 1600.0, "exchange": "NSE" }
    ],
    "fields_to_return": ["summary", "sector_allocation"]
  }
}
```

---

### `nse_bse_get_esg`
ESG sustainability scores (availability varies for Indian stocks).

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `symbol` | string | required | Stock symbol |
| `exchange` | `NSE`\|`BSE` | `NSE` | Exchange |
| `fields_to_return` | string[] | all | `total_esg`, `environment_score`, `social_score`, `governance_score`, `controversy_level`, `percentile`, `peer_group` |
