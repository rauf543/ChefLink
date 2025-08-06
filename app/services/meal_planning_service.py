from typing import Dict, List, Optional, Tuple
from datetime import date, timedelta
import random

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Recipe, MealType, User
from app.services.recipe_service import RecipeService


class MealPlanningService:
    """Service for intelligent meal planning with calorie/macro allocation."""
    
    # Default meal distribution percentages
    DEFAULT_MEAL_DISTRIBUTION = {
        MealType.BREAKFAST: 0.25,  # 25% of daily calories
        MealType.LUNCH: 0.35,       # 35% of daily calories
        MealType.DINNER: 0.35,      # 35% of daily calories
        MealType.SNACK: 0.05        # 5% of daily calories
    }
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.recipe_service = RecipeService(db)
    
    async def create_intelligent_meal_plan(
        self,
        user: User,
        start_date: date,
        days: int = 7,
        include_snacks: bool = True
    ) -> List[Dict]:
        """Create an intelligent meal plan based on user preferences and nutritional goals."""
        
        # Get user's dietary preferences
        dietary_prefs = user.dietary_preferences or {}
        calorie_target = dietary_prefs.get("calorie_target", 2000)  # Default 2000 cal
        macro_targets = dietary_prefs.get("macro_targets", {
            "protein_g": 50,
            "fat_g": 65,
            "carbs_g": 275
        })
        restrictions = dietary_prefs.get("restrictions", [])
        allergies = dietary_prefs.get("allergies", [])
        dislikes = dietary_prefs.get("dislikes", [])
        
        # Calculate per-meal targets
        meal_targets = self._calculate_meal_targets(calorie_target, macro_targets, include_snacks)
        
        # Get all suitable recipes
        suitable_recipes = await self._get_suitable_recipes(restrictions, allergies, dislikes)
        
        # Group recipes by meal type suitability
        breakfast_recipes = [r for r in suitable_recipes if self._is_breakfast_suitable(r)]
        lunch_recipes = [r for r in suitable_recipes if self._is_lunch_suitable(r)]
        dinner_recipes = [r for r in suitable_recipes if self._is_dinner_suitable(r)]
        snack_recipes = [r for r in suitable_recipes if self._is_snack_suitable(r)]
        
        # Plan meals for each day
        meal_plans = []
        recent_proteins = []  # Track recent proteins to avoid repetition
        
        for day_offset in range(days):
            current_date = start_date + timedelta(days=day_offset)
            
            # Plan each meal type
            for meal_type, targets in meal_targets.items():
                if meal_type == MealType.SNACK and not include_snacks:
                    continue
                
                # Select appropriate recipe pool
                if meal_type == MealType.BREAKFAST:
                    recipe_pool = breakfast_recipes
                elif meal_type == MealType.LUNCH:
                    recipe_pool = lunch_recipes
                elif meal_type == MealType.DINNER:
                    recipe_pool = dinner_recipes
                else:
                    recipe_pool = snack_recipes
                
                # Find best matching recipe
                recipe = await self._select_best_recipe(
                    recipe_pool,
                    targets,
                    recent_proteins,
                    meal_type
                )
                
                if recipe:
                    meal_plans.append({
                        "date": current_date.isoformat(),
                        "meal_type": meal_type.value,
                        "recipe_id": str(recipe.id),
                        "servings": 1
                    })
                    
                    # Track main proteins to avoid repetition
                    if meal_type in [MealType.LUNCH, MealType.DINNER]:
                        recent_proteins.extend(recipe.main_protein)
                        # Keep only last 4 main meals' proteins
                        recent_proteins = recent_proteins[-4:]
        
        return meal_plans
    
    def _calculate_meal_targets(
        self,
        daily_calories: int,
        daily_macros: Dict[str, int],
        include_snacks: bool
    ) -> Dict[MealType, Dict[str, int]]:
        """Calculate nutritional targets for each meal type."""
        targets = {}
        
        # Adjust distribution if no snacks
        distribution = self.DEFAULT_MEAL_DISTRIBUTION.copy()
        if not include_snacks:
            # Redistribute snack calories to other meals
            snack_portion = distribution[MealType.SNACK]
            del distribution[MealType.SNACK]
            # Add evenly to remaining meals
            extra_per_meal = snack_portion / len(distribution)
            for meal_type in distribution:
                distribution[meal_type] += extra_per_meal
        
        # Calculate targets for each meal
        for meal_type, percentage in distribution.items():
            targets[meal_type] = {
                "calories": int(daily_calories * percentage),
                "protein_g": int(daily_macros["protein_g"] * percentage),
                "fat_g": int(daily_macros["fat_g"] * percentage),
                "carbs_g": int(daily_macros["carbs_g"] * percentage)
            }
        
        return targets
    
    async def _get_suitable_recipes(
        self,
        restrictions: List[str],
        allergies: List[str],
        dislikes: List[str]
    ) -> List[Recipe]:
        """Get all recipes that match user's dietary restrictions."""
        query = select(Recipe)
        
        # For now, get all recipes and filter in memory
        # In production, this would use more sophisticated filtering
        result = await self.db.execute(query)
        all_recipes = result.scalars().all()
        
        suitable_recipes = []
        for recipe in all_recipes:
            # Check restrictions (simplified - in production would parse ingredients)
            if self._matches_restrictions(recipe, restrictions, allergies, dislikes):
                suitable_recipes.append(recipe)
        
        return suitable_recipes
    
    def _matches_restrictions(
        self,
        recipe: Recipe,
        restrictions: List[str],
        allergies: List[str],
        dislikes: List[str]
    ) -> bool:
        """Check if recipe matches dietary restrictions."""
        # Simplified implementation - in production would use NLP to analyze ingredients
        ingredients_text = " ".join(recipe.ingredients).lower()
        
        # Check allergies (strict)
        for allergy in allergies:
            if allergy.lower() in ingredients_text:
                return False
        
        # Check dislikes (strict for main ingredients)
        for dislike in dislikes:
            if dislike.lower() in recipe.recipe_name.lower():
                return False
            # Check if it's a main protein
            if any(dislike.lower() in protein.lower() for protein in recipe.main_protein):
                return False
        
        # Check dietary restrictions (simplified)
        if "vegetarian" in restrictions:
            meat_keywords = ["chicken", "beef", "pork", "fish", "salmon", "tuna", "shrimp"]
            if any(keyword in ingredients_text for keyword in meat_keywords):
                return False
        
        if "vegan" in restrictions:
            animal_keywords = ["chicken", "beef", "pork", "fish", "egg", "milk", "cheese", "butter", "cream"]
            if any(keyword in ingredients_text for keyword in animal_keywords):
                return False
        
        if "gluten-free" in restrictions:
            gluten_keywords = ["wheat", "flour", "bread", "pasta", "noodles"]
            if any(keyword in ingredients_text for keyword in gluten_keywords):
                return False
        
        return True
    
    def _is_breakfast_suitable(self, recipe: Recipe) -> bool:
        """Check if recipe is suitable for breakfast."""
        breakfast_keywords = ["egg", "oatmeal", "pancake", "waffle", "cereal", "toast", "smoothie", "yogurt"]
        name_lower = recipe.recipe_name.lower()
        return any(keyword in name_lower for keyword in breakfast_keywords) or recipe.calories_per_serving < 600
    
    def _is_lunch_suitable(self, recipe: Recipe) -> bool:
        """Check if recipe is suitable for lunch."""
        # Most recipes are suitable for lunch
        return 400 <= recipe.calories_per_serving <= 800
    
    def _is_dinner_suitable(self, recipe: Recipe) -> bool:
        """Check if recipe is suitable for dinner."""
        # Most recipes are suitable for dinner
        return 500 <= recipe.calories_per_serving <= 900
    
    def _is_snack_suitable(self, recipe: Recipe) -> bool:
        """Check if recipe is suitable as a snack."""
        return recipe.calories_per_serving < 300
    
    async def _select_best_recipe(
        self,
        recipe_pool: List[Recipe],
        targets: Dict[str, int],
        recent_proteins: List[str],
        meal_type: MealType
    ) -> Optional[Recipe]:
        """Select the best matching recipe for the given targets."""
        if not recipe_pool:
            return None
        
        # Filter out recently used proteins (for main meals)
        if meal_type in [MealType.LUNCH, MealType.DINNER] and recent_proteins:
            filtered_pool = []
            for recipe in recipe_pool:
                # Check if any of the recipe's main proteins were used recently
                if not any(protein in recent_proteins[-2:] for protein in recipe.main_protein):
                    filtered_pool.append(recipe)
            # Use filtered pool if it has options, otherwise use original
            if filtered_pool:
                recipe_pool = filtered_pool
        
        # Score recipes based on nutritional match
        scored_recipes = []
        for recipe in recipe_pool:
            score = self._calculate_recipe_score(recipe, targets)
            scored_recipes.append((score, recipe))
        
        # Sort by score (lower is better)
        scored_recipes.sort(key=lambda x: x[0])
        
        # Add some randomness - pick from top 5 matches
        top_matches = scored_recipes[:5]
        if top_matches:
            return random.choice(top_matches)[1]
        
        return None
    
    def _calculate_recipe_score(self, recipe: Recipe, targets: Dict[str, int]) -> float:
        """Calculate how well a recipe matches the nutritional targets."""
        # Calculate percentage differences for each metric
        calorie_diff = abs(recipe.calories_per_serving - targets["calories"]) / targets["calories"]
        protein_diff = abs(recipe.macro_nutrients.get("protein_g", 0) - targets["protein_g"]) / targets["protein_g"]
        
        # Weight calories more heavily
        score = (calorie_diff * 2) + protein_diff
        
        return score