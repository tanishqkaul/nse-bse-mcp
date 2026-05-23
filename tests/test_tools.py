"""
Integration-style tool tests with mocked yfinance.

Every MCP tool is tested for:
  - Happy-path output shape and key correctness
  - fields_to_return filtering
  - limit / top_n parameters
  - Graceful degradation on empty/unavailable data
  - Pydantic validation errors on bad inputs
  - Error-JSON format on exceptions

Async tools are driven with pytest-asyncio.
yfinance.Ticker is patched at the server module level.
"""
import json
import math
import pytest
import asyncio
import pandas as pd
import numpy as np
import sys, os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import server  # imported so we can patch server.yf.Ticker
from server import (
    # Tools
    nse_bse_get_quote,
    nse_bse_get_historical,
    nse_bse_get_fundamentals,
    nse_bse_get_financials,
    nse_bse_compare_stocks,
    nse_bse_get_index,
    nse_bse_list_indices,
    nse_bse_get_dividends,
    nse_bse_get_shareholders,
    nse_bse_get_options,
    nse_bse_get_news,
    nse_bse_get_analyst_view,
    nse_bse_get_earnings,
    nse_bse_get_insider_activity,
    nse_bse_get_technicals,
    nse_bse_sector_snapshot,
    nse_bse_portfolio_analysis,
    nse_bse_get_corporate_actions,
    nse_bse_get_esg,
    # Input models
    StockInput, HistoricalInput, CompareInput, IndexInput,
    OptionsInput, NewsInput, AnalystInput, EarningsInput,
    InsiderInput, TechnicalInput, SectorSnapshotInput,
    PortfolioInput, PortfolioHolding, FinancialsInput,
    ShareholdersInput, ESGInput, Exchange,
)
from tests.conftest import make_mock_ticker


# ─── Helpers ─────────────────────────────────────────────────────────────────

def parse(result: str) -> dict | list:
    return json.loads(result)


def assert_no_error(data):
    assert "error" not in data, f"Unexpected error: {data.get('error')}"


# ─── pytest-asyncio config ────────────────────────────────────────────────────

