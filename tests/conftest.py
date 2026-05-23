"""
Shared pytest fixtures and mock factories for NSE/BSE MCP tests.
"""
import math
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from unittest.mock import MagicMock


# ─── Mock ticker.info fixture ─────────────────────────────────────────────────

@pytest.fixture
def mock_info():
    """Realistic ticker.info dict for a fictional NSE stock."""
    return {
        "symbol":               "TEST.NS",
        "longName":             "Test Corporation Ltd",
        "shortName":            "TestCorp",
        "regularMarketPrice":   1500.0,
        "currentPrice":         1500.0,
        "previousClose":        1480.0,
        "open":                 1485.0,
        "dayHigh":              1525.0,
        "dayLow":               1470.0,
        "volume":               1_200_000,
        "averageVolume10days":  1_100_000,
        "fiftyTwoWeekHigh":     1800.0,
        "fiftyTwoWeekLow":      1100.0,
        "fiftyDayAverage":      1450.0,
        "twoHundredDayAverage": 1380.0,
        "marketCap":            500_000_000_000,   # 500 Bn = 50,000 Cr
        "trailingPE":           25.0,
        "forwardPE":            22.0,
        "priceToBook":          4.5,
        "trailingEps":          60.0,
        "forwardEps":           68.0,
        "dividendYield":        0.02,
        "beta":                 1.1,
        "sector":               "Technology",
        "industry":             "Software — Infrastructure",
        "currency":             "INR",
        "isin":                 "INE123456789",
        # Fundamentals
        "totalRevenue":         100_000_000_000,   # 10,000 Cr
        "grossProfits":          40_000_000_000,
        "ebitda":                30_000_000_000,
        "operatingIncome":       28_000_000_000,
        "netIncomeToCommon":     20_000_000_000,
        "grossMargins":          0.40,
        "operatingMargins":      0.28,
        "profitMargins":         0.20,
        "returnOnEquity":        0.25,
        "returnOnAssets":        0.15,
        "totalAssets":          200_000_000_000,
        "totalDebt":             10_000_000_000,
        "totalCash":             50_000_000_000,
        "bookValue":             333.33,
        "debtToEquity":          10.0,
        "currentRatio":          3.2,
        "quickRatio":            2.8,
        "revenuePerShare":       250.0,
        "totalCashPerShare":     125.0,
        "lastDividendValue":     30.0,
        "payoutRatio":           0.50,
        "earningsGrowth":        0.15,
        "revenueGrowth":         0.12,
        "targetMeanPrice":       1750.0,
        "targetHighPrice":       1950.0,
        "targetLowPrice":        1400.0,
        "targetMedianPrice":     1720.0,
        "recommendationKey":     "buy",
        "numberOfAnalystOpinions": 22,
        "longBusinessSummary":   "Test Corporation provides software infrastructure services globally.",
    }


# ─── Mock fast_info fixture ───────────────────────────────────────────────────

@pytest.fixture
def mock_fast_info():
    fi = MagicMock()
    fi.last_price                    = 1500.0
    fi.previous_close                = 1480.0
    fi.regular_market_previous_close = 1480.0
    fi.day_high                      = 1525.0
    fi.day_low                       = 1470.0
    fi.day_volume                    = 1_200_000
    fi.year_high                     = 1800.0
    fi.year_low                      = 1100.0
    fi.market_cap                    = 500_000_000_000
    fi.fifty_day_average             = 1450.0
    fi.two_hundred_day_average       = 1380.0
    return fi


# ─── Mock historical DataFrame ────────────────────────────────────────────────

@pytest.fixture
def mock_history_df():
    """60 trading days of synthetic OHLCV data."""
    n = 60
    np.random.seed(42)
    dates  = pd.bdate_range(end=datetime.today(), periods=n)
    close  = 1400.0 + np.cumsum(np.random.randn(n) * 8)
    high   = close + np.abs(np.random.randn(n) * 5)
    low    = close - np.abs(np.random.randn(n) * 5)
    open_  = close + np.random.randn(n) * 3
    volume = (np.random.rand(n) * 500_000 + 800_000).astype(int)

    df = pd.DataFrame({
        "Open":          open_,
        "High":          high,
        "Low":           low,
        "Close":         close,
        "Volume":        volume,
        "Dividends":     np.zeros(n),
        "Stock Splits":  np.zeros(n),
    }, index=dates)
    df.index.name = "Date"
    return df


