"""
NSE/BSE MCP Server v2.0
========================
A Model Context Protocol server for Indian stock market data.
Covers NSE (National Stock Exchange) and BSE (Bombay Stock Exchange).

Data source: Yahoo Finance via yfinance (no API key required)
Exchange suffixes: .NS for NSE, .BO for BSE

Design Philosophy
-----------------
Every tool accepts filtering arguments (fields_to_return, limit_*, top_n, indicators)
so the LLM specifies exactly what it needs — avoiding 10,000-token JSON dumps.
Network calls run in a ThreadPoolExecutor for correct async behavior.
A 5-minute TTL cache reduces Yahoo Finance rate-limit hits.

Author: Vanshika / Tanishq
License: MIT
"""

import json
import asyncio
import time
import math
import numpy as np
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

import yfinance as yf
import pandas as pd
from pydantic import BaseModel, Field, field_validator, ConfigDict, model_validator
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# ─── Server Init ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    "nse_bse_mcp",
    instructions=(
        "Indian stock market MCP for NSE/BSE. Use bare symbols (RELIANCE, not RELIANCE.NS) "
        "and specify exchange separately. Every tool accepts fields_to_return — always list "
        "only the fields you actually need to keep responses compact."
    ),
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

# ─── Constants ───────────────────────────────────────────────────────────────────

NSE_SUFFIX = ".NS"
BSE_SUFFIX = ".BO"

INDICES: Dict[str, str] = {
    # Broad market
    "NIFTY50":              "^NSEI",
    "NIFTY100":             "^CNX100",
    "NIFTY200":             "^CNX200",
    "NIFTY500":             "^CRSLDX",
    "NIFTYNEXT50":          "^NSMIDCP",
    # Mid & Small Cap
    "NIFTYMIDCAP50":        "^NSEMDCP50",
    "NIFTYMIDCAP100":       "^CNXMDCP100",
    "NIFTYMIDCAP150":       "^NIFTYMDCP150",
    "NIFTYSMALLCAP50":      "^NSESC50",
    "NIFTYSMALLCAP100":     "^NSESC100",
    "NIFTYSMALLCAP250":     "^CNXSC",
    "NIFTYLARGEMIDCAP250":  "^NIFTYLMID250",
    # BSE
    "SENSEX":               "^BSESN",
    # Sectoral
    "NIFTYBANK":            "^NSEBANK",
    "NIFTYIT":              "^CNXIT",
    "NIFTYPHARMA":          "^CNXPHARMA",
    "NIFTYFMCG":            "^CNXFMCG",
    "NIFTYAUTO":            "^CNXAUTO",
    "NIFTYREALTY":          "^CNXREALTY",
    "NIFTYINFRA":           "^CNXINFRA",
    "NIFTYMETAL":           "^CNXMETAL",
    "NIFTYENERGY":          "^CNXENERGY",
    "NIFTYCOMMODITIES":     "^CNXCMDT",
    "NIFTYFINSERVICE":      "^NIFTYFIN",
    # Volatility
    "INDIAVIX":             "^INDIAVIX",
}

VALID_PERIODS   = ["1d","5d","1mo","3mo","6mo","1y","2y","5y","10y","ytd","max"]
VALID_INTERVALS = ["1m","2m","5m","15m","30m","60m","90m","1h","1d","5d","1wk","1mo","3mo"]

QUOTE_FIELDS = [
    "symbol","exchange","name","price","change","change_pct","direction",
    "open","high","low","prev_close","volume","avg_volume",
    "week52_high","week52_low","ma_50d","ma_200d",
    "market_cap","market_cap_crore","pe_ratio","forward_pe","pb_ratio",
    "eps","forward_eps","dividend_yield","beta",
    "sector","industry","currency","isin",
]

OPTIONS_FIELDS = [
    "contract_symbol","strike","last_price","bid","ask",
    "change","change_pct","volume","open_interest",
    "implied_volatility","in_the_money","expiry",
]

TECHNICAL_INDICATORS = [
    "rsi","macd","bollinger_bands","atr","moving_averages","volume_trend","supertrend",
]

# ─── In-Memory TTL Cache ──────────────────────────────────────────────────────

_CACHE: Dict[str, tuple] = {}
_CACHE_TTL = 300  # 5 minutes

def _cache_get(key: str) -> Optional[Any]:
    if key in _CACHE:
        data, ts = _CACHE[key]
        if time.time() - ts < _CACHE_TTL:
            return data
        del _CACHE[key]
    return None

def _cache_set(key: str, data: Any) -> None:
    _CACHE[key] = (data, time.time())

# ─── Thread Pool (yfinance is sync) ──────────────────────────────────────────

_EXECUTOR = ThreadPoolExecutor(max_workers=12)

async def _run_sync(fn):
    """Run a zero-argument callable in the thread-pool and await the result."""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_EXECUTOR, fn)

# ─── Core Helpers ────────────────────────────────────────────────────────────

def build_ticker(symbol: str, exchange: str) -> str:
    s = symbol.upper().strip()
    return f"{s}{BSE_SUFFIX}" if exchange.upper() == "BSE" else f"{s}{NSE_SUFFIX}"

def safe_float(v) -> Optional[float]:
    try:
        f = float(v)
        return None if (math.isnan(f) or math.isinf(f)) else f
    except (TypeError, ValueError):
        return None

def safe_int(v) -> Optional[int]:
    try:
        return int(v)
    except (TypeError, ValueError):
        return None

def fmt_crore(value) -> str:
    f = safe_float(value)
    if f is None:
        return "N/A"
    crore = f / 1e7
    if crore >= 1e5:
        return f"₹{crore/1e5:.2f} Lakh Cr"
    if crore >= 1e2:
        return f"₹{crore:.2f} Cr"
    return f"₹{f:,.2f}"

def fmt_pct(value) -> str:
    f = safe_float(value)
    return "N/A" if f is None else f"{f*100:.2f}%"

def fmt_num(value, decimals: int = 2) -> str:
    f = safe_float(value)
    return "N/A" if f is None else f"{f:,.{decimals}f}"

def handle_error(e: Exception, context: str = "") -> str:
    msg = str(e)
    if "No data found" in msg or "404" in msg:
        return json.dumps({"error": f"Symbol not found on this exchange. Try NSE/BSE or check spelling.", "context": context})
    if "Rate" in msg or "429" in msg:
        return json.dumps({"error": "Rate limit hit. Wait a few seconds and retry."})
    if "timeout" in msg.lower():
        return json.dumps({"error": "Request timed out. Please retry.", "context": context})
    return json.dumps({"error": msg, "context": context})

def filter_fields(data: dict, fields: Optional[List[str]]) -> dict:
    """Return only specified keys from a dict; return all if fields is None."""
    if not fields:
        return data
    return {k: v for k, v in data.items() if k in fields}

def filter_records(records: List[dict], fields: Optional[List[str]]) -> List[dict]:
    """Apply filter_fields to every record in a list."""
    if not fields:
        return records
    return [{k: v for k, v in r.items() if k in fields} for r in records]

def _df_to_crore_dict(df: pd.DataFrame, max_cols: int = 4) -> dict:
    """Convert a financial-statement DataFrame to an ₹-crore dict."""
    if df is None or df.empty:
        return {}
    result: dict = {}
    for col in list(df.columns)[:max_cols]:
        col_str = str(col)[:10]
        result[col_str] = {}
        for row, val in df[col].items():
            f = safe_float(val)
            result[col_str][str(row)] = round(f / 1e7, 2) if f is not None else None
    return result

def _series_to_crore_dict(s) -> dict:
    """Convert a single-column TTM DataFrame or Series to ₹-crore dict."""
    if s is None:
        return {}
    if isinstance(s, pd.DataFrame):
        s = s.iloc[:, 0]
    result: dict = {}
    for row, val in s.items():
        f = safe_float(val)
        result[str(row)] = round(f / 1e7, 2) if f is not None else None
    return result

# ─── Technical Indicator Functions ───────────────────────────────────────────

