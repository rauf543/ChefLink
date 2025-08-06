#!/usr/bin/env python3
"""Test script to verify family_v3_refactored handler works correctly"""

import asyncio
import json
from datetime import datetime, date
import uuid
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.database.base import AsyncSessionLocal
from app.database.models import Recipe, User, MealPlan
from app.services.telegram.handlers.family_v3_refactored import FamilyHandlerV3
from app.core.tools.executor import ToolExecutor


async def test_recipe_validation():
    """Test that invalid recipe IDs are properly handled"""
    
    async with AsyncSessionLocal() as db:
        # Get a test user
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        
        if not user:
            print("No users found in database")
            return
        
        print(f"Testing with user: {user.name}")
        
        # Create tool executor for testing
        tool_executor = ToolExecutor(db, user)
        
        # Test 1: Try to create meal plan with invalid recipe ID
        print("\n1. Testing create_meal_plan with invalid recipe ID...")
        invalid_recipe_id = "c92aee60-0606-4b3e-bae0-f14fe2f121c0"
        
        result = await tool_executor.execute(
            "create_meal_plan",
            {
                "date": "2025-08-06",
                "meals": [{
                    "recipe_id": invalid_recipe_id,
                    "meal_type": "breakfast",
                    "servings": 1
                }]
            }
        )
        
        print(f"Result: {json.dumps(result, indent=2)}")
        if result["success"]:
            assert len(result["result"]["meals_created"]) == 0, "Should not have created plans with invalid recipe"
        else:
            assert "error" in result, "Should have error for invalid recipe"
        
        # Test 2: Try to update meal plan with invalid recipe ID
        print("\n2. Testing update_meal_plan with invalid recipe ID...")
        
        result = await tool_executor.execute(
            "update_meal_plan",
            {
                "date": "2025-08-06",
                "meal_type": "lunch",
                "recipe_id": invalid_recipe_id,
                "servings": 2
            }
        )
        
        print(f"Result: {json.dumps(result, indent=2)}")
        assert not result["success"] or not result["result"].get("updated"), "Should fail with invalid recipe"
        
        # Test 3: Try to get details for invalid recipe
        print("\n3. Testing get_recipe_details with invalid recipe ID...")
        result = await tool_executor.execute(
            "get_recipe_details",
            {"recipe_id": invalid_recipe_id}
        )
        
        print(f"Result: {json.dumps(result, indent=2)}")
        assert not result["success"], "Should fail with invalid recipe"
        
        # Test 4: Try with a valid recipe
        print("\n4. Testing with a valid recipe...")
        valid_recipe = await db.execute(select(Recipe).limit(1))
        recipe = valid_recipe.scalar_one_or_none()
        
        if recipe:
            print(f"Using valid recipe: {recipe.recipe_name} (ID: {recipe.id})")
            
            result = await tool_executor.execute(
                "create_meal_plan",
                {
                    "date": "2025-08-07",
                    "meals": [{
                        "recipe_id": str(recipe.id),
                        "meal_type": "lunch",
                        "servings": 2
                    }]
                }
            )
            
            print(f"Result: {json.dumps(result, indent=2)}")
            assert result["success"], "Should succeed with valid recipe"
            assert len(result["result"]["meals_created"]) > 0, "Should have created meal plan"
        else:
            print("No recipes found in database")
    
    print("\n✅ All recipe validation tests completed!")


async def test_tool_execution():
    """Test tool execution through the new architecture"""
    
    async with AsyncSessionLocal() as db:
        # Get a test user
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        
        if not user:
            print("No users found in database")
            return
        
        # Create tool executor
        tool_executor = ToolExecutor(db, user)
        
        # Test search recipes
        print("\n5. Testing search_recipes tool...")
        result = await tool_executor.execute(
            "search_recipes",
            {
                "query": "chicken",
                "max_calories": 500,
                "limit": 5
            }
        )
        
        print(f"Search result: Found {result['result']['count']} recipes")
        assert result["success"], "Search should succeed"
        
        # Test get meal plans
        print("\n6. Testing get_meal_plans tool...")
        result = await tool_executor.execute(
            "get_meal_plans",
            {"days": 7}
        )
        
        print(f"Meal plans result: {len(result['result']['meal_plans'])} days with plans")
        assert result["success"], "Get meal plans should succeed"
        
        # Test nutrition analysis
        print("\n7. Testing analyze_nutrition tool...")
        result = await tool_executor.execute(
            "analyze_nutrition",
            {
                "date": "2025-08-06",
                "meal_type": "all"
            }
        )
        
        print(f"Nutrition result: Total calories = {result['result']['total_nutrition']['calories']}")
        assert result["success"], "Nutrition analysis should succeed"
        
        # Test preferences
        print("\n8. Testing user preference tools...")
        
        # Get current preferences
        result = await tool_executor.execute(
            "get_user_preferences",
            {}
        )
        print(f"Current preferences: {result['result']['dietary_preferences']}")
        assert result["success"], "Get preferences should succeed"
        
        # Update preferences
        result = await tool_executor.execute(
            "update_dietary_preferences",
            {
                "preferences": {
                    "vegetarian": False,
                    "low_carb": True,
                    "allergies": ["nuts"]
                }
            }
        )
        print(f"Updated preferences: {result['result']['preferences']}")
        assert result["success"], "Update preferences should succeed"
    
    print("\n✅ All tool execution tests completed!")


async def test_handler_integration():
    """Test the full handler integration"""
    
    async with AsyncSessionLocal() as db:
        # Create handler
        handler = FamilyHandlerV3(db)
        
        # Get a test user
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        
        if not user:
            print("No users found in database")
            return
        
        print("\n9. Testing handler conversation context...")
        
        # Get conversation context
        context = handler._get_conversation_context(user)
        assert context is not None, "Should create conversation context"
        
        # Add some messages
        context.add_message("user", "Hello, can you help me plan meals?")
        context.add_message("assistant", "Of course! I'd be happy to help you plan your meals.")
        
        # Check token usage
        usage = context.get_token_usage()
        print(f"Token usage: {usage['current_tokens']}/{usage['max_tokens']} ({usage['usage_percentage']:.1f}%)")
        assert usage['current_tokens'] > 0, "Should track token usage"
        
        # Test context compression (add many messages)
        print("\n10. Testing context compression...")
        for i in range(50):
            context.add_message("user", f"Test message {i} " * 20)
            context.add_message("assistant", f"Response {i} " * 20)
        
        usage = context.get_token_usage()
        print(f"After many messages: {usage['message_count']} messages, {usage['compression_count']} compressions")
        assert usage['compression_count'] > 0, "Should have compressed context"
        assert usage['current_tokens'] <= usage['max_tokens'], "Should stay within token limit"
    
    print("\n✅ Handler integration tests completed!")


async def main():
    """Run all tests"""
    print("🧪 Testing family_v3_refactored handler...")
    print("=" * 60)
    
    await test_recipe_validation()
    await test_tool_execution()
    await test_handler_integration()
    
    print("\n" + "=" * 60)
    print("✨ All tests completed successfully!")
    print("The refactored handler is working correctly.")


if __name__ == "__main__":
    asyncio.run(main())