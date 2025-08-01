"""
Data sources package for DEM Backend.

Phase 3B.3: DataSource Strategy Pattern implementation.
Contains concrete implementations of DataSource interface for S3, GPXZ, and Google APIs.
"""

from .s3_source import S3Source
from .gpxz_source import GPXZSource  
from .google_source import GoogleSource
from .elevation_provider import UnifiedElevationProvider

__all__ = ['S3Source', 'GPXZSource', 'GoogleSource', 'UnifiedElevationProvider']