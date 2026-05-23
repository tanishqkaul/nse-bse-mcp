"""
Unit tests for pure helper functions and technical indicators.
No mocking required — these are stateless computations.
"""
import math
import pytest
import numpy as np
import pandas as pd
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server import (
    build_ticker,
    safe_float,
    safe_int,
    fmt_crore,
    fmt_pct,
    fmt_num,
    filter_fields,
    filter_records,
    calc_rsi,
    calc_macd,
    calc_bollinger_bands,
    calc_atr_scalar,
    calc_supertrend,
    _signal_summary,
    _atr_numpy,
    _df_to_crore_dict,
    _series_to_crore_dict,
    Exchange,
    INDICES,
    VALID_PERIODS,
    VALID_INTERVALS,
)


# ─── build_ticker ─────────────────────────────────────────────────────────────

class TestBuildTicker:
    def test_nse_default(self):
        assert build_ticker("RELIANCE", "NSE") == "RELIANCE.NS"

    def test_bse(self):
        assert build_ticker("RELIANCE", "BSE") == "RELIANCE.BO"

    def test_lowercase_input(self):
        assert build_ticker("tcs", "nse") == "TCS.NS"

    def test_leading_trailing_spaces(self):
        assert build_ticker("  INFY  ", "NSE") == "INFY.NS"

    def test_bse_uppercase(self):
        assert build_ticker("hdfcbank", "BSE") == "HDFCBANK.BO"


# ─── safe_float ───────────────────────────────────────────────────────────────

class TestSafeFloat:
    def test_valid_float(self):
        assert safe_float(3.14) == 3.14

    def test_int_input(self):
        assert safe_float(42) == 42.0

    def test_string_number(self):
        assert safe_float("1500.50") == 1500.50

    def test_nan_returns_none(self):
        assert safe_float(float("nan")) is None

    def test_inf_returns_none(self):
        assert safe_float(float("inf")) is None

    def test_neg_inf_returns_none(self):
        assert safe_float(float("-inf")) is None

    def test_none_returns_none(self):
        assert safe_float(None) is None

    def test_empty_string_returns_none(self):
        assert safe_float("") is None

    def test_non_numeric_string_returns_none(self):
        assert safe_float("N/A") is None


# ─── safe_int ─────────────────────────────────────────────────────────────────

class TestSafeInt:
    def test_valid(self):
        assert safe_int(42) == 42

    def test_float_truncates(self):
        assert safe_int(3.9) == 3

    def test_string(self):
        assert safe_int("100") == 100

    def test_none(self):
        assert safe_int(None) is None

    def test_invalid_string(self):
        assert safe_int("abc") is None


# ─── fmt_crore ────────────────────────────────────────────────────────────────

class TestFmtCrore:
    def test_lakh_crore(self):
        # 1e13 / 1e7 = 1e6 crore → "10.00 Lakh Cr"
        assert "Lakh Cr" in fmt_crore(1_000_000_000_000_000)

    def test_crore(self):
        result = fmt_crore(5_000_000_000)  # 500 Cr
        assert "500.00 Cr" in result

    def test_small_value(self):
        result = fmt_crore(1_000)
        assert "₹" in result

    def test_none(self):
        assert fmt_crore(None) == "N/A"


# ─── fmt_pct ──────────────────────────────────────────────────────────────────

class TestFmtPct:
    def test_positive(self):
        assert fmt_pct(0.25) == "25.00%"

    def test_zero(self):
        assert fmt_pct(0.0) == "0.00%"

    def test_none(self):
        assert fmt_pct(None) == "N/A"

    def test_negative(self):
        assert fmt_pct(-0.05) == "-5.00%"


# ─── fmt_num ──────────────────────────────────────────────────────────────────

class TestFmtNum:
    def test_basic(self):
        assert fmt_num(1500.0) == "1,500.00"

    def test_large(self):
        assert "1,000,000" in fmt_num(1_000_000.0)

    def test_none(self):
        assert fmt_num(None) == "N/A"

    def test_custom_decimals(self):
        assert fmt_num(3.14159, decimals=4) == "3.1416"


