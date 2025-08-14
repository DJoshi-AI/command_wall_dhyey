from pydantic import BaseModel
from typing import List, Dict, Any

class ChatRequest(BaseModel):
    """Request model for the chat endpoint."""
    query: str
    conversation_history: List[Dict[str, Any]] = []

class ChatResponse(BaseModel):
    """Response model for the chat endpoint."""
    answer: str
    updated_history: List[Dict[str, Any]]
