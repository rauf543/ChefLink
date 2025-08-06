#!/usr/bin/env python3
"""
Initialize the database with sample data for testing.
"""
import asyncio
import uuid
from datetime import date, timedelta

from app.database.base import AsyncSessionLocal, engine
from app.database.models import Base, Recipe, User, UserRole


async def init_db():
    """Initialize database with sample data."""
    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    # Add sample data
    async with AsyncSessionLocal() as db:
        # Check if data already exists
        from sqlalchemy import select
        result = await db.execute(select(Recipe).limit(1))
        if result.scalar_one_or_none():
            print("Database already contains data. Skipping initialization.")
            return
            
        # Create sample recipes
        recipes = [
            Recipe(
                id=uuid.uuid4(),
                recipe_name="Grilled Chicken Caesar Salad",
                recipe_author="Chef Maria",
                recipe_book="Healthy Meals",
                page_reference="45",
                servings=1,
                instructions="1. Grill chicken breast. 2. Chop romaine lettuce. 3. Mix with caesar dressing and croutons.",
                ingredients=["1 chicken breast", "2 cups romaine lettuce", "2 tbsp caesar dressing", "1/4 cup croutons"],
                main_protein=["chicken"],
                calories_per_serving=450,
                macro_nutrients={"protein_g": 35, "fat_g": 20, "carbohydrates_g": 25}
            ),
            Recipe(
                id=uuid.uuid4(),
                recipe_name="Vegetarian Buddha Bowl",
                recipe_author="Chef Alex",
                recipe_book="Plant Power",
                page_reference="78",
                servings=1,
                instructions="1. Cook quinoa. 2. Roast vegetables. 3. Arrange in bowl with tahini dressing.",
                ingredients=["1/2 cup quinoa", "1 cup mixed vegetables", "2 tbsp tahini", "1/4 avocado"],
                main_protein=["tofu"],
                calories_per_serving=520,
                macro_nutrients={"protein_g": 18, "fat_g": 25, "carbohydrates_g": 55}
            ),
            Recipe(
                id=uuid.uuid4(),
                recipe_name="Salmon Teriyaki",
                recipe_author="Chef Tanaka",
                recipe_book="Japanese Cuisine",
                page_reference="112",
                servings=1,
                instructions="1. Marinate salmon in teriyaki sauce. 2. Pan-sear until cooked. 3. Serve with rice.",
                ingredients=["1 salmon fillet", "2 tbsp teriyaki sauce", "1/2 cup rice", "1 tsp sesame seeds"],
                main_protein=["salmon"],
                calories_per_serving=480,
                macro_nutrients={"protein_g": 32, "fat_g": 18, "carbohydrates_g": 45}
            ),
        ]
        
        for recipe in recipes:
            db.add(recipe)
            
        # Create sample users
        users = [
            User(
                id=uuid.uuid4(),
                telegram_id="sample_chef_123",
                name="Chef Gordon",
                role=UserRole.CHEF,
                invitation_code="CHEF1234"
            ),
            User(
                id=uuid.uuid4(),
                telegram_id="sample_family_456",
                name="Alice Smith",
                role=UserRole.FAMILY_MEMBER,
                invitation_code="FAM45678",
                dietary_preferences={
                    "calories_target": 2000,
                    "protein_target": 100,
                    "blacklisted": ["shellfish", "peanuts"]
                }
            ),
        ]
        
        for user in users:
            db.add(user)
            
        await db.commit()
        
        print("Database initialized with sample data!")
        print(f"- {len(recipes)} recipes added")
        print(f"- {len(users)} users added")


if __name__ == "__main__":
    asyncio.run(init_db())