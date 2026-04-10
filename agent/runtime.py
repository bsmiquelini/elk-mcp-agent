"""
Runtime compartilhado entre CLI, API HTTP e futuros workers.
"""

from __future__ import annotations

import os
import sys
import threading
import asyncio
import time
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
_SCHEMA_CACHE: dict[str, tuple[float, dict]] = {}


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

    async def ask(
        self,
        question: str,
        session: Session | None = None,
        *,
        return_details: bool = False,
        emit_console: bool = False,
    ) -> str | dict:
        local_session = session or self.new_session()
        return await run_turn(
            config=self.config,
            session=local_session,
            mcp_session=self.mcp_session,
            tools=self.tools_spec,
            user_input=question,
            schema=self.schema,
            emit_console=emit_console,
            return_details=return_details,
        )


class AgentRuntimeWorker:
    def __init__(self, config_path: str | None = None):
        self.config_path = str(Path(config_path) if config_path else CONFIG_PATH)
        self.loop = None
        self.thread = None
        self.runtime = None
        self.context = None
        self.ready = threading.Event()
        self.failed = None
        self.run_lock = threading.Lock()

    def start(self):
        self.thread = threading.Thread(target=self._run, name="agent-runtime", daemon=True)
        self.thread.start()
        self.ready.wait(timeout=30)
        if self.failed:
            raise self.failed
        if not self.runtime:
            raise RuntimeError("Runtime do agente não ficou pronto.")

    def _run(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._startup())
        except Exception as exc:
            self.failed = exc
            self.ready.set()
            return
        self.ready.set()
        self.loop.run_forever()
        self.loop.run_until_complete(self._shutdown())
        self.loop.close()

    async def _startup(self):
        self.context = open_agent_runtime(self.config_path)
        self.runtime = await self.context.__aenter__()

    async def _shutdown(self):
        if self.context is not None:
            await self.context.__aexit__(None, None, None)

    def run(self, coro, *, timeout: int = 180):
        if not self.loop or not self.runtime:
            raise RuntimeError("Runtime do agente indisponível.")
        with self.run_lock:
            future = asyncio.run_coroutine_threadsafe(coro, self.loop)
            return future.result(timeout=timeout)

    def ask(self, question: str, *, return_details: bool = False, emit_console: bool = False, timeout: int = 180):
        return self.run(
            self.runtime.ask(
                question,
                return_details=return_details,
                emit_console=emit_console,
            ),
            timeout=timeout,
        )

    def stop(self):
        if not self.loop:
            return
        self.loop.call_soon_threadsafe(self.loop.stop)
        if self.thread:
            self.thread.join(timeout=10)


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


def _schema_cache_key(config_path: str | None) -> str:
    return str(Path(config_path) if config_path else CONFIG_PATH)


def _load_cached_schema(config: dict, config_path: str | None) -> dict | None:
    cache_cfg = config.get("agent", {}).get("runtime", {})
    ttl = int(cache_cfg.get("schema_cache_ttl_seconds", 300) or 0)
    if ttl <= 0:
        return None

    cached = _SCHEMA_CACHE.get(_schema_cache_key(config_path))
    if not cached:
        return None

    expires_at, schema = cached
    if expires_at < time.time():
        _SCHEMA_CACHE.pop(_schema_cache_key(config_path), None)
        return None
    return schema


def _store_cached_schema(config: dict, config_path: str | None, schema: dict):
    cache_cfg = config.get("agent", {}).get("runtime", {})
    ttl = int(cache_cfg.get("schema_cache_ttl_seconds", 300) or 0)
    if ttl <= 0:
        return
    _SCHEMA_CACHE[_schema_cache_key(config_path)] = (time.time() + ttl, schema)


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
            schema = _load_cached_schema(loaded_config, config_path)
            if schema is None:
                schema = await startup(mcp_session)
                _store_cached_schema(loaded_config, config_path, schema)
            if "error" in schema:
                raise RuntimeError(f"Erro ao carregar schema: {schema['error']}")
            yield AgentRuntime(loaded_config, mcp_session, tools_spec, schema)
