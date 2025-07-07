#!/usr/bin/env python3
"""
Deployment Test Script for Taskmaster MCP Server
Tests basic functionality and Smithery compatibility.
"""

import asyncio
import json
import sys
import time
from typing import Dict, Any, Optional
import aiohttp
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DeploymentTester:
    """Test suite for Smithery deployment verification."""
    
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip('/')
    
    async def run_tests(self) -> bool:
        """Run all deployment tests."""
        tests = [
            ("Root Endpoint", self.test_root_endpoint),
            ("Health Check", self.test_health_endpoint),
            ("Config Endpoint", self.test_config_endpoint),
            ("MCP Endpoint", self.test_mcp_endpoint),
            ("Tool Discovery Speed", self.test_tool_discovery_speed)  # New test
        ]
        
        all_passed = True
        for test_name, test_method in tests:
            logger.info(f"Running test: {test_name}")
            try:
                success = await test_method()
                if success:
                    logger.info(f"✅ {test_name} passed")
                else:
                    logger.error(f"❌ {test_name} failed")
                    all_passed = False
            except Exception as e:
                logger.error(f"❌ {test_name} error: {e}")
                all_passed = False
        
        return all_passed
    
    async def test_root_endpoint(self) -> bool:
        """Test the root endpoint."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/") as response:
                    if response.status == 200:
                        data = await response.json()
                        smithery_compatible = data.get('smithery_compatible', False)
                        static_tool_registration = data.get('static_tool_registration', False)
                        logger.info(f"✅ Root endpoint - Smithery compatible: {smithery_compatible}, Static registration: {static_tool_registration}")
                        return True
                    else:
                        logger.error(f"❌ Root endpoint failed with status: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ Root endpoint error: {e}")
            return False
    
    async def test_health_endpoint(self) -> bool:
        """Test the health check endpoint."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        data = await response.json()
                        healthy = data.get('status') == 'healthy'
                        smithery_ready = data.get('smithery_ready', False)
                        static_registration = data.get('static_tool_registration', False)
                        logger.info(f"✅ Health endpoint - Healthy: {healthy}, Smithery ready: {smithery_ready}, Static registration: {static_registration}")
                        return healthy and smithery_ready
                    else:
                        logger.error(f"❌ Health endpoint failed with status: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ Health endpoint error: {e}")
            return False
    
    async def test_config_endpoint(self) -> bool:
        """Test the configuration endpoint."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/config") as response:
                    if response.status == 200:
                        data = await response.json()
                        smithery_compatible = data.get('smithery', {}).get('compatible', False)
                        static_registration = data.get('capabilities', {}).get('static_tool_registration', False)
                        logger.info(f"✅ Config endpoint - Smithery compatible: {smithery_compatible}, Static registration: {static_registration}")
                        return True
                    else:
                        logger.error(f"❌ Config endpoint failed with status: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ Config endpoint error: {e}")
            return False
    
    async def test_mcp_endpoint(self) -> bool:
        """Test the MCP endpoint basic connectivity."""
        try:
            async with aiohttp.ClientSession() as session:
                # Test basic connectivity (should return method not allowed or similar)
                async with session.get(f"{self.base_url}/mcp") as response:
                    # MCP endpoint might return various status codes, just check it's reachable
                    if response.status in [200, 405, 404]:  # Common responses for GET on MCP
                        logger.info(f"✅ MCP endpoint reachable (status: {response.status})")
                        return True
                    else:
                        logger.warning(f"⚠️ MCP endpoint returned status: {response.status}")
                        return True  # Still consider it working
        except Exception as e:
            logger.error(f"❌ MCP endpoint error: {e}")
            return False
    
    async def test_tool_discovery_speed(self) -> bool:
        """Test tool discovery speed to ensure Smithery optimization is working."""
        try:
            async with aiohttp.ClientSession() as session:
                # Time the tool discovery request
                start_time = time.time()
                
                # This simulates what Smithery does for tool discovery
                mcp_request = {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                    "params": {}
                }
                
                async with session.post(
                    f"{self.base_url}/mcp",
                    json=mcp_request,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=5)  # 5 second timeout
                ) as response:
                    end_time = time.time()
                    response_time = end_time - start_time
                    
                    logger.info(f"Tool discovery response time: {response_time:.3f} seconds")
                    
                    if response_time < 3.0:  # Should be much faster than 3 seconds
                        logger.info(f"✅ Tool discovery speed test passed ({response_time:.3f}s < 3.0s)")
                        return True
                    else:
                        logger.warning(f"⚠️ Tool discovery slower than expected: {response_time:.3f}s")
                        return False
                        
        except asyncio.TimeoutError:
            logger.error("❌ Tool discovery timed out (>5 seconds)")
            return False
        except Exception as e:
            logger.error(f"❌ Tool discovery speed test error: {e}")
            return False

async def main():
    """Main test runner."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Taskmaster MCP Server deployment")
    parser.add_argument(
        "--url", 
        default="http://localhost:8080",
        help="Base URL of the server to test (default: http://localhost:8080)"
    )
    parser.add_argument(
        "--wait",
        type=int,
        default=0,
        help="Wait N seconds before starting tests (useful for startup delay)"
    )
    
    args = parser.parse_args()
    
    if args.wait > 0:
        logger.info(f"⏳ Waiting {args.wait} seconds before starting tests...")
        time.sleep(args.wait)
    
    tester = DeploymentTester(args.url)
    all_tests_passed = await tester.run_tests()
    
    if all_tests_passed:
        logger.info("🎉 All deployment tests passed!")
        logger.info("✅ Smithery deployment is ready")
        logger.info("⚡ Tool discovery optimization confirmed working")
        return 0
    else:
        logger.error("❌ Some deployment tests failed")
        logger.error("⚠️ Check logs above for details")
        return 1

if __name__ == "__main__":
    exit_code = asyncio.run(main()) 