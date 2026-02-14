# FastAPI application entry point
# Defines the main app instance and core routes

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi_mcp import FastApiMCP
from pydantic import BaseModel

from .api import mcp, proxy, tools
from .config import MCP_SERVERS
from .services.mcp_client_manager import MCPClientManager
from .services.proxy_service import ProxyService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    message: str


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown."""
    logger.info("Starting Tool Gating MCP Proxy...")

    try:
        client_manager = MCPClientManager()
        from .services.repository import InMemoryToolRepository

        tool_repository = InMemoryToolRepository()
        proxy_service = ProxyService(client_manager, tool_repository)

        logger.info("Connecting to MCP servers...")
        for server_name, config in MCP_SERVERS.items():
            try:
                logger.info(
                    "Connecting to %s: %s",
                    server_name,
                    config.get("description", "No description"),
                )
                await client_manager.connect_server(server_name, config)
                logger.info("Successfully connected to %s", server_name)
            except Exception as e:
                logger.error("Failed to connect to %s: %s", server_name, e)

        discovered_count = await proxy_service.discover_all_tools()
        logger.info("Discovered %d backend tools during startup", discovered_count)

        app.state.client_manager = client_manager
        app.state.tool_repository = tool_repository
        app.state.proxy_service = proxy_service

        logger.info("Proxy initialization complete")

    except Exception as e:
        logger.error(f"Startup failed: {e}")
        raise

    yield

    logger.info("Shutting down Tool Gating MCP Proxy...")
    if hasattr(app.state, "client_manager"):
        await app.state.client_manager.disconnect_all()
    logger.info("Shutdown complete")


app = FastAPI(
    title="Tool Gating MCP",
    description="FastAPI application for tool gating MCP",
    version="0.2.0",
    lifespan=lifespan,
)

# Include API routers
app.include_router(tools.router)
app.include_router(mcp.router)
app.include_router(proxy.router)


@app.get("/", operation_id="root")
async def root() -> dict[str, str]:
    """Root endpoint."""
    return {"message": "Welcome to Tool Gating MCP"}


@app.get("/health", response_model=HealthResponse, operation_id="health")
async def health() -> HealthResponse:
    """Health check endpoint."""
    return HealthResponse(status="healthy", message="Service is running")


# Exclude specific operations from being exposed as MCP tools
mcp_server = FastApiMCP(
    app,
    name="tool-gating",
    description=(
        "Intelligently manage MCP tools to prevent context bloat. "
        "Discover and provision only the most relevant tools for each task."
    ),
    exclude_operations=["root", "health"],
)


# Note: Tool execution is handled by /api/proxy/execute endpoint
# This avoids duplication and keeps the API organized


# Mount the MCP server to make it available at /mcp endpoint
# This automatically calls setup_server() internally
mcp_server.mount()
