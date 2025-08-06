import json
from typing import Any

import openai
from openai import AsyncOpenAI

from app.core.config import settings
from app.services.llm.base import BaseLLMService


class OpenAIService(BaseLLMService):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = settings.LLM_MODEL

    async def extract_recipe(self, pdf_content: bytes) -> dict[str, Any]:
        system_prompt = """You are a recipe extraction expert. Extract recipe information from the provided text and return it as a JSON object.

IMPORTANT: All ingredient quantities must be converted to single-serving amounts. If the recipe serves multiple people, divide all quantities by the number of servings.

Return the data in this exact JSON schema:
{
    "recipeName": "string",
    "recipeAuthor": "string or null",
    "recipeBook": "string or null",
    "pageReference": "string or null",
    "servings": "integer (original servings)",
    "instructions": "string",
    "ingredients": ["list of strings with single-serving quantities"],
    "ingredientsOriginal": ["list of strings with original quantities"],
    "mainProtein": ["list of main proteins"],
    "caloriesPerServing": "integer",
    "macroNutrients": {
        "protein_g": "integer",
        "fat_g": "integer",
        "carbohydrates_g": "integer"
    }
}

If no valid recipe is detected, return: {"error": "No Recipe Detected"}

Example transformation:
- Original: "2 cups flour (serves 4)"
- Single serving: "1/2 cup flour"
"""

        try:
            # Convert PDF content to text (simplified - in production use proper PDF parsing)
            text_content = pdf_content.decode('utf-8', errors='ignore')
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract recipe from this text:\n\n{text_content}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=2000
            )

            result = json.loads(response.choices[0].message.content)
            
            if "error" in result:
                raise ValueError(result["error"])
                
            return result

        except Exception as e:
            raise Exception(f"Failed to extract recipe: {str(e)}")

    async def extract_table_of_contents(self, pdf_content: bytes) -> dict[str, str]:
        system_prompt = """You are an expert at finding and extracting table of contents from recipe books.
        
Look for the table of contents and return a JSON object mapping recipe names to their page numbers.

Example output:
{
    "Spaghetti Carbonara": "65-67",
    "Chicken Parmesan": "81",
    "Caesar Salad": "23"
}

If no table of contents is found, return: {"error": "No table of contents found"}
"""

        try:
            text_content = pdf_content.decode('utf-8', errors='ignore')
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Extract table of contents from this text:\n\n{text_content}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=2000
            )

            result = json.loads(response.choices[0].message.content)
            
            if "error" in result:
                raise ValueError(result["error"])
                
            return result

        except Exception as e:
            raise Exception(f"Failed to extract table of contents: {str(e)}")

    async def calculate_nutrition(self, ingredients: list[str], servings: int) -> dict[str, Any]:
        system_prompt = """You are a nutrition expert. Calculate the nutritional information for the given ingredients.

Return the data in this JSON format:
{
    "caloriesPerServing": "integer",
    "macroNutrients": {
        "protein_g": "integer",
        "fat_g": "integer",
        "carbohydrates_g": "integer"
    }
}

Provide reasonable estimates based on common nutritional values. The values should be per single serving.
"""

        try:
            ingredients_text = "\n".join(ingredients)
            
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Calculate nutrition for these ingredients (serves {servings}):\n\n{ingredients_text}"}
                ],
                response_format={"type": "json_object"},
                temperature=0.1,
                max_tokens=500
            )

            result = json.loads(response.choices[0].message.content)
            return result

        except Exception as e:
            raise Exception(f"Failed to calculate nutrition: {str(e)}")