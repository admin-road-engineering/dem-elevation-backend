"""
API Campaign Models for Campaigns Endpoints
Pydantic models for type-safe campaigns API responses
"""
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union
from datetime import datetime

class FileInfo(BaseModel):
    """Information about an individual file in a campaign"""
    filename: str = Field(..., description="Name of the file")
    file_path: str = Field(..., description="Full S3 path to the file")
    bounds: Dict[str, float] = Field(..., description="Geographic bounds of the file")
    size_bytes: int = Field(..., description="File size in bytes")

class CampaignSummary(BaseModel):
    """Summary information for a campaign/collection"""
    id: str = Field(..., description="Unique campaign identifier")
    name: str = Field(..., description="Human-readable campaign name")
    country: str = Field(..., description="Country code (AU, NZ)")
    region: Optional[str] = Field(None, description="Geographic region")
    year: Optional[int] = Field(None, description="Survey year")
    file_count: int = Field(..., description="Number of files in the campaign")
    data_type: str = Field(..., description="Type of elevation data (DEM, DSM)")
    resolution_m: float = Field(..., description="Resolution in meters")
    bounds: Optional[Dict[str, float]] = Field(None, description="Geographic bounds")
    crs: Optional[str] = Field(None, description="Coordinate reference system")

class CampaignDetails(CampaignSummary):
    """Detailed campaign information with file listings"""
    files: Optional[List['FileInfo']] = Field(None, description="List of files (paginated)")
    files_truncated: Optional[bool] = Field(None, description="Whether file list is truncated")
    total_files: Optional[int] = Field(None, description="Total number of files")

class CampaignsResult(BaseModel):
    """Response model for campaigns listing"""
    total_campaigns: int = Field(..., description="Total number of campaigns")
    campaigns_by_country: Dict[str, List[CampaignSummary]] = Field(..., description="Campaigns grouped by country")
    country_summary: Dict[str, int] = Field(..., description="Campaign count by country")
    status: str = Field(..., description="Response status")