pytestmark = pytest.mark.asyncio


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 1: nse_bse_get_quote
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetQuote:
    async def test_basic_quote(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        result = await nse_bse_get_quote(StockInput(symbol="TEST", exchange=Exchange.NSE))
        data   = parse(result)
        assert_no_error(data)
        assert data["symbol"]   == "TEST"
        assert data["exchange"] == "NSE"
        assert data["price"]    == 1500.0
        assert data["change"]   == pytest.approx(1500.0 - 1480.0, abs=0.01)
        assert data["change_pct"] is not None
        assert data["direction"] in ("▲", "▼")

    async def test_valuation_metrics_present(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_quote(StockInput(symbol="TEST")))
        assert data["pe_ratio"]   == 25.0
        assert data["pb_ratio"]   == 4.5
        assert data["eps"]        == 60.0
        assert data["beta"]       == 1.1
        assert data["sector"]     == "Technology"

    async def test_market_cap_crore(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_quote(StockInput(symbol="TEST")))
        # 500_000_000_000 / 1e7 = 50,000 Cr
        assert data["market_cap_crore"] == pytest.approx(50000.0, rel=0.01)

    async def test_fields_to_return(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_quote(
            StockInput(symbol="TEST", fields_to_return=["price", "pe_ratio", "sector"])
        ))
        assert set(data.keys()) == {"price", "pe_ratio", "sector"}

    async def test_bse_exchange(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        result = await nse_bse_get_quote(StockInput(symbol="RELIANCE", exchange=Exchange.BSE))
        data   = parse(result)
        assert data.get("exchange") == "BSE"

    async def test_no_price_returns_error(self, mocker):
        mt = make_mock_ticker(info={"longName": "Empty Co"})  # no price
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_quote(StockInput(symbol="EMPTY")))
        assert "error" in data

    async def test_isin_included(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_quote(StockInput(symbol="TEST")))
        assert data["isin"] == "INE123456789"


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 2: nse_bse_get_historical
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetHistorical:
    async def test_basic(self, mock_history_df, mocker):
        mt = make_mock_ticker(history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_historical(
            HistoricalInput(symbol="TEST", period="3mo")
        ))
        assert_no_error(data)
        assert "summary" in data
        assert "data" in data
        assert len(data["data"]) > 0

    async def test_summary_fields(self, mock_history_df, mocker):
        mt = make_mock_ticker(history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data    = parse(await nse_bse_get_historical(HistoricalInput(symbol="TEST", period="3mo")))
        summary = data["summary"]
        assert "start_date"       in summary
        assert "end_date"         in summary
        assert "total_return_pct" in summary
        assert "period_high"      in summary
        assert "avg_daily_volume" in summary

    async def test_max_records_respected(self, mock_history_df, mocker):
        mt = make_mock_ticker(history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_historical(
            HistoricalInput(symbol="TEST", period="3mo", max_records=10)
        ))
        assert len(data["data"]) <= 10

    async def test_fields_to_return_per_record(self, mock_history_df, mocker):
        mt = make_mock_ticker(history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_historical(
            HistoricalInput(symbol="TEST", period="3mo", fields_to_return=["date", "close"])
        ))
        for row in data["data"]:
            assert set(row.keys()) == {"date", "close"}

    async def test_each_record_has_date_and_ohlcv(self, mock_history_df, mocker):
        mt = make_mock_ticker(history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_historical(HistoricalInput(symbol="TEST", period="3mo")))
        for row in data["data"]:
            for field in ("date","open","high","low","close","volume"):
                assert field in row

    async def test_empty_df_returns_error(self, mocker):
        mt = make_mock_ticker(history_df=pd.DataFrame())
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_historical(HistoricalInput(symbol="EMPTY", period="1d")))
        assert "error" in data

    async def test_invalid_period_raises(self):
        with pytest.raises(Exception):
            HistoricalInput(symbol="TEST", period="99yr")

    async def test_start_end_date(self, mock_history_df, mocker):
        mt = make_mock_ticker(history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_historical(
            HistoricalInput(symbol="TEST", start_date="2025-01-01", end_date="2025-06-01")
        ))
        assert_no_error(data)
        assert "data" in data


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 3: nse_bse_get_fundamentals
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetFundamentals:
    async def test_basic(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_fundamentals(StockInput(symbol="TEST")))
        assert_no_error(data)
        assert data["symbol"] == "TEST"

    async def test_revenue_in_crore(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_fundamentals(StockInput(symbol="TEST")))
        # 100_000_000_000 / 1e7 = 10000 Cr
        assert data["revenue"] == pytest.approx(10000.0, rel=0.01)

    async def test_margins_as_floats(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_fundamentals(StockInput(symbol="TEST")))
        assert data["gross_margin"]    == pytest.approx(0.40, rel=0.01)
        assert data["operating_margin"]== pytest.approx(0.28, rel=0.01)

    async def test_analyst_fields(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_fundamentals(StockInput(symbol="TEST")))
        assert data["recommendation"]  == "buy"
        assert data["analyst_count"]   == 22
        assert data["target_mean"]     == 1750.0

    async def test_fields_to_return(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_fundamentals(
            StockInput(symbol="TEST", fields_to_return=["revenue","roe","recommendation"])
        ))
        assert set(data.keys()) == {"revenue","roe","recommendation"}

    async def test_description_truncated(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_fundamentals(StockInput(symbol="TEST")))
        assert len(data.get("description","")) <= 610


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 4: nse_bse_get_financials
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetFinancials:
    async def test_annual(self, mock_financials_df, mocker):
        mt = make_mock_ticker(
            financials=mock_financials_df,
            quarterly_income_stmt=None,
            quarterly_balance_sheet=None,
            quarterly_cashflow=None,
        )
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_financials(
            FinancialsInput(symbol="TEST", frequency="annual", statements=["income_statement"])
        ))
        assert_no_error(data)
        assert data["frequency"] == "annual"
        assert "income_statement" in data

    async def test_quarterly(self, mock_financials_df, mocker):
        mt = make_mock_ticker(quarterly_income_stmt=mock_financials_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_financials(
            FinancialsInput(symbol="TEST", frequency="quarterly", statements=["income_statement"])
        ))
        assert data["frequency"] == "quarterly"
        assert "income_statement" in data

    async def test_statements_filter(self, mock_financials_df, mocker):
        mt = make_mock_ticker(financials=mock_financials_df, quarterly_balance_sheet=mock_financials_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_financials(
            FinancialsInput(symbol="TEST", frequency="annual", statements=["income_statement"])
        ))
        assert "income_statement" in data
        assert "balance_sheet" not in data

    async def test_invalid_frequency(self):
        with pytest.raises(Exception):
            FinancialsInput(symbol="TEST", frequency="weekly")

    async def test_note_field_present(self, mock_financials_df, mocker):
        mt = make_mock_ticker(financials=mock_financials_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_financials(FinancialsInput(symbol="TEST", frequency="annual")))
        assert "note" in data
        assert "Crore" in data["note"]


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 5: nse_bse_compare_stocks
# ═══════════════════════════════════════════════════════════════════════════════

