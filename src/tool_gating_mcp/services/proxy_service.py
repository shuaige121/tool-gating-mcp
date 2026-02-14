"""Proxy service for tool routing and backend execution forwarding."""

import json
from dataclasses import dataclass
from typing import Any

from ..models.tool import Tool
from .mcp_client_manager import MCPClientManager
from .repository import InMemoryToolRepository


@dataclass(frozen=True)
class ToolRoute:
    server_name: str
    tool_name: str


class ProxyService:
    """Route tool calls to the right backend MCP server."""

    def __init__(
        self, client_manager: MCPClientManager, tool_repository: InMemoryToolRepository
    ) -> None:
        self.client_manager = client_manager
        self.tool_repository = tool_repository
        self.provisioned_tools: set[str] = set()
        self._routes: dict[str, ToolRoute] = {}

    async def discover_all_tools(self) -> int:
        """Discover and index tools from all connected backend servers."""
        discovered_count = 0
        for server_name in self.client_manager.server_tools:
            discovered_count += await self.discover_server_tools(server_name)
        return discovered_count

    async def discover_server_tools(self, server_name: str) -> int:
        """Discover and index tools from one backend server."""
        tools = self.client_manager.server_tools.get(server_name, [])
        registered_count = 0

        for raw_tool in tools:
            tool_name = self._get_field(raw_tool, "name", "unknown")
            if not tool_name:
                continue
            raw_description = self._get_field(raw_tool, "description")
            if raw_description is None:
                continue
            description = str(raw_description)

            tool_obj = Tool(
                id=f"{server_name}_{tool_name}",
                name=tool_name,
                description=description,
                parameters=(
                    self._get_field(raw_tool, "inputSchema")
                    or self._get_field(raw_tool, "parameters")
                    or {}
                ),
                server=server_name,
                tags=self._extract_tags(description),
                estimated_tokens=self._estimate_tokens(raw_tool),
            )
            await self.tool_repository.add_tool(tool_obj)
            self._routes[tool_obj.id] = ToolRoute(
                server_name=server_name, tool_name=tool_name
            )
            registered_count += 1

        return registered_count

    def provision_tool(self, tool_id: str) -> None:
        self.provisioned_tools.add(tool_id)

    def unprovision_tool(self, tool_id: str) -> None:
        self.provisioned_tools.discard(tool_id)

    def is_provisioned(self, tool_id: str) -> bool:
        return tool_id in self.provisioned_tools

    async def get_tool_execution_info(
        self, tool_id: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        tool = self.tool_repository.get_tool(tool_id)
        if not tool:
            raise ValueError(f"Tool {tool_id} not found")

        return {
            "tool_name": tool.name,
            "server": tool.server,
            "description": tool.description,
            "action_summary": self._generate_action_summary(tool, arguments),
            "estimated_tokens": tool.estimated_tokens,
            "tags": tool.tags,
        }

    async def execute_tool(self, tool_id: str, arguments: dict[str, Any]) -> Any:
        """Execute a tool by routing it to the owning backend MCP server."""
        route = self._routes.get(tool_id)
        tool = self.tool_repository.get_tool(tool_id)

        if route is None:
            if tool is None:
                raise ValueError(f"Tool {tool_id} not found in repository")
            if not tool.server:
                raise ValueError(f"Tool {tool_id} has no backend server mapping")
            route = ToolRoute(server_name=tool.server, tool_name=tool.name)
            self._routes[tool_id] = route

        result = await self.client_manager.execute_tool(
            route.server_name, route.tool_name, arguments
        )
        if tool is not None:
            await self.tool_repository.increment_usage(tool.id)
        return result

    def _generate_action_summary(self, tool: Tool, arguments: dict[str, Any]) -> str:
        tool_name = tool.name.lower()
        if "search" in tool_name:
            query = arguments.get("query", "")
            return f"Will search for '{query}'"
        if "screenshot" in tool_name:
            name = arguments.get("name", "screenshot")
            return f"Will capture screenshot '{name}'"
        if "write" in tool_name:
            title = arguments.get("title", "note")
            return f"Will write note '{title}'"
        if "research" in tool_name:
            target = arguments.get("query", "target")
            return f"Will research '{target}'"
        return f"Will execute {tool.name} with provided arguments"

    def _extract_tags(self, description: str | None) -> list[str]:
        if not description:
            return []

        tags = []
        keywords = ["search", "web", "browser", "file", "code", "api", "data"]
        desc_lower = description.lower()

        for keyword in keywords:
            if keyword in desc_lower:
                tags.append(keyword)
        if "screenshot" in desc_lower:
            tags.append("screenshot")
        if "navigate" in desc_lower or "navigation" in desc_lower:
            tags.append("navigation")
        if "read" in desc_lower:
            tags.append("read")
        if "write" in desc_lower:
            tags.append("write")
        if "documentation" in desc_lower or "docs" in desc_lower:
            tags.append("documentation")

        return sorted(set(tags))

    def _estimate_tokens(self, tool: Any) -> int:
        description = self._get_field(tool, "description", "") or ""
        schema = (
            self._get_field(tool, "inputSchema")
            or self._get_field(tool, "parameters")
            or {}
        )
        desc_tokens = len(description.split()) * 1.3
        schema_tokens = len(json.dumps(schema, ensure_ascii=True)) / 4
        return int(desc_tokens + schema_tokens + 50)

    def _get_field(self, source: Any, field: str, default: Any = None) -> Any:
        if isinstance(source, dict):
            return source.get(field, default)
        return getattr(source, field, default)