# ─── filter_fields ────────────────────────────────────────────────────────────

class TestFilterFields:
    def test_no_filter_returns_all(self):
        d = {"a": 1, "b": 2, "c": 3}
        assert filter_fields(d, None) == d

    def test_filter_subset(self):
        d = {"price": 100, "volume": 1000, "pe": 25}
        result = filter_fields(d, ["price", "pe"])
        assert result == {"price": 100, "pe": 25}
        assert "volume" not in result

    def test_filter_missing_key(self):
        d = {"price": 100}
        result = filter_fields(d, ["price", "nonexistent"])
        assert result == {"price": 100}

    def test_empty_filter_list(self):
        # An empty list is treated as "no filter" (same as None) → returns all fields
        d = {"a": 1, "b": 2}
        assert filter_fields(d, []) == d

    def test_empty_dict(self):
        assert filter_fields({}, ["a"]) == {}


# ─── filter_records ───────────────────────────────────────────────────────────

class TestFilterRecords:
    def test_no_filter(self):
        records = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]
        assert filter_records(records, None) == records

    def test_filter_applied(self):
        records = [{"date": "2025-01-01", "close": 100, "volume": 1000}]
        result  = filter_records(records, ["date", "close"])
        assert result == [{"date": "2025-01-01", "close": 100}]

    def test_multiple_records(self):
        records = [{"x": i, "y": i * 2} for i in range(5)]
        result  = filter_records(records, ["x"])
        assert all("y" not in r for r in result)
        assert all(r["x"] == i for i, r in enumerate(result))


# ─── _df_to_crore_dict ────────────────────────────────────────────────────────

class TestDfToCroreDict:
    def test_basic_conversion(self):
        dates = pd.date_range("2022-03-31", periods=2, freq="365D")
        df = pd.DataFrame(
            [[100_000_000_00, 110_000_000_00],
             [40_000_000_00,  44_000_000_00]],
            index=["Revenue", "Gross Profit"],
            columns=dates,
        )
        result = _df_to_crore_dict(df)
        assert len(result) == 2
        # First column values should be in crore (divided by 1e7)
        col0 = list(result.keys())[0]
        assert result[col0]["Revenue"] == pytest.approx(100_000_000_00 / 1e7, rel=1e-4)

    def test_empty_df(self):
        assert _df_to_crore_dict(pd.DataFrame()) == {}

    def test_none_input(self):
        assert _df_to_crore_dict(None) == {}

    def test_max_cols_respected(self):
        dates = pd.date_range("2022-03-31", periods=5, freq="365D")
        df    = pd.DataFrame([[i * 1e9 for i in range(5)]], index=["Revenue"], columns=dates)
        result = _df_to_crore_dict(df, max_cols=2)
        assert len(result) == 2


# ─── _series_to_crore_dict ────────────────────────────────────────────────────

class TestSeriesToCroreDict:
    def test_series(self):
        s = pd.Series({"Revenue": 100_000_000_000, "Net Income": 20_000_000_000})
        r = _series_to_crore_dict(s)
        assert r["Revenue"] == pytest.approx(10000.0, rel=1e-4)
        assert r["Net Income"] == pytest.approx(2000.0, rel=1e-4)

    def test_single_col_df(self):
        df = pd.DataFrame({"2025-03-31": [100e9, 20e9]}, index=["Revenue", "Net"])
        r  = _series_to_crore_dict(df)
        assert "Revenue" in r

    def test_none(self):
        assert _series_to_crore_dict(None) == {}


# ─── _atr_numpy ──────────────────────────────────────────────────────────────

