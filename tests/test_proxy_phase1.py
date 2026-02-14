"""Phase 1.1 proxy tests: client manager, proxy routing, and startup discovery."""

import importlib
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

main_module = importlib.import_module("tool_gating_mcp.main")
from tool_gating_mcp.api.proxy import ExecuteToolRequest, execute_tool
from tool_gating_mcp.services.gating import GatingService
from tool_gating_mcp.services.mcp_client_manager import MCPClientManager
from tool_gating_mcp.services.proxy_service import ProxyService
from tool_gating_mcp.services.repository import InMemoryToolRepository


class _FakeCallToolResult:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def model_dump(
        self,
        mode: str = "python",
        exclude_none: bool = False,
    ) -> dict[str, Any]:
        del mode, exclude_none
        return self._payload


class _FakeStdioContext:
    def __init__(self, counters: dict[str, int]) -> None:
        self._counters = counters

    async def __aenter__(self) -> tuple[str, str]:
        self._counters["stdio_enter"] += 1
        return ("read_stream", "write_stream")

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self._counters["stdio_exit"] += 1
        return None


class _FakeClientSession:
    def __init__(
        self,
        read_stream: str,
        write_stream: str,
        counters: dict[str, int],
    ) -> None:
        del read_stream, write_stream
        self._counters = counters

    async def __aenter__(self) -> "_FakeClientSession":
        self._counters["session_enter"] += 1
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        self._counters["session_exit"] += 1
        return None

    async def initialize(self) -> None:
        self._counters["initialize"] += 1

    async def list_tools(self) -> Any:
        self._counters["list_tools"] += 1
        return SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="sum_numbers",
                    description="Add two numbers",
                    inputSchema={"type": "object"},
                )
            ]
        )

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any],
    ) -> _FakeCallToolResult:
        self._counters["call_tool"] += 1
        return _FakeCallToolResult(
            {
                "content": [{"type": "text", "text": f"{name}:{arguments}"}],
                "isError": False,
            }
        )


@pytest.mark.asyncio
async def test_client_manager_keeps_persistent_stdio_session(
    monkeypatch: pytest.MonkeyPatch,
):
    counters = {
        "stdio_enter": 0,
        "stdio_exit": 0,
        "session_enter": 0,
        "session_exit": 0,
        "initialize": 0,
        "list_tools": 0,
        "call_tool": 0,
    }

    from tool_gating_mcp.services import mcp_client_manager as manager_module

    monkeypatch.setattr(manager_module, "HAS_MCP_SDK", True)
    monkeypatch.setattr(
        manager_module,
        "StdioServerParameters",
        lambda **kwargs: kwargs,
    )
    monkeypatch.setattr(
        manager_module,
        "stdio_client",
        lambda params: _FakeStdioContext(counters),  # noqa: ARG005
    )
    monkeypatch.setattr(
        manager_module,
        "ClientSession",
        lambda read_stream, write_stream: _FakeClientSession(
            read_stream,
            write_stream,
            counters,
        ),
    )

    manager = MCPClientManager()
    await manager.connect_server("math", {"command": "fake"})
    assert "math" in manager.sessions
    assert len(manager.server_tools["math"]) == 1
    assert counters["initialize"] == 1
    assert counters["list_tools"] == 1

    result_1 = await manager.execute_tool("math", "sum_numbers", {"a": 1, "b": 2})
    result_2 = await manager.execute_tool("math", "sum_numbers", {"a": 3, "b": 4})
    assert result_1["isError"] is False
    assert result_2["isError"] is False
    assert counters["call_tool"] == 2
    assert counters["stdio_enter"] == 1
    assert counters["session_enter"] == 1

    await manager.disconnect_all()
    assert counters["stdio_exit"] == 1
    assert counters["session_exit"] == 1