def _atr_numpy(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's ATR using pure numpy (avoids pandas SettingWithCopyWarning)."""
    prev_close = np.empty_like(close)
    prev_close[0] = close[0]
    prev_close[1:] = close[:-1]
    tr = np.maximum(
        high - low,
        np.maximum(np.abs(high - prev_close), np.abs(low - prev_close))
    )
    atr = np.zeros(len(tr))
    atr[0] = tr[0]
    for i in range(1, len(tr)):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period
    return atr

def calc_rsi(close: pd.Series, period: int = 14) -> Optional[float]:
    delta = close.diff()
    gain  = delta.clip(lower=0)
    loss  = (-delta).clip(lower=0)
    avg_g = gain.ewm(com=period - 1, adjust=False).mean()
    avg_l = loss.ewm(com=period - 1, adjust=False).mean()
    # When avg_loss is 0 (pure uptrend), RSI = 100 by definition
    last_loss = safe_float(avg_l.iloc[-1])
    if last_loss is not None and last_loss == 0.0:
        return 100.0
    avg_l_safe = avg_l.replace(0, float("nan"))
    rsi = 100 - (100 / (1 + avg_g / avg_l_safe))
    v = safe_float(rsi.iloc[-1])
    return round(v, 2) if v is not None else None

def calc_macd(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> dict:
    ema_f    = close.ewm(span=fast,   adjust=False).mean()
    ema_s    = close.ewm(span=slow,   adjust=False).mean()
    macd_l   = ema_f - ema_s
    signal_l = macd_l.ewm(span=signal, adjust=False).mean()
    hist     = macd_l - signal_l
    m  = safe_float(macd_l.iloc[-1])   or 0.0
    sl = safe_float(signal_l.iloc[-1]) or 0.0
    h  = safe_float(hist.iloc[-1])     or 0.0
    return {
        "macd_line":   round(m,  4),
        "signal_line": round(sl, 4),
        "histogram":   round(h,  4),
        "crossover":   "bullish" if m > sl else "bearish",
    }

def calc_bollinger_bands(close: pd.Series, period: int = 20, std_dev: float = 2.0) -> dict:
    sma   = close.rolling(period).mean()
    std   = close.rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    price = float(close.iloc[-1])
    u = safe_float(upper.iloc[-1])
    l = safe_float(lower.iloc[-1])
    m = safe_float(sma.iloc[-1])
    pct_b = ((price - l) / (u - l)) if (u and l and u != l) else None
    return {
        "upper":  round(u, 2) if u else None,
        "middle": round(m, 2) if m else None,
        "lower":  round(l, 2) if l else None,
        "pct_b":  round(pct_b, 4) if pct_b is not None else None,
        "signal": "overbought" if (pct_b and pct_b > 1) else ("oversold" if (pct_b and pct_b < 0) else "neutral"),
    }

def calc_atr_scalar(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    arr = _atr_numpy(df["High"].values, df["Low"].values, df["Close"].values, period)
    v   = safe_float(arr[-1])
    return round(v, 2) if v else None

def calc_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> dict:
    h = df["High"].values
    l = df["Low"].values
    c = df["Close"].values
    if len(c) < period + 1:
        return {"direction": "insufficient_data", "value": None}
    atr   = _atr_numpy(h, l, c, period)
    hl2   = (h + l) / 2
    upper = hl2 + multiplier * atr
    lower = hl2 - multiplier * atr
    fu = upper.copy()
    fl = lower.copy()
    direction = np.ones(len(c), dtype=int)
    for i in range(1, len(c)):
        fu[i] = upper[i] if (upper[i] < fu[i-1] or c[i-1] > fu[i-1]) else fu[i-1]
        fl[i] = lower[i] if (lower[i] > fl[i-1] or c[i-1] < fl[i-1]) else fl[i-1]
        if direction[i-1] == 1:
            direction[i] = -1 if c[i] < fl[i] else 1
        else:
            direction[i] = 1 if c[i] > fu[i] else -1
    is_bull = direction[-1] == 1
    return {
        "direction": "bullish" if is_bull else "bearish",
        "value":     round(float(fl[-1] if is_bull else fu[-1]), 2),
    }

def _signal_summary(rsi: Optional[float], macd: dict, bb: dict, st: dict) -> dict:
    score, reasons = 0, []
    if rsi is not None:
        if   rsi < 30: score += 2; reasons.append("RSI oversold (<30)")
        elif rsi < 45: score += 1; reasons.append("RSI in lower zone (30-45)")
        elif rsi > 70: score -= 2; reasons.append("RSI overbought (>70)")
        elif rsi > 55: score -= 1; reasons.append("RSI in upper zone (55-70)")
    if macd.get("crossover") == "bullish": score += 1; reasons.append("MACD bullish crossover")
    elif macd.get("crossover") == "bearish": score -= 1; reasons.append("MACD bearish crossover")
    if bb.get("signal") == "oversold":   score += 1; reasons.append("Price below lower BB")
    elif bb.get("signal") == "overbought": score -= 1; reasons.append("Price above upper BB")
    if st.get("direction") == "bullish":  score += 1; reasons.append("Supertrend bullish")
    elif st.get("direction") == "bearish": score -= 1; reasons.append("Supertrend bearish")
    if score >= 3:  label = "STRONG_BUY"
    elif score >= 1: label = "BUY"
    elif score <= -3: label = "STRONG_SELL"
    elif score <= -1: label = "SELL"
    else: label = "NEUTRAL"
    return {"signal": label, "score": score, "reasons": reasons}

# ─── Pydantic Input Models ───────────────────────────────────────────────────

class Exchange(str, Enum):
    NSE = "NSE"
    BSE = "BSE"


class StockInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbol: str = Field(..., description="Bare stock symbol, e.g. RELIANCE, TCS, INFY", min_length=1, max_length=20)
    exchange: Exchange = Field(default=Exchange.NSE, description="'NSE' (default) or 'BSE'")
    fields_to_return: Optional[List[str]] = Field(
        default=None,
        description=f"Limit response fields. Available: {', '.join(QUOTE_FIELDS)}"
    )
    @field_validator("symbol")
    @classmethod
    def _up(cls, v): return v.upper()


class HistoricalInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbol:   str      = Field(..., min_length=1, max_length=20)
    exchange: Exchange = Field(default=Exchange.NSE)
    period:   Optional[str] = Field(default=None, description="1d,5d,1mo,3mo,6mo,1y,2y,5y,10y,ytd,max")
    interval: str      = Field(default="1d",  description="1m,5m,15m,1h,1d,1wk,1mo")
    start_date: Optional[str] = Field(default=None, description="YYYY-MM-DD start date (alternative to period)")
    end_date:   Optional[str] = Field(default=None, description="YYYY-MM-DD end date (default: today)")
    max_records: int = Field(default=100, ge=1, le=500, description="Max rows to return (1–500)")
    fields_to_return: Optional[List[str]] = Field(
        default=None, description="Fields per row: date,open,high,low,close,volume,daily_return_pct"
    )
    @field_validator("symbol")
    @classmethod
    def _up(cls, v): return v.upper()
    @field_validator("period")
    @classmethod
    def _vp(cls, v):
        if v and v not in VALID_PERIODS:
            raise ValueError(f"period must be one of: {', '.join(VALID_PERIODS)}")
        return v
    @field_validator("interval")
    @classmethod
    def _vi(cls, v):
        if v not in VALID_INTERVALS:
            raise ValueError(f"interval must be one of: {', '.join(VALID_INTERVALS)}")
        return v
    @model_validator(mode="after")
    def _default_period(self):
        if self.period is None and self.start_date is None:
            self.period = "3mo"
        return self


class CompareInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbols: List[str] = Field(..., min_length=2, max_length=10,
        description="2–10 stock symbols, e.g. ['RELIANCE','TCS','INFY']")
    exchange: Exchange = Field(default=Exchange.NSE)
    fields_to_return: Optional[List[str]] = Field(
        default=None,
        description="Metrics: price,change_pct,market_cap_cr,pe,pb,roe_pct,npm_pct,div_yield_pct,beta,sector"
    )
    @field_validator("symbols")
    @classmethod
    def _up(cls, v): return [s.upper().strip() for s in v]


class IndexInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    index:  str      = Field(..., description=f"Options: {', '.join(INDICES.keys())}")
    period: str      = Field(default="1d", description="1d,5d,1mo,3mo,6mo,1y")
    fields_to_return: Optional[List[str]] = Field(default=None)
    @field_validator("index")
    @classmethod
    def _up(cls, v): return v.upper().strip()


class OptionsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbol:   str      = Field(..., min_length=1, max_length=20,
        description="Stock symbol, e.g. RELIANCE. Note: options availability varies on Yahoo Finance.")
    exchange: Exchange = Field(default=Exchange.NSE)
    expiry:   Optional[str] = Field(default=None,
        description="YYYY-MM-DD expiry. If omitted, returns available expiry dates.")
    option_type: str = Field(default="both", description="'calls', 'puts', or 'both'")
    fields_to_return: Optional[List[str]] = Field(
        default=None, description=f"Fields: {', '.join(OPTIONS_FIELDS)}"
    )
    limit_strikes_near_atm: Optional[int] = Field(
        default=None, ge=1, le=20,
        description="Return only N strikes above AND below ATM. E.g. 5 → 11 total strikes."
    )
    @field_validator("symbol")
    @classmethod
    def _up(cls, v): return v.upper()
    @field_validator("option_type")
    @classmethod
    def _ot(cls, v):
        if v not in ("calls","puts","both"):
            raise ValueError("option_type must be 'calls', 'puts', or 'both'")
        return v


class NewsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbol:   str      = Field(..., min_length=1, max_length=20)
    exchange: Exchange = Field(default=Exchange.NSE)
    limit:    int      = Field(default=10, ge=1, le=25, description="Number of articles (1–25)")
    fields_to_return: Optional[List[str]] = Field(
        default=None, description="Fields: title,publisher,link,published_at,related_tickers"
    )
    @field_validator("symbol")
    @classmethod
    def _up(cls, v): return v.upper()


class AnalystInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbol:   str      = Field(..., min_length=1, max_length=20)
    exchange: Exchange = Field(default=Exchange.NSE)
    include:  Optional[List[str]] = Field(
        default=None,
        description="Sections: recommendations_summary, upgrades_downgrades, price_targets, "
                    "earnings_estimates, revenue_estimates, growth_estimates. None = all."
    )
    limit_upgrades: int = Field(default=10, ge=1, le=50)
    @field_validator("symbol")
    @classmethod
    def _up(cls, v): return v.upper()


class EarningsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbol:   str      = Field(..., min_length=1, max_length=20)
    exchange: Exchange = Field(default=Exchange.NSE)
    include:  Optional[List[str]] = Field(
        default=None,
        description="Sections: earnings_dates, calendar, earnings_history, quarterly_earnings. None = all."
    )
    limit: int = Field(default=8, ge=1, le=20)
    @field_validator("symbol")
    @classmethod
    def _up(cls, v): return v.upper()


class InsiderInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbol:   str      = Field(..., min_length=1, max_length=20)
    exchange: Exchange = Field(default=Exchange.NSE)
    include:  Optional[List[str]] = Field(
        default=None, description="Sections: transactions, purchases, roster. None = all."
    )
    limit: int = Field(default=20, ge=1, le=50)
    transaction_type: Optional[str] = Field(
        default=None, description="Filter by: 'buy', 'sell', or None for all"
    )
    @field_validator("symbol")
    @classmethod
    def _up(cls, v): return v.upper()


class TechnicalInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbol:     str      = Field(..., min_length=1, max_length=20)
    exchange:   Exchange = Field(default=Exchange.NSE)
    indicators: Optional[List[str]] = Field(
        default=None,
        description=f"Indicators to compute: {', '.join(TECHNICAL_INDICATORS)}. None = all."
    )
    period: str = Field(default="6mo", description="Historical period for computation: 3mo, 6mo, 1y")
    @field_validator("symbol")
    @classmethod
    def _up(cls, v): return v.upper()


class SectorSnapshotInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    indices: Optional[List[str]] = Field(
        default=None, description="Specific indices to include. None = all."
    )
    fields_to_return: Optional[List[str]] = Field(
        default=None, description="Fields per index: name,level,change,change_pct,week52_high,week52_low"
    )


class PortfolioHolding(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbol:         str      = Field(..., min_length=1, max_length=20)
    quantity:       float    = Field(..., gt=0)
    avg_buy_price:  float    = Field(..., gt=0, description="Average buy price per share in INR")
    exchange:       Exchange = Field(default=Exchange.NSE)
    @field_validator("symbol")
    @classmethod
    def _up(cls, v): return v.upper()


class PortfolioInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    holdings: List[PortfolioHolding] = Field(..., min_length=1, max_length=30)
    fields_to_return: Optional[List[str]] = Field(
        default=None,
        description="Sections: summary, per_stock, sector_allocation, risk_metrics. None = all."
    )


class FinancialsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbol:    str      = Field(..., min_length=1, max_length=20)
    exchange:  Exchange = Field(default=Exchange.NSE)
    frequency: str      = Field(
        default="annual",
        description="'annual' (last 4 FY), 'quarterly' (last 4 quarters), 'ttm' (trailing 12 months)"
    )
    statements: Optional[List[str]] = Field(
        default=None,
        description="Statements: income_statement, balance_sheet, cash_flow. None = all."
    )
    @field_validator("symbol")
    @classmethod
    def _up(cls, v): return v.upper()
    @field_validator("frequency")
    @classmethod
    def _vf(cls, v):
        if v not in ("annual","quarterly","ttm"):
            raise ValueError("frequency must be 'annual', 'quarterly', or 'ttm'")
        return v


class ShareholdersInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbol:              str      = Field(..., min_length=1, max_length=20)
    exchange:            Exchange = Field(default=Exchange.NSE)
    include_mutualfunds: bool     = Field(default=True)
    top_n:               int      = Field(default=15, ge=1, le=50)
    @field_validator("symbol")
    @classmethod
    def _up(cls, v): return v.upper()


class ESGInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, validate_assignment=True, extra="forbid")
    symbol:   str      = Field(..., min_length=1, max_length=20)
    exchange: Exchange = Field(default=Exchange.NSE)
    fields_to_return: Optional[List[str]] = Field(
        default=None,
        description="Fields: total_esg,environment_score,social_score,governance_score,"
                    "controversy_level,percentile,peer_group"
    )
    @field_validator("symbol")
    @classmethod
    def _up(cls, v): return v.upper()


# ─── Tool 1: Live Quote ───────────────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_quote",
    annotations={"title":"Get Live Stock Quote","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_quote(params: StockInput) -> str:
    """
    Get a real-time quote for any NSE/BSE stock.

    Returns price, change, valuation metrics (P/E, P/B, EPS, market cap),
    52-week range, moving averages, sector, and ISIN.
    Use fields_to_return to get only the metrics you need.

    Args:
        params: symbol, exchange, fields_to_return (optional)
    Returns:
        JSON with quote data. Monetary values in INR.
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        cache_key  = f"quote:{ticker_str}"
        info = _cache_get(cache_key)
        if info is None:
            t    = yf.Ticker(ticker_str)
            info = await _run_sync(lambda: t.info)
            _cache_set(cache_key, info)

        price      = safe_float(info.get("regularMarketPrice") or info.get("currentPrice"))
        prev_close = safe_float(info.get("previousClose"))
        if not price:
            return json.dumps({"error": f"No price data for {params.symbol} on {params.exchange}."})
        change     = round(price - prev_close, 2) if prev_close else None
        pct_change = round((change / prev_close) * 100, 2) if (change and prev_close) else None
        market_cap = safe_float(info.get("marketCap"))

        result = {
            "symbol":          params.symbol,
            "exchange":        params.exchange,
            "name":            info.get("longName", params.symbol),
            "price":           price,
            "change":          change,
            "change_pct":      pct_change,
            "direction":       "▲" if (change and change >= 0) else "▼",
            "open":            safe_float(info.get("open")),
            "high":            safe_float(info.get("dayHigh")),
            "low":             safe_float(info.get("dayLow")),
            "prev_close":      prev_close,
            "volume":          safe_int(info.get("volume")),
            "avg_volume":      safe_int(info.get("averageVolume10days")),
            "week52_high":     safe_float(info.get("fiftyTwoWeekHigh")),
            "week52_low":      safe_float(info.get("fiftyTwoWeekLow")),
            "ma_50d":          safe_float(info.get("fiftyDayAverage")),
            "ma_200d":         safe_float(info.get("twoHundredDayAverage")),
            "market_cap":      market_cap,
            "market_cap_crore": round(market_cap / 1e7, 2) if market_cap else None,
            "pe_ratio":        safe_float(info.get("trailingPE")),
            "forward_pe":      safe_float(info.get("forwardPE")),
            "pb_ratio":        safe_float(info.get("priceToBook")),
            "eps":             safe_float(info.get("trailingEps")),
            "forward_eps":     safe_float(info.get("forwardEps")),
            "dividend_yield":  safe_float(info.get("dividendYield")),
            "beta":            safe_float(info.get("beta")),
            "sector":          info.get("sector", "N/A"),
            "industry":        info.get("industry", "N/A"),
            "currency":        info.get("currency", "INR"),
            "isin":            info.get("isin", "N/A"),
        }
        return json.dumps(filter_fields(result, params.fields_to_return), indent=2)
    except Exception as e:
        return handle_error(e, f"{params.symbol} on {params.exchange}")


# ─── Tool 2: Historical OHLCV ────────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_historical",
    annotations={"title":"Get Historical OHLCV Data","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_historical(params: HistoricalInput) -> str:
    """
    Get OHLCV price history for a stock.

    Supports both period= (e.g. '1y') and start_date/end_date (e.g. '2024-01-01').
    Use max_records to cap row count, fields_to_return to limit columns.

    Args:
        params: symbol, exchange, period|start_date/end_date, interval, max_records, fields_to_return
    Returns:
        JSON with summary + list of OHLCV records.
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        t = yf.Ticker(ticker_str)

        if params.start_date:
            df = await _run_sync(
                lambda: t.history(
                    start=params.start_date,
                    end=params.end_date or datetime.today().strftime("%Y-%m-%d"),
                    interval=params.interval,
                )
            )
        else:
            df = await _run_sync(lambda: t.history(period=params.period, interval=params.interval))

        if df.empty:
            return json.dumps({"error": f"No data for {params.symbol} ({params.period or params.start_date})"})

        df = df.reset_index()
        df["Date"] = df["Date"].astype(str).str[:10]
        df["Return_%"] = df["Close"].pct_change().mul(100).round(2)

        records = []
        for _, row in df.tail(params.max_records).iterrows():
            rec = {
                "date":              str(row["Date"]),
                "open":              round(float(row["Open"]), 2),
                "high":              round(float(row["High"]), 2),
                "low":               round(float(row["Low"]), 2),
                "close":             round(float(row["Close"]), 2),
                "volume":            int(row["Volume"]),
                "daily_return_pct":  safe_float(row["Return_%"]),
            }
            records.append(rec)

        first_c = float(df["Close"].iloc[0])
        last_c  = float(df["Close"].iloc[-1])
        result  = {
            "symbol":   params.symbol,
            "exchange": params.exchange,
            "period":   params.period or f"{params.start_date} → {params.end_date or 'today'}",
            "interval": params.interval,
            "summary": {
                "start_date":        records[0]["date"] if records else None,
                "end_date":          records[-1]["date"] if records else None,
                "start_price":       round(first_c, 2),
                "end_price":         round(last_c, 2),
                "total_return_pct":  round(((last_c - first_c) / first_c) * 100, 2),
                "period_high":       round(float(df["High"].max()), 2),
                "period_low":        round(float(df["Low"].min()), 2),
                "avg_daily_volume":  int(df["Volume"].mean()),
                "records_shown":     len(records),
            },
            "data": filter_records(records, params.fields_to_return),
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        return handle_error(e, f"historical {params.symbol}")


# ─── Tool 3: Fundamentals ────────────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_fundamentals",
    annotations={"title":"Get Stock Fundamentals","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_fundamentals(params: StockInput) -> str:
    """
    Get profitability, balance-sheet, per-share, growth, and analyst metrics.

    Covers revenue, margins, ROE/ROA, debt ratios, EPS, dividend, analyst targets.
    Use fields_to_return to limit which metrics are returned.

    Available fields (fields_to_return): revenue, gross_profit, ebitda,
    operating_income, net_income, gross_margin, operating_margin, net_margin,
    roe, roa, total_assets, total_debt, cash, book_value, debt_equity,
    current_ratio, quick_ratio, eps_ttm, forward_eps, revenue_per_share,
    cash_per_share, dividend_per_share, payout_ratio, earnings_growth,
    revenue_growth, target_mean, target_high, target_low, recommendation,
    analyst_count, description.

    Args:
        params: symbol, exchange, fields_to_return
    Returns:
        JSON with fundamental data. Monetary values in INR crore unless noted.
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        cache_key  = f"info:{ticker_str}"
        info = _cache_get(cache_key)
        if info is None:
            t    = yf.Ticker(ticker_str)
            info = await _run_sync(lambda: t.info)
            _cache_set(cache_key, info)

        def crore(k): return round(safe_float(info.get(k)) / 1e7, 2) if safe_float(info.get(k)) else None
        def pct(k):   return safe_float(info.get(k))

        result = {
            "symbol":            params.symbol,
            "exchange":          params.exchange,
            "name":              info.get("longName", params.symbol),
            # Income
            "revenue":           crore("totalRevenue"),
            "gross_profit":      crore("grossProfits"),
            "ebitda":            crore("ebitda"),
            "operating_income":  crore("operatingIncome"),
            "net_income":        crore("netIncomeToCommon"),
            # Margins
            "gross_margin":      pct("grossMargins"),
            "operating_margin":  pct("operatingMargins"),
            "net_margin":        pct("profitMargins"),
            "roe":               pct("returnOnEquity"),
            "roa":               pct("returnOnAssets"),
            # Balance sheet
            "total_assets":      crore("totalAssets"),
            "total_debt":        crore("totalDebt"),
            "cash":              crore("totalCash"),
            "book_value":        safe_float(info.get("bookValue")),
            "debt_equity":       safe_float(info.get("debtToEquity")),
            "current_ratio":     safe_float(info.get("currentRatio")),
            "quick_ratio":       safe_float(info.get("quickRatio")),
            # Per share
            "eps_ttm":           safe_float(info.get("trailingEps")),
            "forward_eps":       safe_float(info.get("forwardEps")),
            "revenue_per_share": safe_float(info.get("revenuePerShare")),
            "cash_per_share":    safe_float(info.get("totalCashPerShare")),
            "dividend_per_share":safe_float(info.get("lastDividendValue")),
            "payout_ratio":      pct("payoutRatio"),
            # Growth
            "earnings_growth":   pct("earningsGrowth"),
            "revenue_growth":    pct("revenueGrowth"),
            # Analyst
            "target_mean":       safe_float(info.get("targetMeanPrice")),
            "target_high":       safe_float(info.get("targetHighPrice")),
            "target_low":        safe_float(info.get("targetLowPrice")),
            "recommendation":    info.get("recommendationKey","N/A"),
            "analyst_count":     safe_int(info.get("numberOfAnalystOpinions")),
            "description":       (info.get("longBusinessSummary","")[:600] or "N/A"),
        }
        return json.dumps(filter_fields(result, params.fields_to_return), indent=2)
    except Exception as e:
        return handle_error(e, f"fundamentals {params.symbol}")


# ─── Tool 4: Financial Statements (annual / quarterly / TTM) ─────────────────

@mcp.tool(
    name="nse_bse_get_financials",
    annotations={"title":"Get Financial Statements","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_financials(params: FinancialsInput) -> str:
    """
    Get income statement, balance sheet, and cash flow statement.

    Use frequency='annual' (last 4 FY), 'quarterly' (last 4 quarters),
    or 'ttm' (trailing 12-month). Use statements= to limit which statements
    are fetched (income_statement, balance_sheet, cash_flow).

    Args:
        params: symbol, exchange, frequency, statements
    Returns:
        JSON with financial data. All values in Indian Crore (₹).
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        t = yf.Ticker(ticker_str)
        want = set(params.statements or ["income_statement","balance_sheet","cash_flow"])
        result: dict = {
            "symbol":    params.symbol,
            "exchange":  params.exchange,
            "frequency": params.frequency,
            "note":      "All monetary values in Indian Crore (₹). Column headers are period-end dates.",
        }

        if params.frequency == "annual":
            if "income_statement" in want:
                df = await _run_sync(lambda: t.financials)
                result["income_statement"] = _df_to_crore_dict(df) if (df is not None and not df.empty) else "unavailable"
            if "balance_sheet" in want:
                df = await _run_sync(lambda: t.balance_sheet)
                result["balance_sheet"] = _df_to_crore_dict(df) if (df is not None and not df.empty) else "unavailable"
            if "cash_flow" in want:
                df = await _run_sync(lambda: t.cashflow)
                result["cash_flow"] = _df_to_crore_dict(df) if (df is not None and not df.empty) else "unavailable"

        elif params.frequency == "quarterly":
            if "income_statement" in want:
                df = await _run_sync(lambda: t.quarterly_income_stmt)
                result["income_statement"] = _df_to_crore_dict(df) if (df is not None and not df.empty) else "unavailable"
            if "balance_sheet" in want:
                df = await _run_sync(lambda: t.quarterly_balance_sheet)
                result["balance_sheet"] = _df_to_crore_dict(df) if (df is not None and not df.empty) else "unavailable"
            if "cash_flow" in want:
                df = await _run_sync(lambda: t.quarterly_cashflow)
                result["cash_flow"] = _df_to_crore_dict(df) if (df is not None and not df.empty) else "unavailable"

        else:  # ttm
            if "income_statement" in want:
                df = await _run_sync(lambda: t.ttm_income_stmt)
                result["income_statement"] = _series_to_crore_dict(df) if df is not None else "unavailable"
            if "cash_flow" in want:
                df = await _run_sync(lambda: t.ttm_cashflow)
                result["cash_flow"] = _series_to_crore_dict(df) if df is not None else "unavailable"
            if "balance_sheet" in want:
                df = await _run_sync(lambda: t.quarterly_balance_sheet)
                result["balance_sheet_latest_quarter"] = _df_to_crore_dict(df, max_cols=1) if (df is not None and not df.empty) else "unavailable"

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return handle_error(e, f"financials {params.symbol}")


# ─── Tool 5: Compare Stocks (parallel fetch) ─────────────────────────────────

@mcp.tool(
    name="nse_bse_compare_stocks",
    annotations={"title":"Compare Multiple Stocks","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_compare_stocks(params: CompareInput) -> str:
    """
    Compare key metrics for 2–10 stocks side-by-side using parallel fetch.

    Default metrics: price, change_pct, market_cap_cr, pe, pb, roe_pct, npm_pct,
    div_yield_pct, beta, sector. Use fields_to_return to select only the metrics needed.

    Args:
        params: symbols (list), exchange, fields_to_return
    Returns:
        JSON list of per-stock metric objects.
    """
    async def fetch_one(sym: str) -> dict:
        ticker_str = build_ticker(sym, params.exchange)
        try:
            t    = yf.Ticker(ticker_str)
            info = await _run_sync(lambda: t.info)
            price      = safe_float(info.get("regularMarketPrice") or info.get("currentPrice"))
            prev_close = safe_float(info.get("previousClose"))
            change_pct = round(((price - prev_close) / prev_close) * 100, 2) if (price and prev_close) else None
            mc = safe_float(info.get("marketCap"))
            return {
                "symbol":        sym,
                "name":          info.get("shortName", sym)[:25],
                "price":         price,
                "change_pct":    change_pct,
                "direction":     "▲" if (change_pct and change_pct >= 0) else "▼",
                "market_cap_cr": round(mc / 1e7, 0) if mc else None,
                "pe":            safe_float(info.get("trailingPE")),
                "pb":            safe_float(info.get("priceToBook")),
                "roe_pct":       round(safe_float(info.get("returnOnEquity")) * 100, 1) if safe_float(info.get("returnOnEquity")) else None,
                "npm_pct":       round(safe_float(info.get("profitMargins")) * 100, 1) if safe_float(info.get("profitMargins")) else None,
                "div_yield_pct": round(safe_float(info.get("dividendYield")) * 100, 2) if safe_float(info.get("dividendYield")) else None,
                "beta":          safe_float(info.get("beta")),
                "sector":        info.get("sector", "N/A"),
            }
        except Exception as e:
            return {"symbol": sym, "error": str(e)}

    try:
        rows = await asyncio.gather(*[fetch_one(s) for s in params.symbols])
        filtered = [filter_fields(r, params.fields_to_return) for r in rows]
        return json.dumps({"exchange": params.exchange, "data": filtered}, indent=2)
    except Exception as e:
        return handle_error(e, "compare stocks")


# ─── Tool 6: Index Quote ─────────────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_index",
    annotations={"title":"Get Index Quote & Performance","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_index(params: IndexInput) -> str:
    """
    Get current quote and period performance for a major Indian market index.

    Supported: NIFTY50, SENSEX, NIFTYBANK, and 20+ more. See nse_bse_list_indices.

    Args:
        params: index, period, fields_to_return
    Returns:
        JSON with level, change, 52-week range, period performance.
    """
    try:
        if params.index not in INDICES:
            return json.dumps({"error": f"Unknown index '{params.index}'.", "valid": list(INDICES.keys())})
        ticker_str = INDICES[params.index]
        t = yf.Ticker(ticker_str)
        info = await _run_sync(lambda: t.info)
        hist = await _run_sync(lambda: t.history(period=params.period, interval="1d"))

        price      = safe_float(info.get("regularMarketPrice") or info.get("previousClose"))
        prev_close = safe_float(info.get("previousClose"))
        change     = round(price - prev_close, 2) if (price and prev_close) else None
        pct_change = round((change / prev_close) * 100, 2) if (change and prev_close) else None

        period_perf: dict = {}
        if not hist.empty:
            s = float(hist["Close"].iloc[0])
            e = float(hist["Close"].iloc[-1])
            period_perf = {
                "period_return_pct": round(((e - s) / s) * 100, 2),
                "period_high":       round(float(hist["High"].max()), 2),
                "period_low":        round(float(hist["Low"].min()), 2),
            }

        result = {
            "index":       params.index,
            "yahoo_ticker":ticker_str,
            "level":       price,
            "change":      change,
            "change_pct":  pct_change,
            "direction":   "▲" if (change and change >= 0) else "▼",
            "week52_high": safe_float(info.get("fiftyTwoWeekHigh")),
            "week52_low":  safe_float(info.get("fiftyTwoWeekLow")),
            "ma_50d":      safe_float(info.get("fiftyDayAverage")),
            "ma_200d":     safe_float(info.get("twoHundredDayAverage")),
            **period_perf,
        }
        return json.dumps(filter_fields(result, params.fields_to_return), indent=2)
    except Exception as e:
        return handle_error(e, f"index {params.index}")


# ─── Tool 7: List Indices ────────────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_list_indices",
    annotations={"title":"List Available Indices","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":False},
)
async def nse_bse_list_indices() -> str:
    """
    List all Indian market indices supported by this MCP server.

    Returns:
        JSON list of {name, yahoo_ticker} objects.
    """
    return json.dumps(
        [{"name": k, "yahoo_ticker": v} for k, v in INDICES.items()],
        indent=2,
    )


# ─── Tool 8: Dividends ───────────────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_dividends",
    annotations={"title":"Get Dividend History","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_dividends(params: StockInput) -> str:
    """
    Get full dividend payout history for a stock.

    Returns the most recent 20 dividends (most recent first), total paid in last 5 years.

    Args:
        params: symbol, exchange
    Returns:
        JSON with dividend list and summary stats.
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        t    = yf.Ticker(ticker_str)
        divs = await _run_sync(lambda: t.dividends)

        if divs is None or divs.empty:
            return json.dumps({"symbol": params.symbol, "exchange": params.exchange,
                                "message": "No dividend history. Stock may not pay dividends.", "dividends": []})
        div_list = [{"date": str(d)[:10], "dividend_inr": round(float(a), 4)} for d, a in divs.items()]
        div_list.reverse()
        current_year = datetime.now().year
        total_5y = sum(d["dividend_inr"] for d in div_list if int(d["date"][:4]) >= current_year - 5)
        return json.dumps({
            "symbol":                    params.symbol,
            "exchange":                  params.exchange,
            "total_dividends_last_5y":   round(total_5y, 2),
            "total_payments_on_record":  len(div_list),
            "dividends":                 div_list[:20],
        }, indent=2)
    except Exception as e:
        return handle_error(e, f"dividends {params.symbol}")


# ─── Tool 9: Shareholders ────────────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_shareholders",
    annotations={"title":"Get Shareholding Data","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_shareholders(params: ShareholdersInput) -> str:
    """
    Get major holders, institutional holders, and optionally mutual fund holders.

    Args:
        params: symbol, exchange, include_mutualfunds, top_n
    Returns:
        JSON with major_holders, institutional_holders, mutualfund_holders (if requested).
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        t = yf.Ticker(ticker_str)
        result: dict = {"symbol": params.symbol, "exchange": params.exchange}

        major = await _run_sync(lambda: t.major_holders)
        if major is not None and not major.empty:
            result["major_holders"] = {str(row.iloc[1]): str(row.iloc[0]) for _, row in major.iterrows()}
        else:
            result["major_holders"] = "unavailable"

        inst = await _run_sync(lambda: t.institutional_holders)
        if inst is not None and not inst.empty:
            result["institutional_holders"] = [
                {
                    "holder":        str(r.get("Holder","")),
                    "shares":        safe_int(r.get("Shares")),
                    "date_reported": str(r.get("Date Reported",""))[:10],
                    "pct_held":      round(float(r.get("% Out", 0)) * 100, 2) if r.get("% Out") is not None else None,
                    "value_crore":   round(float(r.get("Value", 0)) / 1e7, 2) if r.get("Value") is not None else None,
                }
                for _, r in inst.head(params.top_n).iterrows()
            ]
        else:
            result["institutional_holders"] = "unavailable"

        if params.include_mutualfunds:
            mf = await _run_sync(lambda: t.mutualfund_holders)
            if mf is not None and not mf.empty:
                result["mutualfund_holders"] = [
                    {
                        "holder":        str(r.get("Holder","")),
                        "shares":        safe_int(r.get("Shares")),
                        "date_reported": str(r.get("Date Reported",""))[:10],
                        "pct_held":      round(float(r.get("% Out", 0)) * 100, 2) if r.get("% Out") is not None else None,
                        "value_crore":   round(float(r.get("Value", 0)) / 1e7, 2) if r.get("Value") is not None else None,
                    }
                    for _, r in mf.head(params.top_n).iterrows()
                ]
            else:
                result["mutualfund_holders"] = "unavailable"

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return handle_error(e, f"shareholders {params.symbol}")


# ─── Tool 10: Options Chain ──────────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_options",
    annotations={"title":"Get Options Chain","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_options(params: OptionsInput) -> str:
    """
    Get options chain data for a stock.

    If expiry is omitted, returns available expiry dates.
    If expiry is provided, returns the full or filtered options chain.
    Use limit_strikes_near_atm=5 to get only the 5 strikes above and below ATM.
    Use fields_to_return to select specific columns.

    NOTE: Yahoo Finance options data for Indian stocks is limited. Liquid NSE stocks
    (RELIANCE, INFY, TCS, HDFCBANK) are most likely to have data. For comprehensive
    F&O data use NSE's official API or broker APIs.

    Args:
        params: symbol, exchange, expiry, option_type, fields_to_return, limit_strikes_near_atm
    Returns:
        JSON with calls/puts data or available expiries list.
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        t = yf.Ticker(ticker_str)

        expiries = await _run_sync(lambda: t.options)
        if not expiries:
            return json.dumps({
                "symbol": params.symbol, "exchange": params.exchange,
                "message": "No options data available on Yahoo Finance for this symbol.",
                "suggestion": "Try RELIANCE, INFY, TCS, HDFCBANK, or NIFTY index.",
            })

        if params.expiry is None:
            return json.dumps({"symbol": params.symbol, "exchange": params.exchange,
                                "available_expiries": list(expiries)})

        if params.expiry not in expiries:
            return json.dumps({"error": f"Expiry '{params.expiry}' not available.",
                                "available_expiries": list(expiries)})

        chain = await _run_sync(lambda: t.option_chain(params.expiry))

        # Get ATM price
        info  = await _run_sync(lambda: t.fast_info)
        atm   = safe_float(getattr(info, "last_price", None)) or safe_float(getattr(info, "previous_close", None))

        def process_df(df: pd.DataFrame, expiry: str) -> list:
            if df is None or df.empty:
                return []
            col_map = {
                "contractSymbol":  "contract_symbol",
                "strike":          "strike",
                "lastPrice":       "last_price",
                "bid":             "bid",
                "ask":             "ask",
                "change":          "change",
                "percentChange":   "change_pct",
                "volume":          "volume",
                "openInterest":    "open_interest",
                "impliedVolatility":"implied_volatility",
                "inTheMoney":      "in_the_money",
            }
            df = df.rename(columns=col_map)
            df["expiry"] = expiry
            # ATM filter
            if params.limit_strikes_near_atm and atm and "strike" in df.columns:
                strikes = sorted(df["strike"].unique().tolist())
                if strikes:
                    atm_idx = min(range(len(strikes)), key=lambda i: abs(strikes[i] - atm))
                    n = params.limit_strikes_near_atm
                    selected = set(strikes[max(0, atm_idx - n): atm_idx + n + 1])
                    df = df[df["strike"].isin(selected)]
            records = df.to_dict(orient="records")
            # Clean NaN
            clean = []
            for r in records:
                clean.append({k: (None if (isinstance(v, float) and math.isnan(v)) else v) for k, v in r.items()})
            return filter_records(clean, params.fields_to_return)

        result: dict = {"symbol": params.symbol, "exchange": params.exchange, "expiry": params.expiry}
        if atm:
            result["current_price"] = atm

        if params.option_type in ("calls","both"):
            result["calls"] = process_df(chain.calls, params.expiry)
        if params.option_type in ("puts","both"):
            result["puts"] = process_df(chain.puts, params.expiry)

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return handle_error(e, f"options {params.symbol}")


# ─── Tool 11: News Feed ──────────────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_news",
    annotations={"title":"Get Stock News","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_news(params: NewsInput) -> str:
    """
    Get recent news articles for a stock from Yahoo Finance.

    Returns title, publisher, link, published_at, and related tickers.
    Combine with Claude's summarization for a quick news digest.

    Args:
        params: symbol, exchange, limit (1–25), fields_to_return
    Returns:
        JSON list of news articles.
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        t    = yf.Ticker(ticker_str)
        news = await _run_sync(lambda: t.news)

        if not news:
            return json.dumps({"symbol": params.symbol, "exchange": params.exchange,
                                "message": "No news available.", "articles": []})

        articles = []
        for item in news[: params.limit]:
            pub_ts = item.get("providerPublishTime")
            pub_at = datetime.fromtimestamp(pub_ts).strftime("%Y-%m-%d %H:%M") if pub_ts else None
            rec = {
                "title":            item.get("title",""),
                "publisher":        item.get("publisher",""),
                "link":             item.get("link",""),
                "published_at":     pub_at,
                "related_tickers":  item.get("relatedTickers",[]),
            }
            articles.append(rec)

        return json.dumps({
            "symbol":   params.symbol,
            "exchange": params.exchange,
            "count":    len(articles),
            "articles": filter_records(articles, params.fields_to_return),
        }, indent=2)
    except Exception as e:
        return handle_error(e, f"news {params.symbol}")


# ─── Tool 12: Analyst View ───────────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_analyst_view",
    annotations={"title":"Get Analyst Recommendations","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_analyst_view(params: AnalystInput) -> str:
    """
    Get analyst consensus: recommendations, rating changes, price targets,
    EPS/revenue estimates, and growth forecasts.

    Use include= to request only specific sections and limit_upgrades= to
    cap the number of recent rating changes returned.

    Sections available: recommendations_summary, upgrades_downgrades,
    price_targets, earnings_estimates, revenue_estimates, growth_estimates.

    Args:
        params: symbol, exchange, include, limit_upgrades
    Returns:
        JSON with requested analyst sections.
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        t    = yf.Ticker(ticker_str)
        want = set(params.include or [
            "recommendations_summary","upgrades_downgrades","price_targets",
            "earnings_estimates","revenue_estimates","growth_estimates",
        ])
        result: dict = {"symbol": params.symbol, "exchange": params.exchange}

        if "recommendations_summary" in want:
            try:
                df = await _run_sync(lambda: t.recommendations)
                if df is not None and not df.empty:
                    latest = df.iloc[-1] if "period" not in df.columns else None
                    if "period" in df.columns:
                        result["recommendations_summary"] = df.tail(4).to_dict(orient="records")
                    else:
                        result["recommendations_summary"] = df.tail(4).to_dict(orient="records")
                else:
                    result["recommendations_summary"] = "unavailable"
            except Exception:
                result["recommendations_summary"] = "unavailable"

        if "upgrades_downgrades" in want:
            try:
                df = await _run_sync(lambda: t.upgrades_downgrades)
                if df is not None and not df.empty:
                    df = df.reset_index()
                    records = df.head(params.limit_upgrades).to_dict(orient="records")
                    result["upgrades_downgrades"] = [{k: str(v) for k,v in r.items()} for r in records]
                else:
                    result["upgrades_downgrades"] = "unavailable"
            except Exception:
                result["upgrades_downgrades"] = "unavailable"

        if "price_targets" in want:
            try:
                info_cache_key = f"info:{ticker_str}"
                info = _cache_get(info_cache_key)
                if info is None:
                    info = await _run_sync(lambda: t.info)
                    _cache_set(info_cache_key, info)
                result["price_targets"] = {
                    "mean":   safe_float(info.get("targetMeanPrice")),
                    "high":   safe_float(info.get("targetHighPrice")),
                    "low":    safe_float(info.get("targetLowPrice")),
                    "median": safe_float(info.get("targetMedianPrice")),
                    "analyst_count": safe_int(info.get("numberOfAnalystOpinions")),
                    "recommendation": info.get("recommendationKey","N/A"),
                }
            except Exception:
                result["price_targets"] = "unavailable"

        if "earnings_estimates" in want:
            try:
                df = await _run_sync(lambda: t.earnings_estimate)
                result["earnings_estimates"] = df.to_dict() if (df is not None and not df.empty) else "unavailable"
            except Exception:
                result["earnings_estimates"] = "unavailable"

        if "revenue_estimates" in want:
            try:
                df = await _run_sync(lambda: t.revenue_estimate)
                result["revenue_estimates"] = df.to_dict() if (df is not None and not df.empty) else "unavailable"
            except Exception:
                result["revenue_estimates"] = "unavailable"

        if "growth_estimates" in want:
            try:
                df = await _run_sync(lambda: t.growth_estimates)
                result["growth_estimates"] = df.to_dict() if (df is not None and not df.empty) else "unavailable"
            except Exception:
                result["growth_estimates"] = "unavailable"

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return handle_error(e, f"analyst view {params.symbol}")


# ─── Tool 13: Earnings ───────────────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_earnings",
    annotations={"title":"Get Earnings Data & Calendar","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_earnings(params: EarningsInput) -> str:
    """
    Get earnings dates, calendar events, earnings history (actual vs estimate),
    and quarterly EPS/revenue trend.

    Sections: earnings_dates, calendar, earnings_history, quarterly_earnings.

    Args:
        params: symbol, exchange, include, limit
    Returns:
        JSON with requested earnings sections.
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        t    = yf.Ticker(ticker_str)
        want = set(params.include or ["earnings_dates","calendar","earnings_history","quarterly_earnings"])
        result: dict = {"symbol": params.symbol, "exchange": params.exchange}

        if "earnings_dates" in want:
            try:
                df = await _run_sync(lambda: t.earnings_dates)
                if df is not None and not df.empty:
                    df = df.reset_index()
                    result["earnings_dates"] = df.head(params.limit).to_dict(orient="records")
                else:
                    result["earnings_dates"] = "unavailable"
            except Exception:
                result["earnings_dates"] = "unavailable"

        if "calendar" in want:
            try:
                cal = await _run_sync(lambda: t.calendar)
                if cal is not None:
                    result["calendar"] = {k: str(v) for k, v in cal.items()} if isinstance(cal, dict) else str(cal)
                else:
                    result["calendar"] = "unavailable"
            except Exception:
                result["calendar"] = "unavailable"

        if "earnings_history" in want:
            try:
                df = await _run_sync(lambda: t.earnings_history)
                if df is not None and not df.empty:
                    result["earnings_history"] = df.tail(params.limit).to_dict(orient="records")
                else:
                    result["earnings_history"] = "unavailable"
            except Exception:
                result["earnings_history"] = "unavailable"

        if "quarterly_earnings" in want:
            try:
                df = await _run_sync(lambda: t.quarterly_earnings)
                if df is not None and not df.empty:
                    df = df.reset_index()
                    result["quarterly_earnings"] = df.tail(params.limit).to_dict(orient="records")
                else:
                    result["quarterly_earnings"] = "unavailable"
            except Exception:
                result["quarterly_earnings"] = "unavailable"

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return handle_error(e, f"earnings {params.symbol}")


# ─── Tool 14: Insider Activity ───────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_insider_activity",
    annotations={"title":"Get Insider Transactions","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_insider_activity(params: InsiderInput) -> str:
    """
    Get promoter/insider buy-sell activity for a stock.

    Sections: transactions (all), purchases (buys only), roster (current holdings).
    Use transaction_type='buy' or 'sell' to filter. Useful for tracking
    promoter confidence signals.

    Args:
        params: symbol, exchange, include, limit, transaction_type
    Returns:
        JSON with insider transaction data.
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        t    = yf.Ticker(ticker_str)
        want = set(params.include or ["transactions","purchases","roster"])
        result: dict = {"symbol": params.symbol, "exchange": params.exchange}

        if "transactions" in want:
            try:
                df = await _run_sync(lambda: t.insider_transactions)
                if df is not None and not df.empty:
                    df = df.reset_index(drop=True)
                    if params.transaction_type:
                        mask = df.get("Transaction","").str.lower().str.contains(
                            params.transaction_type.lower(), na=False
                        )
                        df = df[mask]
                    result["transactions"] = df.head(params.limit).to_dict(orient="records")
                else:
                    result["transactions"] = "unavailable"
            except Exception:
                result["transactions"] = "unavailable"

        if "purchases" in want:
            try:
                df = await _run_sync(lambda: t.insider_purchases)
                if df is not None and not df.empty:
                    result["purchases"] = df.head(params.limit).to_dict(orient="records")
                else:
                    result["purchases"] = "unavailable"
            except Exception:
                result["purchases"] = "unavailable"

        if "roster" in want:
            try:
                df = await _run_sync(lambda: t.insider_roster_holders)
                if df is not None and not df.empty:
                    result["roster"] = df.to_dict(orient="records")
                else:
                    result["roster"] = "unavailable"
            except Exception:
                result["roster"] = "unavailable"

        return json.dumps(result, indent=2, default=str)
    except Exception as e:
        return handle_error(e, f"insider activity {params.symbol}")


# ─── Tool 15: Technical Indicators ──────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_technicals",
    annotations={"title":"Get Technical Indicators","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_technicals(params: TechnicalInput) -> str:
    """
    Compute technical indicators from historical price data.

    Indicators: rsi, macd, bollinger_bands, atr, moving_averages, volume_trend, supertrend.
    All computed from daily OHLCV data. Includes an overall signal summary.

    Args:
        params: symbol, exchange, indicators (list or None for all), period
    Returns:
        JSON with computed indicator values and a composite signal.
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        t  = yf.Ticker(ticker_str)
        df = await _run_sync(lambda: t.history(period=params.period, interval="1d"))

        if df.empty or len(df) < 30:
            return json.dumps({"error": "Insufficient data for technical analysis. Try period='1y'."})

        want = set(params.indicators or TECHNICAL_INDICATORS)
        close  = df["Close"]
        result: dict = {"symbol": params.symbol, "exchange": params.exchange,
                         "period": params.period, "latest_close": round(float(close.iloc[-1]), 2)}

        rsi_val, macd_val, bb_val, st_val = None, {}, {}, {}

        if "rsi" in want:
            rsi_val = calc_rsi(close)
            result["rsi"] = {"value": rsi_val, "period": 14,
                              "signal": "oversold" if (rsi_val and rsi_val < 30) else ("overbought" if (rsi_val and rsi_val > 70) else "neutral")}

        if "macd" in want:
            macd_val = calc_macd(close)
            result["macd"] = {**macd_val, "params": "12/26/9"}

        if "bollinger_bands" in want:
            bb_val = calc_bollinger_bands(close)
            result["bollinger_bands"] = {**bb_val, "params": "20-period, 2σ"}

        if "atr" in want:
            result["atr"] = {"value": calc_atr_scalar(df), "period": 14}

        if "moving_averages" in want:
            result["moving_averages"] = {
                "ma_20d":  round(float(close.rolling(20).mean().iloc[-1]), 2) if len(close) >= 20 else None,
                "ma_50d":  round(float(close.rolling(50).mean().iloc[-1]), 2) if len(close) >= 50 else None,
                "ma_200d": round(float(close.rolling(200).mean().iloc[-1]), 2) if len(close) >= 200 else None,
                "price_vs_ma50":  "above" if len(close) >= 50 and float(close.iloc[-1]) > float(close.rolling(50).mean().iloc[-1]) else "below",
                "price_vs_ma200": "above" if len(close) >= 200 and float(close.iloc[-1]) > float(close.rolling(200).mean().iloc[-1]) else "below",
            }

        if "volume_trend" in want:
            vol = df["Volume"]
            avg_5d  = float(vol.tail(5).mean())
            avg_20d = float(vol.tail(20).mean())
            result["volume_trend"] = {
                "avg_volume_5d":   int(avg_5d),
                "avg_volume_20d":  int(avg_20d),
                "ratio_5d_vs_20d": round(avg_5d / avg_20d, 2) if avg_20d else None,
                "signal": "high" if avg_5d > avg_20d * 1.2 else ("low" if avg_5d < avg_20d * 0.8 else "normal"),
            }

        if "supertrend" in want:
            st_val = calc_supertrend(df)
            result["supertrend"] = {**st_val, "params": "10-period, 3× multiplier"}

        # Composite signal
        result["signal_summary"] = _signal_summary(rsi_val, macd_val, bb_val, st_val)
        return json.dumps(result, indent=2)
    except Exception as e:
        return handle_error(e, f"technicals {params.symbol}")


# ─── Tool 16: Sector Snapshot ────────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_sector_snapshot",
    annotations={"title":"Sector & Index Heatmap","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_sector_snapshot(params: SectorSnapshotInput) -> str:
    """
    Fetch real-time levels and % change for all (or selected) Indian market indices.
    Uses parallel fetch with a rate-limit semaphore.

    Useful for identifying which sectors are leading or lagging on a given day.

    Args:
        params: indices (list or None for all), fields_to_return
    Returns:
        JSON list of index snapshots sorted by % change (descending).
    """
    target = params.indices or list(INDICES.keys())
    invalid = [i for i in target if i not in INDICES]
    if invalid:
        return json.dumps({"error": f"Unknown indices: {invalid}", "valid": list(INDICES.keys())})

    sem = asyncio.Semaphore(6)

    async def fetch_one(name: str) -> dict:
        async with sem:
            try:
                ts   = INDICES[name]
                t    = yf.Ticker(ts)
                info = await _run_sync(lambda: t.fast_info)
                price      = safe_float(getattr(info, "last_price", None)) or safe_float(getattr(info, "previous_close", None))
                prev_close = safe_float(getattr(info, "regular_market_previous_close", None)) or safe_float(getattr(info, "previous_close", None))
                change     = round(price - prev_close, 2) if (price and prev_close) else None
                change_pct = round((change / prev_close) * 100, 2) if (change and prev_close) else None
                return {
                    "name":        name,
                    "yahoo_ticker":ts,
                    "level":       price,
                    "change":      change,
                    "change_pct":  change_pct,
                    "direction":   "▲" if (change_pct and change_pct >= 0) else "▼",
                    "week52_high": safe_float(getattr(info, "year_high", None)),
                    "week52_low":  safe_float(getattr(info, "year_low", None)),
                }
            except Exception as e:
                return {"name": name, "error": str(e)}

    rows = await asyncio.gather(*[fetch_one(n) for n in target])
    # Sort by change_pct desc, errors last
    rows.sort(key=lambda r: r.get("change_pct") or -999, reverse=True)
    filtered = [filter_fields(r, params.fields_to_return) for r in rows]
    return json.dumps({"snapshot_time": datetime.now().strftime("%Y-%m-%d %H:%M IST"),
                        "count": len(filtered), "data": filtered}, indent=2)


# ─── Tool 17: Portfolio Analytics ────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_portfolio_analysis",
    annotations={"title":"Portfolio P&L & Analytics","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_portfolio_analysis(params: PortfolioInput) -> str:
    """
    Analyse a portfolio of holdings: P&L, sector allocation, and risk metrics.

    Input: list of {symbol, quantity, avg_buy_price, exchange}.
    Sections (fields_to_return): summary, per_stock, sector_allocation, risk_metrics.

    Args:
        params: holdings (list of PortfolioHolding), fields_to_return
    Returns:
        JSON with portfolio analytics.
    """
    async def fetch_holding(h: PortfolioHolding) -> dict:
        ticker_str = build_ticker(h.symbol, h.exchange)
        try:
            t    = yf.Ticker(ticker_str)
            info = await _run_sync(lambda: t.info)
            price  = safe_float(info.get("regularMarketPrice") or info.get("currentPrice"))
            cost   = h.quantity * h.avg_buy_price
            cur_val= h.quantity * price if price else None
            pnl    = (cur_val - cost) if cur_val else None
            pnl_pct= round((pnl / cost) * 100, 2) if (pnl is not None and cost) else None
            return {
                "symbol":          h.symbol,
                "exchange":        h.exchange,
                "quantity":        h.quantity,
                "avg_buy_price":   h.avg_buy_price,
                "current_price":   price,
                "cost":            round(cost, 2),
                "current_value":   round(cur_val, 2) if cur_val else None,
                "pnl":             round(pnl, 2) if pnl is not None else None,
                "pnl_pct":         pnl_pct,
                "pnl_direction":   "▲" if (pnl_pct and pnl_pct >= 0) else "▼",
                "sector":          info.get("sector","Unknown"),
                "beta":            safe_float(info.get("beta")),
            }
        except Exception as e:
            cost = h.quantity * h.avg_buy_price
            return {"symbol": h.symbol, "exchange": h.exchange,
                    "quantity": h.quantity, "avg_buy_price": h.avg_buy_price,
                    "cost": round(cost, 2), "error": str(e)}

    try:
        want     = set(params.fields_to_return or ["summary","per_stock","sector_allocation","risk_metrics"])
        holdings = await asyncio.gather(*[fetch_holding(h) for h in params.holdings])
        result:  dict = {}

        valid_h = [h for h in holdings if "current_value" in h and h.get("current_value")]
        total_cost  = sum(h["cost"] for h in holdings)
        total_value = sum(h["current_value"] for h in valid_h if h["current_value"]) or 0

        if "summary" in want:
            total_pnl = total_value - total_cost
            result["summary"] = {
                "total_invested":  round(total_cost, 2),
                "current_value":   round(total_value, 2),
                "total_pnl":       round(total_pnl, 2),
                "total_pnl_pct":   round((total_pnl / total_cost) * 100, 2) if total_cost else None,
                "holdings_count":  len(params.holdings),
            }

        if "per_stock" in want:
            result["per_stock"] = holdings

        if "sector_allocation" in want and total_value:
            sector_map: dict = {}
            for h in valid_h:
                s = h.get("sector","Unknown")
                sector_map[s] = sector_map.get(s, 0) + (h.get("current_value") or 0)
            result["sector_allocation"] = [
                {"sector": s, "value": round(v, 2), "weight_pct": round((v / total_value) * 100, 2)}
                for s, v in sorted(sector_map.items(), key=lambda x: -x[1])
            ]

        if "risk_metrics" in want and total_value:
            weighted_beta = sum(
                (h.get("beta") or 1.0) * ((h.get("current_value") or 0) / total_value)
                for h in valid_h
            )
            result["risk_metrics"] = {
                "portfolio_beta":           round(weighted_beta, 3),
                "beta_interpretation":      "aggressive" if weighted_beta > 1.2 else ("defensive" if weighted_beta < 0.8 else "market-neutral"),
                "largest_position_pct":     round(max((h.get("current_value") or 0) / total_value * 100 for h in valid_h), 2) if valid_h else None,
                "diversification_note":     "Concentrated" if len(params.holdings) <= 5 else ("Moderate" if len(params.holdings) <= 15 else "Diversified"),
            }

        return json.dumps(result, indent=2)
    except Exception as e:
        return handle_error(e, "portfolio analysis")


# ─── Tool 18: Corporate Actions ──────────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_corporate_actions",
    annotations={"title":"Get Corporate Actions","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_corporate_actions(params: StockInput) -> str:
    """
    Get complete corporate action history: dividends, stock splits, and capital gains.

    Returns a unified timeline of all corporate actions sorted by date (newest first).

    Args:
        params: symbol, exchange
    Returns:
        JSON with splits, dividends, and capital_gains lists.
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        t = yf.Ticker(ticker_str)
        result: dict = {"symbol": params.symbol, "exchange": params.exchange}

        splits = await _run_sync(lambda: t.splits)
        if splits is not None and not splits.empty:
            result["splits"] = [
                {"date": str(d)[:10], "split_ratio": round(float(v), 4)}
                for d, v in splits.items()
            ]
            result["splits"].reverse()
        else:
            result["splits"] = []

        divs = await _run_sync(lambda: t.dividends)
        if divs is not None and not divs.empty:
            result["dividends"] = [
                {"date": str(d)[:10], "amount_inr": round(float(v), 4)}
                for d, v in divs.items()
            ]
            result["dividends"].reverse()
            result["dividends"] = result["dividends"][:20]
        else:
            result["dividends"] = []

        try:
            cg = await _run_sync(lambda: t.capital_gains)
            if cg is not None and not cg.empty:
                result["capital_gains"] = [
                    {"date": str(d)[:10], "amount": round(float(v), 4)}
                    for d, v in cg.items()
                ]
            else:
                result["capital_gains"] = []
        except Exception:
            result["capital_gains"] = []

        return json.dumps(result, indent=2)
    except Exception as e:
        return handle_error(e, f"corporate actions {params.symbol}")


# ─── Tool 19: ESG / Sustainability ──────────────────────────────────────────

@mcp.tool(
    name="nse_bse_get_esg",
    annotations={"title":"Get ESG Sustainability Scores","readOnlyHint":True,"destructiveHint":False,"idempotentHint":True,"openWorldHint":True},
)
async def nse_bse_get_esg(params: ESGInput) -> str:
    """
    Get ESG (Environmental, Social, Governance) sustainability scores.

    NOTE: Yahoo Finance ESG data is primarily available for large-cap global companies.
    Coverage for Indian-listed stocks may be limited.

    Available fields: total_esg, environment_score, social_score, governance_score,
    controversy_level, percentile, peer_group.

    Args:
        params: symbol, exchange, fields_to_return
    Returns:
        JSON with ESG scores.
    """
    try:
        ticker_str = build_ticker(params.symbol, params.exchange)
        t    = yf.Ticker(ticker_str)
        sust = await _run_sync(lambda: t.sustainability)

        if sust is None or (isinstance(sust, pd.DataFrame) and sust.empty):
            return json.dumps({
                "symbol": params.symbol, "exchange": params.exchange,
                "message": "ESG data not available for this stock on Yahoo Finance.",
                "suggestion": "ESG data is more commonly available for large-cap globally listed companies.",
            })

        # sustainability is a DataFrame with one column; transpose for easy access
        if isinstance(sust, pd.DataFrame):
            s = sust.iloc[:, 0].to_dict()
        else:
            s = dict(sust)

        def _get(key: str): return safe_float(s.get(key))

        result = {
            "symbol":             params.symbol,
            "exchange":           params.exchange,
            "total_esg":          _get("totalEsg"),
            "environment_score":  _get("environmentScore"),
            "social_score":       _get("socialScore"),
            "governance_score":   _get("governanceScore"),
            "controversy_level":  s.get("highestControversy"),
            "percentile":         _get("percentile"),
            "peer_group":         s.get("peerGroup"),
            "esg_performance":    s.get("esgPerformance"),
            "rating_year":        s.get("ratingYear"),
            "rating_month":       s.get("ratingMonth"),
            "raw_data":           {k: str(v) for k, v in s.items()},
        }
        return json.dumps(filter_fields(result, params.fields_to_return), indent=2)
    except Exception as e:
        return handle_error(e, f"ESG {params.symbol}")


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
