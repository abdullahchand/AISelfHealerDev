#!/usr/bin/env python3
"""
Simple test script for the AI Runtime Environment
"""

import asyncio
import sys
import os

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from shared.config import ConfigManager
from shared.models import Issue, IssueType, Task, ActionType
from shared.llm_analyzer import LLMAnalyzer
from shared.utils import setup_logging


async def test_llm_analyzer():
    """Test the LLM analyzer functionality."""
    print("🧪 Testing LLM Analyzer...")
    
    # Setup logging
    logger = setup_logging()
    
    # Initialize LLM analyzer
    llm_analyzer = LLMAnalyzer()
    
    # Create a test issue
    test_issue = Issue(
        issue_id="test-001",
        worker_id="worker-001",
        app_name="web-app",
        issue_type=IssueType.PORT_CONFLICT,
        description="Port 3000 is already in use",
        confidence_score=0.9,
        logs=["Error: Port 3000 is already in use", "Failed to bind to port 3000"],
        context={"port": "3000", "process": "node"},
        timestamp=1234567890
    )
    
    # Test available workers
    available_workers = [
        {
            "worker_id": "worker-001",
            "status": "healthy",
            "apps": ["web-app", "api-server"],
            "load": 2
        },
        {
            "worker_id": "worker-002", 
            "status": "healthy",
            "apps": ["database", "cache"],
            "load": 1
        }
    ]
    
    # Test issue analysis
    print("📊 Analyzing test issue...")
    analysis = await llm_analyzer.analyze_issue(test_issue, available_workers)
    print(f"✅ LLM Analysis Result: {analysis}")
    
    # Test worker selection
    test_task = Task(
        task_id="task-001",
        worker_id="",
        action=ActionType.RESTART,
        app_name="web-app",
        parameters={"reason": "port conflict"},
        priority=1
    )
    
    print("🤖 Selecting worker for task...")
    selected_worker = await llm_analyzer.decide_worker_assignment(test_task, available_workers)
    print(f"✅ Selected Worker: {selected_worker}")
    
    # Test resolution suggestion
    print("💡 Getting resolution suggestion...")
    resolution = await llm_analyzer.suggest_resolution(test_issue, available_workers[0]['worker_id'], available_workers[0])
    print(f"✅ Resolution Suggestion: {resolution}")


async def test_config_manager():
    """Test the configuration manager."""
    print("\n📋 Testing Configuration Manager...")
    
    config_manager = ConfigManager()
    
    # Test master config
    master_config = config_manager.get_master_config()
    print(f"✅ Master Config: {master_config.agent_id} on {master_config.host}:{master_config.port}")
    
    # Test app configs
    app_configs = config_manager.get_app_configs()
    print(f"✅ Found {len(app_configs)} configured apps")
    
    for app in app_configs:
        print(f"   - {app.name}: {app.command}")


async def test_models():
    """Test the data models."""
    print("\n🏗️ Testing Data Models...")
    
    # Test Issue model
    issue = Issue(
        issue_id="test-002",
        worker_id="worker-001",
        app_name="api-server",
        issue_type=IssueType.PROCESS_CRASH,
        description="Process crashed unexpectedly",
        confidence_score=0.95
    )
    
    print(f"✅ Created Issue: {issue.issue_type.value} - {issue.description}")
    
    # Test Task model
    task = Task(
        task_id="task-002",
        worker_id="worker-001",
        action=ActionType.START,
        app_name="api-server",
        priority=1
    )
    
    print(f"✅ Created Task: {task.action.value} {task.app_name}")


async def main():
    """Run all tests."""
    print("🚀 AI Runtime Environment Test Suite")
    print("=" * 50)
    
    try:
        await test_models()
        await test_config_manager()
        await test_llm_analyzer()
        
        print("\n" + "=" * 50)
        print("✅ All tests completed successfully!")
        print("\n🎉 Your AI Runtime Environment is ready!")
        print("\nNext steps:")
        print("1. Set OPENAI_API_KEY environment variable for LLM features")
        print("2. Run: ai-runtime start --master")
        print("3. Run: ai-runtime start --worker")
        print("4. Run: ai-runtime diagnose")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main()) 