"""MCP Server Configuration Models"""

from typing import Any

from pydantic import BaseModel, Field


class MCPServerConfig(BaseModel):
    """Configuration for an MCP server"""

    command: str = Field(..., description="Command to run the MCP server")
    args: list[str] = Field(default_factory=list, description="Command arguments")
    env: dict[str, str] = Field(
        default_factory=dict, description="Environment variables"
    )

    model_config = {
        "extra": "allow",
    }  # Allow additional fields for future compatibility


class MCPServerRegistration(BaseModel):
    """Registration request for a new MCP server"""

    name: str = Field(..., description="Unique name for the MCP server")
    config: MCPServerConfig = Field(..., description="Server configuration")
    description: str | None = Field(None, description="Human-readable description")
    estimated_tools: int | None = Field(
        None, description="Estimated number of tools"
    )


class MCPToolDiscoveryRequest(BaseModel):
    """Request to discover tools from an MCP server configuration"""

    server_name: str = Field(..., description="Name of the MCP server")
    config: MCPServerConfig = Field(..., description="Server configuration to test")
    auto_register: bool = Field(
        True, description="Automatically register discovered tools"
    )


class MCPServerInfo(BaseModel):
    """Information about a registered MCP server"""

    name: str
    description: str | None
    tool_count: int
    total_tokens: int
    tags: list[str]


class AnthropicMCPConfig(BaseModel):
    """Configuration for using MCP via Anthropic API"""

    api_key: str = Field(..., description="Anthropic API key")
    mcp_servers: list[dict[str, Any]] = Field(
        default_factory=list, description="MCP servers to connect via API"
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "api_key": "sk-ant-...",
                "mcp_servers": [
                    {
                        "name": "github",
                        "type": "url",
                        "url": "https://github-mcp.example.com",
                        "authorization_token": "optional-token",
                    }
                ],
            }
        }
    }


class MCPToolSchema(BaseModel):
    """Schema for a tool discovered from an MCP server"""

    name: str
    description: str
    inputSchema: dict[str, Any]  # noqa: N815

    def to_internal_tool(self, server_name: str) -> dict[str, Any]:
        """Convert MCP tool to internal tool format"""
        # Extract tags from description
        tags = []
        description_lower = self.description.lower()

        # Common action tags
        for action in [
            "search",
            "create",
            "update",
            "delete",
            "list",
            "get",
            "send",
            "upload",
        ]:
            if action in description_lower:
                tags.append(action)

        # Estimate tokens
        base_tokens = 50
        desc_tokens = len(self.description) // 4
        param_tokens = len(str(self.inputSchema)) // 4
        estimated_tokens = base_tokens + desc_tokens + param_tokens + 20

        return {
            "id": f"{server_name}_{self.name}",
            "name": self.name,
            "description": self.description,
            "parameters": self.inputSchema,
            "estimated_tokens": estimated_tokens,
            "tags": tags,
            "server": server_name,
        }
