"""
Migration Assistant Router

Endpoints for converting pipeline configurations between formats.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from app.services.migration_assistant import migration_assistant_service

router = APIRouter(prefix="/migration-assistant", tags=["Migration Assistant"])


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class DetectFormatRequest(BaseModel):
    pipeline_content: str


class ConvertRequest(BaseModel):
    pipeline_content: str
    source_format: str
    target_format: str
    language: Optional[str] = None
    use_llm: bool = False


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/detect")
async def detect_format(request: DetectFormatRequest):
    """Auto-detect the format of a pipeline configuration."""
    try:
        result = migration_assistant_service.detect_format(request.pipeline_content)
        return {"success": True, **result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/convert")
async def convert_pipeline(request: ConvertRequest):
    """Convert a pipeline configuration from one format to another."""
    try:
        result = await migration_assistant_service.convert(
            pipeline_content=request.pipeline_content,
            source_format=request.source_format,
            target_format=request.target_format,
            language=request.language,
            use_llm=request.use_llm,
        )
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Conversion failed"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/languages")
async def get_supported_languages():
    """Get supported languages per pipeline format."""
    return migration_assistant_service.get_supported_languages()