class TestCompareStocks:
    async def test_basic_comparison(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_compare_stocks(
            CompareInput(symbols=["TEST","TEST2"])
        ))
        assert_no_error(data)
        assert "data" in data
        assert len(data["data"]) == 2

    async def test_fields_to_return(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_compare_stocks(
            CompareInput(symbols=["A","B"], fields_to_return=["symbol","price","pe"])
        ))
        for row in data["data"]:
            assert set(row.keys()) == {"symbol","price","pe"}

    async def test_min_2_symbols_required(self):
        with pytest.raises(Exception):
            CompareInput(symbols=["ONLY_ONE"])

    async def test_max_10_symbols(self):
        with pytest.raises(Exception):
            CompareInput(symbols=[f"S{i}" for i in range(11)])

    async def test_error_per_stock_isolated(self, mock_info, mocker):
        """One failing stock should not crash the whole comparison."""
        call_count = [0]
        def ticker_factory(ts):
            call_count[0] += 1
            if "FAIL" in ts:
                m = make_mock_ticker(info={})
                m.info = {}
                return m
            return make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", side_effect=ticker_factory)
        data = parse(await nse_bse_compare_stocks(
            CompareInput(symbols=["TEST","FAIL"])
        ))
        assert len(data["data"]) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 6: nse_bse_get_index
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetIndex:
    async def test_valid_index(self, mock_info, mock_history_df, mocker):
        mt = make_mock_ticker(info=mock_info, history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_index(IndexInput(index="NIFTY50", period="1mo")))
        assert_no_error(data)
        assert data["index"] == "NIFTY50"
        assert "level" in data

    async def test_invalid_index_returns_error(self, mocker):
        mocker.patch("yfinance.Ticker", return_value=make_mock_ticker())
        data = parse(await nse_bse_get_index(IndexInput(index="FAKEINDEX", period="1d")))
        assert "error" in data
        assert "valid" in data

    async def test_period_performance_included(self, mock_info, mock_history_df, mocker):
        mt = make_mock_ticker(info=mock_info, history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_index(IndexInput(index="SENSEX", period="1mo")))
        assert "period_return_pct" in data

    async def test_fields_to_return(self, mock_info, mock_history_df, mocker):
        mt = make_mock_ticker(info=mock_info, history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_index(
            IndexInput(index="NIFTYBANK", period="1d", fields_to_return=["index","level","change_pct"])
        ))
        assert set(data.keys()) == {"index","level","change_pct"}


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 7: nse_bse_list_indices
# ═══════════════════════════════════════════════════════════════════════════════

