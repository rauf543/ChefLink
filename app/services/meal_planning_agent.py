import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.schemas.recipe import RecipeSearch
from app.database.models import MealPlan, MealPlanStatus, MealType, Recipe, User
from app.services.llm.factory import get_llm_service
from app.services.recipe_service import RecipeService

logger = logging.getLogger(__name__)


class MealPlanningAgent:
    """AI agent for intelligent meal planning."""
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self.llm_service = get_llm_service()
        self.recipe_service = RecipeService(db)
        
    async def create_meal_plan(
        self,
        user: User,
        duration_days: int,
        dietary_goals: Dict[str, Any],
        eating_habits: Dict[str, Any]
    ) -> List[MealPlan]:
        """Create a personalized meal plan for the user."""
        
        # Step 1: Analyze user requirements and create high-level structure
        plan_structure = await self._create_plan_structure(
            duration_days, dietary_goals, eating_habits
        )
        
        # Step 2: Search and assign recipes for each meal slot
        meal_plans = []
        start_date = date.today()
        
        for day_offset in range(duration_days):
            current_date = start_date + timedelta(days=day_offset)
            
            # Check if plans for this date are already locked
            if await self._is_date_locked(current_date):
                continue
                
            for meal_type, requirements in plan_structure['daily_meals'].items():
                # Search for appropriate recipe
                recipe = await self._find_recipe_for_slot(
                    requirements,
                    dietary_goals.get('blacklisted_ingredients', []),
                    meal_plans  # Pass existing plans to avoid repetition
                )
                
                if recipe:
                    meal_plan = MealPlan(
                        user_id=user.id,
                        date=current_date,
                        meal_type=MealType(meal_type.lower()),
                        recipe_id=recipe.id,
                        status=MealPlanStatus.UNLOCKED
                    )
                    self.db.add(meal_plan)
                    meal_plans.append(meal_plan)
                    
        await self.db.commit()
        return meal_plans
        
    async def modify_meal_plan(
        self,
        user: User,
        modification_request: str
    ) -> Dict[str, Any]:
        """Modify existing meal plan based on user request."""
        
        # Use Claude to understand the modification request
        system_prompt = """You are a meal planning assistant. Analyze the user's modification request and return a JSON object with the following structure:
{
    "action": "swap|remove|add",
    "target": {
        "date": "YYYY-MM-DD or relative date",
        "meal_type": "breakfast|lunch|dinner|snack"
    },
    "constraints": {
        "calories_max": int or null,
        "protein_min": int or null,
        "main_protein": "string or null",
        "exclude_ingredients": []
    }
}
"""

        try:
            response = await self.llm_service.client.messages.create(
                model=self.llm_service.model,
                max_tokens=1000,
                temperature=0.1,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": f"Analyze this meal plan modification request: {modification_request}"
                    }
                ],
                thinking={
                    "type": "enabled",
                    "budget_tokens": 4000
                }
            )
            
            # Parse Claude's response
            modification_data = json.loads(response.content[0].text)
            
            # Execute the modification
            result = await self._execute_modification(user, modification_data)
            return result
            
        except Exception as e:
            logger.error(f"Error modifying meal plan: {str(e)}")
            return {"success": False, "error": str(e)}
            
    async def _create_plan_structure(
        self,
        duration_days: int,
        dietary_goals: Dict[str, Any],
        eating_habits: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Create high-level meal plan structure."""
        
        system_prompt = """You are a nutrition expert. Create a daily meal plan structure based on the user's requirements.

Return a JSON object with this structure:
{
    "daily_meals": {
        "breakfast": {"calories": int, "protein_g": int},
        "lunch": {"calories": int, "protein_g": int},
        "dinner": {"calories": int, "protein_g": int},
        "snack": {"calories": int, "protein_g": int}  // optional
    },
    "total_daily": {
        "calories": int,
        "protein_g": int,
        "fat_g": int,
        "carbohydrates_g": int
    }
}

The sum of meal calories should equal the daily target. Remove snack if user prefers 3 meals.
"""

        prompt = f"""Create a meal plan structure for:
Duration: {duration_days} days
Dietary Goals: {json.dumps(dietary_goals)}
Eating Habits: {json.dumps(eating_habits)}
"""

        try:
            response = await self.llm_service.client.messages.create(
                model=self.llm_service.model,
                max_tokens=1000,
                temperature=0.1,
                system=system_prompt,
                messages=[
                    {"role": "user", "content": prompt}
                ],
                thinking={
                    "type": "enabled",
                    "budget_tokens": 6000
                }
            )
            
            # Extract JSON from response
            response_text = response.content[0].text
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            json_str = response_text[start:end]
            
            return json.loads(json_str)
            
        except Exception as e:
            logger.error(f"Error creating plan structure: {str(e)}")
            # Return default structure
            return {
                "daily_meals": {
                    "breakfast": {"calories": 400, "protein_g": 20},
                    "lunch": {"calories": 600, "protein_g": 30},
                    "dinner": {"calories": 800, "protein_g": 40}
                },
                "total_daily": {
                    "calories": 1800,
                    "protein_g": 90,
                    "fat_g": 60,
                    "carbohydrates_g": 180
                }
            }
            
    async def _find_recipe_for_slot(
        self,
        requirements: Dict[str, Any],
        blacklisted_ingredients: List[str],
        existing_plans: List[MealPlan]
    ) -> Recipe | None:
        """Find appropriate recipe for a meal slot."""
        
        # Create search parameters based on requirements
        search_params = RecipeSearch(
            calories_min=int(requirements['calories'] * 0.8),
            calories_max=int(requirements['calories'] * 1.2),
            protein_min=int(requirements.get('protein_g', 0) * 0.8),
            randomize=True,
            limit=10
        )
        
        recipes = await self.recipe_service.search_recipes(search_params)
        
        # Filter out recipes with blacklisted ingredients
        if blacklisted_ingredients:
            recipes = [
                r for r in recipes
                if not any(
                    blacklist.lower() in ' '.join(r.ingredients).lower()
                    for blacklist in blacklisted_ingredients
                )
            ]
            
        # Avoid recipes already in recent plans
        recent_recipe_ids = {p.recipe_id for p in existing_plans[-7:]}
        recipes = [r for r in recipes if r.id not in recent_recipe_ids]
        
        return recipes[0] if recipes else None
        
    async def _is_date_locked(self, check_date: date) -> bool:
        """Check if meal plans for a date are locked."""
        result = await self.db.execute(
            select(MealPlan)
            .where(MealPlan.date == check_date)
            .where(MealPlan.status == MealPlanStatus.LOCKED)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None
        
    async def _execute_modification(
        self,
        user: User,
        modification_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a meal plan modification."""
        
        action = modification_data['action']
        target = modification_data['target']
        
        # Parse target date
        target_date = self._parse_date(target['date'])
        meal_type = MealType(target['meal_type'])
        
        if action == 'swap':
            # Find and replace the meal
            result = await self.db.execute(
                select(MealPlan)
                .where(MealPlan.user_id == user.id)
                .where(MealPlan.date == target_date)
                .where(MealPlan.meal_type == meal_type)
                .where(MealPlan.status == MealPlanStatus.UNLOCKED)
            )
            
            meal_plan = result.scalar_one_or_none()
            
            if not meal_plan:
                return {"success": False, "error": "Meal plan not found or is locked"}
                
            # Find new recipe
            constraints = modification_data.get('constraints', {})
            search_params = RecipeSearch(
                calories_max=constraints.get('calories_max'),
                protein_min=constraints.get('protein_min'),
                main_protein=constraints.get('main_protein'),
                randomize=True,
                limit=5
            )
            
            recipes = await self.recipe_service.search_recipes(search_params)
            
            if not recipes:
                return {"success": False, "error": "No suitable recipes found"}
                
            # Update meal plan
            meal_plan.recipe_id = recipes[0].id
            await self.db.commit()
            
            return {
                "success": True,
                "new_recipe": recipes[0].recipe_name,
                "message": f"Successfully swapped {meal_type.value} on {target_date}"
            }
            
        # Handle other actions (remove, add) similarly
        return {"success": False, "error": f"Action '{action}' not implemented"}
        
    def _parse_date(self, date_str: str) -> date:
        """Parse date string to date object."""
        if date_str == 'today':
            return date.today()
        elif date_str == 'tomorrow':
            return date.today() + timedelta(days=1)
        else:
            from datetime import datetime
            return datetime.strptime(date_str, '%Y-%m-%d').date()