#!/usr/bin/env python3
"""List all recipes in the database with their IDs"""

import asyncio
from sqlalchemy import select
from app.database.base import AsyncSessionLocal
from app.database.models import Recipe


async def list_recipes():
    """List all recipes with their IDs and basic info"""
    
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Recipe).order_by(Recipe.recipe_name)
        )
        recipes = result.scalars().all()
        
        if not recipes:
            print("No recipes found in the database!")
            print("Please run: python scripts/add_test_recipes.py")
            return
        
        print(f"\n📚 Found {len(recipes)} recipes in the database:\n")
        print("-" * 100)
        print(f"{'Recipe Name':<50} {'ID':<40} {'Calories':<10}")
        print("-" * 100)
        
        for recipe in recipes:
            print(f"{recipe.recipe_name[:48]:<50} {str(recipe.id):<40} {recipe.calories_per_serving:<10}")
        
        print("-" * 100)
        print(f"\nTotal: {len(recipes)} recipes")
        
        # Check if the problematic ID exists
        problematic_id = "c92aee60-0606-4b3e-bae0-f14fe2f121c0"
        matching = [r for r in recipes if str(r.id) == problematic_id]
        
        if matching:
            print(f"\n⚠️  Found recipe with ID {problematic_id}: {matching[0].recipe_name}")
        else:
            print(f"\n❌ Recipe with ID {problematic_id} does NOT exist in the database")
            print("This is why the bot is getting foreign key constraint errors!")
        
        # Show a sample valid recipe ID
        if recipes:
            print(f"\n💡 Example valid recipe ID you can use: {recipes[0].id}")
            print(f"   Recipe name: {recipes[0].recipe_name}")


if __name__ == "__main__":
    asyncio.run(list_recipes())