class TestListIndices:
    async def test_returns_list(self):
        data = parse(await nse_bse_list_indices())
        assert isinstance(data, list)
        assert len(data) >= 15

    async def test_each_has_name_and_ticker(self):
        data = parse(await nse_bse_list_indices())
        for item in data:
            assert "name" in item
            assert "yahoo_ticker" in item
            assert len(item["yahoo_ticker"]) > 0

    async def test_nifty50_present(self):
        data  = parse(await nse_bse_list_indices())
        names = [d["name"] for d in data]
        assert "NIFTY50" in names
        assert "SENSEX"  in names


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 8: nse_bse_get_dividends
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetDividends:
    async def test_with_dividends(self, mock_dividends, mocker):
        mt = make_mock_ticker(dividends=mock_dividends)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_dividends(StockInput(symbol="TEST")))
        assert "dividends" in data
        assert len(data["dividends"]) > 0
        assert data["total_dividends_last_5y"] > 0

    async def test_no_dividends(self, mocker):
        mt = make_mock_ticker(dividends=pd.Series(dtype=float))
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_dividends(StockInput(symbol="NODIV")))
        assert data["dividends"] == []
        assert "message" in data

    async def test_max_20_dividends_returned(self, mocker):
        dates  = pd.date_range("2000-01-01", periods=50, freq="180D")
        divs   = pd.Series([10.0] * 50, index=dates)
        mt     = make_mock_ticker(dividends=divs)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data   = parse(await nse_bse_get_dividends(StockInput(symbol="TEST")))
        assert len(data["dividends"]) <= 20

    async def test_most_recent_first(self, mock_dividends, mocker):
        mt = make_mock_ticker(dividends=mock_dividends)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data  = parse(await nse_bse_get_dividends(StockInput(symbol="TEST")))
        dates = [d["date"] for d in data["dividends"]]
        assert dates == sorted(dates, reverse=True)


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 9: nse_bse_get_shareholders
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetShareholders:
    async def test_with_data(self, mock_inst_holders, mock_major_holders, mocker):
        mf = mock_inst_holders.copy()  # reuse as mutual fund mock
        mt = make_mock_ticker(
            institutional_holders=mock_inst_holders,
            major_holders=mock_major_holders,
            mutualfund_holders=mf,
        )
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_shareholders(
            ShareholdersInput(symbol="TEST", include_mutualfunds=True)
        ))
        assert "institutional_holders" in data
        assert "major_holders" in data
        assert "mutualfund_holders" in data

    async def test_top_n_respected(self, mock_inst_holders, mock_major_holders, mocker):
        mt = make_mock_ticker(
            institutional_holders=mock_inst_holders,
            major_holders=mock_major_holders,
        )
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_shareholders(
            ShareholdersInput(symbol="TEST", top_n=2)
        ))
        assert len(data["institutional_holders"]) <= 2

    async def test_no_mutualfunds_if_disabled(self, mock_inst_holders, mock_major_holders, mocker):
        mt = make_mock_ticker(
            institutional_holders=mock_inst_holders,
            major_holders=mock_major_holders,
        )
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_shareholders(
            ShareholdersInput(symbol="TEST", include_mutualfunds=False)
        ))
        assert "mutualfund_holders" not in data

    async def test_unavailable_graceful(self, mocker):
        mt = make_mock_ticker()  # all None by default
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_shareholders(ShareholdersInput(symbol="TEST")))
        assert data.get("institutional_holders") == "unavailable"


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 10: nse_bse_get_options
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetOptions:
    async def test_returns_expiries_when_no_expiry(self, mock_fast_info, mock_options_chain, mocker):
        mt = make_mock_ticker(
            options=("2026-06-25","2026-07-31"),
            fast_info=mock_fast_info,
            option_chain=mock_options_chain,
        )
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_options(OptionsInput(symbol="TEST")))
        assert "available_expiries" in data
        assert "2026-06-25" in data["available_expiries"]

    async def test_calls_and_puts(self, mock_fast_info, mock_options_chain, mocker):
        mt = make_mock_ticker(
            options=("2026-06-25",),
            fast_info=mock_fast_info,
            option_chain=mock_options_chain,
        )
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_options(
            OptionsInput(symbol="TEST", expiry="2026-06-25", option_type="both")
        ))
        assert "calls" in data
        assert "puts"  in data

    async def test_only_calls(self, mock_fast_info, mock_options_chain, mocker):
        mt = make_mock_ticker(
            options=("2026-06-25",),
            fast_info=mock_fast_info,
            option_chain=mock_options_chain,
        )
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_options(
            OptionsInput(symbol="TEST", expiry="2026-06-25", option_type="calls")
        ))
        assert "calls" in data
        assert "puts"  not in data

    async def test_limit_strikes_near_atm(self, mock_fast_info, mock_options_chain, mocker):
        mt = make_mock_ticker(
            options=("2026-06-25",),
            fast_info=mock_fast_info,
            option_chain=mock_options_chain,
        )
        mocker.patch("yfinance.Ticker", return_value=mt)
        # ATM ~ 1500; limit to 1 strike each side → max 3 strikes
        data = parse(await nse_bse_get_options(
            OptionsInput(symbol="TEST", expiry="2026-06-25", option_type="calls", limit_strikes_near_atm=1)
        ))
        assert len(data["calls"]) <= 3

    async def test_fields_to_return(self, mock_fast_info, mock_options_chain, mocker):
        mt = make_mock_ticker(
            options=("2026-06-25",),
            fast_info=mock_fast_info,
            option_chain=mock_options_chain,
        )
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_options(
            OptionsInput(symbol="TEST", expiry="2026-06-25",
                         fields_to_return=["strike","implied_volatility"])
        ))
        for row in data.get("calls", []) + data.get("puts", []):
            assert set(row.keys()) == {"strike","implied_volatility"}

    async def test_no_options_message(self, mocker):
        mt = make_mock_ticker(options=())
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_options(OptionsInput(symbol="NOOPT")))
        assert "message" in data

    async def test_invalid_expiry_returns_error(self, mock_fast_info, mocker):
        mt = make_mock_ticker(options=("2026-06-25",), fast_info=mock_fast_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_options(
            OptionsInput(symbol="TEST", expiry="2099-01-01")
        ))
        assert "error" in data

    async def test_invalid_option_type(self):
        with pytest.raises(Exception):
            OptionsInput(symbol="TEST", option_type="straddle")


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 11: nse_bse_get_news
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetNews:
    async def test_basic(self, mock_news, mocker):
        mt = make_mock_ticker(news=mock_news)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_news(NewsInput(symbol="TEST", limit=5)))
        assert_no_error(data)
        assert data["count"] == 2  # only 2 articles in fixture
        assert len(data["articles"]) == 2

    async def test_limit_respected(self, mock_news, mocker):
        mt = make_mock_ticker(news=mock_news * 10)  # 20 articles
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_news(NewsInput(symbol="TEST", limit=5)))
        assert len(data["articles"]) <= 5

    async def test_article_fields(self, mock_news, mocker):
        mt = make_mock_ticker(news=mock_news)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_news(NewsInput(symbol="TEST")))
        for art in data["articles"]:
            assert "title"        in art
            assert "publisher"    in art
            assert "link"         in art
            assert "published_at" in art

    async def test_published_at_format(self, mock_news, mocker):
        mt = make_mock_ticker(news=mock_news)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_news(NewsInput(symbol="TEST")))
        pa = data["articles"][0]["published_at"]
        assert len(pa) == 16  # YYYY-MM-DD HH:MM

    async def test_fields_to_return(self, mock_news, mocker):
        mt = make_mock_ticker(news=mock_news)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_news(
            NewsInput(symbol="TEST", fields_to_return=["title","publisher"])
        ))
        for art in data["articles"]:
            assert set(art.keys()) == {"title","publisher"}

    async def test_no_news(self, mocker):
        mt = make_mock_ticker(news=[])
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_news(NewsInput(symbol="QUIET")))
        assert data["articles"] == []
        assert "message" in data


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 12: nse_bse_get_analyst_view
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetAnalystView:
    async def test_price_targets(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_analyst_view(
            AnalystInput(symbol="TEST", include=["price_targets"])
        ))
        pt = data.get("price_targets", {})
        assert pt.get("mean")  == 1750.0
        assert pt.get("high")  == 1950.0
        assert pt.get("low")   == 1400.0

    async def test_include_filter(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_analyst_view(
            AnalystInput(symbol="TEST", include=["price_targets"])
        ))
        assert "price_targets" in data
        assert "upgrades_downgrades" not in data

    async def test_unavailable_sections_handled(self, mock_info, mocker):
        mt = make_mock_ticker(info=mock_info, recommendations=None, upgrades_downgrades=None)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_analyst_view(
            AnalystInput(symbol="TEST", include=["recommendations_summary","upgrades_downgrades"])
        ))
        # Should not crash; sections marked "unavailable"
        assert data.get("recommendations_summary")  in (None,"unavailable") or isinstance(data.get("recommendations_summary"), list)


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 13: nse_bse_get_earnings
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetEarnings:
    async def test_calendar(self, mocker):
        calendar = {
            "Earnings Date":  ["2026-07-15"],
            "Ex-Dividend Date": "2026-06-01",
        }
        mt = make_mock_ticker(calendar=calendar)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_earnings(
            EarningsInput(symbol="TEST", include=["calendar"])
        ))
        assert "calendar" in data

    async def test_include_filter(self, mocker):
        mt = make_mock_ticker()
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_earnings(
            EarningsInput(symbol="TEST", include=["calendar"])
        ))
        assert "earnings_dates" not in data
        assert "earnings_history" not in data

    async def test_earnings_dates(self, mocker):
        df = pd.DataFrame({
            "Earnings Date":  pd.date_range("2025-01-15", periods=4, freq="90D"),
            "EPS Estimate":   [60, 65, 68, 70],
            "Reported EPS":   [62, 64, 70, None],
        })
        df.set_index("Earnings Date", inplace=True)
        mt = make_mock_ticker(earnings_dates=df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_earnings(
            EarningsInput(symbol="TEST", include=["earnings_dates"])
        ))
        assert isinstance(data.get("earnings_dates"), list)


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 14: nse_bse_get_insider_activity
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetInsiderActivity:
    async def _mock_txn_df(self):
        return pd.DataFrame({
            "Insider":     ["Promoter A", "Promoter B", "CFO"],
            "Shares":      [100_000, 50_000, 10_000],
            "Value":       [150_000_000, 75_000_000, 15_000_000],
            "Transaction": ["Buy", "Buy", "Sell"],
            "Date":        ["2025-12-01", "2026-01-10", "2026-02-15"],
            "Position":    ["MD", "Director", "CFO"],
        })

    async def test_transactions(self, mocker):
        df = await self._mock_txn_df()
        mt = make_mock_ticker(insider_transactions=df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_insider_activity(
            InsiderInput(symbol="TEST", include=["transactions"])
        ))
        assert isinstance(data.get("transactions"), list)
        assert len(data["transactions"]) == 3

    async def test_limit(self, mocker):
        df = await self._mock_txn_df()
        mt = make_mock_ticker(insider_transactions=df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_insider_activity(
            InsiderInput(symbol="TEST", include=["transactions"], limit=2)
        ))
        assert len(data["transactions"]) <= 2

    async def test_transaction_type_filter_buy(self, mocker):
        df = await self._mock_txn_df()
        mt = make_mock_ticker(insider_transactions=df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_insider_activity(
            InsiderInput(symbol="TEST", include=["transactions"], transaction_type="buy")
        ))
        for txn in data.get("transactions", []):
            assert "buy" in str(txn.get("Transaction","")).lower()

    async def test_unavailable_graceful(self, mocker):
        mt = make_mock_ticker()
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_insider_activity(InsiderInput(symbol="TEST")))
        assert "transactions" in data


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 15: nse_bse_get_technicals
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetTechnicals:
    async def test_all_indicators(self, mock_history_df, mocker):
        mt = make_mock_ticker(history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_technicals(TechnicalInput(symbol="TEST", period="6mo")))
        assert_no_error(data)
        assert "rsi"              in data
        assert "macd"             in data
        assert "bollinger_bands"  in data
        assert "atr"              in data
        assert "moving_averages"  in data
        assert "volume_trend"     in data
        assert "supertrend"       in data
        assert "signal_summary"   in data

    async def test_rsi_in_range(self, mock_history_df, mocker):
        mt = make_mock_ticker(history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_technicals(TechnicalInput(symbol="TEST")))
        rsi = data["rsi"]["value"]
        assert 0 <= rsi <= 100

    async def test_specific_indicators_filter(self, mock_history_df, mocker):
        mt = make_mock_ticker(history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_technicals(
            TechnicalInput(symbol="TEST", indicators=["rsi","macd"])
        ))
        assert "rsi"   in data
        assert "macd"  in data
        assert "supertrend" not in data

    async def test_signal_summary_signal_valid(self, mock_history_df, mocker):
        mt = make_mock_ticker(history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_technicals(TechnicalInput(symbol="TEST")))
        assert data["signal_summary"]["signal"] in (
            "STRONG_BUY","BUY","NEUTRAL","SELL","STRONG_SELL"
        )

    async def test_insufficient_data_returns_error(self, mocker):
        small_df = pd.DataFrame({
            "Open": [100, 101], "High": [105, 106], "Low": [99, 100],
            "Close": [103, 104], "Volume": [1000, 1000],
        })
        mt = make_mock_ticker(history_df=small_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_technicals(TechnicalInput(symbol="TEST")))
        assert "error" in data

    async def test_macd_crossover_field(self, mock_history_df, mocker):
        mt = make_mock_ticker(history_df=mock_history_df)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_technicals(TechnicalInput(symbol="TEST", indicators=["macd"])))
        assert data["macd"]["crossover"] in ("bullish","bearish")


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 16: nse_bse_sector_snapshot
# ═══════════════════════════════════════════════════════════════════════════════

