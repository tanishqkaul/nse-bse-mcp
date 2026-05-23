#!/usr/bin/env python3
"""Test live MCP tool execution."""

import asyncio
import json
from server import mcp
from server import StockInput

async def test_quote_tool():
    """Test the nse_bse_get_quote tool."""
    print("Testing nse_bse_get_quote Tool (Live)")
    print("=" * 60)

    try:
        # Create input
        params = StockInput(symbol="RELIANCE", exchange="NSE")

        # Call the tool
        result = await mcp.call_tool("nse_bse_get_quote", {"params": {"symbol": "RELIANCE", "exchange": "NSE"}})

        print(f"[SUCCESS] Tool executed successfully!\n")
        print("Response:")
        print("-" * 60)
        # Handle unicode characters
        if isinstance(result, str):
            print(result.encode('utf-8', errors='replace').decode('utf-8'))
        else:
            print(str(result).encode('utf-8', errors='replace').decode('utf-8'))
        print("-" * 60)
        return True

    except Exception as e:
        print(f"[ERROR] {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_quote_tool())
    exit(0 if success else 1)
