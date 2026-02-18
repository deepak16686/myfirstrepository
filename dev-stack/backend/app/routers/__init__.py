"""
File: __init__.py
Purpose: Package initializer for the routers module that exposes all FastAPI APIRouter instances for the DevOps platform.
When Used: Imported by the main FastAPI application during startup to register all API route prefixes and endpoint handlers.
Why Created: Groups all router modules into a single package so the main app can discover and include them via a clean import path.
"""
