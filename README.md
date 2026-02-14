# Tool Gating MCP

An intelligent proxy/router for Model Context Protocol (MCP) that enables Claude Desktop and other MCP clients to dynamically discover and use tools from multiple MCP servers while maintaining a single connection point. This system prevents context bloat by intelligently selecting only the most relevant tools for each task.

## 🎯 The Problem

MCP clients like Claude Desktop must load all servers at startup and cannot dynamically add servers during conversations. When using multiple MCP servers:
- **Exa server**: 7 search tools (web, research papers, Twitter, companies, etc.)
- **Puppeteer**: Browser automation tools
- **Context7**: Documentation search tools
- **Desktop Commander**: 18+ desktop automation tools

Loading all servers directly leads to:
- 🚨 **Context bloat**: 100+ tools consuming most of the context window
- 🔒 **Static configuration**: Cannot add servers without restarting Claude
- 💸 **Increased costs**: More tokens consumed per request
- 🎯 **Poor tool selection**: AI struggles to choose from too many options

## 💡 The Solution

Tool Gating MCP acts as an intelligent proxy that:
1. **Single Connection**: Claude Desktop connects only to Tool Gating
2. **Backend Management**: Maintains connections to multiple MCP servers
3. **Smart Discovery**: Finds relevant tools across all servers using semantic search
4. **Dynamic Provisioning**: Loads only needed tools within token budgets
5. **Transparent Routing**: Executes tools on appropriate backend servers

**Example**: Instead of configuring 10 MCP servers with 100+ tools, configure just Tool Gating. Then dynamically discover and use only the 2-3 tools you need.

## 🚀 Features

- **Proxy Architecture**: Single MCP server that routes to multiple backend servers
- **Dynamic Tool Discovery**: Find tools across all servers without manual configuration
- **Semantic Search**: Natural language queries to find the right tools
- **Smart Provisioning**: Load only relevant tools within token budgets
- **Transparent Execution**: Route tool calls to appropriate backend servers
- **Native MCP Server**: Direct integration with Claude Desktop via mcp-proxy
- **Cross-Server Intelligence**: Unified view of tools from Puppeteer, Exa, Context7, etc.
- **Token Optimization**: 90%+ reduction in context usage vs. loading all servers
- **Zero Configuration**: Claude Desktop needs only Tool Gating configuration

## 📋 Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager

## 🔧 Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/tool-gating-mcp.git
cd tool-gating-mcp
```

2. Create and activate virtual environment:
```bash
uv venv
source .venv/bin/activate  # On Unix/macOS
# .venv\Scripts\activate  # On Windows
```

3. Install dependencies:
```bash
uv sync
```

4. Install package in development mode:
```bash
uv pip install -e .
```

## 🏃 Running the Server

### As HTTP API Server

```bash
# Start the server
tool-gating-mcp

# Or with uvicorn for development
uvicorn tool_gating_mcp.main:app --reload
```

The server will run on `http://localhost:8000`

API documentation available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- MCP Endpoint: `http://localhost:8000/mcp` (SSE transport)

### As MCP Server (Recommended)

Tool Gating MCP is now a native MCP server that works directly with Claude Desktop:

1. **Start the server**:
   ```bash
   tool-gating-mcp
   ```

2. **Install mcp-proxy** (if not already installed):
   ```bash
   uv tool install mcp-proxy
   ```

3. **Add to Claude Desktop**:
   
   Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:
   ```json
   {
     "mcpServers": {
       "tool-gating": {
         "command": "/Users/YOUR_USERNAME/.local/bin/mcp-proxy",
         "args": ["http://localhost:8000/mcp"]
       }
     }
   }
   ```
   
   Note: Replace `YOUR_USERNAME` with your actual username.

4. **Restart Claude Desktop**

You'll see Tool Gating's tools available in Claude, including:
- `discover_tools` - Find relevant tools based on queries
- `provision_tools` - Select tools within token budgets
- `register_tool` - Add new tools to the registry
- `list_mcp_servers` - View registered MCP servers
- And more!

See [MCP Native Usage Guide](docs/MCP_NATIVE_USAGE.md) for detailed instructions.

## 🔍 API Endpoints

### Tool Discovery
```bash
POST /api/tools/discover
```
Discover relevant tools based on semantic search.

**Request:**
```json
{
  "query": "I need to perform calculations",
  "tags": ["math", "calculation"],
  "limit": 5
}
```

