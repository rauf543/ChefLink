import json
import logging
import re
import time
import asyncio
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

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


class FamilyHandlersV2Agentic:
    """Enhanced handlers with true agentic workflow for family member users."""
    
    # Constants
    MAX_ITERATIONS = 20
    MAX_TOKENS_PER_CALL = 8000  # Start conservative, can increase to 20000+
    FINAL_MESSAGE_PATTERN = r'\{\{final_message:\s*(.*?)\}\}'
    
    # Tool allowlist
    ALLOWED_TOOLS = {
        "search_recipes", "create_meal_plan", "update_meal_plan",
        "delete_meal_plan", "get_recipe_details", "update_dietary_preferences"
    }
    
    def __init__(self):
        self.llm_service = get_llm_service()
        # Store conversation history per user
        self.conversation_history = {}
        # Store tool traces for debugging
        self.tool_traces = {}
        # Token limits for context management
        self.max_context_tokens = 50000  # Increased from 8000
        self.max_history_tokens = 10000  # Increased from 2000
    
    def _estimate_tokens(self, text: str) -> int:
        """Rough estimation of tokens (approximately 4 characters per token)."""
        return len(text) // 4
    
    
    def _extract_text_from_response(self, response: Any) -> str:
        """Extract text content from Claude response."""
        text = ""
        if hasattr(response, 'content') and response.content:
            for content in response.content:
                if hasattr(content, 'type') and content.type == "text":
                    text += content.text
        return text
    
    def _extract_tool_calls(self, response: Any) -> List[Any]:
        """Extract tool calls from Claude response."""
        tool_calls = []
        if hasattr(response, 'content') and response.content:
            for content in response.content:
                if hasattr(content, 'type') and content.type == "tool_use":
                    tool_calls.append(content)
        return tool_calls
    
    async def _show_thinking_indicator(self, update: Update) -> Any:
        """Show a progress indicator while the agent thinks."""
        indicators = ["🤔 Thinking...", "🔍 Searching...", "📊 Analyzing...", "✨ Almost done..."]
        message = await update.message.reply_text(indicators[0])
        
        async def update_indicator():
            try:
                for i in range(1, len(indicators)):
                    await asyncio.sleep(3)
                    await message.edit_text(indicators[i])
            except Exception:
                pass  # Message might be deleted already
        
        # Run in background
        self.indicator_task = asyncio.create_task(update_indicator())
        return message
    
    async def _stop_thinking_indicator(self, message: Any) -> None:
        """Stop the thinking indicator."""
        try:
            if hasattr(self, 'indicator_task'):
                self.indicator_task.cancel()
            await message.delete()
        except Exception:
            pass
    
    def _clean_markdown_for_telegram(self, text: str) -> str:
        """Remove markdown formatting that doesn't work in Telegram."""
        # Remove bold markdown
        text = text.replace("**", "")
        # Remove italic markdown (single asterisks that aren't part of lists)
        import re
        # Replace single asterisks that aren't at the start of a line or after newline
        text = re.sub(r'(?<!^)(?<!\n)\*([^\*\n]+)\*', r'\1', text)
        # Remove code blocks if they exist
        text = text.replace("```", "")
        return text
    
    async def _compress_history(self, messages: List[Dict[str, Any]]) -> str:
        """Compress message history into a summary."""
        # Create a summary prompt
        summary_messages = [
            {
                "role": "user",
                "content": "Summarize the following conversation history concisely, focusing on key decisions, preferences, and actions taken:\n\n" + 
                         json.dumps(messages, indent=2)[:4000]  # Limit size
            }
        ]
        
        try:
            response = await self.llm_service.client.messages.create(
                model=self.llm_service.model,
                max_tokens=500,
                temperature=0.3,
                messages=summary_messages,
                system="You are a helpful assistant that creates concise summaries."
            )
            
            if response.content and response.content[0].text:
                return response.content[0].text
        except Exception as e:
            logger.error(f"Error compressing history: {e}")
        
        return "Previous conversation context included searches and meal planning."
    
    async def _compress_if_needed(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compress old messages if history is too large."""
        # Estimate total tokens
        total_text = json.dumps(messages)
        total_tokens = self._estimate_tokens(total_text)
        
        if total_tokens > 8000 and len(messages) > 12:
            # Keep system prompt and last 5 exchanges (10 messages)
            system_messages = [m for m in messages if m.get("role") == "system"]
            recent_messages = messages[-10:]
            
            # Summarize the middle part
            messages_to_compress = [m for m in messages if m not in system_messages and m not in recent_messages]
            if messages_to_compress:
                summary = await self._compress_history(messages_to_compress)
                compressed_messages = system_messages + [
                    {"role": "assistant", "content": f"[Previous context: {summary}]"}
                ] + recent_messages
                return compressed_messages
        
        return messages
    
    def _summarize_tool_result(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize large tool results to avoid token bloat."""
        result_str = json.dumps(result)
        if len(result_str) > 2000:
            # Summarize based on result type
            if "recipes" in result and isinstance(result["recipes"], list):
                return {
                    "recipes": result["recipes"][:5],  # Keep only first 5
                    "total_count": len(result["recipes"]),
                    "truncated": True
                }
            elif "created" in result:
                return {
                    "created": result["created"],
                    "summary": f"Created {len(result['created'])} meal plans"
                }
            else:
                # Generic truncation
                return {
                    "summary": "Large result truncated",
                    "keys": list(result.keys()),
                    "truncated": True
                }
        return result
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Handle all messages through Claude with agentic workflow."""
        user_id = str(update.effective_user.id)
        
        async with AsyncSessionLocal() as db:
            user = await get_user_by_telegram_id(db, user_id)
            
            if not user or user.role.value != 'family_member':
                await update.message.reply_text(
                    "This feature is only available for family members."
                )
                return
            
            # Show thinking indicator
            thinking_message = await self._show_thinking_indicator(update)
            
            try:
                # Prepare initial context
                user_message = update.message.text
                initial_messages = await self._prepare_initial_messages(db, user, user_message)
                
                # Get initial response from Claude
                initial_response = await self.llm_service.client.messages.create(
                    model=self.llm_service.model,
                    max_tokens=self.MAX_TOKENS_PER_CALL,
                    temperature=0.7,
                    system=self._get_agentic_system_prompt(user),
                    messages=initial_messages,
                    tools=self._get_tool_definitions(),
                    tool_choice={"type": "auto"}
                )
                
                # Process with agentic workflow
                await self._process_agentic_response(
                    initial_response, update, db, user, user_id, thinking_message, initial_messages
                )
                
            except Exception as e:
                logger.error(f"Error in agentic conversation: {str(e)}", exc_info=True)
                await self._stop_thinking_indicator(thinking_message)
                await update.message.reply_text(
                    "I encountered an error. Please try again or rephrase your request."
                )
    
    async def _prepare_initial_messages(
        self, 
        db: AsyncSession, 
        user: User, 
        user_message: str
    ) -> List[Dict[str, Any]]:
        """Prepare initial messages with context."""
        # Get current meal plans for context
        meal_plans = await self._get_user_meal_plans(db, user.id)
        
        # Get available recipes (sample)
        recipes = await self._get_all_recipes(db)
        
        # Build messages with conversation history
        messages = []
        
        # Add conversation history if exists
        user_id = str(user.telegram_id)
        if user_id in self.conversation_history:
            # Get recent history
            recent_history = self.conversation_history[user_id][-10:]  # Last 5 exchanges
            messages.extend(recent_history)
        
        # Add current message with formatting instructions and context
        context_info = {
            "meal_plans": self._format_meal_plan_context(meal_plans),
            "total_recipes": len(recipes),
            "dietary_preferences": user.dietary_preferences or {}
        }
        
        # Formatting instructions as message prefix
        formatting_instructions = """IMPORTANT: When you are ready to respond to the user (after thinking/searching/analyzing), you MUST format your response as follows:

Start with EXACTLY: {{final_message: 
Then write your complete response
End with EXACTLY: }}

Example format:
{{final_message: Here's your personalized meal plan recommendation...}}

Everything between {{final_message: and }} will be sent to the user. Do not send a final message until you've completed your analysis.

---"""
        
        messages.append({
            "role": "user",
            "content": f"{formatting_instructions}\n\nUser request: {user_message}\n\nContext: {json.dumps(context_info)}"
        })
        
        return messages
    
    def _get_agentic_system_prompt(self, user: User) -> str:
        """Get the agentic system prompt."""
        return f"""You are ChefLink, a helpful meal planning assistant for {user.name}.

You operate in a multi-step thinking mode where you can:
- Think through problems step-by-step across multiple messages
- Use tools repeatedly to search recipes, analyze nutrition, and manage meal plans
- Refine your approach based on results

The user CANNOT see your thinking process - only your final response when you're ready."""
    
    async def _process_agentic_response(
        self,
        initial_response: Any,
        update: Update,
        db: AsyncSession,
        user: User,
        user_id: str,
        thinking_message: Any,
        initial_messages: List[Dict[str, Any]]
    ) -> None:
        """Process response with true agentic workflow."""
        messages = initial_messages.copy()  # Start with the initial messages
        tool_trace = []
        iteration_count = 0
        start_time = time.time()
        
        current_response = initial_response
        
        # Initialize tool trace for this conversation
        trace_id = str(uuid.uuid4())
        self.tool_traces[trace_id] = {
            "user_id": user_id,
            "start_time": start_time,
            "iterations": []
        }
        
        while iteration_count < self.MAX_ITERATIONS:
            iteration_count += 1
            
            iteration_data = {
                "iteration": iteration_count,
                "timestamp": time.time()
            }
            
            # Parse response
            response_text = self._extract_text_from_response(current_response)
            iteration_data["response_text"] = response_text[:500]  # Truncate for trace
            
            # Enhanced debug logging to understand what Claude is sending
            logger.info(f"Iteration {iteration_count}: Response text preview: {response_text[:100]}")
            
            # Debug: Log the full response structure
            if hasattr(current_response, 'content') and current_response.content:
                logger.info(f"Iteration {iteration_count}: Number of content blocks: {len(current_response.content)}")
                for i, block in enumerate(current_response.content):
                    if hasattr(block, 'type'):
                        logger.info(f"  Block {i}: type={block.type}")
                        if block.type == 'text' and hasattr(block, 'text'):
                            # Log full text for first few iterations to debug
                            if iteration_count <= 3:
                                logger.info(f"  Block {i} full text: {block.text}")
                            else:
                                logger.info(f"  Block {i} text preview: {block.text[:200] if block.text else '[EMPTY]'}")
                        elif block.type == 'tool_use':
                            logger.info(f"  Block {i} tool: name={block.name if hasattr(block, 'name') else 'unknown'}")
            else:
                logger.info(f"Iteration {iteration_count}: No content blocks found in response")
            
            # Check for malformed final message (missing closing brackets)
            if '{{final_message:' in response_text and not '}}' in response_text:
                logger.warning(f"Malformed final message detected (missing closing brackets) in iteration {iteration_count}")
                # Add a user message to correct the format
                messages.append({
                    "role": "assistant",
                    "content": response_text
                })
                messages.append({
                    "role": "user", 
                    "content": "Your response is missing the closing }}. Please resend with the correct format."
                })
                # Skip tool processing and continue to next iteration
            # Check for final message sentinel with correct format
            elif '{{final_message:' in response_text and '}}' in response_text:
                final_match = re.search(self.FINAL_MESSAGE_PATTERN, response_text, re.DOTALL | re.MULTILINE)
                if not final_match:
                    logger.error(f"Final message format detected but regex failed to match in iteration {iteration_count}")
                    # Fallback: extract content manually
                    start_idx = response_text.find('{{final_message:') + len('{{final_message:')
                    end_idx = response_text.rfind('}}')
                    final_message = response_text[start_idx:end_idx].strip()
                else:
                    final_message = final_match.group(1).strip()
                
                # Save to conversation history
                if user_id not in self.conversation_history:
                    self.conversation_history[user_id] = []
                
                self.conversation_history[user_id].append({
                    "role": "user",
                    "content": update.message.text
                })
                self.conversation_history[user_id].append({
                    "role": "assistant",
                    "content": final_message
                })
                
                # Trim history if too long
                if len(self.conversation_history[user_id]) > 20:
                    self.conversation_history[user_id] = self.conversation_history[user_id][-20:]
                
                # Send final message
                await self._stop_thinking_indicator(thinking_message)
                cleaned = self._clean_markdown_for_telegram(final_message)
                await update.message.reply_text(cleaned)
                
                # Log successful completion
                self.tool_traces[trace_id]["iterations"].append(iteration_data)
                self.tool_traces[trace_id]["status"] = "completed"
                self.tool_traces[trace_id]["total_iterations"] = iteration_count
                
                return
            else:
                # Not a final message - process normally (tools or thinking)
                tool_calls = self._extract_tool_calls(current_response)
                if tool_calls:
                    # Validate tools are in allowlist
                    for tool_call in tool_calls:
                        if tool_call.name not in self.ALLOWED_TOOLS:
                            logger.warning(f"Blocked unauthorized tool: {tool_call.name}")
                            tool_calls.remove(tool_call)
                    
                    if tool_calls:  # If any valid tools remain
                        tool_results = await self._execute_tools_with_trace(
                            tool_calls, db, user, tool_trace
                        )
                        
                        iteration_data["tools_executed"] = [
                            {"name": tc.name, "args": tc.input} for tc in tool_calls
                        ]
                        
                        # When tools are used, we need to preserve the content structure
                        # Convert content blocks to dict format for API
                        content_blocks = []
                        for block in current_response.content:
                            if hasattr(block, 'type'):
                                if block.type == 'text':
                                    content_blocks.append({
                                        "type": "text",
                                        "text": block.text
                                    })
                                elif block.type == 'tool_use':
                                    content_blocks.append({
                                        "type": "tool_use",
                                        "id": block.id,
                                        "name": block.name,
                                        "input": block.input
                                    })
                        
                        messages.append({
                            "role": "assistant",
                            "content": content_blocks
                        })
                        messages.append({
                            "role": "user",
                            "content": tool_results
                        })
                else:
                    # No tools and no final message - agent is thinking
                    messages.append({
                        "role": "assistant",
                        "content": response_text  # Use extracted text, not raw content
                    })
            
            # Compress history if needed
            messages = await self._compress_if_needed(messages)
            
            # Save iteration data
            self.tool_traces[trace_id]["iterations"].append(iteration_data)
            
            # Next iteration
            try:
                current_response = await self.llm_service.client.messages.create(
                    model=self.llm_service.model,
                    max_tokens=self.MAX_TOKENS_PER_CALL,
                    temperature=0.7,
                    system=self._get_agentic_system_prompt(user),
                    messages=messages,
                    tools=self._get_tool_definitions(),
                    tool_choice={"type": "auto"}
                )
            except Exception as e:
                logger.error(f"Error in iteration {iteration_count}: {e}")
                break
        
        # Fallback if no final message after all iterations
        await self._stop_thinking_indicator(thinking_message)
        self.tool_traces[trace_id]["status"] = "fallback"
        
        # Try to generate a final response based on what we have
        fallback_prompt = [{
            "role": "user",
            "content": "Please provide a final response summarizing what you've found. Start with {{final_message:"
        }]
        
        try:
            fallback_response = await self.llm_service.client.messages.create(
                model=self.llm_service.model,
                max_tokens=1000,
                temperature=0.5,
                system=self._get_agentic_system_prompt(user),
                messages=messages[-4:] + fallback_prompt  # Last 2 exchanges + prompt
            )
            
            fallback_text = self._extract_text_from_response(fallback_response)
            final_match = re.search(self.FINAL_MESSAGE_PATTERN, fallback_text, re.DOTALL | re.MULTILINE)
            
            if final_match:
                final_message = final_match.group(1).strip()
                cleaned = self._clean_markdown_for_telegram(final_message)
                await update.message.reply_text(cleaned)
            else:
                await update.message.reply_text(
                    "I couldn't complete my analysis. Please try rephrasing your request or breaking it into smaller parts."
                )
        except Exception as e:
            logger.error(f"Error generating fallback response: {e}")
            await update.message.reply_text(
                "I encountered an error while processing your request. Please try again."
            )
    
    async def _execute_tools_with_trace(
        self,
        tool_calls: List[Any],
        db: AsyncSession,
        user: User,
        trace: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Execute tools with full tracing for debugging."""
        results = []
        
        for tool_call in tool_calls:
            start_time = time.time()
            tool_trace_entry = {
                "timestamp": start_time,
                "tool": tool_call.name,
                "args": tool_call.input
            }
            
            try:
                result = await self._execute_tool_call(
                    tool_call.name,
                    tool_call.input,
                    db,
                    user
                )
                
                # Safety: Truncate large results
                result_str = json.dumps(result)
                if len(result_str) > 2000:
                    result = self._summarize_tool_result(result)
                
                tool_trace_entry["result"] = result
                tool_trace_entry["status"] = "success"
                
            except Exception as e:
                logger.error(f"Tool execution error: {str(e)}")
                result = {"error": str(e)}
                tool_trace_entry["result"] = result
                tool_trace_entry["status"] = "error"
            
            tool_trace_entry["duration"] = time.time() - start_time
            trace.append(tool_trace_entry)
            
            results.append({
                "type": "tool_result",
                "tool_use_id": tool_call.id,
                "content": json.dumps(result)
            })
        
        return results
    
    # Tool execution methods (same as original implementation)
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
    
    # Helper methods from original file
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
    
    def _get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions for Claude."""
        return [
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
    
    # Additional methods for monitoring and debugging
    async def get_trace_summary(self, trace_id: str) -> Dict[str, Any]:
        """Get a summary of a tool trace for debugging."""
        if trace_id not in self.tool_traces:
            return {"error": "Trace not found"}
        
        trace = self.tool_traces[trace_id]
        return {
            "trace_id": trace_id,
            "user_id": trace["user_id"],
            "duration": trace.get("end_time", time.time()) - trace["start_time"],
            "iterations": len(trace["iterations"]),
            "status": trace.get("status", "in_progress"),
            "total_cost": trace.get("total_cost", 0),
            "tools_used": self._extract_tools_from_trace(trace)
        }
    
    def _extract_tools_from_trace(self, trace: Dict[str, Any]) -> List[str]:
        """Extract unique tools used from a trace."""
        tools = set()
        for iteration in trace.get("iterations", []):
            for tool in iteration.get("tools_executed", []):
                tools.add(tool["name"])
        return list(tools)