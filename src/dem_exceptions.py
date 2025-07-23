"""
DEM Service Specific Exceptions
Addresses code review feedback about overly broad exception handling
"""

class DEMServiceError(Exception):
    """Base exception for DEM service errors"""
    pass

class DEMSourceError(DEMServiceError):
    """Error related to DEM source selection or configuration"""
    pass

class DEMFileError(DEMServiceError):
    """Error related to DEM file access or reading"""
    pass

class DEMCoordinateError(DEMServiceError):
    """Error related to coordinate transformation or validation"""
    pass

class DEMCacheError(DEMServiceError):
    """Error related to dataset caching operations"""
    pass

class DEMProcessingError(DEMServiceError):
    """Error during elevation processing or contour generation"""
    pass

class DEMConfigurationError(DEMServiceError):
    """Error in DEM service configuration"""
    pass

# API-specific exceptions
class DEMAPIError(DEMServiceError):
    """Base class for external API errors"""
    pass

class DEMAPIRateLimitError(DEMAPIError):
    """API rate limit exceeded"""
    pass

class DEMAPIAuthenticationError(DEMAPIError):
    """API authentication failed"""
    pass

class DEMAPIUnavailableError(DEMAPIError):
    """External API is unavailable"""
    pass

# S3-specific exceptions  
class DEMS3Error(DEMServiceError):
    """Base class for S3-related errors"""
    pass

class DEMS3AccessError(DEMS3Error):
    """S3 access denied or credentials invalid"""
    pass

class DEMS3FileNotFoundError(DEMS3Error):
    """Requested S3 file not found"""
    pass

class DEMS3ConnectionError(DEMS3Error):
    """S3 connection failed"""
    pass