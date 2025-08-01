"""
Custom Exception Hierarchy for DEM Backend

Implements structured error handling for precise telemetry and better error categorization.
Part of Phase 3B.3.2: Advanced Pattern Refinements toward A+ architecture.
"""

class DataSourceError(Exception):
    """Base exception for all data source related errors"""
    
    def __init__(self, message: str, source_type: str = None, source_id: str = None):
        super().__init__(message)
        self.source_type = source_type
        self.source_id = source_id
        self.message = message


class S3IndexNotFoundError(DataSourceError):
    """Raised when S3 spatial index file cannot be found"""
    
    def __init__(self, index_path: str, bucket: str, source_id: str = None):
        message = f"S3 spatial index not found: {index_path} in bucket {bucket}"
        super().__init__(message, source_type="s3", source_id=source_id)
        self.index_path = index_path
        self.bucket = bucket


class S3AccessError(DataSourceError):
    """Raised when S3 access fails due to credentials or permissions"""
    
    def __init__(self, bucket: str, operation: str, source_id: str = None):
        message = f"S3 access denied for bucket {bucket} during {operation}"
        super().__init__(message, source_type="s3", source_id=source_id)
        self.bucket = bucket
        self.operation = operation


class APITimeoutError(DataSourceError):
    """Raised when external API calls timeout"""
    
    def __init__(self, api_name: str, timeout_seconds: float, source_id: str = None):
        message = f"API timeout after {timeout_seconds}s: {api_name}"
        super().__init__(message, source_type="api", source_id=source_id)
        self.api_name = api_name
        self.timeout_seconds = timeout_seconds


class APIRateLimitError(DataSourceError):
    """Raised when API rate limits are exceeded"""
    
    def __init__(self, api_name: str, retry_after: int = None, source_id: str = None):
        message = f"API rate limit exceeded: {api_name}"
        if retry_after:
            message += f" (retry after {retry_after}s)"
        super().__init__(message, source_type="api", source_id=source_id)
        self.api_name = api_name
        self.retry_after = retry_after


class DataNotFoundError(DataSourceError):
    """Raised when no elevation data is available for a location"""
    
    def __init__(self, latitude: float, longitude: float, source_id: str = None):
        message = f"No elevation data found for coordinates ({latitude}, {longitude})"
        super().__init__(message, source_id=source_id)
        self.latitude = latitude
        self.longitude = longitude


class ConfigurationError(DataSourceError):
    """Raised when data source configuration is invalid"""
    
    def __init__(self, config_field: str, reason: str, source_id: str = None):
        message = f"Configuration error in {config_field}: {reason}"
        super().__init__(message, source_id=source_id)
        self.config_field = config_field
        self.reason = reason