"""
Runtime compartilhado entre CLI, API HTTP e futuros workers.
"""

from __future__ import annotations

import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "mcp_server"))

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config_loader import load_config
from prompts import build_system_prompt
from session import Session
from renderer import configure_interface
from core import build_tools_spec, run_turn, startup


ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.yaml"


class AgentRuntime:
    def __init__(self, config: dict, mcp_session, tools_spec: list, schema: dict):
        self.config = config
        self.mcp_session = mcp_session
        self.tools_spec = tools_spec
        self.schema = schema
        self.agent_cfg = config.get("agent", {})
        self.session_cfg = self.agent_cfg.get("session", {})
        self.system_prompt = build_system_prompt(config, schema)

    def new_session(self) -> Session:
        session = Session(max_history=self.session_cfg.get("max_history_messages", 20))
        session.set_system_prompt(self.system_prompt)
        return session

    async def ask(self, question: str, session: Session | None = None) -> str:
        local_session = session or self.new_session()
        return await run_turn(
            config=self.config,
            session=local_session,
            mcp_session=self.mcp_session,
            tools=self.tools_spec,
            user_input=question,
            schema=self.schema,
        )


def build_server_params() -> StdioServerParameters:
    mcp_path = ROOT / "mcp_server" / "main.py"
    return StdioServerParameters(
        command="python3",
        args=[str(mcp_path)],
        env={
            **os.environ,
            "PYTHONPATH": str(mcp_path.parent),
            "PYTHONUNBUFFERED": "1",
        },
    )


@asynccontextmanager
async def open_agent_runtime(config_path: str | None = None):
    loaded_config = load_config(str(Path(config_path) if config_path else CONFIG_PATH))
    interface_cfg = loaded_config.get("agent", {}).get("interface", {})
    configure_interface(interface_cfg, loaded_config)

    server_params = build_server_params()
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as mcp_session:
            await mcp_session.initialize()
            mcp_tools = await mcp_session.list_tools()
            tools_spec = build_tools_spec(mcp_tools.tools)
            schema = await startup(mcp_session)
            if "error" in schema:
                raise RuntimeError(f"Erro ao carregar schema: {schema['error']}")
            yield AgentRuntime(loaded_config, mcp_session, tools_spec, schema)
