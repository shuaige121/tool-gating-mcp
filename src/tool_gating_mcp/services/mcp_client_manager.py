"""MCP client manager for backend stdio MCP servers."""

import asyncio
import logging
from contextlib import AsyncExitStack
from typing import Any

try:
    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    HAS_MCP_SDK = True
except ImportError:
    ClientSession = Any  # type: ignore[misc,assignment]
    StdioServerParameters = Any  # type: ignore[misc,assignment]
    stdio_client = None
    HAS_MCP_SDK = False

logger = logging.getLogger(__name__)


class MCPClientManager:
    """Manage persistent stdio MCP sessions for backend servers."""

    def __init__(self) -> None:
        self.sessions: dict[str, ClientSession] = {}
        self.server_tools: dict[str, list[Any]] = {}
        self._server_info: dict[str, dict[str, Any]] = {}
        self._connection_stacks: dict[str, AsyncExitStack] = {}
        self._lock = asyncio.Lock()

    async def connect_server(self, name: str, config: dict[str, Any]) -> None:
        """Connect to a backend MCP server and cache its tools."""
        async with self._lock:
            if name in self.sessions:
                return

            self._server_info[name] = {"config": config, "connected": False}

            if not HAS_MCP_SDK or stdio_client is None:
                logger.warning(
                    "MCP SDK unavailable, running in mock mode for server '%s'", name
                )
                self.server_tools[name] = self._mock_tools_for(name)
                self._server_info[name].update(
                    {
                        "connected": False,
                        "reason": "MCP SDK not available (mock mode)",
                        "tools_discovered": len(self.server_tools[name]),
                    }
                )
                return

            stack = AsyncExitStack()
            try:
                server_params = StdioServerParameters(
                    command=config["command"],
                    args=config.get("args", []),
                    env=config.get("env", {}),
                )
                read_stream, write_stream = await stack.enter_async_context(
                    stdio_client(server_params)
                )
                session = await stack.enter_async_context(
                    ClientSession(read_stream, write_stream)
                )
                await session.initialize()

                tools = await self._list_session_tools(session)
                self.sessions[name] = session
                self._connection_stacks[name] = stack
                self.server_tools[name] = tools
                self._server_info[name].update(
                    {
                        "connected": True,
                        "tools_discovered": len(tools),
                    }
                )
                logger.info("Connected to '%s' with %d tools", name, len(tools))
            except Exception as exc:
                await stack.aclose()
                self.server_tools[name] = []
                self._server_info[name].update({"connected": False, "error": str(exc)})
                raise RuntimeError(f"Failed to connect server '{name}': {exc}") from exc

    async def refresh_server_tools(self, name: str) -> list[Any]:
        """Refresh cached tool list for a connected server."""
        session = self.sessions.get(name)
        if session is None:
            raise ValueError(f"Server '{name}' is not connected")

        tools = await self._list_session_tools(session)
        self.server_tools[name] = tools
        server_info = self._server_info.get(name, {})
        server_info["tools_discovered"] = len(tools)
        self._server_info[name] = server_info
        return tools

    async def execute_tool(
        self, server_name: str, tool_name: str, arguments: dict[str, Any]
    ) -> Any:
        """Execute a tool through an existing backend session."""
        session = self.sessions.get(server_name)
        if session is None:
            if server_name not in self._server_info:
                raise ValueError(f"Server '{server_name}' is not registered")
            await self.connect_server(
                server_name,
                self._server_info[server_name]["config"],
            )
            session = self.sessions.get(server_name)
            if session is None:
                raise RuntimeError(f"Server '{server_name}' is unavailable")

        result = await session.call_tool(tool_name, arguments or {})
        if hasattr(result, "model_dump"):
            return result.model_dump(mode="json", exclude_none=True)
        return result

    async def disconnect_all(self) -> None:
        """Disconnect all backend servers."""
        for name in list(self._server_info.keys()):
            await self.disconnect_server(name)

    async def disconnect_server(self, name: str) -> None:
        """Disconnect one backend server and release resources."""
        stack = self._connection_stacks.pop(name, None)
        if stack is not None:
            await stack.aclose()

        self.sessions.pop(name, None)
        self.server_tools.pop(name, None)
        if name in self._server_info:
            self._server_info[name]["connected"] = False

    async def _list_session_tools(self, session: ClientSession) -> list[Any]:
        tools_response = await session.list_tools()
        return list(getattr(tools_response, "tools", []))

    def _mock_tools_for(self, name: str) -> list[Any]:
        if name != "context7":
            return []

        return [
            type(
                "MockTool",
                (),
                {
                    "name": "resolve-library-id",
                    "description": (
                        "Resolves package/product name to "
                        "Context7-compatible library ID"
                    ),
                    "inputSchema": {
                        "type": "object",
                        "properties": {"libraryName": {"type": "string"}},
                    },
                },
            )(),
            type(
                "MockTool",
                (),
                {
                    "name": "get-library-docs",
                    "description": "Fetches up-to-date docs for a library",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "context7CompatibleLibraryID": {"type": "string"}
                        },
                    },
                },
            )(),
        ]
