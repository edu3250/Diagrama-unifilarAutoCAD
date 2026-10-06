"""``python -m pvsld.mcp``: run the MCP server over stdio."""

import sys

from pvsld.mcp.server import main

if __name__ == "__main__":
    sys.exit(main())
