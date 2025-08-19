#chat.py
from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class ChatRequest(BaseModel):
    query: str = Field(..., description="User message")
    history: List[Dict[str, str]] = Field(
        default_factory=list,
        description='[{ "type": "human"|"ai", "content": "..." }]'
    )
    session_id: Optional[str] = Field(None, description="Session identifier to persist chat and client_id")
    client_id: Optional[str] = Field(None, description="Optional client id to set/override for this session")

class ChatResponse(BaseModel):
    answer: str
    history: List[Dict[str, str]]
    client_id: Optional[str] = None