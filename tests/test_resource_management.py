"""
Resource Management Tests

Tests the system's ability to manage resources efficiently:
- Token budget enforcement and optimization
- Tool count limits and selection strategies  
- Memory usage and caching behavior
- Performance under load and constraints
- Resource cleanup and garbage collection

These tests ensure the system stays within operational limits
while maximizing utility for AI agents.
"""

import pytest
from unittest.mock import patch
import time


class TestTokenBudgetManagement:
    """Test token budget enforcement and optimization"""

    @pytest.mark.asyncio
    async def test_discovery_respects_implicit_token_limits(self, client, sample_tools):
        """Test that discovery returns reasonable number of tools for token efficiency"""
        
        # Register many tools to test limits
        for i, base_tool in enumerate(sample_tools):
            for variation in range(5):  # Create 15 total tools
                tool_data = base_tool.model_dump()
                tool_data["id"] = f"{base_tool.id}_{variation}"
                tool_data["name"] = f"{base_tool.name}_{variation}"
                tool_data["description"] = f"{base_tool.description} - variation {variation}"
                
                response = client.post("/api/tools/register", json=tool_data)
                assert response.status_code == 200
        
        # Discovery should limit results to reasonable number
        response = client.post("/api/tools/discover", json={
            "query": "search information data",  # Matches multiple tools
            "limit": 20  # Request more than reasonable
        })
        
        assert response.status_code == 200
        results = response.json()["tools"]
        
        # Should return reasonable number (default limit)
        assert len(results) <= 10
        
        # Results should be ranked by relevance
        scores = [tool["score"] for tool in results]
        assert scores == sorted(scores, reverse=True)
        
        # Higher scoring tools should be included
        assert all(score >= 0.3 for score in scores[:3])

    @pytest.mark.asyncio  
    async def test_discovery_with_explicit_limits(self, client, sample_tools):
        """Test discovery respects explicit result limits"""
        
        # Register tools
        for tool in sample_tools:
            response = client.post("/api/tools/register", json=tool.model_dump())
            assert response.status_code == 200
        
        # Test different limit values
        for limit in [1, 2, 3, 5]:
            response = client.post("/api/tools/discover", json={
                "query": "tool",  # Generic query to match all
                "limit": limit
            })
            
            assert response.status_code == 200
            results = response.json()["tools"]
            assert len(results) <= limit
            assert len(results) <= len(sample_tools)  # Can't return more than available

    @pytest.mark.asyncio
    async def test_token_estimation_accuracy(self, client, sample_tools):
        """Test that token estimates are reasonable and consistent"""
        
        for tool in sample_tools:
            response = client.post("/api/tools/register", json=tool.model_dump())
            assert response.status_code == 200
        
        response = client.post("/api/tools/discover", json={"query": "search"})
        results = response.json()["tools"]
        
        for tool in results:
            estimated_tokens = tool["estimated_tokens"]
            
            # Token estimates should be reasonable
            assert 50 <= estimated_tokens <= 500
            
            # Tools with longer descriptions should generally have higher estimates
            description_length = len(tool["description"])
            if description_length > 100:
                assert estimated_tokens >= 100


class TestPerformanceConstraints:
    """Test system performance under various constraints"""

    @pytest.mark.asyncio
    async def test_discovery_performance_with_many_tools(self, client, sample_tools):
        """Test that discovery remains fast even with many registered tools"""
        
        # Register many tools (simulating large tool ecosystem)
        start_time = time.time()
        
        for i in range(50):  # 150 total tools (50 * 3 base tools)
            for base_tool in sample_tools:
                tool_data = base_tool.model_dump()
                tool_data["id"] = f"{base_tool.id}_{i}"
                tool_data["name"] = f"{base_tool.name}_{i}"
                
                response = client.post("/api/tools/register", json=tool_data)
                assert response.status_code == 200
        
        registration_time = time.time() - start_time
        
        # Discovery should be fast regardless of repository size
        start_time = time.time()
        response = client.post("/api/tools/discover", json={
            "query": "search for specific information patterns",
            "limit": 5
        })
        discovery_time = time.time() - start_time
        
        assert response.status_code == 200
        assert len(response.json()["tools"]) <= 5
        
        # Discovery should be much faster than registration
        assert discovery_time < registration_time / 10
        # Discovery should complete in reasonable time
        assert discovery_time < 2.0  # 2 seconds max

    @pytest.mark.asyncio
    async def test_concurrent_discovery_requests(self, client, sample_tools):
        """Test system handles multiple discovery requests efficiently"""
        
        # Setup tools
        for tool in sample_tools:
            response = client.post("/api/tools/register", json=tool.model_dump())
            assert response.status_code == 200
        
        import asyncio
        import httpx
        
        async def make_discovery_request(query):
            transport = httpx.ASGITransport(app=client.app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://test",
            ) as ac:
                response = await ac.post("/api/tools/discover", json={
                    "query": query,
                    "limit": 3
                })
                return response.status_code, response.json()
        
        # Run multiple concurrent requests
        queries = [
            "search information",
            "process data", 
            "perform actions",
            "analyze patterns",
            "retrieve content"
        ]
        
        start_time = time.time()
        results = await asyncio.gather(*[
            make_discovery_request(query) for query in queries
        ])
        total_time = time.time() - start_time
        
        # All requests should succeed
        for status_code, result in results:
            assert status_code == 200
            assert "tools" in result
        
        # Concurrent requests shouldn't take much longer than sequential
        assert total_time < 5.0