**Response:**
```json
{
  "tools": [
    {
      "tool_id": "calculator",
      "name": "Calculator",
      "description": "Perform mathematical calculations",
      "score": 0.95,
      "matched_tags": ["math", "calculation"],
      "estimated_tokens": 50
    }
  ],
  "query_id": "uuid",
  "timestamp": "2024-01-01T00:00:00"
}
```

### Tool Provisioning
```bash
POST /api/tools/provision
```
Select and format tools for LLM consumption with token budget enforcement.

**Request:**
```json
{
  "tool_ids": ["calculator", "web-search"],
  "max_tools": 3
}
```

**Response:**
```json
{
  "tools": [
    {
      "name": "Calculator",
      "description": "Perform mathematical calculations",
      "parameters": { "type": "object", "properties": {...} },
      "token_count": 50
    }
  ],
  "metadata": {
    "total_tokens": 150,
    "gating_applied": true
  }
}
```


## 🔄 How It Works

1. **Claude Desktop Configuration**: Configure only Tool Gating MCP
   ```json
   {
     "mcpServers": {
       "tool-gating": {
         "command": "mcp-proxy",
         "args": ["http://localhost:8000/mcp"]
       }
     }
   }
   ```

2. **Backend Server Connection**: Tool Gating connects to multiple MCP servers
   ```
   Tool Gating → puppeteer (browser tools)
              → exa (search tools)
              → context7 (documentation)
              → filesystem (file operations)
   ```

3. **Natural Language Discovery**: "I need to search for research papers"
   ```
   Claude → discover_tools → Semantic Search → Returns relevant tools
   ```

4. **Real-time Tool Execution**: Tools are loaded on-demand
   ```
   execute_tool("exa_research_paper_search", {...}) → Validates → Loads → Executes
   ```
   
   No provisioning needed! Tools are dynamically loaded when you use them.

## 🎯 Usage Examples

### Running the Demo

```bash
# Make sure the server is running first
tool-gating-mcp

# In another terminal, run the interactive demo
python demo.py
```

### Manual Testing

```bash
# Test the server endpoints
python test_server.py
```

### Example: Finding Math Tools

```python
import httpx
import asyncio

async def find_math_tools():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/tools/discover",
            json={
                "query": "I need to solve equations",
                "tags": ["math"],
                "limit": 3
            }
        )
        tools = response.json()["tools"]
        print(f"Found {len(tools)} relevant tools")
        for tool in tools:
            print(f"- {tool['name']}: {tool['score']:.3f}")

asyncio.run(find_math_tools())
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=tool_gating_mcp

# Run specific test files
pytest tests/test_discovery_service.py -v

# Run integration tests
pytest tests/test_integration.py -v
```

## 📊 Architecture Details

1. **Tool Registration**: Tools are registered with metadata, tags, and token estimates
2. **Semantic Search**: User queries are embedded using sentence transformers
3. **Relevance Scoring**: Tools are scored based on:
   - Cosine similarity between query and tool embeddings
   - Tag matches (adds 0.2 boost per matching tag)
4. **Real-time Loading**: Tools are validated and loaded on-demand during execution
5. **MCP Formatting**: Selected tools are formatted according to MCP protocol


## 🔀 Proxy Layer (v0.3.0)

The proxy layer enables Tool Gating MCP to maintain persistent connections to backend MCP servers and transparently route tool execution requests.

### Components

- **MCPClientManager** — Manages persistent stdio connections to backend MCP servers. Starts connections on first use, caches `ClientSession` instances, and handles lifecycle (connect/disconnect/reconnect).
- **ProxyService** — Routes `execute_tool` calls to the correct backend server via a `tool_id → (server_name, tool_name)` mapping. Performs startup-time tool indexing across all backends.
- **Transparent Execution** — `/api/proxy/execute` endpoint forwards tool calls to the appropriate backend, preserving the existing API contract.

### How It Works

1. On startup, `ProxyService` connects to all configured backends via `MCPClientManager`
2. Each backend's tools are discovered (`list_tools`) and indexed into the shared `InMemoryToolRepository`
3. When a tool execution request arrives, the proxy resolves the target backend and forwards the call via the persistent session
4. New backends added via `/api/mcp/add_server` trigger incremental tool discovery

### Configuration

Backend servers are defined in `mcp-servers.json`:

```json
{
  "servers": {
    "my-backend": {
      "command": "uvx",
      "args": ["my-mcp-server"]
    }
  }
}
```