class TestSectorSnapshot:
    async def test_all_indices(self, mock_fast_info, mocker):
        mocker.patch("yfinance.Ticker", return_value=make_mock_ticker(fast_info=mock_fast_info))
        data = parse(await nse_bse_sector_snapshot(SectorSnapshotInput()))
        assert "data" in data
        assert data["count"] > 0

    async def test_specific_indices(self, mock_fast_info, mocker):
        mocker.patch("yfinance.Ticker", return_value=make_mock_ticker(fast_info=mock_fast_info))
        data = parse(await nse_bse_sector_snapshot(
            SectorSnapshotInput(indices=["NIFTY50","NIFTYBANK"])
        ))
        assert data["count"] == 2
        names = [r["name"] for r in data["data"]]
        assert "NIFTY50" in names
        assert "NIFTYBANK" in names

    async def test_invalid_index_returns_error(self, mocker):
        mocker.patch("yfinance.Ticker", return_value=make_mock_ticker())
        data = parse(await nse_bse_sector_snapshot(SectorSnapshotInput(indices=["FAKE_IDX"])))
        assert "error" in data

    async def test_fields_to_return(self, mock_fast_info, mocker):
        mocker.patch("yfinance.Ticker", return_value=make_mock_ticker(fast_info=mock_fast_info))
        data = parse(await nse_bse_sector_snapshot(
            SectorSnapshotInput(indices=["NIFTY50","SENSEX"], fields_to_return=["name","change_pct"])
        ))
        for row in data["data"]:
            assert set(row.keys()) == {"name","change_pct"}

    async def test_sorted_by_change_pct_desc(self, mocker):
        """Indices should come back sorted by change_pct descending."""
        mocker.patch("yfinance.Ticker", return_value=make_mock_ticker(fast_info=make_fast_info(1500, 1480)))
        data = parse(await nse_bse_sector_snapshot(SectorSnapshotInput(indices=["NIFTY50","SENSEX"])))
        pcts = [r.get("change_pct") or -999 for r in data["data"]]
        assert pcts == sorted(pcts, reverse=True)


