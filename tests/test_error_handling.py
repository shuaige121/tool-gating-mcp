"""
Error Handling Tests

Tests the system's ability to handle errors gracefully:
- Invalid input validation and error messages
- Server connection failures and retries
- Tool execution errors and fallbacks  
- Resource exhaustion scenarios
- Malformed data handling
- Recovery from partial failures

These tests ensure the system provides useful error information
and maintains stability under adverse conditions.
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi import HTTPException


class TestInputValidation:
    """Test validation of inputs and error responses"""

    @pytest.mark.asyncio
    async def test_discovery_with_invalid_queries(self, client):
        """Test discovery handles invalid query inputs gracefully"""
        
        invalid_queries = [
            {},  # Missing query
            {"query": ""},  # Empty query
            {"query": "   "},  # Whitespace only
            {"query": "a" * 1000},  # Extremely long query
            {"limit": -1},  # Invalid limit
            {"limit": "not_a_number"},  # Wrong type for limit
        ]
        
        for invalid_query in invalid_queries:
            response = client.post("/api/tools/discover", json=invalid_query)
            
            # Should return error status for validation failures
            if "query" not in invalid_query or not invalid_query.get("query", "").strip():
                assert response.status_code in [400, 422]
            else:
                # For other invalid inputs, should handle gracefully
                assert response.status_code in [200, 400, 422]
                
                if response.status_code == 200:
                    # If accepted, should return valid structure
                    result = response.json()
                    assert "tools" in result
                    assert isinstance(result["tools"], list)

    @pytest.mark.asyncio
    async def test_tool_registration_with_invalid_data(self, client):
        """Test tool registration validates input data properly"""
        
        invalid_tools = [
            {},  # Empty object
            {"name": "test"},  # Missing required fields
            {"id": "", "name": "", "description": ""},  # Empty required fields
            {
                "id": "test_tool",
                "name": "test",
                "description": "test",
                "parameters": "not_an_object",  # Wrong type
                "estimated_tokens": -1  # Invalid value
            },
            {
                "id": "test/tool",  # Invalid characters
                "name": "test tool with spaces",
                "description": "test",
                "parameters": {"type": "object"},
                "estimated_tokens": "not_a_number"  # Wrong type
            }
        ]
        
        for invalid_tool in invalid_tools:
            response = client.post("/api/tools/register", json=invalid_tool)
            
            # Should reject invalid data
            assert response.status_code in [400, 422]
            
            # Should provide useful error information
            if response.status_code == 422:
                error_data = response.json()
                assert "detail" in error_data

    @pytest.mark.asyncio
    async def test_server_registration_with_invalid_config(self, client):
        """Test server registration validates configuration properly"""
        
        invalid_configs = [
            {},  # Empty config
            {"name": ""},  # Empty name
            {"name": "test", "config": {}},  # Empty config
            {
                "name": "test/server",  # Invalid name characters
                "config": {"command": ""}  # Empty command
            },
            {
                "name": "test_server",
                "config": {"command": "test", "args": "not_a_list"}  # Wrong type
            }
        ]
        
        for invalid_config in invalid_configs:
            response = client.post("/api/mcp/add_server", json=invalid_config)
            
            # Should reject invalid configurations
            assert response.status_code in [400, 422, 500]


class TestServerConnectionErrors:
    """Test handling of MCP server connection failures"""

    @pytest.mark.asyncio
    async def test_add_server_connection_failure(self, client):
        """Test handling when MCP server connection fails"""
        
        # Mock connection failure
        with patch('tool_gating_mcp.main.app.state.client_manager') as mock_manager:
            mock_manager.connect_server = AsyncMock(side_effect=ConnectionError("Server not responding"))
            
            response = client.post("/api/mcp/add_server", json={
                "name": "failing_server",
                "config": {
                    "command": "nonexistent-server",
                    "args": [],
                    "env": {}
                },
                "description": "Server that fails to connect"
            })
            
            # Should handle connection failure gracefully
            assert response.status_code == 500
            error_data = response.json()
            assert "Failed to add server" in error_data["detail"]

    @pytest.mark.asyncio
    async def test_tool_execution_with_server_error(self, client, sample_tools):
        """Test tool execution when MCP server encounters errors"""
        
        # Register a tool first
        tool = sample_tools[0]
        response = client.post("/api/tools/register", json=tool.model_dump())
        assert response.status_code == 200
        
        # Mock execution failure
        with patch('tool_gating_mcp.services.proxy_service.ProxyService.execute_tool') as mock_execute:
            mock_execute.side_effect = ConnectionError("Server disconnected during execution")
            
            response = client.post("/api/proxy/execute", json={
                "tool_id": tool.id,
                "arguments": {"query": "test"}
            })
            
            # Should return appropriate error
            assert response.status_code == 500
            error_data = response.json()
            assert "Tool execution failed" in error_data["detail"]

    @pytest.mark.asyncio
    async def test_partial_tool_discovery_failure(self, client):
        """Test when some tools from a server can be discovered but others fail"""
        
        # Mock partial failure scenario
        mock_tools = [
            type('MockTool', (), {
                'name': 'working_tool',
                'description': 'This tool works fine',
                'inputSchema': {'type': 'object'}
            })(),
            # Simulate a problematic tool that causes registration to fail
            type('MockTool', (), {
                'name': 'broken_tool', 
                'description': None,  # Missing description causes error
                'inputSchema': {'type': 'object'}
            })()
        ]
        
        with patch('tool_gating_mcp.main.app.state.client_manager') as mock_manager:
            mock_manager.connect_server = AsyncMock()
            mock_manager.server_tools = {"test_server": mock_tools}
            
            response = client.post("/api/mcp/add_server", json={
                "name": "test_server",
                "config": {
                    "command": "test-server",
                    "args": [],
                    "env": {}
                }
            })
            
            # Should succeed partially
            assert response.status_code == 200
            result = response.json()
            
            # Should have registered the working tool but not the broken one
            assert result["status"] == "success"
            assert "working_tool" in result["tools_discovered"]
            assert "broken_tool" not in result["tools_discovered"]


class TestToolExecutionErrors:
    """Test handling of tool execution failures"""

    @pytest.mark.asyncio
    async def test_execute_nonexistent_tool(self, client):
        """Test execution of tool that doesn't exist"""
        
        response = client.post("/api/proxy/execute", json={
            "tool_id": "nonexistent_server_nonexistent_tool",
            "arguments": {}
        })
        
        # Should return appropriate error
        assert response.status_code in [400, 404, 500]
        error_data = response.json()
        assert "detail" in error_data

    @pytest.mark.asyncio
    async def test_execute_tool_with_invalid_arguments(self, client, sample_tools):
        """Test execution with malformed arguments"""
        
        # Register a tool
        tool = sample_tools[0]  # search_tool requires "query" parameter
        response = client.post("/api/tools/register", json=tool.model_dump())
        assert response.status_code == 200
        
        # Mock successful tool lookup but execution failure due to bad args
        with patch('tool_gating_mcp.services.proxy_service.ProxyService.execute_tool') as mock_execute:
            mock_execute.side_effect = ValueError("Missing required parameter: query")
            
            response = client.post("/api/proxy/execute", json={
                "tool_id": tool.id,
                "arguments": {}  # Missing required "query" parameter
            })
            
            # Should return appropriate error
            assert response.status_code == 400
            error_data = response.json()
            assert "Missing required parameter" in error_data["detail"]

    @pytest.mark.asyncio
    async def test_tool_execution_timeout(self, client, sample_tools):
        """Test handling of tool execution timeouts"""
        
        # Register a tool
        tool = sample_tools[0]
        response = client.post("/api/tools/register", json=tool.model_dump())
        assert response.status_code == 200
        
        # Mock timeout error
        with patch('tool_gating_mcp.services.proxy_service.ProxyService.execute_tool') as mock_execute:
            mock_execute.side_effect = TimeoutError("Tool execution timed out after 30 seconds")
            
            response = client.post("/api/proxy/execute", json={
                "tool_id": tool.id,
                "arguments": {"query": "test"}
            })
            
            # Should handle timeout gracefully
            assert response.status_code == 500
            error_data = response.json()
            assert "Tool execution failed" in error_data["detail"]


