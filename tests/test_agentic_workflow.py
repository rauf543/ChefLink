import asyncio
import json
import pytest
import re
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime

from app.services.telegram.handlers.family_v2_agentic import FamilyHandlersV2Agentic
from app.database.models import User, UserRole


class TestAgenticWorkflow:
    """Test cases for the agentic workflow implementation."""
    
    @pytest.fixture
    def handler(self):
        """Create a handler instance with mocked LLM service."""
        handler = FamilyHandlersV2Agentic()
        handler.llm_service = Mock()
        handler.llm_service.model = "claude-opus-4-20250514"
        handler.llm_service.client = AsyncMock()
        return handler
    
    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        user = Mock(spec=User)
        user.id = "test-user-id"
        user.telegram_id = "123456"
        user.name = "Test User"
        user.role = UserRole.FAMILY_MEMBER
        user.dietary_preferences = {"restrictions": ["vegetarian"]}
        return user
    
    @pytest.fixture
    def mock_update(self):
        """Create a mock Telegram update."""
        update = Mock()
        update.effective_user = Mock(id="123456")
        update.message = Mock()
        update.message.text = "Find me healthy breakfast recipes"
        update.message.reply_text = AsyncMock()
        return update
    
    @pytest.mark.asyncio
    async def test_final_message_extraction(self, handler):
        """Test that final message is correctly extracted from response."""
        # Test various final message formats
        test_cases = [
            ("{{final_message: Hello world!}}", "Hello world!"),
            ("{{final_message: Multi\nline\nmessage}}", "Multi\nline\nmessage"),
            ("{{final_message:   Spaces around   }}", "Spaces around"),
            ("Some thinking...\n{{final_message: The actual response}}", "The actual response"),
        ]
        
        for input_text, expected in test_cases:
            match = re.match(handler.FINAL_MESSAGE_PATTERN, input_text, re.DOTALL | re.MULTILINE)
            if expected:
                assert match is not None
                assert match.group(1).strip() == expected
            else:
                assert match is None
    
    @pytest.mark.asyncio
    async def test_no_false_positive_final_message(self, handler):
        """Test that normal text with similar patterns doesn't trigger final message."""
        test_cases = [
            "Let me search for recipes with {{protein: chicken}}",
            "The format should be {{final_message: your text}} but I'm not done yet",
            "Thinking about the best approach...",
        ]
        
        for text in test_cases:
            match = re.match(handler.FINAL_MESSAGE_PATTERN, text, re.DOTALL | re.MULTILINE)
            assert match is None
    
    @pytest.mark.asyncio
    async def test_cost_estimation(self, handler):
        """Test cost estimation calculation."""
        # Mock response with usage data
        response = Mock()
        response.usage = Mock(input_tokens=1000, output_tokens=500)
        
        cost = handler._estimate_cost(response)
        # (1000 * 0.015 + 500 * 0.075) / 1000 = 0.0525
        assert abs(cost - 0.0525) < 0.001
    
    @pytest.mark.asyncio
    async def test_tool_allowlist_enforcement(self, handler, mock_user):
        """Test that only allowed tools are executed."""
        # Create mock tool calls
        allowed_tool = Mock()
        allowed_tool.name = "search_recipes"
        allowed_tool.input = {"name": "eggs"}
        allowed_tool.id = "tool1"
        
        disallowed_tool = Mock()
        disallowed_tool.name = "delete_all_data"  # Not in allowlist
        disallowed_tool.input = {}
        disallowed_tool.id = "tool2"
        
        tool_calls = [allowed_tool, disallowed_tool]
        
        # Mock the actual tool execution
        handler._execute_tool_call = AsyncMock(return_value={"recipes": []})
        
        # Execute tools
        db = Mock()
        trace = []
        results = await handler._execute_tools_with_trace(tool_calls, db, mock_user, trace)
        
        # Should only execute the allowed tool
        handler._execute_tool_call.assert_called_once_with(
            "search_recipes", {"name": "eggs"}, db, mock_user
        )
        assert len(results) == 2  # Both get results, but one is blocked
    
    @pytest.mark.asyncio
    async def test_iteration_limit(self, handler, mock_update, mock_user):
        """Test that the agent stops after MAX_ITERATIONS."""
        # Mock database
        db = AsyncMock()
        
        # Mock responses that never include final message
        thinking_response = Mock()
        thinking_response.content = [Mock(type="text", text="Still thinking...")]
        thinking_response.usage = Mock(input_tokens=100, output_tokens=50)
        
        handler.llm_service.client.messages.create.return_value = thinking_response
        
        # Mock helper methods
        handler._get_user_meal_plans = AsyncMock(return_value=[])
        handler._get_all_recipes = AsyncMock(return_value=[])
        
        # Set a low iteration limit for testing
        handler.MAX_ITERATIONS = 3
        
        # Create a mock thinking indicator
        thinking_message = Mock()
        thinking_message.edit_text = AsyncMock()
        thinking_message.delete = AsyncMock()
        
        # Run the agentic response
        await handler._process_agentic_response(
            thinking_response, mock_update, db, mock_user, "123456", thinking_message
        )
        
        # Should have made MAX_ITERATIONS + 1 calls (initial + iterations)
        assert handler.llm_service.client.messages.create.call_count >= handler.MAX_ITERATIONS
        
        # Should send a fallback message
        mock_update.message.reply_text.assert_called()
    
    @pytest.mark.asyncio
    async def test_timeout_handling(self, handler, mock_update, mock_user):
        """Test that the agent stops after timeout."""
        # Mock database
        db = AsyncMock()
        
        # Mock slow responses
        async def slow_response(*args, **kwargs):
            await asyncio.sleep(0.1)  # Simulate slow response
            response = Mock()
            response.content = [Mock(type="text", text="Still thinking...")]
            response.usage = Mock(input_tokens=100, output_tokens=50)
            return response
        
        handler.llm_service.client.messages.create.side_effect = slow_response
        
        # Set a very short timeout for testing
        handler.MAX_TIME_SECONDS = 0.05
        
        # Mock helper methods
        handler._get_user_meal_plans = AsyncMock(return_value=[])
        handler._get_all_recipes = AsyncMock(return_value=[])
        
        # Create a mock thinking indicator
        thinking_message = Mock()
        thinking_message.edit_text = AsyncMock()
        thinking_message.delete = AsyncMock()
        
        # Run the agentic response
        await handler._process_agentic_response(
            Mock(content=[], usage=Mock(input_tokens=100, output_tokens=50)), 
            mock_update, db, mock_user, "123456", thinking_message
        )
        
        # Should send timeout message
        mock_update.message.reply_text.assert_called_with(
            "I'm taking too long to think. Let me give you what I have so far..."
        )
    
    @pytest.mark.asyncio
    async def test_successful_flow_with_tools(self, handler, mock_update, mock_user):
        """Test successful completion with tool usage."""
        # Mock database
        db = AsyncMock()
        
        # First response: thinking + tool call
        first_response = Mock()
        first_response.content = [
            Mock(type="text", text="Let me search for breakfast recipes."),
            Mock(type="tool_use", name="search_recipes", input={"max_calories": 300}, id="tool1")
        ]
        first_response.usage = Mock(input_tokens=100, output_tokens=50)
        
        # Second response: final message
        final_response = Mock()
        final_response.content = [
            Mock(type="text", text="{{final_message: I found 3 healthy breakfast recipes for you!}}")
        ]
        final_response.usage = Mock(input_tokens=150, output_tokens=60)
        
        handler.llm_service.client.messages.create.side_effect = [first_response, final_response]
        
        # Mock tool execution
        handler._execute_tool_call = AsyncMock(return_value={
            "recipes": [
                {"name": "Veggie Omelet", "calories": 200},
                {"name": "Greek Yogurt", "calories": 150},
                {"name": "Overnight Oats", "calories": 250}
            ]
        })
        
        # Mock helper methods
        handler._get_user_meal_plans = AsyncMock(return_value=[])
        handler._get_all_recipes = AsyncMock(return_value=[])
        
        # Create a mock thinking indicator
        thinking_message = Mock()
        thinking_message.edit_text = AsyncMock()
        thinking_message.delete = AsyncMock()
        
        # Run the agentic response
        await handler._process_agentic_response(
            first_response, mock_update, db, mock_user, "123456", thinking_message
        )
        
        # Should execute the tool
        handler._execute_tool_call.assert_called_once()
        
        # Should send the final message
        mock_update.message.reply_text.assert_called_with(
            "I found 3 healthy breakfast recipes for you!"
        )
        
        # Should stop the thinking indicator
        thinking_message.delete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_compression_triggered(self, handler):
        """Test that message compression is triggered when needed."""
        # Create a large message history
        messages = [{"role": "system", "content": "System prompt"}]
        
        # Add many messages to exceed token limit
        for i in range(20):
            messages.append({
                "role": "user",
                "content": f"This is message {i} with some content to make it longer"
            })
            messages.append({
                "role": "assistant",
                "content": f"Response {i} with detailed information about recipes and meal planning"
            })
        
        # Mock the compression method
        handler._compress_history = AsyncMock(return_value="Compressed summary of conversation")
        
        # Run compression
        compressed = await handler._compress_if_needed(messages)
        
        # Should have called compression
        handler._compress_history.assert_called_once()
        
        # Should have fewer messages
        assert len(compressed) < len(messages)
        
        # Should keep system prompt and recent messages
        assert compressed[0]["role"] == "system"
        assert any("Previous context" in msg.get("content", "") for msg in compressed)
    
    @pytest.mark.asyncio
    async def test_tool_result_truncation(self, handler):
        """Test that large tool results are truncated."""
        # Create a large recipe result
        large_result = {
            "recipes": [{"name": f"Recipe {i}", "calories": i * 100} for i in range(100)]
        }
        
        truncated = handler._summarize_tool_result(large_result)
        
        # Should truncate to first 5 recipes
        assert len(truncated["recipes"]) == 5
        assert truncated["total_count"] == 100
        assert truncated["truncated"] is True
    
    @pytest.mark.asyncio
    async def test_trace_recording(self, handler, mock_user):
        """Test that tool execution traces are recorded correctly."""
        # Mock tool execution
        tool_call = Mock()
        tool_call.name = "search_recipes"
        tool_call.input = {"name": "eggs"}
        tool_call.id = "tool1"
        
        handler._execute_tool_call = AsyncMock(return_value={"recipes": []})
        
        # Execute with trace
        db = Mock()
        trace = []
        await handler._execute_tools_with_trace([tool_call], db, mock_user, trace)
        
        # Check trace
        assert len(trace) == 1
        assert trace[0]["tool"] == "search_recipes"
        assert trace[0]["args"] == {"name": "eggs"}
        assert trace[0]["status"] == "success"
        assert "duration" in trace[0]
        assert "timestamp" in trace[0]