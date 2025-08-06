"""
Conversation context manager to handle conversation state, history, and token management.
Provides a clean abstraction for managing LLM conversations.
"""
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
import json
import logging
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """Represents a single message in the conversation"""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    token_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for LLM API"""
        return {
            "role": self.role,
            "content": self.content
        }
    
    def estimate_tokens(self) -> int:
        """Estimate token count for this message"""
        # Simple estimation: ~4 characters per token
        # In production, use tiktoken or provider-specific tokenizer
        if self.token_count == 0:
            self.token_count = len(self.content) // 4
        return self.token_count


@dataclass
class ConversationContext:
    """
    Manages conversation context with intelligent history management.
    Handles token limits, context compression, and message prioritization.
    """
    
    max_tokens: int = 8000
    max_messages: int = 20
    system_prompt: Optional[str] = None
    
    def __init__(
        self,
        max_tokens: int = 8000,
        max_messages: int = 20,
        system_prompt: Optional[str] = None
    ):
        self.max_tokens = max_tokens
        self.max_messages = max_messages
        self.system_prompt = system_prompt
        self.messages: deque[Message] = deque(maxlen=max_messages * 2)  # Keep extra for compression
        self.total_tokens = 0
        self.compression_count = 0
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict] = None) -> None:
        """
        Add a message to the conversation history.
        
        Args:
            role: Message role (user/assistant/system)
            content: Message content
            metadata: Optional metadata for the message
        """
        message = Message(role=role, content=content, metadata=metadata or {})
        message.estimate_tokens()
        
        self.messages.append(message)
        self.total_tokens += message.token_count
        
        # Check if compression needed
        if self.total_tokens > self.max_tokens:
            self._compress_context()
    
    def get_context_for_llm(self, include_system: bool = True) -> List[Dict[str, str]]:
        """
        Get the conversation context formatted for LLM API.
        
        Args:
            include_system: Whether to include system prompt
            
        Returns:
            List of message dictionaries
        """
        messages = []
        
        # Add system prompt if provided
        if include_system and self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        
        # Add conversation messages
        for message in self.messages:
            messages.append(message.to_dict())
        
        return messages
    
    def _compress_context(self) -> None:
        """
        Compress conversation context when approaching token limit.
        Uses intelligent strategies to maintain context quality.
        """
        logger.info(f"Compressing context (attempt #{self.compression_count + 1})")
        self.compression_count += 1
        
        # Strategy 1: Remove old assistant messages first (keep user messages for context)
        messages_to_keep = deque()
        current_tokens = 0
        
        # Always keep the system prompt token count
        if self.system_prompt:
            current_tokens += len(self.system_prompt) // 4
        
        # Keep recent messages up to 70% of max tokens
        target_tokens = int(self.max_tokens * 0.7)
        
        # Iterate from newest to oldest
        for message in reversed(self.messages):
            if current_tokens + message.token_count <= target_tokens:
                messages_to_keep.appendleft(message)
                current_tokens += message.token_count
            else:
                # For older messages, only keep user messages (they provide context)
                if message.role == "user" and current_tokens + message.token_count <= self.max_tokens:
                    messages_to_keep.appendleft(message)
                    current_tokens += message.token_count
        
        self.messages = messages_to_keep
        self.total_tokens = current_tokens
        
        # Add compression summary if significant content was removed
        if self.compression_count == 1:
            summary = Message(
                role="system",
                content="[Previous conversation history compressed. Key context maintained.]",
                metadata={"compression": True}
            )
            summary.estimate_tokens()
            self.messages.appendleft(summary)
            self.total_tokens += summary.token_count
    
    def get_token_usage(self) -> Dict[str, int]:
        """Get current token usage statistics"""
        return {
            "current_tokens": self.total_tokens,
            "max_tokens": self.max_tokens,
            "usage_percentage": (self.total_tokens / self.max_tokens) * 100,
            "compression_count": self.compression_count,
            "message_count": len(self.messages)
        }
    
    def clear(self) -> None:
        """Clear conversation history"""
        self.messages.clear()
        self.total_tokens = 0
        self.compression_count = 0
    
    def get_recent_messages(self, count: int = 5) -> List[Message]:
        """Get the most recent messages"""
        return list(self.messages)[-count:]
    
    def find_tool_calls(self) -> List[Tuple[Message, Dict]]:
        """
        Find all tool calls in the conversation.
        
        Returns:
            List of (message, tool_call) tuples
        """
        tool_calls = []
        for message in self.messages:
            if message.role == "assistant" and "tool_calls" in message.metadata:
                for tool_call in message.metadata["tool_calls"]:
                    tool_calls.append((message, tool_call))
        return tool_calls
    
    def export_conversation(self) -> Dict[str, Any]:
        """Export entire conversation for debugging or logging"""
        return {
            "system_prompt": self.system_prompt,
            "messages": [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "metadata": msg.metadata,
                    "tokens": msg.token_count
                }
                for msg in self.messages
            ],
            "stats": self.get_token_usage()
        }


class ConversationManager:
    """
    High-level conversation manager that handles multiple conversation contexts.
    Useful for managing conversations across different users or sessions.
    """
    
    def __init__(self, default_max_tokens: int = 8000):
        self.conversations: Dict[str, ConversationContext] = {}
        self.default_max_tokens = default_max_tokens
    
    def get_or_create_context(
        self,
        conversation_id: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None
    ) -> ConversationContext:
        """Get existing context or create new one"""
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = ConversationContext(
                max_tokens=max_tokens or self.default_max_tokens,
                system_prompt=system_prompt
            )
        return self.conversations[conversation_id]
    
    def clear_context(self, conversation_id: str) -> None:
        """Clear a specific conversation context"""
        if conversation_id in self.conversations:
            self.conversations[conversation_id].clear()
    
    def remove_context(self, conversation_id: str) -> None:
        """Remove a conversation context entirely"""
        if conversation_id in self.conversations:
            del self.conversations[conversation_id]
    
    def get_all_contexts(self) -> Dict[str, ConversationContext]:
        """Get all active conversation contexts"""
        return self.conversations
    
    def export_all_conversations(self) -> Dict[str, Any]:
        """Export all conversations for debugging"""
        return {
            conv_id: context.export_conversation()
            for conv_id, context in self.conversations.items()
        }