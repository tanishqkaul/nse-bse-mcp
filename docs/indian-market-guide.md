# Indian Stock Market Guide for LLMs

Essential context about NSE, BSE, and Indian financial markets. Read this before
answering questions about Indian stocks to avoid common mistakes.

---

## NSE vs BSE

| Feature | NSE (National Stock Exchange) | BSE (Bombay Stock Exchange) |
|---------|------------------------------|-----------------------------|
| Founded | 1992 | 1875 (Asia's oldest) |
| Flagship index | NIFTY 50 | SENSEX (BSE 30) |
| Yahoo suffix | `.NS` | `.BO` |
| Primary use | Equities + F&O trading | Equities, SME listings |
| Derivatives | World's largest by volume | Limited derivatives |
| Liquidity | Higher for most large-caps | Better for some mid/small caps |

**Rule of thumb:** Use NSE by default. Switch to BSE only if:
- A stock is not listed on NSE
- The user specifically asks for BSE data
- You get a "no data" error on NSE

---

## Market Hours

| Session | IST | Note |
|---------|-----|------|
| Pre-open | 09:00–09:15 | Order matching, no execution |
| Regular session | 09:15–15:30 | All exchanges |
| Post-close | 15:30–16:00 | Closing price calculation |
| Currency / Commodity futures | Extended hours | Not covered by this MCP |

**Time zone:** India Standard Time (IST) = UTC +5:30. No daylight saving.

**Data delay:** Yahoo Finance data is delayed by ~15 minutes during market hours.
Prices shown are NOT real-time. For real-time data, use NSE's official API or a
broker API (Zerodha Kite, AngelOne SmartAPI, Upstox).

---

## Symbol Conventions

### Equities
- NSE: Bare symbol + `.NS` → `RELIANCE.NS` (handled automatically by this MCP)
- BSE: Bare symbol + `.BO` → `RELIANCE.BO` (handled automatically)
- **Always pass the bare symbol** to tools, e.g. `RELIANCE` not `RELIANCE.NS`

### F&O symbols on NSE
NSE F&O symbols often differ from equity symbols:
- NIFTY options → traded as `NIFTY` (not NIFTY50)
- BANKNIFTY → traded as `BANKNIFTY`
- Individual stock F&O → same symbol as equity

### BSE Stock Codes
BSE also uses numeric codes (e.g. RELIANCE = 500325). This MCP uses symbol names,
not BSE codes. Yahoo Finance resolves `RELIANCE.BO` automatically.

---

## Key Indices Explained

| Index | Composition | Use |
|-------|-------------|-----|
| **NIFTY 50** | 50 largest NSE stocks by free-float market cap | Benchmark for Indian equities |
| **SENSEX** | 30 largest BSE stocks | BSE benchmark, often moves in sync with NIFTY |
| **NIFTY Bank** | 12 most liquid banking stocks | Banking sector pulse |
| **NIFTY IT** | 10 IT stocks | IT sector (TCS, Infosys, Wipro, HCL, etc.) |
| **INDIA VIX** | 30-day implied volatility of NIFTY | Fear gauge; >20 = elevated fear |
| **NIFTY Next 50** | 50 stocks ranked 51–100 by market cap | Large-cap expansion universe |
| **NIFTY Midcap 150** | Stocks ranked 101–250 | Mid-cap universe |
| **NIFTY Smallcap 250** | Stocks ranked 251–500 | Small-cap universe |

**INDIA VIX interpretation:**
- < 13: Complacency, very calm market
- 13–17: Normal volatility
- 17–20: Slightly elevated
- 20–25: Elevated fear, consider protective positions
- \> 25: High fear, market stress (e.g. COVID crash, budget shocks)

---

## Indian Financial Year

India's fiscal year runs **April 1 to March 31**, not January–December.

- FY2025 = April 2024 to March 2025
- Q1 FY2025 = April–June 2024
- Q2 FY2025 = July–September 2024
- Q3 FY2025 = October–December 2024
- Q4 FY2025 = January–March 2025

**Impact on financials data:**
- `get_financials(frequency="annual")` returns columns like `2025-03-31` (March year-end)
- Quarterly results are announced typically 3–6 weeks after quarter-end

---

## Currency and Denomination

All prices and financial values in this MCP are in **Indian Rupee (INR, ₹)**.

**Indian number system** (different from Western):
- 1 Lakh = 1,00,000 (100 thousand)
- 1 Crore = 1,00,00,000 (10 million)
- 1 Lakh Crore = 1 Trillion

**In this MCP:**
- Prices: in ₹ (raw value, e.g. 1500.00)
- Market cap, revenue, profit: in ₹ Crore (e.g. 50,000 Cr = ₹500 Billion)
- Always state the unit when presenting to users

---

## F&O (Futures & Options) Basics

NSE is the **world's largest derivatives exchange by contract volume** (since 2023).

### Key F&O terminology
| Term | Meaning |
|------|---------|
| **CE** | Call option (right to buy) |
| **PE** | Put option (right to sell) |
| **ATM** | At-The-Money — strike nearest to current price |
| **ITM** | In-The-Money — intrinsic value |
| **OTM** | Out-of-The-Money — only time value |
| **OI** | Open Interest — outstanding contracts |
| **PCR** | Put-Call Ratio — OI puts / OI calls |
| **IV** | Implied Volatility — market's expected future volatility |
| **Expiry** | Last Thursday of the month (weekly: every Thursday) |

### PCR interpretation
- PCR > 1.2: Bearish sentiment (more puts bought = hedging)
- PCR 0.8–1.2: Neutral
- PCR < 0.8: Bullish sentiment (more calls bought)

### Options pricing note
Indian index options (NIFTY, BANKNIFTY) are **European-style** (exercised only at expiry).
Individual stock options are **American-style** (can be exercised any time).

---

## Important Sectors

| Sector | Key Stocks | Weight in NIFTY 50 (approx) |
|--------|------------|------------------------------|
| Financial Services | HDFCBANK, ICICIBANK, KOTAKBANK, SBI, BAJFINANCE | ~35% |
| IT | TCS, INFOSYS, WIPRO, HCLTECH, TECHM | ~15% |
| Oil & Gas | RELIANCE, ONGC, BPCL | ~12% |
| FMCG | ITC, HINDUNILEVER, NESTLEIND | ~8% |
| Automobiles | MARUTI, TATAMOTORS, M&M, BAJAJ-AUTO | ~7% |
| Pharma | SUNPHARMA, DRREDDY, CIPLA | ~5% |
| Metals | TATASTEEL, HINDALCO, JSWSTEEL | ~4% |

---

## Data Quality Notes

### What Yahoo Finance does well for Indian stocks:
- Daily OHLCV history (very complete, goes back 20+ years for large caps)
- Basic quote data (price, volume, P/E, market cap)
- Dividend history
- Annual financial statements

### What Yahoo Finance is weak on for Indian stocks:
- **Options data**: Coverage is limited and often delayed
- **Intraday data**: Only last 60 days, limited granularity
- **ESG scores**: Sparse for most Indian stocks
- **Mutual fund holdings**: May be incomplete or lagged
- **Insider transactions**: Less complete than US stocks
- **Quarterly earnings surprise data**: Often unavailable

### When to use other sources:
| Data need | Better source |
|-----------|---------------|
| Real-time F&O data | NSE India official website (nseindia.com) |
| Complete financial statements | Screener.in, Tickertape.in |
| BSE filings | BSE website (bseindia.com), BSE API |
| Promoter holdings (quarterly) | NSE/BSE shareholding pattern disclosures |
| Corporate announcements | BSE Corpus, NSE India announcements |
| Mutual fund NAV | AMFI India (amfiindia.com) |

---

## Settlement Cycle

Indian equities settle on **T+1 basis** (since January 2023):
- Buy on Monday → shares credited by Tuesday
- Sell on Monday → money credited by Tuesday

This is relevant when discussing:
- Ex-dividend dates (buy before ex-date to receive dividend)
- Record dates for corporate actions
- BTST (Buy Today Sell Tomorrow) trades

---

## Common Indian Market Events

| Event | Typical Timing | Market Impact |
|-------|---------------|---------------|
| **Union Budget** | February 1 | High volatility; broad market move |
| **RBI Monetary Policy** | 6 times/year (Feb, Apr, Jun, Aug, Oct, Dec) | Bank stocks, interest-rate sensitive sectors |
| **Quarterly Results Season** | 3–6 weeks after each quarter end | Individual stock volatility |
| **FII/DII Data** | Daily after market close | Sentiment indicator |
| **GST Collection Data** | Monthly | Economy health signal |
| **Auto Sales Data** | 1st week of each month | Auto sector indicator |

---

## Regulatory Bodies

| Body | Role |
|------|------|
| **SEBI** | Securities regulator (like SEC in US) |
| **RBI** | Central bank; sets interest rates |
| **NSE** | Exchange + clearing |
| **BSE** | Exchange |
| **CDSL / NSDL** | Depositories (hold shares electronically) |

---

## Disclaimers for User Responses

Always include when giving investment-related analysis:
> *Data sourced from Yahoo Finance and may be delayed by 15+ minutes. This is for informational purposes only and not investment advice. Verify data from official NSE/BSE sources before making investment decisions.*