## 🔧 Configuration

The system uses sensible defaults but can be configured:

- **Max Tokens**: Default 2000 tokens per request
- **Max Tools**: Default 10 tools per request
- **Embedding Model**: `all-MiniLM-L6-v2` (384-dimensional embeddings)

## 📖 Documentation

- [Tool Discovery System](docs/DISCOVERY.md) - How semantic search and tags work together
- [Adding New MCP Servers](docs/ADDING_SERVERS.md) - Step-by-step guide to integrate new servers
- [AI Integration Guide](docs/AI_INTEGRATION.md) - How AI assistants can automatically add MCP servers
- [Architecture Overview](ARCHITECTURE.md) - System design and component interactions

## 📁 Project Structure

```
tool-gating-mcp/
├── src/
│   └── tool_gating_mcp/
│       ├── __init__.py
│       ├── main.py              # FastAPI application
│       ├── api/
│       │   ├── models.py        # Pydantic models
│       │   ├── tools.py         # Tool management endpoints
│       │   └── mcp.py           # MCP server endpoints
│       ├── models/
│       │   └── tool.py          # Domain models
│       └── services/
│           ├── discovery.py     # Semantic search
│           ├── gating.py        # Tool selection logic
│           └── repository.py    # Tool storage
├── tests/
│   ├── test_*.py               # Test files
│   └── test_integration.py     # Integration tests
├── demo.py                     # Interactive demo
├── test_server.py              # Manual testing script
└── pyproject.toml              # Project configuration
```

## 🔌 Integration with MCP Servers

### Registering Tools from MCP Servers

```python
# 1. Clear existing demo tools
DELETE /api/tools/clear

# 2. Register tools from your MCP servers
POST /api/tools/register
{
  "id": "exa_research_paper_search",
  "name": "research_paper_search",
  "description": "Search across 100M+ research papers with full text access",
  "tags": ["search", "research", "academic"],
  "estimated_tokens": 250,
  "server": "exa",
  "parameters": {
    "type": "object",
    "properties": {
      "query": {"type": "string"},
      "numResults": {"type": "number", "default": 5}
    },
    "required": ["query"]
  }
}
```

### Using with LLM Orchestration

1. **LLM receives user query**: "Find recent papers on quantum computing"
2. **Orchestrator queries tool gating**: 
   ```
   POST /api/tools/discover
   {"query": "find research papers", "limit": 3}
   ```
3. **System returns relevant tools**: Only research tools, not file editors
4. **Orchestrator provisions tools**:
   ```
   POST /api/tools/provision
   {"tool_ids": ["exa_research_paper_search"], "max_tokens": 500}
   ```
5. **LLM executes directly with MCP server**: Using the provisioned tool definition

### AI-Assisted Server Registration

AI assistants can automatically add new MCP servers:

```python
# User: "Add this Slack MCP server to tool gating"
# AI: Connects to server, discovers tools, and registers everything

POST /api/mcp/ai/register-server
{
  "server_name": "slack",
  "config": {
    "command": "npx",
    "args": ["@slack/mcp-server"],
    "env": {"SLACK_TOKEN": "xoxb-..."}
  },
  "tools": [
    // AI provides all discovered tools with metadata
  ]
}

# Result: Slack server + all tools registered and ready for use
```

## 🧑‍💻 Development

### Code Quality

```bash
# Format code
black .

# Run linter
ruff check . --fix

# Type checking
mypy .

# Run all checks
black . && ruff check . --fix && mypy . && pytest
```

### Adding New Tools

Tools can be added to the repository in `services/repository.py`:

```python
Tool(
    id="my-tool",
    name="My Tool",
    description="Description for semantic search",
    tags=["category", "function"],
    estimated_tokens=100,
    parameters={
        "type": "object",
        "properties": {...},
        "required": [...]
    }
)
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes and add tests
4. Run quality checks (`black`, `ruff`, `mypy`, `pytest`)
5. Commit your changes (`git commit -m 'Add amazing feature'`)
6. Push to the branch (`git push origin feature/amazing-feature`)
7. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Built with [FastAPI](https://fastapi.tiangolo.com/)
- Semantic search powered by [Sentence Transformers](https://www.sbert.net/)
- MCP protocol integration via [fastapi-mcp](https://github.com/tadata-org/fastapi_mcp)
- Demo UI using [Rich](https://github.com/Textualize/rich)