class TestResourceExhaustionErrors:
    """Test handling when system resources are exhausted"""

    @pytest.mark.asyncio
    async def test_discovery_with_repository_error(self, client):
        """Test discovery when repository encounters errors"""
        
        with patch('tool_gating_mcp.services.discovery.DiscoveryService.search_tools') as mock_search:
            mock_search.side_effect = MemoryError("Out of memory during search")
            
            response = client.post("/api/tools/discover", json={
                "query": "search for information"
            })
            
            # Should handle gracefully
            assert response.status_code == 500

    @pytest.mark.asyncio
    async def test_tool_registration_storage_error(self, client):
        """Test tool registration when storage fails"""
        
        tool_data = {
            "id": "test_tool",
            "name": "test_tool",
            "description": "Test tool",
            "parameters": {"type": "object"},
            "server": "test_server",
            "tags": [],
            "estimated_tokens": 100
        }
        
        with patch('tool_gating_mcp.services.repository.InMemoryToolRepository.add_tool') as mock_add:
            mock_add.side_effect = OSError("Disk full")
            
            response = client.post("/api/tools/register", json=tool_data)
            
            # Should handle storage error
            assert response.status_code == 500


class TestMalformedDataHandling:
    """Test handling of malformed or corrupted data"""

    @pytest.mark.asyncio
    async def test_discovery_with_corrupted_tool_data(self, client):
        """Test discovery when tool repository contains corrupted data"""
        
        # Register a tool with some valid data
        tool_data = {
            "id": "test_tool",
            "name": "test_tool", 
            "description": "Test tool",
            "parameters": {"type": "object"},
            "server": "test_server",
            "tags": [],
            "estimated_tokens": 100
        }
        
        response = client.post("/api/tools/register", json=tool_data)
        assert response.status_code == 200
        
        # Mock repository returning corrupted data
        with patch('tool_gating_mcp.services.repository.InMemoryToolRepository.get_all_tools') as mock_get_all:
            # Return mix of valid and invalid tools
            valid_tool = type('Tool', (), tool_data)()
            corrupted_tool = type('Tool', (), {"id": None, "name": "", "description": None})()
            
            mock_get_all.return_value = [valid_tool, corrupted_tool]
            
            response = client.post("/api/tools/discover", json={
                "query": "test"
            })
            
            # Should handle corrupted data gracefully
            # May return partial results or empty results, but shouldn't crash
            assert response.status_code in [200, 500]
            
            if response.status_code == 200:
                results = response.json()
                assert "tools" in results
                # Should filter out corrupted tools
                valid_results = [t for t in results["tools"] if t.get("name")]
                assert len(valid_results) <= 1

    @pytest.mark.asyncio
    async def test_malformed_json_requests(self, client):
        """Test handling of malformed JSON in requests"""
        
        import json
        
        # Test with various malformed JSON scenarios
        malformed_requests = [
            '{"query": "test"',  # Unclosed brace
            '{"query": "test", }',  # Trailing comma
            '{"query": undefined}',  # JavaScript undefined
            '{"query": "test\\}',  # Malformed escape
        ]
        
        for malformed_json in malformed_requests:
            response = client.post(
                "/api/tools/discover",
                content=malformed_json,
                headers={"Content-Type": "application/json"},
            )

            # Should reject malformed JSON
            assert response.status_code in [400, 422]


