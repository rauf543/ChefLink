#!/usr/bin/env python3
"""Add test recipes to the database."""

import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add the parent directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from app.database.base import AsyncSessionLocal
from app.database.models import Recipe


async def add_test_recipes():
    """Add some test recipes to the database."""
    
    test_recipes = [
        {
            "recipe_name": "Grilled Chicken Breast",
            "recipe_author": "Test Chef",
            "recipe_book": "Quick & Healthy",
            "page_reference": "15",
            "servings": 1,
            "instructions": "1. Season chicken breast with salt, pepper, and herbs. 2. Heat grill to medium-high. 3. Grill chicken for 6-7 minutes per side until internal temp reaches 165°F. 4. Let rest for 5 minutes before serving.",
            "ingredients": ["1 chicken breast (6 oz)", "1 tsp olive oil", "1/2 tsp salt", "1/4 tsp black pepper", "1 tsp mixed herbs"],
            "ingredients_original": ["1 chicken breast (6 oz)", "1 tsp olive oil", "1/2 tsp salt", "1/4 tsp black pepper", "1 tsp mixed herbs"],
            "main_protein": ["chicken"],
            "calories_per_serving": 250,
            "macro_nutrients": {"protein_g": 35, "fat_g": 8, "carbohydrates_g": 2}
        },
        {
            "recipe_name": "Caesar Salad",
            "recipe_author": "Test Chef",
            "recipe_book": "Quick & Healthy",
            "page_reference": "23",
            "servings": 1,
            "instructions": "1. Wash and chop romaine lettuce. 2. Mix dressing ingredients. 3. Toss lettuce with dressing. 4. Top with croutons and parmesan.",
            "ingredients": ["2 cups romaine lettuce", "2 tbsp caesar dressing", "1/4 cup croutons", "2 tbsp parmesan cheese"],
            "ingredients_original": ["2 cups romaine lettuce", "2 tbsp caesar dressing", "1/4 cup croutons", "2 tbsp parmesan cheese"],
            "main_protein": [],
            "calories_per_serving": 220,
            "macro_nutrients": {"protein_g": 8, "fat_g": 15, "carbohydrates_g": 12}
        },
        {
            "recipe_name": "Salmon with Vegetables",
            "recipe_author": "Test Chef",
            "recipe_book": "Quick & Healthy",
            "page_reference": "45",
            "servings": 1,
            "instructions": "1. Season salmon with lemon, salt, and pepper. 2. Heat olive oil in pan. 3. Cook salmon 4-5 minutes per side. 4. Steam vegetables and serve alongside.",
            "ingredients": ["6 oz salmon fillet", "1 cup mixed vegetables", "1 tbsp olive oil", "1 lemon wedge", "salt and pepper to taste"],
            "ingredients_original": ["6 oz salmon fillet", "1 cup mixed vegetables", "1 tbsp olive oil", "1 lemon wedge", "salt and pepper to taste"],
            "main_protein": ["salmon"],
            "calories_per_serving": 380,
            "macro_nutrients": {"protein_g": 32, "fat_g": 22, "carbohydrates_g": 8}
        },
        {
            "recipe_name": "Vegetable Stir Fry",
            "recipe_author": "Test Chef",
            "recipe_book": "Quick & Healthy",
            "page_reference": "67",
            "servings": 1,
            "instructions": "1. Heat oil in wok or large pan. 2. Add vegetables starting with hardest ones. 3. Stir fry for 5-7 minutes. 4. Add sauce and cook 2 more minutes.",
            "ingredients": ["2 cups mixed vegetables", "1 tbsp oil", "2 tbsp soy sauce", "1 tsp garlic", "1 tsp ginger"],
            "ingredients_original": ["2 cups mixed vegetables", "1 tbsp oil", "2 tbsp soy sauce", "1 tsp garlic", "1 tsp ginger"],
            "main_protein": [],
            "calories_per_serving": 180,
            "macro_nutrients": {"protein_g": 6, "fat_g": 8, "carbohydrates_g": 22}
        },
        {
            "recipe_name": "Greek Yogurt Parfait",
            "recipe_author": "Test Chef",
            "recipe_book": "Quick & Healthy",
            "page_reference": "89",
            "servings": 1,
            "instructions": "1. Layer yogurt in a glass. 2. Add berries. 3. Add granola. 4. Repeat layers. 5. Drizzle with honey.",
            "ingredients": ["1 cup Greek yogurt", "1/2 cup mixed berries", "1/4 cup granola", "1 tbsp honey"],
            "ingredients_original": ["1 cup Greek yogurt", "1/2 cup mixed berries", "1/4 cup granola", "1 tbsp honey"],
            "main_protein": [],
            "calories_per_serving": 280,
            "macro_nutrients": {"protein_g": 18, "fat_g": 6, "carbohydrates_g": 38}
        }
    ]
    
    async with AsyncSessionLocal() as db:
        for recipe_data in test_recipes:
            recipe = Recipe(
                id=uuid.uuid4(),
                **recipe_data,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            db.add(recipe)
        
        await db.commit()
        print(f"Added {len(test_recipes)} test recipes to the database!")


if __name__ == "__main__":
    asyncio.run(add_test_recipes())