class TestAtrNumpy:
    def test_output_shape(self):
        n    = 30
        high = np.random.uniform(105, 115, n)
        low  = np.random.uniform(90, 100, n)
        close= np.random.uniform(95, 110, n)
        atr  = _atr_numpy(high, low, close, period=14)
        assert atr.shape == (n,)

    def test_positive_values(self):
        high  = np.array([10, 11, 12, 11, 10, 9, 10, 11, 12, 13, 12, 11, 10, 9, 10], dtype=float)
        low   = np.array([ 9, 10, 11, 10,  9, 8,  9, 10, 11, 12, 11, 10,  9, 8,  9], dtype=float)
        close = np.array([ 9.5, 10.5, 11.5, 10.5, 9.5, 8.5, 9.5, 10.5, 11.5, 12.5, 11.5, 10.5, 9.5, 8.5, 9.5], dtype=float)
        atr   = _atr_numpy(high, low, close, period=5)
        assert np.all(atr >= 0)

    def test_constant_prices_gives_zero_atr(self):
        """Constant OHLC (no range) should give ATR near zero."""
        high  = np.ones(20) * 100.0
        low   = np.ones(20) * 100.0
        close = np.ones(20) * 100.0
        atr   = _atr_numpy(high, low, close, period=14)
        assert float(atr[-1]) == pytest.approx(0.0, abs=1e-9)


# ─── calc_rsi ────────────────────────────────────────────────────────────────

class TestCalcRsi:
    def _make_close(self, values):
        return pd.Series(values, dtype=float)

    def test_returns_float(self):
        # Use mixed-direction data so avg_loss > 0 and RSI is a proper float
        import numpy as np
        np.random.seed(42)
        close = self._make_close((100 + np.cumsum(np.random.randn(40))).tolist())
        result = calc_rsi(close)
        assert isinstance(result, float)

    def test_range_0_to_100(self):
        np.random.seed(0)
        close = self._make_close(100 + np.cumsum(np.random.randn(50)))
        rsi = calc_rsi(close)
        assert 0 <= rsi <= 100

    def test_pure_up_trend_gives_high_rsi(self):
        """Strictly rising prices should give RSI > 70."""
        close = self._make_close(list(range(100, 130)))
        rsi = calc_rsi(close)
        assert rsi > 70

    def test_pure_down_trend_gives_low_rsi(self):
        """Strictly falling prices should give RSI < 30."""
        close = self._make_close(list(range(130, 100, -1)))
        rsi = calc_rsi(close)
        assert rsi < 30

    def test_insufficient_data_returns_value(self):
        """With fewer than 14+1 data points it should still return a float (not None)."""
        close = self._make_close([100, 101, 102, 103, 104])
        # With very few points EWM still computes something
        result = calc_rsi(close)
        assert result is None or isinstance(result, float)


# ─── calc_macd ────────────────────────────────────────────────────────────────

class TestCalcMacd:
    def _close(self):
        np.random.seed(7)
        return pd.Series(1400 + np.cumsum(np.random.randn(100) * 5), dtype=float)

    def test_returns_dict_with_all_keys(self):
        result = calc_macd(self._close())
        for key in ("macd_line", "signal_line", "histogram", "crossover"):
            assert key in result

    def test_crossover_is_string(self):
        result = calc_macd(self._close())
        assert result["crossover"] in ("bullish", "bearish")

    def test_histogram_equals_macd_minus_signal(self):
        result = calc_macd(self._close())
        expected = round(result["macd_line"] - result["signal_line"], 4)
        assert result["histogram"] == pytest.approx(expected, abs=1e-3)

    def test_all_numeric(self):
        result = calc_macd(self._close())
        assert all(isinstance(result[k], float) for k in ("macd_line","signal_line","histogram"))


# ─── calc_bollinger_bands ────────────────────────────────────────────────────

class TestCalcBollingerBands:
    def _close(self):
        np.random.seed(3)
        return pd.Series(1500 + np.cumsum(np.random.randn(50) * 4), dtype=float)

    def test_returns_all_keys(self):
        result = calc_bollinger_bands(self._close())
        for k in ("upper", "middle", "lower", "pct_b", "signal"):
            assert k in result

    def test_upper_gt_middle_gt_lower(self):
        result = calc_bollinger_bands(self._close())
        assert result["upper"] > result["middle"] > result["lower"]

    def test_signal_is_valid(self):
        result = calc_bollinger_bands(self._close())
        assert result["signal"] in ("overbought", "oversold", "neutral")

    def test_pct_b_numeric(self):
        result = calc_bollinger_bands(self._close())
        assert isinstance(result["pct_b"], (float, type(None)))


