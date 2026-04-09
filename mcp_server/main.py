"""
MCP Server — ELK Pipeline Intelligence
Expõe 4 tools genéricas e schema-agnósticas para o agente.
"""

import asyncio
import json
import sys
from pathlib import Path

from mcp.server       import Server
from mcp.server.stdio import stdio_server
from mcp.types        import TextContent

sys.path.insert(0, str(Path(__file__).parent))

from config_loader import load_config
from tool_catalog import build_handlers, list_tool_specs

config = load_config()
server = Server("elk-pipeline-intelligence")
handlers = build_handlers(config)


@server.list_tools()
async def handle_list_tools():
    return list_tool_specs()


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name not in handlers:
        return [TextContent(type="text", text=json.dumps({"error": f"Tool '{name}' não encontrada"}))]

    try:
        result = handlers[name](arguments)
        return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]
    except Exception as e:
        return [TextContent(type="text", text=json.dumps({"error": str(e)}))]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
