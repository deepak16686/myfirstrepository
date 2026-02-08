"""
Chat Router - API endpoints for chat functionality
"""
from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.chat_service import ChatService
from app.config import settings

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])

# Initialize chat service
chat_service = ChatService(settings)


class ChatRequest(BaseModel):
    """Request model for chat endpoint"""
    message: str
    conversation_id: Optional[str] = None
    model: str = "qwen3:32b"


class ChatResponse(BaseModel):
    """Response model for chat endpoint"""
    conversation_id: str
    message: str
    pending_pipeline: Optional[dict] = None
    monitoring: Optional[dict] = None


class ConversationResponse(BaseModel):
    """Response model for conversation"""
    conversation_id: str


@router.post("/", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Send a message and get AI response.

    If conversation_id is not provided, a new conversation will be created.
    """
    try:
        # Create new conversation if needed
        conversation_id = request.conversation_id
        if not conversation_id:
            conversation_id = await chat_service.create_conversation()

        # Process message
        result = await chat_service.chat(
            conversation_id=conversation_id,
            user_message=request.message,
            model=request.model
        )

        return ChatResponse(
            conversation_id=result["conversation_id"],
            message=result["message"],
            pending_pipeline=result.get("pending_pipeline"),
            monitoring=result.get("monitoring")
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/new", response_model=ConversationResponse)
async def new_conversation():
    """Create a new conversation"""
    try:
        conversation_id = await chat_service.create_conversation()
        return ConversationResponse(conversation_id=conversation_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history/{conversation_id}")
async def get_history(conversation_id: str):
    """Get conversation history"""
    try:
        history = await chat_service.get_conversation(conversation_id)
        return {"conversation_id": conversation_id, "messages": history}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
