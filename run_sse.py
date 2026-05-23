import sys
sys.path.insert(0, r"C:\Users\TANISHQ KAUL\Documents\Claude\Projects\PMS\nse-bse-mcp")
from server import mcp
mcp.settings.port = 8000
mcp.run(transport="sse")
