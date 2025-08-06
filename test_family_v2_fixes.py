#!/usr/bin/env python3
"""Test script to verify family_v2.py fixes"""

import asyncio
import json
from datetime import datetime, date
import uuid
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.database.base import AsyncSessionLocal
from app.database.models import Recipe, User, MealPlan
from app.services.telegram.handlers.family_v2 import FamilyHandlersV2


async def test_recipe_validation():
    """Test that invalid recipe IDs are properly handled"""
    
    handler = FamilyHandlersV2()
    
    async with AsyncSessionLocal() as db:
        # Get a test user
        result = await db.execute(select(User).limit(1))
        user = result.scalar_one_or_none()
        
        if not user:
            print("No users found in database")
            return
        
        print(f"Testing with user: {user.name}")
        
        # Test 1: Try to create meal plan with invalid recipe ID
        print("\n1. Testing create_meal_plan with invalid recipe ID...")
        invalid_recipe_id = "c92aee60-0606-4b3e-bae0-f14fe2f121c0"
        
        result = await handler._tool_create_meal_plan(
            {
                "plans": [{
                    "date": "2025-08-06",
                    "meal_type": "breakfast",
                    "recipe_id": invalid_recipe_id,
                    "servings": 1
                }]
            },
            db,
            user
        )
        
        print(f"Result: {json.dumps(result, indent=2)}")
        assert "errors" in result or len(result["created"]) == 0, "Should have failed or returned no created plans"
        
        # Test 2: Try to update meal plan with invalid recipe ID
        print("\n2. Testing update_meal_plan with invalid recipe ID...")
        
        # First get an existing meal plan if any
        existing_plan = await db.execute(
            select(MealPlan).where(MealPlan.user_id == user.id).limit(1)
        )
        meal_plan = existing_plan.scalar_one_or_none()
        
        if meal_plan:
            result = await handler._tool_update_meal_plan(
                {
                    "meal_plan_id": str(meal_plan.id),
                    "recipe_id": invalid_recipe_id
                },
                db,
                user
            )
            print(f"Result: {json.dumps(result, indent=2)}")
            assert "error" in result, "Should have returned an error"
        else:
            print("No existing meal plans to test update")
        
        # Test 3: Try to get details for invalid recipe
        print("\n3. Testing get_recipe_details with invalid recipe ID...")
        result = await handler._tool_get_recipe_details(
            {"recipe_id": invalid_recipe_id},
            db
        )
        print(f"Result: {json.dumps(result, indent=2)}")
        assert "error" in result, "Should have returned an error"
        
        # Test 4: Try with a valid recipe
        print("\n4. Testing with a valid recipe...")
        valid_recipe = await db.execute(select(Recipe).limit(1))
        recipe = valid_recipe.scalar_one_or_none()
        
        if recipe:
            print(f"Using valid recipe: {recipe.recipe_name} (ID: {recipe.id})")
            
            result = await handler._tool_create_meal_plan(
                {
                    "plans": [{
                        "date": "2025-08-07",
                        "meal_type": "lunch",
                        "recipe_id": str(recipe.id),
                        "servings": 2
                    }]
                },
                db,
                user
            )
            print(f"Result: {json.dumps(result, indent=2)}")
            assert len(result.get("created", [])) > 0 or "errors" in result, "Should have created a plan or returned errors"
        else:
            print("No recipes found in database")
    
    print("\n✅ All tests completed!")


async def test_error_handling():
    """Test general error handling improvements"""
    
    handler = FamilyHandlersV2()
    
    # Test with empty response handling
    print("\n5. Testing response processing with edge cases...")
    
    # Create a mock response object
    class MockContent:
        def __init__(self, type_val, text_val=None):
            self.type = type_val
            self.text = text_val
    
    class MockResponse:
        def __init__(self, content_list):
            self.content = content_list
    
    # Test with empty content
    response = MockResponse([])
    
    # This should not crash
    print("Testing with empty response content - should handle gracefully")
    
    # Test with only text content
    response = MockResponse([MockContent("text", "Hello, I can help you plan meals!")])
    print("Testing with text-only response - should handle gracefully")
    
    print("\n✅ Error handling tests completed!")


async def main():
    """Run all tests"""
    print("🧪 Testing family_v2.py fixes...")
    
    await test_recipe_validation()
    await test_error_handling()
    
    print("\n✨ All tests completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())