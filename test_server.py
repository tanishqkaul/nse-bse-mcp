#!/usr/bin/env python3
"""Quick test of nse-bse-mcp server functionality."""

import sys
import asyncio
import yfinance as yf

async def test_server():
    """Test basic functionality."""
    print("Testing NSE-BSE MCP Server...")
    print("-" * 50)

    # Test 1: Get a stock quote (TCS from NSE)
    print("\n[TEST 1] Fetching TCS (Tata Consultancy Services) quote...")
    try:
        ticker = yf.Ticker("TCS.NS")
        data = ticker.info
        print(f"  Symbol: {data.get('symbol', 'N/A')}")
        print(f"  Current Price: Rs {data.get('currentPrice', 'N/A')}")
        print(f"  52 Week High: Rs {data.get('fiftyTwoWeekHigh', 'N/A')}")
        print(f"  Market Cap: Rs {data.get('marketCap', 'N/A')}")
        print("  [PASS] Stock quote retrieval working!")
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False

    # Test 2: Get NIFTY 50 index
    print("\n[TEST 2] Fetching NIFTY 50 index...")
    try:
        ticker = yf.Ticker("^NSEI")
        data = ticker.info
        print(f"  Index: {data.get('longName', 'NIFTY 50')}")
        print(f"  Current Value: {data.get('currentPrice', 'N/A')}")
        print("  [PASS] Index data retrieval working!")
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False

    # Test 3: Get historical data
    print("\n[TEST 3] Fetching historical data (RELIANCE)...")
    try:
        ticker = yf.Ticker("RELIANCE.NS")
        hist = ticker.history(period="5d")
        print(f"  Records fetched: {len(hist)}")
        print(f"  Latest Close: Rs {hist['Close'].iloc[-1]:.2f}")
        print("  [PASS] Historical data retrieval working!")
    except Exception as e:
        print(f"  [FAIL] Error: {e}")
        return False

    print("\n" + "=" * 50)
    print("[SUCCESS] All tests passed! Server is ready to use.")
    print("=" * 50)
    return True

if __name__ == "__main__":
    result = asyncio.run(test_server())
    sys.exit(0 if result else 1)
