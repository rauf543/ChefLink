"""
Unified tool executor that handles tool execution across different contexts.
Eliminates duplication between family_v2 and family_v2_agentic handlers.
"""
from typing import Dict, Any, Optional, List
from uuid import UUID
from datetime import datetime, timedelta
import logging
import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, Recipe, MealPlan
from app.services.recipe_service import RecipeService
from app.services.meal_planning_service import MealPlanningService
from app.services.nutrition_service import NutritionService
from app.core.tools.registry import get_tool_registry

logger = logging.getLogger(__name__)


class ToolExecutor:
    """
    Centralized tool executor that handles all tool executions.
    Provides a clean separation between tool definition and execution.
    """
    
    def __init__(
        self,
        db_session: AsyncSession,
        user: User,
        recipe_service: Optional[RecipeService] = None,
        meal_planning_service: Optional[MealPlanningService] = None,
        nutrition_service: Optional[NutritionService] = None
    ):
        self.db = db_session
        self.user = user
        
        # Initialize services with dependency injection
        self.recipe_service = recipe_service or RecipeService(db_session)
        self.meal_planning_service = meal_planning_service or MealPlanningService(
            db_session, 
            self.recipe_service
        )
        self.nutrition_service = nutrition_service or NutritionService()
        
        # Register executors for each tool
        self._register_executors()
    
    def _register_executors(self):
        """Register executor functions for all tools"""
        registry = get_tool_registry()
        
        # Meal Planning Tools
        registry.attach_executor("create_meal_plan", self._execute_create_meal_plan)
        registry.attach_executor("update_meal_plan", self._execute_update_meal_plan)
        registry.attach_executor("get_meal_plans", self._execute_get_meal_plans)
        
        # Recipe Search Tools
        registry.attach_executor("search_recipes", self._execute_search_recipes)
        registry.attach_executor("get_recipe_details", self._execute_get_recipe_details)
        
        # Nutrition Tools
        registry.attach_executor("analyze_nutrition", self._execute_analyze_nutrition)
        
        # User Preference Tools
        registry.attach_executor("update_dietary_preferences", self._execute_update_preferences)
        registry.attach_executor("get_user_preferences", self._execute_get_preferences)
    
    async def execute(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a tool by name with given parameters.
        
        Args:
            tool_name: Name of the tool to execute
            parameters: Parameters for the tool
            
        Returns:
            Tool execution result
            
        Raises:
            ValueError: If tool not found or execution fails
        """
        registry = get_tool_registry()
        tool = registry.get_tool(tool_name)
        
        if not tool:
            raise ValueError(f"Tool '{tool_name}' not found")
        
        if not tool.executor:
            raise ValueError(f"No executor registered for tool '{tool_name}'")
        
        try:
            # Validate parameters against tool definition
            self._validate_parameters(tool, parameters)
            
            # Execute the tool
            result = await tool.executor(parameters)
            
            return {
                "success": True,
                "result": result
            }
        except Exception as e:
            logger.error(f"Tool execution failed for {tool_name}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _validate_parameters(self, tool, parameters: Dict[str, Any]):
        """Validate parameters against tool definition"""
        # Check required parameters
        for param in tool.parameters:
            if param.required and param.name not in parameters:
                raise ValueError(f"Missing required parameter: {param.name}")
            
            # Validate enum values
            if param.enum and param.name in parameters:
                if parameters[param.name] not in param.enum:
                    raise ValueError(
                        f"Invalid value for {param.name}: {parameters[param.name]}. "
                        f"Must be one of: {param.enum}"
                    )
    
    # Tool Execution Methods
    
    async def _execute_create_meal_plan(self, params: Dict[str, Any]) -> Dict:
        """Execute create_meal_plan tool"""
        date_str = params["date"]
        meals = params["meals"]
        
        # Parse date
        meal_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # Create meal plans
        created_plans = []
        for meal_data in meals:
            recipe = await self.recipe_service.get_recipe(UUID(meal_data["recipe_id"]))
            if not recipe:
                continue
            
            meal_plan = MealPlan(
                user_id=self.user.id,
                recipe_id=recipe.id,
                date=meal_date,
                meal_type=meal_data["meal_type"],
                servings=meal_data.get("servings", 1)
            )
            
            self.db.add(meal_plan)
            created_plans.append({
                "meal_type": meal_data["meal_type"],
                "recipe_name": recipe.recipe_name,
                "servings": meal_data.get("servings", 1)
            })
        
        await self.db.commit()
        
        return {
            "date": date_str,
            "meals_created": created_plans
        }
    
    async def _execute_update_meal_plan(self, params: Dict[str, Any]) -> Dict:
        """Execute update_meal_plan tool"""
        date_str = params["date"]
        meal_type = params["meal_type"]
        recipe_id = params["recipe_id"]
        servings = params.get("servings", 1)
        
        # Parse date
        meal_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # Find existing meal plan
        existing = await self.db.query(MealPlan).filter(
            MealPlan.user_id == self.user.id,
            MealPlan.date == meal_date,
            MealPlan.meal_type == meal_type
        ).first()
        
        if existing:
            # Update existing
            existing.recipe_id = UUID(recipe_id)
            existing.servings = servings
        else:
            # Create new
            meal_plan = MealPlan(
                user_id=self.user.id,
                recipe_id=UUID(recipe_id),
                date=meal_date,
                meal_type=meal_type,
                servings=servings
            )
            self.db.add(meal_plan)
        
        await self.db.commit()
        
        # Get recipe details for response
        recipe = await self.recipe_service.get_recipe(UUID(recipe_id))
        
        return {
            "date": date_str,
            "meal_type": meal_type,
            "recipe_name": recipe.recipe_name if recipe else "Unknown",
            "servings": servings,
            "updated": bool(existing)
        }
    
    async def _execute_get_meal_plans(self, params: Dict[str, Any]) -> Dict:
        """Execute get_meal_plans tool"""
        # Determine date range
        if "start_date" in params and "end_date" in params:
            start_date = datetime.strptime(params["start_date"], "%Y-%m-%d").date()
            end_date = datetime.strptime(params["end_date"], "%Y-%m-%d").date()
        else:
            days = params.get("days", 7)
            start_date = datetime.now().date()
            end_date = start_date + timedelta(days=days)
        
        # Query meal plans
        meal_plans = await self.meal_planning_service.get_user_meal_plans(
            self.user.id,
            start_date,
            end_date
        )
        
        # Format response
        plans_by_date = {}
        for plan in meal_plans:
            date_str = plan.date.strftime("%Y-%m-%d")
            if date_str not in plans_by_date:
                plans_by_date[date_str] = []
            
            plans_by_date[date_str].append({
                "meal_type": plan.meal_type,
                "recipe_name": plan.recipe.recipe_name,
                "servings": plan.servings,
                "calories": plan.recipe.calories_per_serving * plan.servings
            })
        
        return {
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "meal_plans": plans_by_date
        }
    
    async def _execute_search_recipes(self, params: Dict[str, Any]) -> Dict:
        """Execute search_recipes tool"""
        # Extract search parameters
        search_params = {
            "query": params.get("query"),
            "main_protein": params.get("main_protein"),
            "max_calories": params.get("max_calories"),
            "min_protein": params.get("min_protein"),
            "limit": params.get("limit", 10)
        }
        
        # Remove None values
        search_params = {k: v for k, v in search_params.items() if v is not None}
        
        # Search recipes
        recipes = await self.recipe_service.search_recipes(**search_params)
        
        # Format response
        recipe_results = []
        for recipe in recipes:
            recipe_results.append({
                "id": str(recipe.id),
                "name": recipe.recipe_name,
                "author": recipe.recipe_author,
                "calories": recipe.calories_per_serving,
                "protein": recipe.macro_nutrients.get("protein_g", 0) if recipe.macro_nutrients else 0,
                "main_protein": recipe.main_protein
            })
        
        return {
            "count": len(recipe_results),
            "recipes": recipe_results
        }
    
    async def _execute_get_recipe_details(self, params: Dict[str, Any]) -> Dict:
        """Execute get_recipe_details tool"""
        recipe_id = UUID(params["recipe_id"])
        
        recipe = await self.recipe_service.get_recipe(recipe_id)
        
        if not recipe:
            raise ValueError(f"Recipe {recipe_id} not found")
        
        return {
            "id": str(recipe.id),
            "name": recipe.recipe_name,
            "author": recipe.recipe_author,
            "book": recipe.recipe_book,
            "page": recipe.page_reference,
            "servings": recipe.servings,
            "calories": recipe.calories_per_serving,
            "macro_nutrients": recipe.macro_nutrients,
            "ingredients": recipe.ingredients,
            "instructions": recipe.instructions,
            "main_protein": recipe.main_protein
        }
    
    async def _execute_analyze_nutrition(self, params: Dict[str, Any]) -> Dict:
        """Execute analyze_nutrition tool"""
        date_str = params["date"]
        meal_type = params.get("meal_type", "all")
        
        meal_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        
        # Get meal plans for the date
        meal_plans = await self.meal_planning_service.get_user_meal_plans(
            self.user.id,
            meal_date,
            meal_date
        )
        
        # Filter by meal type if specified
        if meal_type != "all":
            meal_plans = [mp for mp in meal_plans if mp.meal_type == meal_type]
        
        # Calculate nutrition
        total_nutrition = {
            "calories": 0,
            "protein_g": 0,
            "fat_g": 0,
            "carbohydrates_g": 0
        }
        
        meal_breakdown = []
        for plan in meal_plans:
            recipe = plan.recipe
            if recipe.macro_nutrients:
                meal_nutrition = {
                    "meal_type": plan.meal_type,
                    "recipe_name": recipe.recipe_name,
                    "servings": plan.servings,
                    "calories": recipe.calories_per_serving * plan.servings,
                    "protein_g": recipe.macro_nutrients.get("protein_g", 0) * plan.servings,
                    "fat_g": recipe.macro_nutrients.get("fat_g", 0) * plan.servings,
                    "carbohydrates_g": recipe.macro_nutrients.get("carbohydrates_g", 0) * plan.servings
                }
                
                meal_breakdown.append(meal_nutrition)
                
                # Add to totals
                total_nutrition["calories"] += meal_nutrition["calories"]
                total_nutrition["protein_g"] += meal_nutrition["protein_g"]
                total_nutrition["fat_g"] += meal_nutrition["fat_g"]
                total_nutrition["carbohydrates_g"] += meal_nutrition["carbohydrates_g"]
        
        return {
            "date": date_str,
            "meal_type": meal_type,
            "total_nutrition": total_nutrition,
            "meal_breakdown": meal_breakdown
        }
    
    async def _execute_update_preferences(self, params: Dict[str, Any]) -> Dict:
        """Execute update_dietary_preferences tool"""
        preferences = params["preferences"]
        
        # Update user preferences
        if not self.user.dietary_preferences:
            self.user.dietary_preferences = {}
        
        self.user.dietary_preferences.update(preferences)
        
        await self.db.commit()
        await self.db.refresh(self.user)
        
        return {
            "updated": True,
            "preferences": self.user.dietary_preferences
        }
    
    async def _execute_get_preferences(self, params: Dict[str, Any]) -> Dict:
        """Execute get_user_preferences tool"""
        return {
            "user_name": self.user.name,
            "dietary_preferences": self.user.dietary_preferences or {},
            "role": self.user.role.value
        }