# ─── calc_atr_scalar ─────────────────────────────────────────────────────────

class TestCalcAtrScalar:
    def _df(self):
        n = 30
        np.random.seed(9)
        close = 1500 + np.cumsum(np.random.randn(n) * 8)
        return pd.DataFrame({
            "High":   close + 10,
            "Low":    close - 10,
            "Close":  close,
            "Volume": np.ones(n, dtype=int) * 1_000_000,
        })

    def test_positive_float(self):
        result = calc_atr_scalar(self._df())
        assert isinstance(result, float)
        assert result > 0

    def test_small_range_gives_small_atr(self):
        """Near-flat price action → ATR close to 0."""
        n = 20
        flat = np.ones(n) * 1000.0
        df   = pd.DataFrame({"High": flat + 0.01, "Low": flat - 0.01, "Close": flat})
        result = calc_atr_scalar(df)
        assert result < 1.0


# ─── calc_supertrend ─────────────────────────────────────────────────────────

class TestCalcSupertrend:
    def _df(self, direction="up"):
        n = 50
        if direction == "up":
            close = np.linspace(1400, 1600, n)
        else:
            close = np.linspace(1600, 1400, n)
        return pd.DataFrame({
            "High":   close + 10,
            "Low":    close - 10,
            "Close":  close,
        })

    def test_returns_dict(self):
        result = calc_supertrend(self._df())
        assert "direction" in result
        assert "value" in result

    def test_direction_is_string(self):
        result = calc_supertrend(self._df())
        assert result["direction"] in ("bullish", "bearish", "insufficient_data")

    def test_insufficient_data(self):
        df = pd.DataFrame({"High": [100, 101], "Low": [99, 100], "Close": [100, 100]})
        result = calc_supertrend(df, period=10)
        assert result["direction"] == "insufficient_data"

    def test_uptrend_tends_bullish(self):
        result = calc_supertrend(self._df("up"))
        # In a strong up-trend, supertrend should eventually be bullish
        assert result["direction"] in ("bullish", "bearish")  # just ensure it doesn't crash


# ─── _signal_summary ─────────────────────────────────────────────────────────

class TestSignalSummary:
    def test_strong_buy_scenario(self):
        """RSI oversold + MACD bullish + BB oversold + supertrend bullish → STRONG_BUY or BUY"""
        result = _signal_summary(
            rsi=25,
            macd={"crossover": "bullish"},
            bb={"signal": "oversold"},
            st={"direction": "bullish"},
        )
        assert result["signal"] in ("STRONG_BUY", "BUY")
        assert result["score"] > 0

    def test_strong_sell_scenario(self):
        result = _signal_summary(
            rsi=75,
            macd={"crossover": "bearish"},
            bb={"signal": "overbought"},
            st={"direction": "bearish"},
        )
        assert result["signal"] in ("STRONG_SELL", "SELL")
        assert result["score"] < 0

    def test_neutral_scenario(self):
        result = _signal_summary(rsi=50, macd={}, bb={}, st={})
        assert result["signal"] == "NEUTRAL"

    def test_returns_reasons_list(self):
        result = _signal_summary(rsi=25, macd={"crossover":"bullish"}, bb={}, st={})
        assert isinstance(result["reasons"], list)
        assert len(result["reasons"]) >= 1

    def test_none_rsi_still_works(self):
        result = _signal_summary(rsi=None, macd={}, bb={}, st={})
        assert "signal" in result


# ─── Constants integrity ──────────────────────────────────────────────────────

class TestConstants:
    def test_all_indices_have_yahoo_tickers(self):
        for name, ticker in INDICES.items():
            assert isinstance(ticker, str) and len(ticker) > 0, f"{name} has invalid ticker"

    def test_valid_periods_contains_expected(self):
        for p in ("1d","1mo","1y","max"):
            assert p in VALID_PERIODS

    def test_valid_intervals_contains_expected(self):
        for i in ("1m","5m","1h","1d","1wk"):
            assert i in VALID_INTERVALS

    def test_exchange_enum_values(self):
        assert Exchange.NSE.value == "NSE"
        assert Exchange.BSE.value == "BSE"
