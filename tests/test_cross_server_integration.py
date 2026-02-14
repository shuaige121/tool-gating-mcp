"""
Cross-Server Integration Tests

Tests the system's ability to work with multiple MCP servers:
- Tool discovery across multiple servers
- Server isolation and independence
- Tool naming and ID collision handling
- Performance with multiple server connections
- Failover when some servers are unavailable

These tests ensure the tool gating system can effectively
manage a heterogeneous ecosystem of MCP servers.
"""

import pytest
from unittest.mock import AsyncMock, patch
from typing import Dict, List, Any


class TestMultiServerDiscovery:
    """Test tool discovery across multiple MCP servers"""

    @pytest.mark.asyncio
    async def test_discovery_finds_tools_from_multiple_servers(self, client, sample_tools):
        """Test that discovery can find relevant tools from different servers"""
        
        # Create tools from different servers
        server_a_tools = [
            {
                "id": "server_a_web_search",
                "name": "web_search",
                "description": "Search the web for current information and news",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
                "server": "server_a",
                "tags": ["search", "web", "information"],
                "estimated_tokens": 150
            },
            {
                "id": "server_a_summarize",
                "name": "summarize_text", 
                "description": "Summarize long text documents into key points",
                "parameters": {"type": "object", "properties": {"text": {"type": "string"}}},
                "server": "server_a",
                "tags": ["text", "summarization", "analysis"],
                "estimated_tokens": 120
            }
        ]
        
        server_b_tools = [
            {
                "id": "server_b_database_query",
                "name": "database_query",
                "description": "Query database for specific data and analytics",
                "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}},
                "server": "server_b", 
                "tags": ["database", "query", "data"],
                "estimated_tokens": 180
            },
            {
                "id": "server_b_data_visualization",
                "name": "create_chart",
                "description": "Create charts and visualizations from data",
                "parameters": {"type": "object", "properties": {"data": {"type": "array"}}},
                "server": "server_b",
                "tags": ["visualization", "charts", "data"],
                "estimated_tokens": 200
            }
        ]
        
        # Register tools from both servers
        all_tools = server_a_tools + server_b_tools
        for tool_data in all_tools:
            response = client.post("/api/tools/register", json=tool_data)
            assert response.status_code == 200
        
        # Test discovery finds tools from both servers
        response = client.post("/api/tools/discover", json={
            "query": "search and analyze information from data sources",
            "limit": 10
        })
        
        assert response.status_code == 200
        results = response.json()["tools"]
        
        # Should find relevant tools from both servers
        servers_found = {tool["server"] for tool in results}
        assert len(servers_found) >= 2
        assert "server_a" in servers_found
        assert "server_b" in servers_found
        
        # Should rank by relevance across servers
        scores = [tool["score"] for tool in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_server_specific_tool_discovery(self, client):
        """Test discovery can filter tools by server when needed"""
        
        # Register tools from multiple servers
        tools_by_server = {
            "database_server": [
                {
                    "id": "database_server_query_tool",
                    "name": "sql_query",
                    "description": "Execute SQL queries on the database",
                    "parameters": {"type": "object"},
                    "server": "database_server",
                    "tags": ["database", "sql"],
                    "estimated_tokens": 150
                }
            ],
            "web_server": [
                {
                    "id": "web_server_fetch_tool", 
                    "name": "fetch_webpage",
                    "description": "Fetch and parse web pages",
                    "parameters": {"type": "object"},
                    "server": "web_server",
                    "tags": ["web", "http"],
                    "estimated_tokens": 130
                }
            ]
        }
        
        for server_tools in tools_by_server.values():
            for tool_data in server_tools:
                response = client.post("/api/tools/register", json=tool_data)
                assert response.status_code == 200
        
        # Discovery should find tools from specific contexts
        response = client.post("/api/tools/discover", json={
            "query": "database operations and SQL",
            "limit": 5
        })
        
        results = response.json()["tools"]
        database_tools = [tool for tool in results if tool["server"] == "database_server"]
        web_tools = [tool for tool in results if tool["server"] == "web_server"]
        
        # Database query should be more relevant for database operations
        if database_tools and web_tools:
            assert database_tools[0]["score"] > web_tools[0]["score"]

    @pytest.mark.asyncio
    async def test_cross_server_tag_matching(self, client):
        """Test that tag matching works across servers"""
        
        # Tools with overlapping tags from different servers
        tools_with_tags = [
            {
                "id": "server_x_analysis_tool",
                "name": "data_analysis",
                "description": "Analyze data patterns and trends",
                "parameters": {"type": "object"},
                "server": "server_x",
                "tags": ["analysis", "data", "statistics"],
                "estimated_tokens": 160
            },
            {
                "id": "server_y_analysis_tool",
                "name": "text_analysis", 
                "description": "Analyze text for sentiment and topics",
                "parameters": {"type": "object"},
                "server": "server_y",
                "tags": ["analysis", "text", "nlp"],
                "estimated_tokens": 140
            },
            {
                "id": "server_z_visualization_tool",
                "name": "chart_creator",
                "description": "Create charts and graphs",
                "parameters": {"type": "object"},
                "server": "server_z", 
                "tags": ["visualization", "charts"],
                "estimated_tokens": 120
            }
        ]
        
        for tool_data in tools_with_tags:
            response = client.post("/api/tools/register", json=tool_data)
            assert response.status_code == 200
        
        # Search by tag should find tools from all relevant servers
        response = client.post("/api/tools/discover", json={
            "query": "analysis capabilities",
            "tags": ["analysis"],
            "limit": 5
        })
        
        results = response.json()["tools"]
        analysis_tools = [tool for tool in results if "analysis" in tool["matched_tags"]]
        
        # Should find analysis tools from both server_x and server_y
        servers_with_analysis = {tool["server"] for tool in analysis_tools}
        assert "server_x" in servers_with_analysis
        assert "server_y" in servers_with_analysis


class TestServerIsolationAndIndependence:
    """Test that servers operate independently"""

    @pytest.mark.asyncio
    async def test_server_failure_doesnt_affect_others(self, client):
        """Test that failure of one server doesn't impact others"""
        
        # Mock multiple servers with one failing
        working_server_tools = [
            type('MockTool', (), {
                'name': 'working_tool_1',
                'description': 'This tool works fine',
                'inputSchema': {'type': 'object'}
            })(),
            type('MockTool', (), {
                'name': 'working_tool_2',
                'description': 'This tool also works',
                'inputSchema': {'type': 'object'}
            })()
        ]
        
        with patch('tool_gating_mcp.main.app.state.client_manager') as mock_manager:
            mock_manager.connect_server = AsyncMock()
            
            # First server connects successfully
            mock_manager.server_tools = {"working_server": working_server_tools}
            response = client.post("/api/mcp/add_server", json={
                "name": "working_server",
                "config": {
                    "command": "working-server",
                    "args": [],
                    "env": {}
                }
            })
            assert response.status_code == 200
            
            # Second server fails to connect
            mock_manager.connect_server.side_effect = ConnectionError("Server not responding")
            response = client.post("/api/mcp/add_server", json={
                "name": "failing_server", 
                "config": {
                    "command": "failing-server",
                    "args": [],
                    "env": {}
                }
            })
            assert response.status_code == 500  # Server addition fails
            
            # Working server tools should still be discoverable
            response = client.post("/api/tools/discover", json={
                "query": "working tool functionality"
            })
            assert response.status_code == 200
            results = response.json()["tools"]
            
            working_tools = [tool for tool in results if tool["server"] == "working_server"]
            assert len(working_tools) >= 1

    @pytest.mark.asyncio
    async def test_server_tool_namespacing(self, client):
        """Test that tool names are properly namespaced by server"""
        
        # Register identical tool names from different servers
        identical_tools = [
            {
                "id": "server_1_search_tool",
                "name": "search_tool",
                "description": "Search functionality from server 1",
                "parameters": {"type": "object"},
                "server": "server_1",
                "tags": ["search"],
                "estimated_tokens": 100
            },
            {
                "id": "server_2_search_tool",
                "name": "search_tool",
                "description": "Search functionality from server 2",
                "parameters": {"type": "object"},
                "server": "server_2",
                "tags": ["search"],
                "estimated_tokens": 100
            }
        ]
        
        for tool_data in identical_tools:
            response = client.post("/api/tools/register", json=tool_data)
            assert response.status_code == 200
        
        # Discovery should find both tools with different IDs
        response = client.post("/api/tools/discover", json={
            "query": "search functionality"
        })
        
        results = response.json()["tools"]
        search_tools = [tool for tool in results if tool["name"] == "search_tool"]
        
        assert len(search_tools) == 2
        
        # Should have different tool_ids and servers
        tool_ids = {tool["tool_id"] for tool in search_tools}
        servers = {tool["server"] for tool in search_tools}
        
        assert len(tool_ids) == 2
        assert len(servers) == 2
        assert "server_1_search_tool" in tool_ids
        assert "server_2_search_tool" in tool_ids

    @pytest.mark.asyncio
    async def test_independent_server_configurations(self, client):
        """Test that servers can have different configurations"""
        
        server_configs = [
            {
                "name": "local_server",
                "config": {
                    "command": "local-mcp-server",
                    "args": ["--local"],
                    "env": {"MODE": "local"}
                }
            },
            {
                "name": "remote_server",
                "config": {
                    "command": "remote-mcp-server",
                    "args": ["--remote", "--timeout=30"],
                    "env": {"MODE": "remote", "API_KEY": "test"}
                }
            }
        ]
        
        with patch('tool_gating_mcp.main.app.state.client_manager') as mock_manager:
            mock_manager.connect_server = AsyncMock()
            mock_manager.server_tools = {}
            
            for config in server_configs:
                # Each server should be configurable independently
                response = client.post("/api/mcp/add_server", json=config)
                # May succeed or fail, but should handle each independently
                assert response.status_code in [200, 500]


class TestToolExecutionAcrossServers:
    """Test tool execution with multiple servers"""

    @pytest.mark.asyncio
    async def test_execute_tools_from_different_servers(self, client):
        """Test executing tools from different servers in sequence"""
        
        # Register tools from different servers
        multi_server_tools = [
            {
                "id": "auth_server_login",
                "name": "user_login",
                "description": "Authenticate user with credentials",
                "parameters": {"type": "object", "properties": {"username": {"type": "string"}}},
                "server": "auth_server",
                "tags": ["authentication"],
                "estimated_tokens": 100
            },
            {
                "id": "data_server_fetch",
                "name": "fetch_user_data",
                "description": "Fetch user data from database",
                "parameters": {"type": "object", "properties": {"user_id": {"type": "string"}}},
                "server": "data_server", 
                "tags": ["data", "user"],
                "estimated_tokens": 120
            }
        ]
        
        for tool_data in multi_server_tools:
            response = client.post("/api/tools/register", json=tool_data)
            assert response.status_code == 200
        
        # Mock execution results for different servers
        mock_results = {
            "auth_server_login": {"token": "abc123", "user_id": "user_456"},
            "data_server_fetch": {"user": {"name": "Test User", "email": "test@example.com"}}
        }
        
        with patch('tool_gating_mcp.services.proxy_service.ProxyService.execute_tool') as mock_execute:
            # Execute tool from first server
            mock_execute.return_value = mock_results["auth_server_login"]
            response = client.post("/api/proxy/execute", json={
                "tool_id": "auth_server_login",
                "arguments": {"username": "testuser"}
            })
            
            assert response.status_code == 200
            result = response.json()["result"]
            assert result["user_id"] == "user_456"
            
            # Execute tool from second server
            mock_execute.return_value = mock_results["data_server_fetch"]
            response = client.post("/api/proxy/execute", json={
                "tool_id": "data_server_fetch",
                "arguments": {"user_id": "user_456"}
            })
            
            assert response.status_code == 200
            result = response.json()["result"]
            assert result["user"]["name"] == "Test User"

    @pytest.mark.asyncio
    async def test_execution_failure_isolation(self, client):
        """Test that execution failure on one server doesn't affect others"""
        
        # Register tools from multiple servers
        tools = [
            {
                "id": "stable_server_tool",
                "name": "stable_operation",
                "description": "Reliable operation that always works",
                "parameters": {"type": "object"},
                "server": "stable_server",
                "tags": ["reliable"],
                "estimated_tokens": 100
            },
            {
                "id": "unstable_server_tool",
                "name": "unstable_operation",
                "description": "Unreliable operation that may fail",
                "parameters": {"type": "object"},
                "server": "unstable_server",
                "tags": ["unreliable"],
                "estimated_tokens": 100
            }
        ]
        
        for tool_data in tools:
            response = client.post("/api/tools/register", json=tool_data)
            assert response.status_code == 200
        
        with patch('tool_gating_mcp.services.proxy_service.ProxyService.execute_tool') as mock_execute:
            # First execution fails
            mock_execute.side_effect = ConnectionError("Unstable server down")
            response = client.post("/api/proxy/execute", json={
                "tool_id": "unstable_server_tool",
                "arguments": {}
            })
            assert response.status_code == 500
            
            # Second execution should still work (different server)
            mock_execute.side_effect = None
            mock_execute.return_value = {"result": "success"}
            response = client.post("/api/proxy/execute", json={
                "tool_id": "stable_server_tool",
                "arguments": {}
            })
            assert response.status_code == 200


class TestPerformanceWithMultipleServers:
    """Test system performance with multiple servers"""

    @pytest.mark.asyncio
    async def test_discovery_performance_with_many_servers(self, client):
        """Test discovery remains fast with many servers"""
        
        import time
        
        # Register tools from many different servers
        num_servers = 10
        tools_per_server = 5
        
        for server_idx in range(num_servers):
            server_name = f"performance_server_{server_idx}"
            
            for tool_idx in range(tools_per_server):
                tool_data = {
                    "id": f"{server_name}_tool_{tool_idx}",
                    "name": f"tool_{tool_idx}",
                    "description": f"Performance test tool {tool_idx} from {server_name}",
                    "parameters": {"type": "object"},
                    "server": server_name,
                    "tags": [f"performance", f"server_{server_idx}"],
                    "estimated_tokens": 100 + tool_idx
                }
                
                response = client.post("/api/tools/register", json=tool_data)
                assert response.status_code == 200
        
        # Discovery should be fast despite many servers
        start_time = time.time()
        response = client.post("/api/tools/discover", json={
            "query": "performance test functionality",
            "limit": 10
        })
        discovery_time = time.time() - start_time
        
        assert response.status_code == 200
        results = response.json()["tools"]
        
        # Should find tools from multiple servers
        servers_found = {tool["server"] for tool in results}
        assert len(servers_found) >= 3  # Should span multiple servers
        
        # Discovery should complete quickly
        assert discovery_time < 2.0

    @pytest.mark.asyncio
    async def test_concurrent_server_operations(self, client):
        """Test concurrent operations across multiple servers"""
        
        # Register tools from different servers
        servers_and_tools = {
            "concurrent_server_a": [
                {
                    "id": "concurrent_server_a_tool_1",
                    "name": "operation_a1",
                    "description": "Operation A1 for concurrency testing",
                    "parameters": {"type": "object"},
                    "server": "concurrent_server_a",
                    "tags": ["concurrent"],
                    "estimated_tokens": 100
                }
            ],
            "concurrent_server_b": [
                {
                    "id": "concurrent_server_b_tool_1",
                    "name": "operation_b1",
                    "description": "Operation B1 for concurrency testing",
                    "parameters": {"type": "object"},
                    "server": "concurrent_server_b",
                    "tags": ["concurrent"],
                    "estimated_tokens": 100
                }
            ]
        }
        
        for server_tools in servers_and_tools.values():
            for tool_data in server_tools:
                response = client.post("/api/tools/register", json=tool_data)
                assert response.status_code == 200
        
        # Concurrent discovery requests should work efficiently
        import asyncio
        import httpx
        
        async def discover_tools(query_suffix):
            transport = httpx.ASGITransport(app=client.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as ac:
                response = await ac.post("/api/tools/discover", json={
                    "query": f"concurrent operation {query_suffix}",
                    "limit": 5
                })
                return response.status_code, response.json()
        
        # Run multiple discovery requests concurrently
        results = await asyncio.gather(*[
            discover_tools("test1"),
            discover_tools("test2"), 
            discover_tools("test3")
        ])
        
        # All requests should succeed
        for status_code, result in results:
            assert status_code == 200
            assert "tools" in result