# ─── Mock dividends Series ────────────────────────────────────────────────────

@pytest.fixture
def mock_dividends():
    dates = pd.date_range("2020-06-15", periods=8, freq="365D")
    return pd.Series([12.0, 15.0, 18.0, 20.0, 22.0, 25.0, 28.0, 30.0], index=dates, name="Dividends")


# ─── Mock splits Series ──────────────────────────────────────────────────────

@pytest.fixture
def mock_splits():
    dates = pd.DatetimeIndex(["2021-03-15"])
    return pd.Series([2.0], index=dates, name="Stock Splits")


# ─── Mock institutional holders DataFrame ────────────────────────────────────

@pytest.fixture
def mock_inst_holders():
    return pd.DataFrame({
        "Holder":        ["HDFC Mutual Fund", "SBI Mutual Fund", "LIC of India"],
        "Shares":        [10_000_000, 8_000_000, 5_000_000],
        "Date Reported": ["2025-12-31", "2025-12-31", "2025-12-31"],
        "% Out":         [0.05, 0.04, 0.025],
        "Value":         [15_000_000_000, 12_000_000_000, 7_500_000_000],
    })


@pytest.fixture
def mock_major_holders():
    return pd.DataFrame([
        ["62.5%", "% of Shares Held by All Insider"],
        ["15.2%", "% of Shares Held by Institutions"],
        ["40.7%", "% of Float Held by Institutions"],
        ["25",    "Number of Institutions Holding Shares"],
    ])


# ─── Mock options chain ──────────────────────────────────────────────────────

@pytest.fixture
def mock_options_chain():
    strikes = [1400, 1450, 1500, 1550, 1600]
    calls = pd.DataFrame({
        "contractSymbol":  [f"TESTCE{s}" for s in strikes],
        "strike":          strikes,
        "lastPrice":       [105, 65, 35, 15, 5],
        "bid":             [103, 63, 33, 13, 4],
        "ask":             [107, 67, 37, 17, 6],
        "change":          [2, 1, -1, -2, -1],
        "percentChange":   [1.9, 1.5, -2.8, -11.8, -16.7],
        "volume":          [500, 1200, 3000, 1500, 400],
        "openInterest":    [5000, 12000, 30000, 15000, 4000],
        "impliedVolatility":[0.22, 0.24, 0.26, 0.29, 0.34],
        "inTheMoney":      [True, True, False, False, False],
    })
    puts = pd.DataFrame({
        "contractSymbol":  [f"TESTPE{s}" for s in strikes],
        "strike":          strikes,
        "lastPrice":       [5, 15, 35, 65, 105],
        "bid":             [4, 13, 33, 63, 103],
        "ask":             [6, 17, 37, 67, 107],
        "change":          [-1, -2, 1, 2, 3],
        "percentChange":   [-16.7, -11.8, 2.9, 3.2, 2.9],
        "volume":          [200, 600, 2500, 1800, 700],
        "openInterest":    [2000, 6000, 25000, 18000, 7000],
        "impliedVolatility":[0.34, 0.29, 0.26, 0.24, 0.22],
        "inTheMoney":      [False, False, False, True, True],
    })
    chain = MagicMock()
    chain.calls = calls
    chain.puts  = puts
    return chain


# ─── Mock news list ───────────────────────────────────────────────────────────

@pytest.fixture
def mock_news():
    return [
        {
            "uuid":                "abc123",
            "title":               "TestCorp Q4 results beat estimates",
            "publisher":           "Economic Times",
            "link":                "https://example.com/article1",
            "providerPublishTime": int(datetime(2026, 5, 20, 10, 0).timestamp()),
            "type":                "STORY",
            "relatedTickers":      ["TEST.NS"],
        },
        {
            "uuid":                "def456",
            "title":               "TestCorp announces ₹30 dividend",
            "publisher":           "Business Standard",
            "link":                "https://example.com/article2",
            "providerPublishTime": int(datetime(2026, 5, 19, 15, 30).timestamp()),
            "type":                "STORY",
            "relatedTickers":      ["TEST.NS", "COMP.NS"],
        },
    ]


