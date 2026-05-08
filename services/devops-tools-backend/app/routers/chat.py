"""
Chat Router - API endpoints for chat functionality
"""
from typing import Any, Dict, Optional
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
    model: str = "llama3.1:8b"
    # Client-generated UUID per send. Used as the inflight polling key so
    # the frontend can poll GET /api/v1/chat/inflight/{request_id} while
    # this main POST is still in flight and render a live phase card.
    # Falls back to conversation_id when not supplied.
    request_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint.

    Carries optional ``monitoring`` (set when ``commit_pipeline`` started a
    self-heal monitor) and ``generation`` (set when ``generate_pipeline``
    ran — describes whether the result was a RAG hit or LLM+fixer output)
    so the frontend can render the live progress card and the pipeline-source
    badge under the assistant bubble.
    """
    conversation_id: str
    message: str
    pending_pipeline: Optional[dict] = None
    monitoring: Optional[Dict[str, Any]] = None
    generation: Optional[Dict[str, Any]] = None


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
            model=request.model,
            request_id=request.request_id,
        )

        # Always clear the inflight phase on completion so the frontend
        # poll loop sees `idle` and stops rendering the live card.
        try:
            chat_service._clear_phase(request.request_id or conversation_id)
        except Exception:
            pass

        return ChatResponse(
            conversation_id=result["conversation_id"],
            message=result["message"],
            pending_pipeline=result.get("pending_pipeline"),
            monitoring=result.get("monitoring"),
            generation=result.get("generation"),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/inflight/{key}")
async def get_inflight(key: str):
    """Return the current pipeline-generation phase for a chat request.

    The frontend polls this every ~1.5s while its main /api/v1/chat/ POST
    is in flight to render a live phase card under the thinking dots.
    Returns ``{"phase":"idle"}`` when nothing is happening for that key.
    """
    from app.services.chat_inflight import get_phase
    state = get_phase(key)
    if not state:
        return {"phase": "idle"}
    return state


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
