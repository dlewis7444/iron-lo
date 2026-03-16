#!/usr/bin/env bash
set -e

# Check if already registered
if claude mcp list 2>/dev/null | grep -q "^iron-lo:"; then
    echo "iron-lo is already registered as an MCP server."
    echo "To reinstall, remove it first:"
    echo ""
    echo "  claude mcp remove iron-lo"
    echo ""
    echo "Then re-run this script."
    exit 1
fi

python3 -m venv .venv
.venv/bin/pip install .
claude mcp add --scope user iron-lo -- "$(pwd)/.venv/bin/python3" "$(pwd)/mcp_server.py"

echo ""
echo "Done. Restart Claude Code to activate iron-lo."
