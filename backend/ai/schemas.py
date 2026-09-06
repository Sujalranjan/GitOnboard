"""Pydantic schemas for LLM requests and responses."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    role: MessageRole
    content: str


class Tool(BaseModel):
    """Tool definition for tool-calling LLM."""
    name: str
    description: str
    parameters: Dict[str, Any]  # JSON schema for tool parameters


class LLMRequest(BaseModel):
    messages: List[Message]
    model: Optional[str] = None
    temperature: float = 0.2
    max_tokens: int = 4096
    response_format: Optional[Dict[str, Any]] = None
    tools: Optional[List[Tool]] = None
    tool_choice: Optional[str] = None  # "auto", "required", or specific tool name


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ToolCall(BaseModel):
    """LLM requested to call a tool."""
    tool_name: str
    parameters: Dict[str, Any]
    tool_call_id: str  # For tracking tool results


class LLMResponse(BaseModel):
    content: str
    model: str
    provider: str
    usage: TokenUsage = Field(default_factory=TokenUsage)
    tool_calls: Optional[List[ToolCall]] = None  # If LLM requested tool calls


class StructuredLLMRequest(LLMRequest):
    """LLMRequest that expects a structured JSON output matching a Pydantic schema."""
    pass


class ProviderError(Exception):
    """Base exception for provider-level errors."""
    def __init__(self, message: str, status_code: Optional[int] = None, retriable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retriable = retriable


class NonRetriableError(ProviderError):
    """Raised for errors that must NOT trigger provider fallback (400, 401, 403, bad schema)."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message, status_code=status_code, retriable=False)


class RetriableError(ProviderError):
    """Raised for transient errors that MAY trigger provider fallback (429, 5xx, timeout)."""
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message, status_code=status_code, retriable=True)
