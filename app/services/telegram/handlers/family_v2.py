import json
import logging
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from telegram import Update
from telegram.ext import ContextTypes

from app.core.schemas.recipe import RecipeSearch
from app.database.base import AsyncSessionLocal
from app.database.models import MealPlan, MealPlanStatus, MealType, Recipe, User
from app.services.llm.factory import get_llm_service
from app.services.meal_planning_service import MealPlanningService
from app.services.recipe_service import RecipeService
from app.services.telegram.utils import format_meal_plan_summary, get_user_by_telegram_id

logger = logging.getLogger(__name__)


class FamilyHandlersV2:
    """Enhanced handlers for family member users with full LLM integration."""
    
    def __init__(self):
        self.llm_service = get_llm_service()
        # Store conversation history per user
        self.conversation_history = {}
        # Token limits for context management
        self.max_context_tokens = 8000  # Total context window
        self.system_prompt_tokens = 500  # Approximate tokens for system prompt
        self.tools_tokens = 1500  # Approximate tokens for tool definitions
        self.response_tokens = 4000  # Reserved for response
        self.max_history_tokens = self.max_context_tokens - self.system_prompt_tokens - self.tools_tokens - self.response_tokens  # ~2000 tokens for history
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation of tokens (approximately 4 characters per token)."""
        return len(text) // 4
    
    def _get_conversation_history_with_limit(self, user_id: str, current_message: str) -> List[Dict[str, Any]]:
        """Get conversation history that fits within token limit."""
        if user_id not in self.conversation_history:
            return []
        
        # Start with current message tokens
        current_tokens = self._estimate_tokens(current_message)
        available_tokens = self.max_history_tokens - current_tokens
        
        # Build history from most recent backwards
        selected_history = []
        total_tokens = 0
        
        # Iterate through history in reverse (most recent first)
        for msg in reversed(self.conversation_history[user_id]):
            # Estimate tokens for this message
            msg_content = msg["content"]
            if isinstance(msg_content, str):
                msg_tokens = self._estimate_tokens(msg_content)
            elif isinstance(msg_content, list):
                # For tool responses, estimate conservatively
                msg_tokens = 200  # Rough estimate for tool responses
            else:
                msg_tokens = 50
            
            # Check if adding this message would exceed limit
            if total_tokens + msg_tokens > available_tokens:
                break
            
            selected_history.insert(0, msg)  # Insert at beginning to maintain order
            total_tokens += msg_tokens
        
        return selected_history
    
    def _clean_markdown_for_telegram(self, text: str) -> str:
        """Remove markdown formatting that doesn't work in Telegram."""
        # Remove bold markdown
        text = text.replace("**", "")
        # Remove italic markdown (single asterisks that aren't part of lists)
        # Be careful not to remove list markers like "* item"
        import re
        # Replace single asterisks that aren't at the start of a line or after newline
        text = re.sub(r'(?<!^)(?<!\n)\*([^\*\n]+)\*', r'\1', text)
        # Remove code blocks if they exist
        text = text.replace("```", "")
        return text
    
    def _trim_conversation_history(self, user_id: str) -> None:
        """Trim conversation history to stay within token limits."""
        if user_id not in self.conversation_history:
            return
        
        total_tokens = 0
        keep_index = 0
        
        # Calculate total tokens from end to beginning
        for i in range(len(self.conversation_history[user_id]) - 1, -1, -1):
            msg = self.conversation_history[user_id][i]
            msg_content = msg["content"]
            
            if isinstance(msg_content, str):
                msg_tokens = self._estimate_tokens(msg_content)
            elif isinstance(msg_content, list):
                msg_tokens = 200  # Conservative estimate for tool responses
            else:
                msg_tokens = 50
            
            total_tokens += msg_tokens
            
            # If we exceed the max history tokens, this is where we cut
            if total_tokens > self.max_history_tokens * 1.5:  # Allow 50% overflow before trimming
                keep_index = i + 1
                break
        
        # Trim the history if needed
        if keep_index > 0:
            self.conversation_history[user_id] = self.conversation_history[user_id][keep_index:]
        
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle all messages through Claude with tool access."""
        user_id = str(update.effective_user.id)
        
        async with AsyncSessionLocal() as db:
            user = await get_user_by_telegram_id(db, user_id)
            
            if not user or user.role.value != 'family_member':
                await update.message.reply_text(
                    "This feature is only available for family members."
                )
                return
            
            user_message = update.message.text
            
            # Get current meal plans for context
            meal_plans = await self._get_user_meal_plans(db, user.id)
            
            # Get available recipes
            recipes = await self._get_all_recipes(db)
            
            # Prepare context for Claude
            system_prompt = """You are ChefLink, a helpful meal planning assistant. You help users plan their meals, 
