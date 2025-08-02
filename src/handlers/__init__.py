"""
Collection handlers package
"""
from .collection_handlers import (
    CollectionHandler,
    BaseCollectionHandler,
    AustralianUTMHandler,
    NewZealandCampaignHandler,
    CollectionHandlerRegistry
)

__all__ = [
    "CollectionHandler",
    "BaseCollectionHandler", 
    "AustralianUTMHandler",
    "NewZealandCampaignHandler",
    "CollectionHandlerRegistry"
]