@pytest.mark.asyncio
async def test_proxy_service_discovers_tools_and_routes_execution():
    repository = InMemoryToolRepository()
    manager = SimpleNamespace(
        server_tools={
            "math": [
                SimpleNamespace(
                    name="sum_numbers",
                    description="Add two numbers",
                    inputSchema={"type": "object"},
                )
            ]
        },
        execute_tool=AsyncMock(
            return_value={"content": [{"type": "text", "text": "3"}]}
        ),
    )
    proxy_service = ProxyService(manager, repository)

    discovered = await proxy_service.discover_all_tools()
    assert discovered == 1
    assert repository.get_tool("math_sum_numbers") is not None

    result = await proxy_service.execute_tool("math_sum_numbers", {"a": 1, "b": 2})
    assert result["content"][0]["text"] == "3"
    manager.execute_tool.assert_awaited_once_with(
        "math",
        "sum_numbers",
        {"a": 1, "b": 2},
    )
    assert repository._usage_counts["math_sum_numbers"] == 1


@pytest.mark.asyncio
async def test_proxy_discovered_tools_are_available_to_gating_service():
    repository = InMemoryToolRepository()
    manager = SimpleNamespace(
        server_tools={
            "data": [
                SimpleNamespace(
                    name="fetch_report",
                    description="Fetch report data",
                    inputSchema={"type": "object"},
                )
            ]
        },
        execute_tool=AsyncMock(return_value={"ok": True}),
    )
    proxy_service = ProxyService(manager, repository)
    await proxy_service.discover_all_tools()

    gating_service = GatingService(tool_repo=repository)
    selected_tools = await gating_service.select_tools(tool_ids=["data_fetch_report"])

    assert len(selected_tools) == 1
    assert selected_tools[0].id == "data_fetch_report"


@pytest.mark.asyncio
async def test_execute_tool_endpoint_transparently_returns_proxy_result():
    proxy_service = AsyncMock()
    proxy_service.execute_tool.return_value = {
        "content": [{"type": "text", "text": "ok"}],
        "isError": False,
    }
    request = ExecuteToolRequest(tool_id="math_sum_numbers", arguments={"a": 1, "b": 2})

    response = await execute_tool(request=request, proxy_service=proxy_service)

    proxy_service.execute_tool.assert_awaited_once_with(
        "math_sum_numbers",
        {"a": 1, "b": 2},
    )
    assert response.result["isError"] is False


@pytest.mark.asyncio
async def test_lifespan_connects_servers_and_discovers_backend_tools(
    monkeypatch: pytest.MonkeyPatch,
):
    class _FakeClientManager:
        def __init__(self) -> None:
            self.connected_servers: list[str] = []
            self.disconnected = False
            self.server_tools: dict[str, list[Any]] = {
                "server_a": [
                    SimpleNamespace(name="tool_a", description="", inputSchema={})
                ],
                "server_b": [
                    SimpleNamespace(name="tool_b", description="", inputSchema={})
                ],
            }

        async def connect_server(self, name: str, config: dict[str, Any]) -> None:
            del config
            self.connected_servers.append(name)

        async def disconnect_all(self) -> None:
            self.disconnected = True

    class _FakeProxyService:
        def __init__(self, client_manager: Any, tool_repository: Any) -> None:
            self.client_manager = client_manager
            self.tool_repository = tool_repository
            self.discovery_called = False

        async def discover_all_tools(self) -> int:
            self.discovery_called = True
            return 2

    monkeypatch.setattr(
        main_module,
        "MCP_SERVERS",
        {
            "server_a": {"command": "a"},
            "server_b": {"command": "b"},
        },
    )
    monkeypatch.setattr(main_module, "MCPClientManager", _FakeClientManager)
    monkeypatch.setattr(main_module, "ProxyService", _FakeProxyService)

    async with main_module.lifespan(main_module.app):
        assert sorted(main_module.app.state.client_manager.connected_servers) == [
            "server_a",
            "server_b",
        ]
        assert main_module.app.state.proxy_service.discovery_called is True
        assert hasattr(main_module.app.state, "tool_repository")

    assert main_module.app.state.client_manager.disconnected is True
