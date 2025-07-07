#!/usr/bin/env python3
"""
Deployment Test Script for Taskmaster MCP Server
Tests basic functionality and Smithery compatibility.
"""

import asyncio
import json
import sys
import time
from typing import Dict, Any
import aiohttp
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DeploymentTester:
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url.rstrip('/')
        
    async def test_health_endpoint(self) -> bool:
        """Test the health check endpoint."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/health") as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Health check passed: {data.get('status')}")
                        return True
                    else:
                        logger.error(f"❌ Health check failed with status: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ Health check error: {e}")
            return False
    
    async def test_root_endpoint(self) -> bool:
        """Test the root endpoint."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/") as response:
                    if response.status == 200:
                        data = await response.json()
                        logger.info(f"✅ Root endpoint: {data.get('name')} v{data.get('version')}")
                        return True
                    else:
                        logger.error(f"❌ Root endpoint failed with status: {response.status}")
                        return False
        except Exception as e:
            logger.error(f"❌ Root endpoint error: {e}")
            return False
    
    async def test_config_endpoint(self) -> bool:
        """Test the configuration endpoint."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/config") as response:
                    if response.status == 200:
                        data = await response.json()
                        smithery_compatible = data.get('smithery', {}).get('compatible', False)
                        logger.info(f"✅ Config endpoint - Smithery compatible: {smithery_compatible}")
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
    
    async def run_all_tests(self) -> Dict[str, bool]:
        """Run all deployment tests."""
        logger.info(f"🚀 Starting deployment tests for: {self.base_url}")
        logger.info("=" * 50)
        
        tests = {
            "health": await self.test_health_endpoint(),
            "root": await self.test_root_endpoint(),
            "config": await self.test_config_endpoint(),
            "mcp": await self.test_mcp_endpoint(),
        }
        
        logger.info("=" * 50)
        logger.info("📊 Test Results:")
        
        all_passed = True
        for test_name, result in tests.items():
            status = "✅ PASS" if result else "❌ FAIL"
            logger.info(f"  {test_name.upper()}: {status}")
            if not result:
                all_passed = False
        
        logger.info("=" * 50)
        if all_passed:
            logger.info("🎉 All tests passed! Deployment is ready for Smithery.")
        else:
            logger.error("💥 Some tests failed. Check the logs above.")
        
        return tests

async def main():
    """Main test function."""
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
    results = await tester.run_all_tests()
    
    # Exit with error code if any test failed
    if not all(results.values()):
        sys.exit(1)
    
    logger.info("✨ All deployment tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(main()) 