def make_fast_info(price, prev):
    from unittest.mock import MagicMock
    fi = MagicMock()
    fi.last_price                    = price
    fi.regular_market_previous_close = prev
    fi.previous_close                = prev
    fi.year_high                     = price * 1.2
    fi.year_low                      = price * 0.8
    return fi


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 17: nse_bse_portfolio_analysis
# ═══════════════════════════════════════════════════════════════════════════════

class TestPortfolioAnalysis:
    def _input(self):
        return PortfolioInput(holdings=[
            PortfolioHolding(symbol="TEST", quantity=100, avg_buy_price=1200.0),
            PortfolioHolding(symbol="TEST2", quantity=50,  avg_buy_price=500.0),
        ])

    async def test_basic(self, mock_info, mocker):
        mocker.patch("yfinance.Ticker", return_value=make_mock_ticker(info=mock_info))
        data = parse(await nse_bse_portfolio_analysis(self._input()))
        assert_no_error(data)
        assert "summary" in data

    async def test_summary_fields(self, mock_info, mocker):
        mocker.patch("yfinance.Ticker", return_value=make_mock_ticker(info=mock_info))
        data = parse(await nse_bse_portfolio_analysis(self._input()))
        summary = data["summary"]
        assert "total_invested"  in summary
        assert "current_value"   in summary
        assert "total_pnl"       in summary
        assert "total_pnl_pct"   in summary

    async def test_per_stock_pnl(self, mock_info, mocker):
        mocker.patch("yfinance.Ticker", return_value=make_mock_ticker(info=mock_info))
        data = parse(await nse_bse_portfolio_analysis(self._input()))
        per  = data.get("per_stock", [])
        assert len(per) == 2
        for h in per:
            if h.get("current_price"):
                assert h["pnl"] is not None

    async def test_sector_allocation(self, mock_info, mocker):
        mocker.patch("yfinance.Ticker", return_value=make_mock_ticker(info=mock_info))
        data = parse(await nse_bse_portfolio_analysis(self._input()))
        sa   = data.get("sector_allocation", [])
        assert isinstance(sa, list)
        if sa:
            # Weights should sum to ~100
            total_w = sum(s["weight_pct"] for s in sa)
            assert total_w == pytest.approx(100.0, abs=0.5)

    async def test_risk_metrics(self, mock_info, mocker):
        mocker.patch("yfinance.Ticker", return_value=make_mock_ticker(info=mock_info))
        data = parse(await nse_bse_portfolio_analysis(self._input()))
        rm   = data.get("risk_metrics", {})
        assert "portfolio_beta"        in rm
        assert "beta_interpretation"   in rm
        assert "diversification_note"  in rm

    async def test_fields_to_return(self, mock_info, mocker):
        mocker.patch("yfinance.Ticker", return_value=make_mock_ticker(info=mock_info))
        data = parse(await nse_bse_portfolio_analysis(
            PortfolioInput(
                holdings=[PortfolioHolding(symbol="TEST", quantity=10, avg_buy_price=1200)],
                fields_to_return=["summary"],
            )
        ))
        assert "summary"            in data
        assert "sector_allocation"  not in data
        assert "per_stock"          not in data


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 18: nse_bse_get_corporate_actions
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetCorporateActions:
    async def test_with_splits_and_dividends(self, mock_splits, mock_dividends, mocker):
        mt = make_mock_ticker(splits=mock_splits, dividends=mock_dividends)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_corporate_actions(StockInput(symbol="TEST")))
        assert_no_error(data)
        assert len(data["splits"]) == 1
        assert data["splits"][0]["split_ratio"] == 2.0
        assert len(data["dividends"]) > 0

    async def test_no_splits(self, mock_dividends, mocker):
        mt = make_mock_ticker(splits=pd.Series(dtype=float), dividends=mock_dividends)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_corporate_actions(StockInput(symbol="TEST")))
        assert data["splits"] == []

    async def test_dividends_most_recent_first(self, mock_dividends, mocker):
        mt = make_mock_ticker(dividends=mock_dividends)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_corporate_actions(StockInput(symbol="TEST")))
        dates = [d["date"] for d in data["dividends"]]
        assert dates == sorted(dates, reverse=True)

    async def test_capital_gains_included(self, mocker):
        dates = pd.DatetimeIndex(["2024-12-15"])
        cg    = pd.Series([5.0], index=dates)
        mt    = make_mock_ticker(capital_gains=cg)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data  = parse(await nse_bse_get_corporate_actions(StockInput(symbol="TEST")))
        assert "capital_gains" in data
        assert len(data["capital_gains"]) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Tool 19: nse_bse_get_esg
