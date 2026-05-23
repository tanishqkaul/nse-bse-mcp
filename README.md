# 🇮🇳 NSE/BSE MCP Server v2.0

A [Model Context Protocol (MCP)](https://modelcontextprotocol.io) server for Indian stock market data —
covering the **National Stock Exchange (NSE)** and **Bombay Stock Exchange (BSE)**.

Plug into Claude Desktop and ask:
- *"Is TCS technically a buy right now? Show me RSI, MACD, and Supertrend."*
- *"What is the NIFTY50 at? Which sectors are leading today?"*
- *"Show me the RELIANCE options chain for next month, ATM ±5 strikes."*
- *"Compare HDFCBANK, ICICIBANK, and KOTAKBANK on P/E, ROE, and net margin."*
- *"Analyse my portfolio: 50 RELIANCE at ₹2400, 20 TCS at ₹3500."*
- *"What are promoters doing in Adani Ports? Any recent insider selling?"*

**No API key required.** Powered by [yfinance](https://github.com/ranaroussi/yfinance).

---

## Design Principle: Filter Arguments, Not Data Dumps

Every tool accepts `fields_to_return`, `limit_*`, `include`, and `indicators` parameters.
This lets the LLM specify exactly what it needs — keeping responses token-efficient and fast.

```json
{
  "name": "nse_bse_get_options",
  "arguments": {
    "symbol": "RELIANCE",
    "expiry": "2026-06-25",
    "option_type": "calls",
    "fields_to_return": ["strike", "implied_volatility", "open_interest"],
    "limit_strikes_near_atm": 5
  }
}
```

See [`docs/token-efficiency.md`](docs/token-efficiency.md) for token budgets and patterns.

---

## 🛠️ Tools (19 Total)

### Market Data
| Tool | Description |
|------|-------------|
| `nse_bse_get_quote` | Live price, change, valuation metrics (P/E, P/B, EPS, beta, ISIN) |
| `nse_bse_get_historical` | OHLCV history — period or date range, configurable interval and row limit |
| `nse_bse_get_index` | Quote and performance for any of 25 supported Indian indices |
| `nse_bse_list_indices` | List all supported indices with Yahoo Finance tickers |
| `nse_bse_sector_snapshot` | Parallel real-time fetch for all or selected indices — sorted by % change |

### Fundamental Analysis
| Tool | Description |
|------|-------------|
| `nse_bse_get_fundamentals` | Revenue, margins, ROE/ROA, balance sheet, analyst targets |
| `nse_bse_get_financials` | Annual / quarterly / TTM income statement, balance sheet, cash flow |
| `nse_bse_compare_stocks` | Side-by-side comparison for 2–10 stocks (parallel async fetch) |

### Options & Derivatives
| Tool | Description |
|------|-------------|
| `nse_bse_get_options` | Options chain with ATM filtering, field selection, calls/puts/both |

### Technical Analysis
| Tool | Description |
|------|-------------|
| `nse_bse_get_technicals` | RSI, MACD, Bollinger Bands, ATR, Supertrend, MAs, volume trend + composite signal |

### Corporate Actions & Events
| Tool | Description |
|------|-------------|
| `nse_bse_get_dividends` | Full dividend history + 5-year total |
| `nse_bse_get_corporate_actions` | Splits, dividends, and capital gains in one unified timeline |
| `nse_bse_get_earnings` | Earnings dates, calendar, EPS history, quarterly trend |

### Ownership & Governance
| Tool | Description |
|------|-------------|
| `nse_bse_get_shareholders` | Major holders, institutional holders, mutual fund holders |
| `nse_bse_get_insider_activity` | Promoter/insider buy-sell transactions with type filter |

### Research & Analyst
| Tool | Description |
|------|-------------|
| `nse_bse_get_analyst_view` | Ratings, upgrades/downgrades, price targets, EPS/revenue estimates |
| `nse_bse_get_news` | Recent news articles with timestamp and publisher |

### Portfolio & ESG
| Tool | Description |
|------|-------------|
| `nse_bse_portfolio_analysis` | P&L, sector allocation, weighted beta for up to 30 holdings |
| `nse_bse_get_esg` | ESG sustainability scores (where available) |

---

## 🚀 Installation

### Prerequisites
- Python 3.10+
- Claude Desktop

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/vanshikaaa01/nse-bse-mcp.git
cd nse-bse-mcp

# 2. Install dependencies
pip install -r requirements.txt
```

### Configure Claude Desktop

Find your config file:
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows:**
```json
{
  "mcpServers": {
    "nse-bse": {
      "command": "C:\\Python312\\python.exe",
      "args": ["C:\\full\\path\\to\\nse-bse-mcp\\server.py"]
    }
  }
}
```

**macOS/Linux:**
```json
{
  "mcpServers": {
    "nse-bse": {
      "command": "python3",
      "args": ["/full/path/to/nse-bse-mcp/server.py"]
    }
  }
}
```

Fully restart Claude Desktop after editing the config.

---

## 🧪 Running Tests

```bash
pip install pytest pytest-asyncio pytest-mock

# Run all tests
pytest

# Run only unit tests (fast, no network)
pytest tests/test_helpers.py

# Run tool tests (mocked yfinance, no network)
pytest tests/test_tools.py

# Verbose output
pytest -v

# Skip slow tests
pytest -m "not integration"
```

---

## 📚 Documentation

| Doc | Description |
|-----|-------------|
| [`docs/llm-best-practices.md`](docs/llm-best-practices.md) | How LLMs should call these tools effectively |
| [`docs/tool-reference.md`](docs/tool-reference.md) | Full parameter reference for all 19 tools |
| [`docs/token-efficiency.md`](docs/token-efficiency.md) | Token budgets and anti-patterns |
| [`docs/prompt-patterns.md`](docs/prompt-patterns.md) | 12 reusable research workflow recipes |
| [`docs/indian-market-guide.md`](docs/indian-market-guide.md) | NSE/BSE context, FY calendar, F&O basics for LLMs |

---

## 📊 Supported Indices (25)

**Broad Market:** NIFTY50, NIFTY100, NIFTY200, NIFTY500, NIFTYNEXT50

**Mid & Small Cap:** NIFTYMIDCAP50, NIFTYMIDCAP100, NIFTYMIDCAP150,
NIFTYSMALLCAP50, NIFTYSMALLCAP100, NIFTYSMALLCAP250, NIFTYLARGEMIDCAP250

**BSE:** SENSEX

**Sectoral:** NIFTYBANK, NIFTYIT, NIFTYPHARMA, NIFTYFMCG, NIFTYAUTO,
NIFTYREALTY, NIFTYINFRA, NIFTYMETAL, NIFTYENERGY, NIFTYCOMMODITIES, NIFTYFINSERVICE

**Volatility:** INDIAVIX

---

## ⚡ Architecture Highlights

- **Parallel fetch** — `compare_stocks` and `sector_snapshot` use `asyncio.gather` for concurrent requests
- **TTL cache** — 5-minute in-memory cache for `ticker.info` reduces Yahoo Finance rate-limit hits
- **Thread-pool execution** — all yfinance (synchronous) calls run in `ThreadPoolExecutor` for proper async behaviour
- **Technical indicators** — RSI, MACD, Bollinger Bands, ATR, Supertrend computed in pure NumPy/pandas (no heavy TA-Lib dependency)
- **Filter arguments** — every tool accepts `fields_to_return` / `include` / `limit_*` to keep responses lean
- **Pydantic v2 validation** — strict input validation with helpful error messages

---

## 📝 Notes

- Exchange suffixes (`.NS`, `.BO`) are added automatically — pass bare symbols like `RELIANCE`
- Data delayed ~15 minutes during market hours (Yahoo Finance limitation)
- Quarterly financial data may lag 3–6 weeks after quarter-end
- Options coverage on Yahoo Finance is limited for Indian stocks (best for: RELIANCE, INFY, TCS, HDFCBANK)
- ESG scores are sparse for Indian-listed companies on Yahoo Finance
- For real-time tick data, use a broker API (Zerodha Kite, AngelOne, Upstox)

---

## ⚠️ Disclaimer

For **educational and research purposes only**. Data sourced from Yahoo Finance and may
contain errors or delays. Not financial advice. Always verify from official NSE/BSE sources
before making investment decisions.

---

## 📄 License

MIT License — free to use, modify, and distribute.
