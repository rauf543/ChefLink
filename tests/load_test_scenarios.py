"""Load test scenarios for agentic workflow."""

import asyncio
import time
from typing import List, Dict, Any
import json
import logging

from app.services.telegram.handlers.family_v2_agentic import FamilyHandlersV2Agentic
from app.database.models import User, UserRole


logger = logging.getLogger(__name__)


class LoadTestScenarios:
    """Representative queries for load testing the agentic workflow."""
    
    SCENARIOS = [
        {
            "name": "Simple greeting",
            "query": "Hello",
            "expected_iterations": 1,
            "expected_tools": []
        },
        {
            "name": "Recipe search",
            "query": "Find me healthy breakfast recipes under 300 calories",
            "expected_iterations": 2,
            "expected_tools": ["search_recipes"]
        },
        {
            "name": "Complex meal planning",
            "query": "I want to plan meals for next week. I'm vegetarian and want to keep it under 1800 calories per day.",
            "expected_iterations": 5,
            "expected_tools": ["search_recipes", "create_meal_plan"]
        },
        {
            "name": "Recipe modification",
            "query": "Change my breakfast tomorrow to something with eggs",
            "expected_iterations": 3,
            "expected_tools": ["search_recipes", "update_meal_plan"]
        },
        {
            "name": "Nutritional analysis",
            "query": "Show me high protein lunch options",
            "expected_iterations": 2,
            "expected_tools": ["search_recipes"]
        },
        {
            "name": "Dietary preference update",
            "query": "I'm allergic to nuts and I want to eat 2000 calories a day",
            "expected_iterations": 2,
            "expected_tools": ["update_dietary_preferences"]
        },
        {
            "name": "Multi-step planning",
            "query": "Plan healthy dinners for the week, but no fish on consecutive days",
            "expected_iterations": 4,
            "expected_tools": ["search_recipes", "create_meal_plan"]
        },
        {
            "name": "Recipe details",
            "query": "Tell me more about the salmon recipe you suggested",
            "expected_iterations": 2,
            "expected_tools": ["get_recipe_details"]
        },
        {
            "name": "Ambiguous request",
            "query": "I need something quick for tonight",
            "expected_iterations": 3,
            "expected_tools": ["search_recipes"]
        },
        {
            "name": "Complex constraints",
            "query": "Find me recipes that are gluten-free, under 400 calories, with at least 25g protein",
            "expected_iterations": 3,
            "expected_tools": ["search_recipes"]
        }
    ]
    
    @classmethod
    async def run_scenario(cls, handler: FamilyHandlersV2Agentic, scenario: Dict[str, Any]) -> Dict[str, Any]:
        """Run a single test scenario and collect metrics."""
        start_time = time.time()
        
        # Mock user and update
        mock_user = cls._create_mock_user()
        mock_update = cls._create_mock_update(scenario["query"])
        mock_db = cls._create_mock_db()
        
        # Track metrics
        metrics = {
            "scenario": scenario["name"],
            "query": scenario["query"],
            "start_time": start_time,
            "iterations": 0,
            "tools_used": [],
            "total_tokens": 0,
            "total_cost": 0,
            "success": False,
            "error": None,
            "response_time": 0
        }
        
        try:
            # Run the scenario
            thinking_message = cls._create_mock_thinking_message()
            
            # We need to mock the LLM responses based on the scenario
            initial_response = cls._create_initial_response(scenario)
            
            await handler._process_agentic_response(
                initial_response,
                mock_update,
                mock_db,
                mock_user,
                "test_user",
                thinking_message
            )
            
            metrics["success"] = True
            
        except Exception as e:
            metrics["error"] = str(e)
            logger.error(f"Scenario '{scenario['name']}' failed: {e}")
        
        metrics["response_time"] = time.time() - start_time
        
        # Extract metrics from handler traces
        if hasattr(handler, 'tool_traces'):
            # Get the latest trace
            latest_trace = list(handler.tool_traces.values())[-1] if handler.tool_traces else None
            if latest_trace:
                metrics["iterations"] = len(latest_trace.get("iterations", []))
                metrics["total_cost"] = latest_trace.get("total_cost", 0)
                
                # Extract tools used
                tools = set()
                for iteration in latest_trace.get("iterations", []):
                    for tool in iteration.get("tools_executed", []):
                        tools.add(tool["name"])
                metrics["tools_used"] = list(tools)
        
        return metrics
    
    @classmethod
    async def run_all_scenarios(cls, handler: FamilyHandlersV2Agentic) -> List[Dict[str, Any]]:
        """Run all test scenarios and collect results."""
        results = []
        
        for scenario in cls.SCENARIOS:
            logger.info(f"Running scenario: {scenario['name']}")
            result = await cls.run_scenario(handler, scenario)
            results.append(result)
            
            # Brief pause between scenarios
            await asyncio.sleep(0.5)
        
        return results
    
    @classmethod
    def analyze_results(cls, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Analyze load test results."""
        total_scenarios = len(results)
        successful = sum(1 for r in results if r["success"])
        
        response_times = [r["response_time"] for r in results if r["success"]]
        avg_response_time = sum(response_times) / len(response_times) if response_times else 0
        
        total_cost = sum(r["total_cost"] for r in results)
        
        avg_iterations = sum(r["iterations"] for r in results) / total_scenarios
        
        # Check if scenarios met expectations
        expectations_met = 0
        for result, scenario in zip(results, cls.SCENARIOS):
            if result["success"]:
                # Check if iterations are reasonable
                if result["iterations"] <= scenario["expected_iterations"] + 2:
                    # Check if expected tools were used
                    if all(tool in result["tools_used"] for tool in scenario["expected_tools"]):
                        expectations_met += 1
        
        analysis = {
            "total_scenarios": total_scenarios,
            "successful": successful,
            "success_rate": successful / total_scenarios * 100,
            "avg_response_time": avg_response_time,
            "max_response_time": max(response_times) if response_times else 0,
            "min_response_time": min(response_times) if response_times else 0,
            "total_cost": total_cost,
            "avg_cost_per_query": total_cost / total_scenarios,
            "avg_iterations": avg_iterations,
            "expectations_met": expectations_met,
            "expectation_rate": expectations_met / total_scenarios * 100
        }
        
        return analysis
    
    @staticmethod
    def _create_mock_user():
        """Create a mock user for testing."""
        from unittest.mock import Mock
        user = Mock(spec=User)
        user.id = "test-user-id"
        user.telegram_id = "123456"
        user.name = "Test User"
        user.role = UserRole.FAMILY_MEMBER
        user.dietary_preferences = {}
        return user
    
    @staticmethod
    def _create_mock_update(text: str):
        """Create a mock Telegram update."""
        from unittest.mock import Mock, AsyncMock
        update = Mock()
        update.effective_user = Mock(id="123456")
        update.message = Mock()
        update.message.text = text
        update.message.reply_text = AsyncMock()
        return update
    
    @staticmethod
    def _create_mock_db():
        """Create a mock database session."""
        from unittest.mock import AsyncMock
        return AsyncMock()
    
    @staticmethod
    def _create_mock_thinking_message():
        """Create a mock thinking message."""
        from unittest.mock import Mock, AsyncMock
        message = Mock()
        message.edit_text = AsyncMock()
        message.delete = AsyncMock()
        return message
    
    @staticmethod
    def _create_initial_response(scenario: Dict[str, Any]):
        """Create a mock initial response based on scenario."""
        from unittest.mock import Mock
        response = Mock()
        
        # For simple scenarios, return final message immediately
        if scenario["name"] == "Simple greeting":
            response.content = [
                Mock(type="text", text="{{final_message: Hello! How can I help you with meal planning today?}}")
            ]
        else:
            # For complex scenarios, return thinking + tool use
            response.content = [
                Mock(type="text", text=f"Let me help you with that. {scenario['query']}"),
            ]
            
            # Add expected tool calls
            if "search_recipes" in scenario["expected_tools"]:
                response.content.append(
                    Mock(type="tool_use", name="search_recipes", input={}, id="tool1")
                )
        
        response.usage = Mock(input_tokens=100, output_tokens=50)
        return response


async def main():
    """Run the load test."""
    logging.basicConfig(level=logging.INFO)
    
    # Create handler instance
    handler = FamilyHandlersV2Agentic()
    
    # Mock the LLM service
    from unittest.mock import Mock, AsyncMock
    handler.llm_service = Mock()
    handler.llm_service.model = "claude-opus-4-20250514"
    handler.llm_service.client = AsyncMock()
    
    # Run scenarios
    print("Starting load test...")
    results = await LoadTestScenarios.run_all_scenarios(handler)
    
    # Analyze results
    analysis = LoadTestScenarios.analyze_results(results)
    
    # Print results
    print("\n" + "="*50)
    print("LOAD TEST RESULTS")
    print("="*50)
    
    for key, value in analysis.items():
        if isinstance(value, float):
            print(f"{key}: {value:.2f}")
        else:
            print(f"{key}: {value}")
    
    print("\nDetailed Results:")
    for result in results:
        print(f"\n{result['scenario']}:")
        print(f"  Success: {result['success']}")
        print(f"  Response Time: {result['response_time']:.2f}s")
        print(f"  Iterations: {result['iterations']}")
        print(f"  Tools Used: {result['tools_used']}")
        if result['error']:
            print(f"  Error: {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())