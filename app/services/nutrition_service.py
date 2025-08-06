from typing import Any

from app.services.llm.factory import get_llm_service


class NutritionService:
    def __init__(self):
        self.llm_service = get_llm_service()
        
    async def calculate_nutrition(self, ingredients: list[str], servings: int) -> dict[str, Any]:
        """Calculate nutrition information for ingredients using Claude's capabilities."""
        # Claude Opus 4 has native web search and comprehensive nutritional knowledge
        nutrition_data = await self.llm_service.calculate_nutrition(ingredients, servings)
        return nutrition_data