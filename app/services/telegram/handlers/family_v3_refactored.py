"""
Refactored family handler that eliminates duplication and improves maintainability.
This replaces both family_v2.py and family_v2_agentic.py with a unified implementation.
"""
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
from uuid import UUID
import json
import logging
import re
from enum import Enum

from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import User, Recipe
from app.services.llm.factory import get_llm_service
from app.services.telegram.utils import telegram_safe_markdown
from app.core.tools.registry import get_tool_registry, ToolCategory
from app.core.tools.executor import ToolExecutor
from app.core.conversation.manager import ConversationContext
from app.core.config import settings
from app.core.feature_flags import FeatureFlags

logger = logging.getLogger(__name__)


class ResponseMode(Enum):
    """Response modes for the handler"""
    DIRECT = "direct"  # Single response mode
    AGENTIC = "agentic"  # Multi-step reasoning mode


class ResponseProcessor:
    """
    Processes LLM responses, extracting tool calls and final messages.
    Centralizes response parsing logic.
    """
    
    FINAL_MESSAGE_PATTERN = re.compile(r'\{\{final_message:\s*(.*?)\}\}', re.DOTALL)
    
    @classmethod
    def extract_final_message(cls, response_text: str) -> Optional[str]:
        """
        Extract final message from response.
        
        Args:
            response_text: Raw response text from LLM
            
        Returns:
            Extracted final message or None
        """
        if '{{final_message:' in response_text:
            match = cls.FINAL_MESSAGE_PATTERN.search(response_text)
            if match:
                return match.group(1).strip()
        return None
    
    @classmethod
    def extract_tool_calls(cls, response: Any) -> List[Dict]:
        """
        Extract tool calls from LLM response.
        
        Args:
            response: LLM response object
            
        Returns:
            List of tool call dictionaries
        """
        tool_calls = []
        
        # Handle Anthropic response format
        if hasattr(response, 'content'):
            for content in response.content:
                if hasattr(content, 'type') and content.type == 'tool_use':
                    tool_calls.append({
                        'id': content.id,
                        'name': content.name,
                        'input': content.input
                    })
        
        # Handle OpenAI response format
        elif hasattr(response, 'choices'):
            choice = response.choices[0]
            if hasattr(choice.message, 'tool_calls'):
                for tool_call in choice.message.tool_calls:
                    tool_calls.append({
                        'id': tool_call.id,
                        'name': tool_call.function.name,
                        'input': json.loads(tool_call.function.arguments)
                    })
        
        return tool_calls
    
    @classmethod
    def extract_text_content(cls, response: Any) -> str:
        """
        Extract text content from LLM response.
        
        Args:
            response: LLM response object
            
        Returns:
            Extracted text content
        """
        # Handle Anthropic response format
        if hasattr(response, 'content'):
            text_parts = []
            for content in response.content:
                if hasattr(content, 'type') and content.type == 'text':
                    text_parts.append(content.text)
            return ' '.join(text_parts)
        
        # Handle OpenAI response format
        elif hasattr(response, 'choices'):
            return response.choices[0].message.content or ""
        
        # Handle string response
        elif isinstance(response, str):
            return response
        
        return ""


