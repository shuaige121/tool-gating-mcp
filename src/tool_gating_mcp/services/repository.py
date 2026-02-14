# Tool repository
# In-memory implementation of tool storage


from ..models.tool import Tool


class InMemoryToolRepository:
    """In-memory implementation of tool repository."""

    def __init__(self) -> None:
        """Initialize empty repository."""
        self._tools: dict[str, Tool] = {}
        self._usage_counts: dict[str, int] = {}

    async def get_all(self) -> list[Tool]:
        """Get all tools in the repository."""
        return list(self._tools.values())

    async def get_all_tools(self) -> list[Tool]:
        """Backward-compatible alias used by legacy tests/helpers."""
        return await self.get_all()

    async def get_by_ids(self, tool_ids: list[str]) -> list[Tool]:
        """Get tools by their IDs."""
        return [self._tools[tool_id] for tool_id in tool_ids if tool_id in self._tools]

    async def get_popular(self, limit: int = 10) -> list[Tool]:
        """Get most popular tools based on usage."""
        # Sort tools by usage count
        sorted_tools = sorted(
            self._tools.items(),
            key=lambda x: self._usage_counts.get(x[0], 0),
            reverse=True,
        )
        return [tool for _, tool in sorted_tools[:limit]]

    async def add_tool(self, tool: Tool) -> None:
        """Add a tool to the repository."""
        self._tools[tool.id] = tool
        if tool.id not in self._usage_counts:
            self._usage_counts[tool.id] = 0

    async def remove_tool(self, tool_id: str) -> None:
        """Remove a tool from the repository."""
        if tool_id in self._tools:
            del self._tools[tool_id]
            if tool_id in self._usage_counts:
                del self._usage_counts[tool_id]

    async def increment_usage(self, tool_id: str) -> None:
        """Increment usage count for a tool."""
        if tool_id in self._tools:
            self._usage_counts[tool_id] = self._usage_counts.get(tool_id, 0) + 1

    # Sync helper methods for testing
    def add_tool_sync(self, tool: Tool) -> None:
        """Add a tool to the repository (sync version)."""
        self._tools[tool.id] = tool
        if tool.id not in self._usage_counts:
            self._usage_counts[tool.id] = 0

    def get_tool(self, tool_id: str) -> Tool | None:
        """Get a tool by ID (sync version)."""
        return self._tools.get(tool_id)

    def list_all_tools(self) -> list[Tool]:
        """Get all tools (sync version)."""
        return list(self._tools.values())

    async def populate_demo_tools(self) -> None:
        """Populate repository with demo tools."""
        demo_tools = [
            Tool(
                id="calculator",
                name="Calculator",
                description="Perform mathematical calculations and solve equations",
                tags=["math", "calculation", "arithmetic"],
                estimated_tokens=50,
                parameters={
                    "type": "object",
                    "properties": {
                        "expression": {
                            "type": "string",
                            "description": "Mathematical expression to evaluate",
                        }
                    },
                    "required": ["expression"],
                },
            ),
            Tool(
                id="web-search",
                name="Web Search",
                description="Search the web for information and retrieve results",
                tags=["search", "web", "internet", "query"],
                estimated_tokens=100,
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "num_results": {
                            "type": "integer",
                            "description": "Number of results to return",
                            "default": 10,
                        },
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                id="file-reader",
                name="File Reader",
                description="Read and parse files from the filesystem",
                tags=["file", "io", "read", "filesystem"],
                estimated_tokens=75,
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path to read"},
                        "encoding": {
                            "type": "string",
                            "description": "File encoding",
                            "default": "utf-8",
                        },
                    },
                    "required": ["path"],
                },
            ),
            Tool(
                id="code-executor",
                name="Code Executor",
                description="Execute code snippets in various programming languages",
                tags=["code", "programming", "execution", "interpreter"],
                estimated_tokens=150,
                parameters={
                    "type": "object",
                    "properties": {
                        "code": {"type": "string", "description": "Code to execute"},
                        "language": {
                            "type": "string",
                            "description": "Programming language",
                            "enum": ["python", "javascript", "bash"],
                        },
                    },
                    "required": ["code", "language"],
                },
            ),
            Tool(
                id="weather-api",
                name="Weather API",
                description="Get current weather and forecasts for any location",
                tags=["weather", "api", "forecast", "temperature"],
                estimated_tokens=80,
                parameters={
                    "type": "object",
                    "properties": {
                        "location": {
                            "type": "string",
                            "description": "City name or coordinates",
                        },
                        "units": {
                            "type": "string",
                            "description": "Temperature units",
                            "enum": ["celsius", "fahrenheit"],
                            "default": "celsius",
                        },
                    },
                    "required": ["location"],
                },
            ),
        ]

        for tool in demo_tools:
            await self.add_tool(tool)