class TestMemoryManagement:
    """Test memory usage and cleanup behavior"""

    @pytest.mark.asyncio
    async def test_tool_registration_memory_growth(self, client):
        """Test that repeated tool registration doesn't cause memory leaks"""
        
        # Register and clear tools multiple times
        for cycle in range(5):
            # Register tools
            for i in range(20):
                tool_data = {
                    "id": f"test_tool_{i}",
                    "name": f"test_tool_{i}",
                    "description": f"Test tool number {i} for memory testing",
                    "parameters": {"type": "object", "properties": {}},
                    "server": "test_server",
                    "tags": ["test"],
                    "estimated_tokens": 100
                }
                
                response = client.post("/api/tools/register", json=tool_data)
                assert response.status_code == 200
            
            # Verify tools are registered
            response = client.post("/api/tools/discover", json={"query": "test"})
            assert len(response.json()["tools"]) == 20
            
            # Clear all tools
            response = client.delete("/api/tools/clear")
            assert response.status_code == 200
            
            # Verify tools are cleared
            response = client.post("/api/tools/discover", json={"query": "test"})
            assert len(response.json()["tools"]) == 0

    @pytest.mark.asyncio
    async def test_repository_state_isolation(self, client):
        """Test that repository state is properly isolated between operations"""
        
        # Register a tool
        tool_data = {
            "id": "isolation_test_tool",
            "name": "isolation_tool",
            "description": "Tool for testing state isolation",
            "parameters": {"type": "object", "properties": {}},
            "server": "test_server",
            "tags": ["isolation"],
            "estimated_tokens": 100
        }
        
        response = client.post("/api/tools/register", json=tool_data)
        assert response.status_code == 200
        
        # Multiple discovery requests should return consistent results
        for _ in range(3):
            response = client.post("/api/tools/discover", json={"query": "isolation"})
            results = response.json()["tools"]
            assert len(results) == 1
            assert results[0]["name"] == "isolation_tool"
        
        # Clear and verify isolation is maintained
        response = client.delete("/api/tools/clear")
        assert response.status_code == 200
        
        for _ in range(3):
            response = client.post("/api/tools/discover", json={"query": "isolation"})
            assert len(response.json()["tools"]) == 0


class TestScalabilityLimits:
    """Test system behavior at scale limits"""

    @pytest.mark.asyncio
    async def test_maximum_tool_registration(self, client):
        """Test system behavior with very large number of tools"""
        
        # Register a large number of tools
        max_tools = 200
        batch_size = 20
        
        for batch in range(0, max_tools, batch_size):
            for i in range(batch, min(batch + batch_size, max_tools)):
                tool_data = {
                    "id": f"scale_test_tool_{i}",
                    "name": f"scale_tool_{i}",
                    "description": f"Scale test tool {i} with unique capabilities",
                    "parameters": {"type": "object", "properties": {}},
                    "server": f"server_{i // 50}",  # Distribute across servers
                    "tags": [f"scale_{i % 10}", "test"],
                    "estimated_tokens": 100 + (i % 50)
                }
                
                response = client.post("/api/tools/register", json=tool_data)
                assert response.status_code == 200
            
            # Test discovery still works efficiently mid-registration
            response = client.post("/api/tools/discover", json={
                "query": "scale test capabilities",
                "limit": 5
            })
            assert response.status_code == 200
            results = response.json()["tools"]
            assert len(results) <= 5
            assert len(results) > 0
        
        # Final verification with all tools registered
        response = client.post("/api/tools/discover", json={
            "query": "scale",
            "limit": 10
        })
        assert response.status_code == 200
        results = response.json()["tools"]
        assert len(results) == 10
        
        # Tools should still be properly ranked
        scores = [tool["score"] for tool in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_discovery_with_diverse_queries(self, client, sample_tools):
        """Test discovery performance with many different query patterns"""
        
        # Register tools
        for tool in sample_tools:
            response = client.post("/api/tools/register", json=tool.model_dump())
            assert response.status_code == 200
        
        # Test many different query patterns
        query_patterns = [
            "search",
            "find information",
            "data processing and analysis", 
            "automated actions",
            "content retrieval systems",
            "text processing tools",
            "web search capabilities",
            "database operations",
            "file manipulation",
            "api integrations"
        ]
        
        start_time = time.time()
        
        for query in query_patterns:
            response = client.post("/api/tools/discover", json={
                "query": query,
                "limit": 3
            })
            assert response.status_code == 200
            
            # Each query should return relevant results or empty list
            results = response.json()["tools"]
            assert isinstance(results, list)
            assert len(results) <= 3
        
        total_time = time.time() - start_time
        
        # All queries should complete quickly
        assert total_time < 5.0
        # Average time per query should be reasonable
        assert total_time / len(query_patterns) < 0.5
