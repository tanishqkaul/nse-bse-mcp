#!/usr/bin/env python3
"""Test MCP tool registration."""

import asyncio
from server import mcp

async def test_tools():
    """List registered tools."""
    print("Checking MCP Tool Registration...")
    print("=" * 60)

    tools = await mcp.list_tools()

    if tools:
        print(f"[SUCCESS] Found {len(tools)} registered tools:\n")
        for tool in tools:
            print(f"  * {tool.name}")
            if tool.description:
                print(f"    Description: {tool.description[:80]}...")
            print()
    else:
        print("[ERROR] No tools registered!")

    print("=" * 60)
    return len(tools) > 0

if __name__ == "__main__":
    success = asyncio.run(test_tools())
    exit(0 if success else 1)
