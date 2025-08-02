"""
S3 Source Configuration for Multi-Bucket Architecture
Implements Gemini's approved design for structured S3 source management
"""
from pydantic import BaseModel, Field
from typing import List, Literal, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)


class S3SourceConfig(BaseModel):
    """Configuration for an S3 data source with region and access type support"""
    
    name: str = Field(..., description="Unique identifier for this source (e.g., 'au', 'nz')")
    bucket: str = Field(..., description="S3 bucket name")
    access_type: Literal["private", "public"] = Field(
        default="private", 
        description="Access type: 'private' requires credentials, 'public' uses unsigned requests"
    )
    index_keys: List[str] = Field(..., description="List of S3 keys for index files in this source")
    region: str = Field(default="ap-southeast-2", description="AWS region for this bucket")
    required: bool = Field(
        default=True, 
        description="If True, startup fails if this source can't be loaded"
    )
    
    def __str__(self) -> str:
        return f"{self.name}({self.bucket}, {self.access_type}, {self.region})"


class S3ConfigurationManager:
    """Manages S3 source configuration with clear precedence hierarchy"""
    
    @staticmethod
    def build_sources_from_settings(settings) -> List[S3SourceConfig]:
        """
        Build S3 sources configuration with Gemini's approved precedence:
        1. Expert Mode: S3_SOURCES_CONFIG JSON (overrides everything)
        2. Simple Mode: Individual environment variables
        3. Legacy Fallback: Existing behavior preserved
        """
        
        # 1. EXPERT MODE: JSON configuration overrides everything
        if hasattr(settings, 'S3_SOURCES_CONFIG') and settings.S3_SOURCES_CONFIG.strip():
            try:
                logger.info("Using Expert Mode: S3_SOURCES_CONFIG JSON configuration")
                sources_data = json.loads(settings.S3_SOURCES_CONFIG)
                sources = [S3SourceConfig(**source) for source in sources_data]
                logger.info(f"Loaded {len(sources)} sources from JSON config")
                return sources
            except (json.JSONDecodeError, Exception) as e:
                logger.critical(f"Invalid S3_SOURCES_CONFIG JSON: {e}")
                raise ValueError(f"S3_SOURCES_CONFIG parsing failed: {e}")
        
        # 2. SIMPLE MODE: Build from individual environment variables
        logger.info("Using Simple Mode: Individual environment variables")
        sources = []
        
        # AU sources (required for backward compatibility)
        au_source = S3SourceConfig(
            name="au",
            bucket=getattr(settings, 'S3_INDEX_BUCKET', 'road-engineering-elevation-data'),
            access_type="private",
            index_keys=[
                "indexes/campaign_index.json",
                "indexes/phase3_brisbane_tiled_index.json", 
                "indexes/spatial_index.json"
            ],
            region="ap-southeast-2",
            required=True
        )
        sources.append(au_source)
        logger.info(f"Added AU source: {au_source}")
        
        # NZ sources (conditional on feature flag)
        enable_nz = getattr(settings, 'ENABLE_NZ_SOURCES', False)
        if enable_nz:
            nz_source = S3SourceConfig(
                name="nz",
                bucket=getattr(settings, 'S3_INDEX_BUCKET', 'road-engineering-elevation-data'),  # Fixed: Use main bucket for indexes
                access_type="private",  # Fixed: Use private access for main bucket  
                index_keys=[getattr(settings, 'S3_NZ_INDEX_KEY', 'indexes/nz_spatial_index.json')],
                region=getattr(settings, 'S3_NZ_REGION', 'ap-southeast-2'),
                required=getattr(settings, 'S3_NZ_REQUIRED', False)
            )
            sources.append(nz_source)
            logger.info(f"Added NZ source: {nz_source}")
        else:
            logger.info("NZ sources disabled (ENABLE_NZ_SOURCES=false)")
        
        return sources
    
    @staticmethod
    def validate_configuration(sources: List[S3SourceConfig]) -> Dict[str, Any]:
        """Validate S3 source configuration for conflicts and completeness"""
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": [],
            "stats": {
                "total_sources": len(sources),
                "required_sources": 0,
                "optional_sources": 0,
                "total_indexes": 0,
                "public_sources": 0,
                "private_sources": 0
            }
        }
        
        if not sources:
            validation_result["valid"] = False
            validation_result["errors"].append("No S3 sources configured")
            return validation_result
        
        # Check for duplicate source names
        source_names = [source.name for source in sources]
        if len(source_names) != len(set(source_names)):
            validation_result["valid"] = False
            validation_result["errors"].append("Duplicate source names found")
        
        # Check for duplicate index keys across sources
        all_index_keys = []
        for source in sources:
            all_index_keys.extend(source.index_keys)
            
            # Update stats
            validation_result["stats"]["total_indexes"] += len(source.index_keys)
            if source.required:
                validation_result["stats"]["required_sources"] += 1
            else:
                validation_result["stats"]["optional_sources"] += 1
            if source.access_type == "public":
                validation_result["stats"]["public_sources"] += 1
            else:
                validation_result["stats"]["private_sources"] += 1
        
        if len(all_index_keys) != len(set(all_index_keys)):
            validation_result["valid"] = False
            validation_result["errors"].append("Duplicate index keys found across sources")
        
        # Warn if no required sources
        if validation_result["stats"]["required_sources"] == 0:
            validation_result["warnings"].append("No required sources configured - service may start without data")
        
        return validation_result