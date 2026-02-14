# Essential Tool API - Core functionality for AI agents
# Includes discovery, registration, and management

import inspect
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from ..api.models import (
    MCPToolDefinition,
    ToolDiscoveryRequest,
    ToolDiscoveryResponse,
    ToolMatchResponse,
    ToolProvisionRequest,
    ToolProvisionResponse,
)
from ..models.tool import Tool
from ..services.discovery import DiscoveryService
from ..services.gating import GatingService
from ..services.repository import InMemoryToolRepository

router = APIRouter(prefix="/api/tools", tags=["tools"])
_tool_repository: InMemoryToolRepository | None = None
_discovery_service: DiscoveryService | None = None
_discovery_repo_id: int | None = None


async def get_tool_repository() -> Any:
    """Get tool repository from app state (initialized in lifespan)."""
    global _tool_repository
    from ..main import app
    if hasattr(app.state, "proxy_service"):
        return app.state.proxy_service.tool_repository
    if hasattr(app.state, "tool_repository"):
        return app.state.tool_repository
    if _tool_repository is None:
        _tool_repository = InMemoryToolRepository()
    return _tool_repository


# Dependency injection for services
async def get_discovery_service() -> DiscoveryService:
    """Get discovery service instance."""
    global _discovery_repo_id
    global _discovery_service

    try:
        repo = await get_tool_repository()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    repo_id = id(repo)
    if _discovery_service is None or _discovery_repo_id != repo_id:
        _discovery_service = DiscoveryService(tool_repo=repo)
        _discovery_repo_id = repo_id
    return _discovery_service


async def get_gating_service() -> GatingService:
    """Get gating service instance."""
    try:
        repo = await get_tool_repository()
        return GatingService(tool_repo=repo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/discover",
    response_model=ToolDiscoveryResponse,
    operation_id="discover_tools",
)
async def discover_tools(
    request: ToolDiscoveryRequest,
    discovery_service: DiscoveryService = Depends(get_discovery_service),  # noqa: B008
) -> ToolDiscoveryResponse:
    """Discover relevant tools based on query and context."""
    try:
        if request.limit is None:
            top_k = 1000
        else:
            top_k = min(request.limit, 10)

        tools = await discovery_service.search_tools(
            query=request.query,
            tags=request.tags,
            top_k=top_k,
        )

        tool_matches = [
            ToolMatchResponse(
                tool_id=match.tool.id,
                name=match.tool.name,
                description=match.tool.description,
                score=match.score,
                matched_tags=match.matched_tags,
                estimated_tokens=match.tool.estimated_tokens,
                server=match.tool.server,
            )
            for match in tools
        ]
        return ToolDiscoveryResponse(
            tools=tool_matches,
            query_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post(
    "/provision",
    response_model=ToolProvisionResponse,
    operation_id="provision_tools",
)
async def provision_tools(
    request: ToolProvisionRequest,
    gating_service: GatingService = Depends(get_gating_service),  # noqa: B008
) -> ToolProvisionResponse:
    """Provision tools from the shared repository with gating constraints."""
    selected_tools = await gating_service.select_tools(
        tool_ids=request.tool_ids,
        max_tools=request.max_tools,
    )

    mcp_tools = [
        MCPToolDefinition(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters or {"type": "object"},
            token_count=tool.estimated_tokens,
            server=tool.server,
        )
        for tool in selected_tools
    ]
    total_tokens = sum(tool.token_count for tool in mcp_tools)

    return ToolProvisionResponse(
        tools=mcp_tools,
        metadata={
            "total_tokens": total_tokens,
            "total_tools": len(mcp_tools),
            "gating_applied": True,
        },
    )


@router.post("/register", operation_id="register_tool")
async def register_tool(tool: Tool) -> dict[str, str]:
    """Register a new tool in the system.

    Essential for AI agents to add tools discovered from MCP servers
    or custom tools defined by users.
    """
    try:
        tool_repo = await get_tool_repository()
        await tool_repo.add_tool(tool)
        return {"status": "success", "tool_id": tool.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/clear", operation_id="clear_tools")
async def clear_tools() -> dict[str, str]:
    """Clear all tools from the repository.

    Useful for administrative cleanup and testing scenarios.
    """
    try:
        tool_repo = await get_tool_repository()
        if hasattr(tool_repo, "_tools"):
            clear_result = tool_repo._tools.clear()
            if inspect.isawaitable(clear_result):
                await clear_result
        if hasattr(tool_repo, "_usage_counts"):
            usage_clear_result = tool_repo._usage_counts.clear()
            if inspect.isawaitable(usage_clear_result):
                await usage_clear_result
        return {"status": "success", "message": "All tools cleared"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


# Note: Tool execution happens via the proxy API (/api/proxy/execute).
# Server management happens via simplified `/api/mcp/add_server`.