# ═══════════════════════════════════════════════════════════════════════════════

class TestGetEsg:
    async def test_with_data(self, mock_sustainability, mocker):
        mt = make_mock_ticker(sustainability=mock_sustainability)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_esg(ESGInput(symbol="TEST")))
        assert_no_error(data)
        assert data["total_esg"]           == pytest.approx(48.5, rel=0.01)
        assert data["environment_score"]   == pytest.approx(10.2, rel=0.01)
        assert data["social_score"]        == pytest.approx(18.7, rel=0.01)
        assert data["governance_score"]    == pytest.approx(19.6, rel=0.01)

    async def test_no_esg_data(self, mocker):
        mt = make_mock_ticker(sustainability=None)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_esg(ESGInput(symbol="NOESG")))
        assert "message" in data

    async def test_fields_to_return(self, mock_sustainability, mocker):
        mt = make_mock_ticker(sustainability=mock_sustainability)
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_esg(
            ESGInput(symbol="TEST", fields_to_return=["total_esg","governance_score"])
        ))
        assert set(data.keys()) == {"total_esg","governance_score"}

    async def test_empty_df_returns_message(self, mocker):
        mt = make_mock_ticker(sustainability=pd.DataFrame())
        mocker.patch("yfinance.Ticker", return_value=mt)
        data = parse(await nse_bse_get_esg(ESGInput(symbol="EMPTY")))
        assert "message" in data