# ─── Mock annual financials DataFrames ───────────────────────────────────────

@pytest.fixture
def mock_financials_df():
    dates = pd.date_range("2022-03-31", periods=4, freq="365D")
    rows  = ["Total Revenue", "Gross Profit", "Net Income", "EBITDA"]
    data  = np.array([
        [100e9, 110e9, 120e9, 130e9],
        [ 40e9,  44e9,  48e9,  52e9],
        [ 20e9,  22e9,  24e9,  26e9],
        [ 30e9,  33e9,  36e9,  39e9],
    ])
    return pd.DataFrame(data, index=rows, columns=dates)


# ─── Mock sustainability Series ──────────────────────────────────────────────

@pytest.fixture
def mock_sustainability():
    data = {
        "totalEsg":            48.5,
        "environmentScore":    10.2,
        "socialScore":         18.7,
        "governanceScore":     19.6,
        "highestControversy":  2,
        "percentile":          62.3,
        "peerGroup":           "Software",
        "esgPerformance":      "UNDER_PERF",
        "ratingYear":          2025,
        "ratingMonth":         11,
    }
    return pd.DataFrame.from_dict(data, orient="index", columns=["Value"])


# ─── Mock Ticker factory ─────────────────────────────────────────────────────

def make_mock_ticker(
    info=None,
    fast_info=None,
    history_df=None,
    dividends=None,
    splits=None,
    institutional_holders=None,
    major_holders=None,
    mutualfund_holders=None,
    options=None,
    option_chain=None,
    news=None,
    financials=None,
    quarterly_income_stmt=None,
    quarterly_balance_sheet=None,
    quarterly_cashflow=None,
    ttm_income_stmt=None,
    ttm_cashflow=None,
    sustainability=None,
    earnings_dates=None,
    calendar=None,
    recommendations=None,
    upgrades_downgrades=None,
    insider_transactions=None,
    insider_purchases=None,
    insider_roster_holders=None,
    earnings_estimate=None,
    revenue_estimate=None,
    growth_estimates=None,
    earnings_history=None,
    quarterly_earnings=None,
    capital_gains=None,
):
    """Return a MagicMock yfinance.Ticker with all common attributes set."""
    m = MagicMock()
    m.info                    = info or {}
    m.fast_info               = fast_info or MagicMock()
    m.history                 = MagicMock(return_value=history_df if history_df is not None else pd.DataFrame())
    m.dividends               = dividends if dividends is not None else pd.Series(dtype=float)
    m.splits                  = splits if splits is not None else pd.Series(dtype=float)
    m.capital_gains           = capital_gains if capital_gains is not None else pd.Series(dtype=float)
    m.institutional_holders   = institutional_holders
    m.major_holders           = major_holders
    m.mutualfund_holders      = mutualfund_holders
    m.options                 = options or ()
    m.option_chain            = MagicMock(return_value=option_chain)
    m.news                    = news or []
    m.financials              = financials
    m.quarterly_income_stmt   = quarterly_income_stmt
    m.quarterly_balance_sheet = quarterly_balance_sheet
    m.quarterly_cashflow      = quarterly_cashflow
    m.ttm_income_stmt         = ttm_income_stmt
    m.ttm_cashflow            = ttm_cashflow
    m.sustainability          = sustainability
    m.earnings_dates          = earnings_dates
    m.calendar                = calendar
    m.recommendations         = recommendations
    m.upgrades_downgrades     = upgrades_downgrades
    m.insider_transactions    = insider_transactions
    m.insider_purchases       = insider_purchases
    m.insider_roster_holders  = insider_roster_holders
    m.earnings_estimate       = earnings_estimate
    m.revenue_estimate        = revenue_estimate
    m.growth_estimates        = growth_estimates
    m.earnings_history        = earnings_history
    m.quarterly_earnings      = quarterly_earnings
    return m
