import base64
import json
from typing import Any

import anthropic

from app.core.config import settings
from app.services.llm.base import BaseLLMService


class AnthropicService(BaseLLMService):
    def __init__(self):
        self.client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        self.model = settings.LLM_MODEL
        self.thinking_enabled = settings.LLM_THINKING_ENABLED
        self.thinking_budget = settings.LLM_THINKING_BUDGET

    async def extract_recipe(self, pdf_content: bytes) -> dict[str, Any]:
        system_prompt = """You are a recipe extraction expert. Extract recipe information from the provided PDF and return it as a JSON object.

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
            # Convert PDF to base64 for Claude's multimodal input
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            
            # Build common parameters
            create_params = {
                "model": self.model,
                "max_tokens": 16000 if self.thinking_enabled else 8000,
                "temperature": 1 if self.thinking_enabled else 0.1,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": "Extract the recipe from this PDF document. Analyze both text and any visual elements like charts or images."
                            }
                        ]
                    }
                ]
            }
            
            if self.thinking_enabled:
                # Add thinking and streaming for long operations
                create_params["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
                create_params["stream"] = True
                
                # Create streaming response
                stream = await self.client.messages.create(**create_params)
                
                # Collect the streamed response
                response_text = ""
                async for event in stream:
                    if event.type == "content_block_delta" and hasattr(event.delta, 'text'):
                        response_text += event.delta.text
                    elif event.type == "message_stop":
                        break
            else:
                # Non-streaming for regular mode
                message = await self.client.messages.create(**create_params)
                response_text = message.content[0].text
            # Try to find JSON in the response
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start != -1 and end != 0:
                json_str = response_text[start:end]
                result = json.loads(json_str)
            else:
                raise ValueError("No valid JSON found in response")
            
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
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
            
            # Build common parameters
            create_params = {
                "model": self.model,
                "max_tokens": 16000 if self.thinking_enabled else 8000,
                "temperature": 1 if self.thinking_enabled else 0.1,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "document",
                                "source": {
                                    "type": "base64",
                                    "media_type": "application/pdf",
                                    "data": pdf_base64
                                }
                            },
                            {
                                "type": "text",
                                "text": "Find and extract the table of contents from this PDF. Look for recipe names and their corresponding page numbers in the first 50 pages."
                            }
                        ]
                    }
                ]
            }
            
            if self.thinking_enabled:
                # Add thinking and streaming for long operations
                create_params["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
                create_params["stream"] = True
                
                # Create streaming response
                stream = await self.client.messages.create(**create_params)
                
                # Collect the streamed response
                response_text = ""
                async for event in stream:
                    if event.type == "content_block_delta" and hasattr(event.delta, 'text'):
                        response_text += event.delta.text
                    elif event.type == "message_stop":
                        break
            else:
                # Non-streaming for regular mode
                message = await self.client.messages.create(**create_params)
                response_text = message.content[0].text
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start != -1 and end != 0:
                json_str = response_text[start:end]
                result = json.loads(json_str)
            else:
                raise ValueError("No valid JSON found in response")
            
            if "error" in result:
                raise ValueError(result["error"])
                
            return result

        except Exception as e:
            raise Exception(f"Failed to extract table of contents: {str(e)}")

    async def calculate_nutrition(self, ingredients: list[str], servings: int) -> dict[str, Any]:
        system_prompt = """You are a nutrition expert. Calculate the nutritional information for the given ingredients.

IMPORTANT: You MUST search the web for accurate nutritional data for any ingredients where you don't have complete confidence in the values. Use your web search capability to find USDA nutritional databases, nutrition labels, or reliable nutrition websites.

Return the data in this JSON format:
{
    "caloriesPerServing": "integer",
    "macroNutrients": {
        "protein_g": "integer",
        "fat_g": "integer",
        "carbohydrates_g": "integer"
    }
}

The values should be per single serving (divide by the number of servings provided).
"""

        try:
            ingredients_text = "\n".join(ingredients)
            
            # Build common parameters with explicit web search instruction
            create_params = {
                "model": self.model,
                "max_tokens": 16000 if self.thinking_enabled else 4000,
                "temperature": 1 if self.thinking_enabled else 0.1,
                "system": system_prompt,
                "messages": [
                    {
                        "role": "user",
                        "content": f"Calculate nutrition for these ingredients (serves {servings} total). Use web search to find accurate nutritional data for any ingredients you're not certain about:\n\n{ingredients_text}\n\nRemember to divide all values by {servings} to get per-serving amounts."
                    }
                ]
            }
            
            if self.thinking_enabled:
                # Add thinking for better reasoning about nutrition
                create_params["thinking"] = {"type": "enabled", "budget_tokens": self.thinking_budget}
                create_params["stream"] = True
                
                # Create streaming response
                stream = await self.client.messages.create(**create_params)
                
                # Collect the streamed response
                response_text = ""
                async for event in stream:
                    if event.type == "content_block_delta" and hasattr(event.delta, 'text'):
                        response_text += event.delta.text
                    elif event.type == "message_stop":
                        break
            else:
                # Non-streaming for regular mode
                message = await self.client.messages.create(**create_params)
                response_text = message.content[0].text

            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            if start != -1 and end != 0:
                json_str = response_text[start:end]
                result = json.loads(json_str)
            else:
                raise ValueError("No valid JSON found in response")
                
            return result

        except Exception as e:
            raise Exception(f"Failed to calculate nutrition: {str(e)}")