class TestRecoveryScenarios:
    """Test system recovery from various failure conditions"""

    @pytest.mark.asyncio
    async def test_recovery_after_tool_clear_error(self, client, sample_tools):
        """Test system recovery after clear operation encounters errors"""
        
        # Register some tools
        for tool in sample_tools:
            response = client.post("/api/tools/register", json=tool.model_dump())
            assert response.status_code == 200
        
        # Mock clear operation failure
        with patch('tool_gating_mcp.api.tools.get_tool_repository') as mock_repo_getter:
            mock_repo = AsyncMock()
            mock_repo._tools.clear.side_effect = RuntimeError("Clear operation failed")
            mock_repo_getter.return_value = mock_repo
            
            response = client.delete("/api/tools/clear")
            assert response.status_code == 500
        
        # System should still be functional after error
        response = client.post("/api/tools/discover", json={"query": "search"})
        assert response.status_code == 200
        
        # Should be able to register new tools
        new_tool_data = {
            "id": "recovery_tool",
            "name": "recovery_tool",
            "description": "Tool for testing recovery",
            "parameters": {"type": "object"},
            "server": "test_server", 
            "tags": [],
            "estimated_tokens": 100
        }
        
        response = client.post("/api/tools/register", json=new_tool_data)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_discovery_recovery_after_service_error(self, client, sample_tools):
        """Test discovery service recovery after encountering errors"""
        
        # Register tools
        for tool in sample_tools:
            response = client.post("/api/tools/register", json=tool.model_dump())
            assert response.status_code == 200
        
        # Cause discovery service error
        with patch('tool_gating_mcp.services.discovery.DiscoveryService.search_tools') as mock_search:
            mock_search.side_effect = RuntimeError("Discovery service error")
            
            response = client.post("/api/tools/discover", json={"query": "search"})
            assert response.status_code == 500
        
        # Service should recover for subsequent requests
        response = client.post("/api/tools/discover", json={"query": "search"})
        assert response.status_code == 200
        results = response.json()
        assert len(results["tools"]) > 0