modify existing plans, search for recipes, and answer questions about nutrition and cooking.

You have access to the following tools:
1. create_meal_plan: Create meal plans for specified dates
2. update_meal_plan: Update existing meal plans
3. delete_meal_plan: Remove meal plans
4. search_recipes: Search for recipes by name, protein, or calories
5. get_recipe_details: Get full details about a specific recipe
6. update_dietary_preferences: Save user's dietary restrictions, allergies, and preferences

Current user context:
- User: {user_name}
- Total recipes available: {recipe_count}
- Current meal plans: {meal_plan_summary}
- Dietary preferences: {dietary_prefs}

When users mention dietary restrictions, allergies, or preferences (like "I'm vegetarian", "I'm allergic to nuts", 
"I want to eat 2000 calories a day"), use the update_dietary_preferences tool to save this information.

When creating meal plans:
- Consider the user's dietary preferences, restrictions, and calorie/macro targets
- Intelligently distribute calories across meals (typically: breakfast 25%, lunch 35%, dinner 35%, snacks 5%)
- Avoid repeating the same protein in consecutive days
- Match recipes to appropriate meal times (lighter for breakfast, heartier for dinner)

Be conversational and helpful. If users want to change something (like "no salmon two days in a row"), 
analyze their current plans and make the necessary adjustments.