class FamilyHandlerV3:
    """
    Unified family handler with clean architecture and no duplication.
    Supports both direct and agentic response modes.
    """
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.llm_service = get_llm_service()
        self.tool_registry = get_tool_registry()
        self.response_processor = ResponseProcessor()
        self.feature_flags = FeatureFlags()
        
        # Response mode configuration
        self.response_mode = (
            ResponseMode.AGENTIC 
            if self.feature_flags.is_enabled("AGENTIC_WORKFLOW")
            else ResponseMode.DIRECT
        )
        
        # Conversation contexts per user
        self.conversations: Dict[str, ConversationContext] = {}
    
    async def handle_message(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user: User
    ) -> None:
        """
        Main entry point for handling family member messages.
        
        Args:
            update: Telegram update object
            context: Telegram context
            user: User object from database
        """
        try:
            message = update.message.text
            
            # Get or create conversation context
            conversation = self._get_conversation_context(user)
            
            # Add user message
            conversation.add_message("user", message)
            
            # Process based on response mode
            if self.response_mode == ResponseMode.AGENTIC:
                await self._handle_agentic_response(update, context, user, conversation)
            else:
                await self._handle_direct_response(update, context, user, conversation)
                
        except Exception as e:
            logger.error(f"Error handling message for user {user.id}: {str(e)}")
            await update.message.reply_text(
                "I encountered an error processing your request. Please try again."
            )
    
    def _get_conversation_context(self, user: User) -> ConversationContext:
        """Get or create conversation context for user"""
        user_id = str(user.id)
        
        if user_id not in self.conversations:
            system_prompt = self._build_system_prompt(user)
            self.conversations[user_id] = ConversationContext(
                max_tokens=8000,
                system_prompt=system_prompt
            )
        
        return self.conversations[user_id]
    
    def _build_system_prompt(self, user: User) -> str:
        """
        Build system prompt for the user.
        Separates identity from formatting instructions.
        """
        if self.response_mode == ResponseMode.AGENTIC:
            return f"""You are ChefLink, a helpful meal planning assistant for {user.name}.

You operate in a multi-step thinking mode where you can:
- Think through problems step-by-step across multiple messages
- Use tools repeatedly to search recipes, analyze nutrition, and manage meal plans
- Refine your approach based on results

The user CANNOT see your thinking process - only your final response when you're ready."""
        else:
            return f"""You are ChefLink, a helpful meal planning assistant for {user.name}.

You have access to tools for searching recipes, creating meal plans, and analyzing nutrition.
Provide helpful, personalized meal planning advice based on the user's preferences and needs."""
    
    async def _handle_direct_response(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user: User,
        conversation: ConversationContext
    ) -> None:
        """
        Handle direct response mode (single response).
        """
        # Create tool executor
        tool_executor = ToolExecutor(self.db, user)
        
        # Get tool schemas
        tools = self.tool_registry.get_tool_schemas(provider="anthropic")
        
        # Build messages with context
        messages = conversation.get_context_for_llm()
        
        # Add formatting instructions if needed
        messages = self._add_formatting_instructions(messages, user)
        
        # Call LLM with tools
        response = await self.llm_service.chat_with_tools(
            messages=messages,
            tools=tools,
            temperature=0.7
        )
        
        # Process response
        await self._process_single_response(
            response, update, context, user, tool_executor, conversation
        )
    
    async def _handle_agentic_response(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user: User,
        conversation: ConversationContext
    ) -> None:
        """
        Handle agentic response mode (multi-step reasoning).
        """
        # Send thinking indicator
        thinking_message = await update.message.reply_text("🤔 Thinking...")
        
        # Create tool executor
        tool_executor = ToolExecutor(self.db, user)
        
        # Get tool schemas
        tools = self.tool_registry.get_tool_schemas(provider="anthropic")
        
        # Agentic loop
        max_iterations = 10
        iteration = 0
        final_response = None
        
        while iteration < max_iterations:
            iteration += 1
            
            # Update thinking indicator
            await thinking_message.edit_text(
                f"🤔 {'.' * (iteration % 4)}"
            )
            
            # Build messages with context
            messages = conversation.get_context_for_llm()
            
            # Add formatting instructions on first iteration
            if iteration == 1:
                messages = self._add_formatting_instructions(messages, user, is_agentic=True)
            
            # Call LLM
            response = await self.llm_service.chat_with_tools(
                messages=messages,
                tools=tools,
                temperature=0.7
            )
            
            # Extract response content
            response_text = self.response_processor.extract_text_content(response)
            
            # Check for final message
            final_message = self.response_processor.extract_final_message(response_text)
            if final_message:
                final_response = final_message
                break
            
            # Process tool calls
            tool_calls = self.response_processor.extract_tool_calls(response)
            if tool_calls:
                # Add assistant message with tool calls
                conversation.add_message(
                    "assistant",
                    response_text,
                    metadata={"tool_calls": tool_calls}
                )
                
                # Execute tools
                for tool_call in tool_calls:
                    result = await tool_executor.execute(
                        tool_call['name'],
                        tool_call['input']
                    )
                    
                    # Add tool result to conversation
                    conversation.add_message(
                        "tool",
                        json.dumps(result),
                        metadata={"tool_id": tool_call['id']}
                    )
            else:
                # Add assistant thinking message
                conversation.add_message("assistant", response_text)
        
        # Delete thinking indicator
        await thinking_message.delete()
        
        # Send final response
        if final_response:
            # Clean and format response
            formatted_response = telegram_safe_markdown(final_response)
            await update.message.reply_text(
                formatted_response,
                parse_mode='MarkdownV2'
            )
            
            # Add to conversation history
            conversation.add_message("assistant", final_response)
        else:
            await update.message.reply_text(
                "I need more time to think about this. Please try rephrasing your question."
            )
    
    async def _process_single_response(
        self,
        response: Any,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user: User,
        tool_executor: ToolExecutor,
        conversation: ConversationContext
    ) -> None:
        """Process a single LLM response with potential tool calls."""
        # Extract content
        response_text = self.response_processor.extract_text_content(response)
        tool_calls = self.response_processor.extract_tool_calls(response)
        
        # Execute tool calls if present
        tool_results = []
        if tool_calls:
            for tool_call in tool_calls:
                result = await tool_executor.execute(
                    tool_call['name'],
                    tool_call['input']
                )
                tool_results.append({
                    "tool_use_id": tool_call['id'],
                    "content": json.dumps(result)
                })
        
        # If we have tool results, call LLM again with results
        if tool_results:
            # Add assistant message with tool calls
            conversation.add_message(
                "assistant",
                response_text,
                metadata={"tool_calls": tool_calls}
            )
            
            # Add tool results
            for result in tool_results:
                conversation.add_message(
                    "tool",
                    result["content"],
                    metadata={"tool_id": result["tool_use_id"]}
                )
            
            # Get final response from LLM
            messages = conversation.get_context_for_llm()
            final_response = await self.llm_service.chat(
                messages=messages,
                temperature=0.7
            )
            
            response_text = self.response_processor.extract_text_content(final_response)
        
        # Send response to user
        formatted_response = telegram_safe_markdown(response_text)
        await update.message.reply_text(
            formatted_response,
            parse_mode='MarkdownV2'
        )
        
        # Add to conversation history
        conversation.add_message("assistant", response_text)
    
    def _add_formatting_instructions(
        self,
        messages: List[Dict],
        user: User,
        is_agentic: bool = False
    ) -> List[Dict]:
        """
        Add formatting instructions to messages.
        Keeps instructions in user message, not system prompt.
        """
        if is_agentic:
            # Add agentic formatting instructions
            formatting = """IMPORTANT: When you are ready to respond to the user (after thinking/searching/analyzing), you MUST format your response as follows:

Start with EXACTLY: {{final_message: 
Then write your complete response
End with EXACTLY: }}

Example format:
{{final_message: Here's your personalized meal plan recommendation...}}

Everything between {{final_message: and }} will be sent to the user. Do not send a final message until you've completed your analysis.

---"""
            
            # Prepend to first user message
            for i, msg in enumerate(messages):
                if msg["role"] == "user":
                    messages[i]["content"] = formatting + "\n\n" + msg["content"]
                    break
        
        # Add user context to the latest user message
        context_info = self._build_user_context(user)
        if context_info:
            for i in range(len(messages) - 1, -1, -1):
                if messages[i]["role"] == "user":
                    messages[i]["content"] += f"\n\n{context_info}"
                    break
        
        return messages
    
    def _build_user_context(self, user: User) -> str:
        """Build contextual information about the user."""
        context_parts = []
        
        # Add dietary preferences
        if user.dietary_preferences:
            prefs = ", ".join([
                f"{k}: {v}" for k, v in user.dietary_preferences.items()
            ])
            context_parts.append(f"Dietary preferences: {prefs}")
        
        # Add family context
        context_parts.append(f"Planning meals for: {user.name}")
        
        return "\n".join(context_parts) if context_parts else ""
    
    async def handle_recipe_search(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        user: User,
        query: str
    ) -> None:
        """
        Handle direct recipe search command.
        """
        tool_executor = ToolExecutor(self.db, user)
        
        # Execute search
        result = await tool_executor.execute(
            "search_recipes",
            {"query": query, "limit": 5}
        )
        
        if result["success"] and result["result"]["recipes"]:
            response = "🔍 **Recipe Search Results:**\n\n"
            for recipe in result["result"]["recipes"]:
                response += (
                    f"📖 **{recipe['name']}**\n"
                    f"   👨‍🍳 By: {recipe['author']}\n"
                    f"   🔥 Calories: {recipe['calories']}\n"
                    f"   💪 Protein: {recipe['protein']}g\n"
                    f"   🆔 ID: `{recipe['id']}`\n\n"
                )
        else:
            response = "No recipes found matching your search."
        
        formatted_response = telegram_safe_markdown(response)
        await update.message.reply_text(
            formatted_response,
            parse_mode='MarkdownV2'
        )