# ═══════════════════════════════════════════════════════════════════════════════
# Pydantic Validation Tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestInputValidation:
    def test_empty_symbol_rejected(self):
        with pytest.raises(Exception):
            StockInput(symbol="")

    def test_symbol_too_long_rejected(self):
        with pytest.raises(Exception):
            StockInput(symbol="A" * 21)

    def test_invalid_exchange_rejected(self):
        with pytest.raises(Exception):
            StockInput(symbol="TEST", exchange="MCX")

    def test_symbol_uppercased(self):
        p = StockInput(symbol="reliance")
        assert p.symbol == "RELIANCE"

    def test_historical_invalid_period(self):
        with pytest.raises(Exception):
            HistoricalInput(symbol="TEST", period="99yr")

    def test_historical_invalid_interval(self):
        with pytest.raises(Exception):
            HistoricalInput(symbol="TEST", interval="2d")

    def test_historical_max_records_clamp(self):
        with pytest.raises(Exception):
            HistoricalInput(symbol="TEST", max_records=501)

    def test_compare_min_symbols(self):
        with pytest.raises(Exception):
            CompareInput(symbols=["ONLY"])

    def test_compare_max_symbols(self):
        with pytest.raises(Exception):
            CompareInput(symbols=[f"S{i}" for i in range(11)])

    def test_options_invalid_option_type(self):
        with pytest.raises(Exception):
            OptionsInput(symbol="TEST", option_type="butterfly")

    def test_options_limit_strikes_out_of_range(self):
        with pytest.raises(Exception):
            OptionsInput(symbol="TEST", limit_strikes_near_atm=21)

    def test_portfolio_holding_qty_must_be_positive(self):
        with pytest.raises(Exception):
            PortfolioHolding(symbol="TEST", quantity=0, avg_buy_price=100)

    def test_portfolio_holding_price_must_be_positive(self):
        with pytest.raises(Exception):
            PortfolioHolding(symbol="TEST", quantity=10, avg_buy_price=-50)

    def test_financials_invalid_frequency(self):
        with pytest.raises(Exception):
            FinancialsInput(symbol="TEST", frequency="daily")

    def test_shareholders_top_n_out_of_range(self):
        with pytest.raises(Exception):
            ShareholdersInput(symbol="TEST", top_n=51)

    def test_news_limit_out_of_range(self):
        with pytest.raises(Exception):
            NewsInput(symbol="TEST", limit=26)