Always think step by step about what the user wants and use tools accordingly."""

            # Format meal plan summary
            meal_plan_summary = self._format_meal_plan_context(meal_plans)
            
            # Format dietary preferences
            dietary_prefs = "None specified"
            if user.dietary_preferences:
                prefs = []
                if user.dietary_preferences.get("restrictions"):
                    prefs.append(f"Restrictions: {', '.join(user.dietary_preferences['restrictions'])}")
                if user.dietary_preferences.get("allergies"):
                    prefs.append(f"Allergies: {', '.join(user.dietary_preferences['allergies'])}")
                if user.dietary_preferences.get("calorie_target"):
                    prefs.append(f"Calorie target: {user.dietary_preferences['calorie_target']}")
                if prefs:
                    dietary_prefs = "; ".join(prefs)
            
            system_prompt = system_prompt.format(
                user_name=user.name,
                recipe_count=len(recipes),
                meal_plan_summary=meal_plan_summary,
                dietary_prefs=dietary_prefs
            )
            
            # Create tool definitions for Claude
            tools = [
                {
                    "name": "create_meal_plan",
                    "description": "Create meal plans for specified dates",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "plans": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                                        "meal_type": {"type": "string", "enum": ["breakfast", "lunch", "dinner", "snack"]},
                                        "recipe_id": {"type": "string", "description": "UUID of the recipe"},
                                        "servings": {"type": "integer", "default": 1}
                                    },
                                    "required": ["date", "meal_type", "recipe_id"]
                                }
                            }
                        },
                        "required": ["plans"]
                    }
                },
                {
                    "name": "update_meal_plan",
                    "description": "Update an existing meal plan",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "meal_plan_id": {"type": "string", "description": "UUID of the meal plan to update"},
                            "recipe_id": {"type": "string", "description": "New recipe UUID"},
                            "servings": {"type": "integer", "description": "New serving size"}
                        },
                        "required": ["meal_plan_id"]
                    }
                },
                {
                    "name": "delete_meal_plan",
                    "description": "Delete a meal plan",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "meal_plan_id": {"type": "string", "description": "UUID of the meal plan to delete"}
                        },
                        "required": ["meal_plan_id"]
                    }
                },
                {
                    "name": "search_recipes",
                    "description": "Search for recipes by various criteria",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "Recipe name to search for"},
                            "main_protein": {"type": "string", "description": "Main protein to filter by"},
                            "min_calories": {"type": "integer", "description": "Minimum calories per serving"},
                            "max_calories": {"type": "integer", "description": "Maximum calories per serving"},
                            "min_protein": {"type": "integer", "description": "Minimum protein in grams"},
                            "max_protein": {"type": "integer", "description": "Maximum protein in grams"},
                            "min_carbs": {"type": "integer", "description": "Minimum carbohydrates in grams"},
                            "max_carbs": {"type": "integer", "description": "Maximum carbohydrates in grams"},
                            "min_fat": {"type": "integer", "description": "Minimum fat in grams"},
                            "max_fat": {"type": "integer", "description": "Maximum fat in grams"},
                            "randomize": {"type": "boolean", "description": "Randomize results instead of alphabetical", "default": False},
                            "limit": {"type": "integer", "description": "Maximum number of results", "default": 10}
                        }
                    }
                },
                {
                    "name": "get_recipe_details",
                    "description": "Get full details about a specific recipe",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "recipe_id": {"type": "string", "description": "UUID of the recipe"}
                        },
                        "required": ["recipe_id"]
                    }
                },
                {
                    "name": "update_dietary_preferences",
                    "description": "Update user's dietary preferences (restrictions, allergies, preferences)",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "preferences": {
                                "type": "object",
                                "description": "Dietary preferences object",
                                "properties": {
                                    "restrictions": {"type": "array", "items": {"type": "string"}, "description": "Dietary restrictions (e.g., vegetarian, vegan, gluten-free)"},
                                    "allergies": {"type": "array", "items": {"type": "string"}, "description": "Food allergies"},
                                    "dislikes": {"type": "array", "items": {"type": "string"}, "description": "Foods the user dislikes"},
                                    "calorie_target": {"type": "integer", "description": "Daily calorie target"},
                                    "macro_targets": {
                                        "type": "object",
                                        "properties": {
                                            "protein_g": {"type": "integer"},
                                            "fat_g": {"type": "integer"},
                                            "carbs_g": {"type": "integer"}
                                        }
                                    }
                                }
                            }
                        },
                        "required": ["preferences"]
                    }
                }
            ]
            
            # Add recipe list to context
            recipe_list = []
            for recipe in recipes:
                recipe_list.append({
                    "id": str(recipe.id),
                    "name": recipe.recipe_name,
                    "calories": recipe.calories_per_serving,
                    "protein": recipe.macro_nutrients.get("protein_g", 0),
                    "main_protein": recipe.main_protein
                })
            
            # Get or initialize conversation history for this user
            if user_id not in self.conversation_history:
                self.conversation_history[user_id] = []
            
            # Build messages list with token-aware history
            messages = []
            
            # Get conversation history that fits within token limit
            selected_history = self._get_conversation_history_with_limit(user_id, user_message)
            
            # Add selected history, filtering out complex tool interactions
            for hist_msg in selected_history:
                # Skip messages with tool results to avoid format issues
                if hist_msg.get("role") == "user" and isinstance(hist_msg.get("content"), list):
                    continue
                # Skip assistant messages with tool calls
                if hist_msg.get("role") == "assistant" and isinstance(hist_msg.get("content"), list):
                    continue
                # Only include simple text messages
                if isinstance(hist_msg.get("content"), str):
                    messages.append({
                        "role": hist_msg["role"],
                        "content": hist_msg["content"]
                    })
            
            # Add current message
            current_message = {
                "role": "user",
                "content": user_message
            }
            
            # Include recipe list if it's the first message or we have room
            include_recipes = len(messages) == 0 or (
                len(messages) < 4 and self._estimate_tokens(json.dumps(recipe_list[:10])) < 200
            )
            
            if include_recipes:
                current_message["content"] += f"\n\nAvailable recipes (sample): {json.dumps(recipe_list[:10])}..."
            
            messages.append(current_message)
            
            # Call Claude with tools
            try:
                # Using the Anthropic messages API with tools
                response = await self.llm_service.client.messages.create(
                    model=self.llm_service.model,
                    max_tokens=4000,
                    temperature=0.7,
                    system=system_prompt,
                    messages=messages,
                    tools=tools,
                    tool_choice={"type": "auto"}
                )
                
                # Save user message to history
                self.conversation_history[user_id].append(current_message)
                
                # Process Claude's response and tool calls
                await self._process_claude_response(response, update, db, user, user_id)
                
            except Exception as e:
                logger.error(f"Error in LLM conversation: {str(e)}", exc_info=True)
                await update.message.reply_text(
                    "I'm having trouble understanding. Could you please rephrase?"
                )
    
    async def _process_claude_response(
        self, 
        response: Any, 
        update: Update, 
        db: AsyncSession,
        user: User,
        user_id: str
    ) -> None:
        """Process Claude's response including any tool calls."""
        
        # Extract text response
        text_response = ""
        tool_calls = []
        
        # Safely handle response content
        if not hasattr(response, 'content') or not response.content:
            logger.error("Response has no content")
            await update.message.reply_text("I encountered an error processing your request. Please try again.")
            return
        
        for content in response.content:
            if hasattr(content, 'type'):
                if content.type == "text":
                    text_response += content.text
                elif content.type == "tool_use":
                    tool_calls.append(content)
        
        # Execute tool calls if any
        tool_results = []
        for tool_call in tool_calls:
            result = await self._execute_tool_call(
                tool_call.name,
                tool_call.input,
                db,
                user
            )
            tool_results.append({
                "tool_use_id": tool_call.id,
                "content": json.dumps(result)
            })
        
        # Send initial text response if any
        if text_response and not tool_calls:
            # No tools, just send the response
            self.conversation_history[user_id].append({
                "role": "assistant",
                "content": text_response
            })
            cleaned_text = self._clean_markdown_for_telegram(text_response)
            await update.message.reply_text(cleaned_text)
        elif text_response and tool_calls:
            # Send the text before executing tools
            cleaned_text = self._clean_markdown_for_telegram(text_response)
            await update.message.reply_text(cleaned_text)
        
        # If there were tool calls, execute them and allow for agentic workflow
        if tool_results:
            # Save the full assistant response (including tool calls) to history
            self.conversation_history[user_id].append({
                "role": "assistant",
                "content": response.content
            })
            
            # Build a map of tool_use_id to tool name for safer access
            tool_map = {tool.id: tool.name for tool in tool_calls}
            
            # Process each tool result and potentially send intermediate messages
            tool_results_content = []
            for result in tool_results:
                tool_results_content.append({
                    "type": "tool_result",
                    "tool_use_id": result["tool_use_id"],
                    "content": result["content"]
                })
                
                # Parse the result to see if we should send an intermediate message
                try:
                    result_data = json.loads(result["content"])
                    tool_name = tool_map.get(result["tool_use_id"], "unknown")
                    
                    # Send intermediate updates based on tool results
                    if tool_name == "search_recipes" and "recipes" in result_data:
                        count = len(result_data["recipes"])
                        if count > 0:
                            await update.message.reply_text(f"I found {count} recipes that match your criteria. Let me analyze them...")
                    elif tool_name == "create_meal_plan" and "created" in result_data:
                        count = len(result_data["created"])
                        if count > 0:
                            await update.message.reply_text(f"I've successfully created {count} meal plan(s). Let me summarize what I've done...")
                    elif tool_name == "update_dietary_preferences" and result_data.get("updated"):
                        await update.message.reply_text("I've saved your dietary preferences. They'll be considered for all future meal planning.")
                except Exception as e:
                    logger.debug(f"Could not parse tool result: {e}")
                    pass  # If we can't parse the result, just continue
            
            # Save tool results to history
            self.conversation_history[user_id].append({
                "role": "user",
                "content": tool_results_content
            })
            
            # Build conversation for final response
            final_messages = []
            
            # Include the current exchange
            final_messages.append({
                "role": "user",
                "content": update.message.text
            })
            final_messages.append({
                "role": "assistant",
                "content": response.content
            })
            final_messages.append({
                "role": "user",
                "content": tool_results_content
            })
            
            # Get final response with more agentic system prompt
            system_prompt = """You are ChefLink, a helpful meal planning assistant. Based on the tool results:

1. Provide a clear, conversational summary of what you did
2. If you created meal plans, briefly mention the key meals
3. If you searched recipes, highlight 2-3 best options
4. Always be helpful and suggest next steps
5. Keep responses concise but informative

Remember: You're having a conversation, not writing a report."""
            
            try:
                final_response = await self.llm_service.client.messages.create(
                    model=self.llm_service.model,
                    max_tokens=2000,
                    temperature=0.7,
                    messages=final_messages,
                    system=system_prompt
                )
                
                # Extract final response text
                final_text = ""
                if hasattr(final_response, 'content') and final_response.content:
                    if hasattr(final_response.content[0], 'text'):
                        final_text = final_response.content[0].text
                    else:
                        final_text = str(final_response.content[0])
                        
            except Exception as e:
                logger.error(f"Error getting final response: {str(e)}", exc_info=True)
                # Provide a helpful fallback message based on what was done
                if tool_results_content:
                    # Try to summarize what was done based on tool results
                    try:
                        first_result = json.loads(tool_results_content[0]["content"])
                        if "recipes" in first_result:
                            count = len(first_result["recipes"])
                            if count > 0:
                                final_text = f"I found {count} recipes for you. Here are some options:\n"
                                for i, recipe in enumerate(first_result["recipes"][:3]):
                                    final_text += f"\n{i+1}. {recipe['name']} ({recipe['calories']} cal)"
                            else:
                                final_text = "I couldn't find any recipes matching your criteria. Try different search terms."
                        elif "created" in first_result:
                            final_text = f"I've successfully created {len(first_result['created'])} meal plan(s) for you."
                        elif "updated" in first_result:
                            final_text = "I've updated your meal plan as requested."
                        else:
                            final_text = "I've completed the requested task. Let me know if you need anything else!"
                    except:
                        final_text = "I've completed the requested actions. Is there anything else you'd like me to help with?"
                else:
                    final_text = "I've processed your request. Let me know if you need anything else!"
            
            # Always send a final message
            if final_text:
                self.conversation_history[user_id].append({
                    "role": "assistant",
                    "content": final_text
                })
                
                cleaned_text = self._clean_markdown_for_telegram(final_text)
                await update.message.reply_text(cleaned_text)
            else:
                # This should rarely happen, but just in case
                await update.message.reply_text("I've completed your request. How else can I help you?")
        
        # Trim history based on total tokens
        self._trim_conversation_history(user_id)
    
    async def _execute_tool_call(
        self,
        tool_name: str,
        tool_input: Dict[str, Any],
        db: AsyncSession,
        user: User
    ) -> Dict[str, Any]:
        """Execute a tool call requested by Claude."""
        
        try:
            if tool_name == "create_meal_plan":
                return await self._tool_create_meal_plan(tool_input, db, user)
            elif tool_name == "update_meal_plan":
                return await self._tool_update_meal_plan(tool_input, db, user)
            elif tool_name == "delete_meal_plan":
                return await self._tool_delete_meal_plan(tool_input, db)
            elif tool_name == "search_recipes":
                return await self._tool_search_recipes(tool_input, db)
            elif tool_name == "get_recipe_details":
                return await self._tool_get_recipe_details(tool_input, db)
            elif tool_name == "update_dietary_preferences":
                return await self._tool_update_dietary_preferences(tool_input, db, user)
            else:
                return {"error": f"Unknown tool: {tool_name}"}
                
        except Exception as e:
            logger.error(f"Tool execution error for {tool_name}: {str(e)}", exc_info=True)
            # Return a more informative error message
            error_msg = str(e)
            if "foreign key constraint" in error_msg.lower():
                return {"error": "The recipe ID does not exist. Please search for available recipes first."}
            elif "uuid" in error_msg.lower():
                return {"error": "Invalid ID format provided. Please use a valid recipe or meal plan ID."}
            else:
                return {"error": f"Tool execution failed: {str(e)}"}
    
    async def _tool_create_meal_plan(
        self,
        input_data: Dict[str, Any],
        db: AsyncSession,
        user: User
    ) -> Dict[str, Any]:
        """Create meal plans."""
        created_plans = []
        errors = []
        
        for plan_data in input_data.get("plans", []):
            try:
                # Parse date
                plan_date = datetime.strptime(plan_data["date"], "%Y-%m-%d").date()
                
                # Convert meal type
                meal_type_map = {
                    "breakfast": MealType.BREAKFAST,
                    "lunch": MealType.LUNCH,
                    "dinner": MealType.DINNER,
                    "snack": MealType.SNACK
                }
                meal_type = meal_type_map.get(plan_data["meal_type"].lower())
                
                if not meal_type:
                    errors.append(f"Invalid meal type: {plan_data['meal_type']}")
                    continue
                
                # Validate recipe exists
                recipe_id = uuid.UUID(plan_data["recipe_id"])
                recipe_exists = await db.execute(
                    select(Recipe).where(Recipe.id == recipe_id)
                )
                if not recipe_exists.scalar_one_or_none():
                    errors.append(f"Recipe {recipe_id} not found. Please search for valid recipes first.")
                    continue
                
                # Check if plan already exists
                existing = await db.execute(
                    select(MealPlan).where(
                        MealPlan.user_id == user.id,
                        MealPlan.date == plan_date,
                        MealPlan.meal_type == meal_type
                    )
                )
                if existing.scalar_one_or_none():
                    errors.append(f"Meal plan already exists for {plan_data['meal_type']} on {plan_data['date']}")
                    continue
                
                meal_plan = MealPlan(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    date=plan_date,
                    recipe_id=recipe_id,
                    meal_type=meal_type,
                    servings=plan_data.get("servings", 1),
                    status=MealPlanStatus.UNLOCKED,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                db.add(meal_plan)
                created_plans.append({
                    "date": plan_data["date"],
                    "meal_type": plan_data["meal_type"],
                    "id": str(meal_plan.id)
                })
            except Exception as e:
                logger.error(f"Error creating meal plan: {e}")
                errors.append(f"Error processing plan for {plan_data.get('date', 'unknown')}: {str(e)}")
        
        if created_plans:
            await db.commit()
        
        result = {"created": created_plans}
        if errors:
            result["errors"] = errors
        return result
    
    async def _tool_update_meal_plan(
        self,
        input_data: Dict[str, Any],
        db: AsyncSession,
        user: User
    ) -> Dict[str, Any]:
        """Update a meal plan."""
        try:
            meal_plan_id = uuid.UUID(input_data["meal_plan_id"])
            
            result = await db.execute(
                select(MealPlan).where(
                    MealPlan.id == meal_plan_id,
                    MealPlan.user_id == user.id
                )
            )
            meal_plan = result.scalar_one_or_none()
            
            if not meal_plan:
                return {"error": "Meal plan not found"}
            
            if "recipe_id" in input_data:
                # Validate the new recipe exists
                new_recipe_id = uuid.UUID(input_data["recipe_id"])
                recipe_exists = await db.execute(
                    select(Recipe).where(Recipe.id == new_recipe_id)
                )
                if not recipe_exists.scalar_one_or_none():
                    return {"error": f"Recipe {new_recipe_id} not found. Please search for valid recipes first."}
                meal_plan.recipe_id = new_recipe_id
            
            if "servings" in input_data:
                meal_plan.servings = input_data["servings"]
            
            meal_plan.updated_at = datetime.utcnow()
            await db.commit()
            
            return {"updated": str(meal_plan_id)}
        except Exception as e:
            logger.error(f"Error updating meal plan: {e}")
            return {"error": f"Failed to update meal plan: {str(e)}"}
    
    async def _tool_delete_meal_plan(
        self,
        input_data: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Delete a meal plan."""
        meal_plan_id = uuid.UUID(input_data["meal_plan_id"])
        
        result = await db.execute(
            delete(MealPlan).where(MealPlan.id == meal_plan_id)
        )
        await db.commit()
        
        return {"deleted": str(meal_plan_id), "rows_affected": result.rowcount}
    
    async def _tool_search_recipes(
        self,
        input_data: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Search for recipes with comprehensive filtering."""
        from sqlalchemy import func
        
        query = select(Recipe)
        
        # Name filter
        if "name" in input_data:
            query = query.where(Recipe.recipe_name.ilike(f"%{input_data['name']}%"))
        
        # Calorie filters
        if "max_calories" in input_data:
            query = query.where(Recipe.calories_per_serving <= input_data["max_calories"])
        if "min_calories" in input_data:
            query = query.where(Recipe.calories_per_serving >= input_data["min_calories"])
        
        # Get limit
        limit = input_data.get("limit", 10)
        
        # Apply randomization if requested
        if input_data.get("randomize", False):
            query = query.order_by(func.random())
        else:
            query = query.order_by(Recipe.recipe_name)
        
        # Execute query
        result = await db.execute(query)
        recipes = result.scalars().all()
        
        # Filter by macro nutrients and main protein in memory
        # (In production, these would be indexed JSON queries)
        filtered_recipes = []
        for recipe in recipes:
            # Main protein filter
            if "main_protein" in input_data:
                if not any(input_data["main_protein"].lower() in p.lower() for p in recipe.main_protein):
                    continue
            
            # Macro nutrient filters
            macros = recipe.macro_nutrients
            if "min_protein" in input_data and macros.get("protein_g", 0) < input_data["min_protein"]:
                continue
            if "max_protein" in input_data and macros.get("protein_g", 0) > input_data["max_protein"]:
                continue
            if "min_carbs" in input_data and macros.get("carbohydrates_g", 0) < input_data["min_carbs"]:
                continue
            if "max_carbs" in input_data and macros.get("carbohydrates_g", 0) > input_data["max_carbs"]:
                continue
            if "min_fat" in input_data and macros.get("fat_g", 0) < input_data["min_fat"]:
                continue
            if "max_fat" in input_data and macros.get("fat_g", 0) > input_data["max_fat"]:
                continue
            
            filtered_recipes.append({
                "id": str(recipe.id),
                "name": recipe.recipe_name,
                "calories": recipe.calories_per_serving,
                "protein_g": macros.get("protein_g", 0),
                "carbs_g": macros.get("carbohydrates_g", 0),
                "fat_g": macros.get("fat_g", 0),
                "main_protein": recipe.main_protein
            })
            
            # Check limit
            if len(filtered_recipes) >= limit:
                break
        
        return {"recipes": filtered_recipes}
    
    async def _tool_get_recipe_details(
        self,
        input_data: Dict[str, Any],
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Get detailed recipe information."""
        try:
            recipe_id = uuid.UUID(input_data["recipe_id"])
            
            result = await db.execute(
                select(Recipe).where(Recipe.id == recipe_id)
            )
            recipe = result.scalar_one_or_none()
            
            if not recipe:
                return {"error": f"Recipe with ID {recipe_id} not found. Please search for available recipes first."}
            
            return {
                "id": str(recipe.id),
                "name": recipe.recipe_name,
                "author": recipe.recipe_author,
                "servings": recipe.servings,
                "calories": recipe.calories_per_serving,
                "macros": recipe.macro_nutrients,
                "ingredients": recipe.ingredients,
                "instructions": recipe.instructions,
                "main_protein": recipe.main_protein
            }
        except ValueError as e:
            return {"error": f"Invalid recipe ID format: {input_data.get('recipe_id', 'none provided')}"}
    
    async def _get_user_meal_plans(
        self,
        db: AsyncSession,
        user_id: uuid.UUID,
        days_ahead: int = 7
    ) -> List[MealPlan]:
        """Get user's meal plans for the next N days."""
        today = date.today()
        end_date = today + timedelta(days=days_ahead)
        
        result = await db.execute(
            select(MealPlan)
            .where(MealPlan.user_id == user_id)
            .where(MealPlan.date >= today)
            .where(MealPlan.date < end_date)
            .options(selectinload(MealPlan.recipe))
            .order_by(MealPlan.date, MealPlan.meal_type)
        )
        
        return result.scalars().all()
    
    async def _get_all_recipes(self, db: AsyncSession) -> List[Recipe]:
        """Get all available recipes."""
        result = await db.execute(select(Recipe))
        return result.scalars().all()
    
    def _format_meal_plan_context(self, meal_plans: List[MealPlan]) -> str:
        """Format meal plans for LLM context."""
        if not meal_plans:
            return "No meal plans scheduled"
        
        context = []
        current_date = None
        
        for plan in meal_plans:
            if plan.date != current_date:
                current_date = plan.date
                context.append(f"\n{plan.date.strftime('%A, %B %d')}:")
            
            context.append(
                f"- {plan.meal_type.value.capitalize()}: {plan.recipe.recipe_name} "
                f"(ID: {plan.id}, {plan.recipe.calories_per_serving} cal)"
            )
        
        return "".join(context)
    
    async def show_meal_plan(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Show formatted meal plan."""
        # This can still be a direct command for quick viewing
        user_id = str(update.effective_user.id)
        
        async with AsyncSessionLocal() as db:
            user = await get_user_by_telegram_id(db, user_id)
            
            if not user:
                await update.message.reply_text("Please register first using /start")
                return
            
            meal_plans = await self._get_user_meal_plans(db, user.id)
            
            if not meal_plans:
                await update.message.reply_text(
                    "You don't have any meal plans scheduled.\n"
                    "Just tell me what you'd like to eat and when!"
                )
                return
            
            # Format the meal plan nicely
            message = "📅 *Your Meal Plan*\n\n"
            current_date = None
            
            for plan in meal_plans:
                if plan.date != current_date:
                    current_date = plan.date
                    message += f"\n*{plan.date.strftime('%A, %B %d')}*\n"
                
                emoji_map = {
                    MealType.BREAKFAST: "🌅",
                    MealType.LUNCH: "🌞", 
                    MealType.DINNER: "🌙",
                    MealType.SNACK: "🍿"
                }
                
                emoji = emoji_map.get(plan.meal_type, "🍽️")
                message += (
                    f"{emoji} *{plan.meal_type.value.capitalize()}*: "
                    f"{plan.recipe.recipe_name}\n"
                    f"   📊 {plan.recipe.calories_per_serving} cal | "
                    f"🥩 {plan.recipe.macro_nutrients.get('protein_g', 0)}g protein\n"
                )
            
            message += "\n💬 _Tell me if you'd like to change anything!_"
            await update.message.reply_text(message, parse_mode='Markdown')
    
    async def clear_history(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Clear conversation history for the user."""
        user_id = str(update.effective_user.id)
        
        if user_id in self.conversation_history:
            self.conversation_history[user_id] = []
            await update.message.reply_text(
                "✨ I've cleared our conversation history. Let's start fresh!"
            )
        else:
            await update.message.reply_text(
                "We don't have any conversation history yet!"
            )
    
    async def _tool_update_dietary_preferences(
        self,
        input_data: Dict[str, Any],
        db: AsyncSession,
        user: User
    ) -> Dict[str, Any]:
        """Update user's dietary preferences."""
        preferences = input_data.get("preferences", {})
        
        # Merge with existing preferences
        if user.dietary_preferences is None:
            user.dietary_preferences = {}
        
        # Update each field if provided
        if "restrictions" in preferences:
            user.dietary_preferences["restrictions"] = preferences["restrictions"]
        if "allergies" in preferences:
            user.dietary_preferences["allergies"] = preferences["allergies"]
        if "dislikes" in preferences:
            user.dietary_preferences["dislikes"] = preferences["dislikes"]
        if "calorie_target" in preferences:
            user.dietary_preferences["calorie_target"] = preferences["calorie_target"]
        if "macro_targets" in preferences:
            user.dietary_preferences["macro_targets"] = preferences["macro_targets"]
        
        # Mark the column as modified for SQLAlchemy to detect the change
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(user, "dietary_preferences")
        
        await db.commit()
        await db.refresh(user)
        
        return {
            "updated": True,
            "preferences": user.dietary_preferences
        }