"""
SourceProvider Dependency Injection

Phase 3A-Fix: FastAPI dependency injection for SourceProvider pattern.
Provides clean access to dynamically loaded data sources throughout the application.
"""

from fastapi import Request, HTTPException
from typing import Dict, Any

from .source_provider import SourceProvider


def get_source_provider(request: Request) -> SourceProvider:
    """
    FastAPI dependency to get SourceProvider from app state.
    
    This replaces direct access to Settings.DEM_SOURCES with async-loaded data.
    
    Args:
        request: FastAPI Request object containing app state
        
    Returns:
        SourceProvider: Initialized provider with loaded data
        
    Raises:
        HTTPException: If SourceProvider not available or not loaded
    """
    if not hasattr(request.app.state, 'source_provider'):
        raise HTTPException(
            status_code=503, 
            detail="SourceProvider not available - service starting up"
        )
    
    provider = request.app.state.source_provider
    if not provider.is_loading_complete():
        raise HTTPException(
            status_code=503,
            detail="Data sources still loading - please wait"
        )
    
    if not provider.is_load_successful():
        raise HTTPException(
            status_code=503,
            detail=f"Data source loading failed: {provider.get_load_errors()}"
        )
    
    return provider


def get_dem_sources(request: Request) -> Dict[str, Any]:
    """
    FastAPI dependency to get DEM sources dict.
    
    This is a convenience function that replaces Settings.DEM_SOURCES
    with dynamically loaded sources from SourceProvider.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Dict[str, Any]: DEM sources configuration with all loaded campaigns
    """
    provider = get_source_provider(request)
    return provider.get_dem_sources()


def get_campaign_index(request: Request) -> Dict[str, Any]:
    """
    FastAPI dependency to get campaign spatial index.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Dict[str, Any]: Campaign spatial index data
    """
    provider = get_source_provider(request)
    return provider.get_campaign_index()


def get_nz_index(request: Request) -> Dict[str, Any]:
    """
    FastAPI dependency to get NZ spatial index.
    
    Args:
        request: FastAPI Request object
        
    Returns:
        Dict[str, Any]: NZ spatial index data
    """
    provider = get_source_provider(request)
    return provider.get_nz_index()