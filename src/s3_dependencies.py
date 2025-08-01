"""
FastAPI Dependencies for S3ClientFactory
Clean Dependency Injection implementation replacing singleton pattern
"""
from fastapi import Request, Depends
from typing import AsyncIterator

from .s3_client_factory import S3ClientFactory


def get_s3_factory(request: Request) -> S3ClientFactory:
    """
    FastAPI dependency to get S3ClientFactory from app.state
    
    Clean DI pattern:
    - Factory stored on app.state during lifespan startup
    - Injected explicitly into services that need it
    - No global state or hidden dependencies
    - Easy to test with mock factories
    
    Usage:
        @app.get("/some-endpoint")
        async def endpoint(s3_factory: S3ClientFactory = Depends(get_s3_factory)):
            async with s3_factory.get_client("private", "ap-southeast-2") as s3_client:
                # Use s3_client
    """
    if not hasattr(request.app.state, 's3_factory'):
        raise RuntimeError("S3ClientFactory not initialized in app.state. Check lifespan configuration.")
    
    return request.app.state.s3_factory


async def get_s3_public_client(
    request: Request, 
    region: str = "ap-southeast-2"
) -> AsyncIterator:
    """
    FastAPI dependency that provides a ready-to-use public S3 client context manager
    
    Usage:
        @app.get("/some-endpoint")
        async def endpoint(s3_client = Depends(get_s3_public_client)):
            async with s3_client as client:
                # Use client for public bucket operations
    """
    s3_factory = get_s3_factory(request)
    return s3_factory.get_client("public", region)


async def get_s3_private_client(
    request: Request,
    region: str = "ap-southeast-2"
) -> AsyncIterator:
    """
    FastAPI dependency that provides a ready-to-use private S3 client context manager
    
    Usage:
        @app.get("/some-endpoint")
        async def endpoint(s3_client = Depends(get_s3_private_client)):
            async with s3_client as client:
                # Use client for private bucket operations
    """
    s3_factory = get_s3_factory(request)
    return s3_factory.get_client("private", region)