import logging
import json
import sys
from datetime import datetime
from typing import Dict, Any
import os

class StructuredJSONFormatter(logging.Formatter):
    """Custom formatter for structured JSON logging compatible with Railway and ELK stacks"""
    
    def __init__(self, service_name: str = "dem-backend"):
        super().__init__()
        self.service_name = service_name
        self.hostname = os.environ.get('RAILWAY_SERVICE_NAME', 'localhost')
        
    def format(self, record: logging.LogRecord) -> str:
        """Format log record as structured JSON"""
        
        # Base log structure
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "service": self.service_name,
            "hostname": self.hostname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add request context if available
        if hasattr(record, 'request_id'):
            log_entry["request_id"] = record.request_id
        if hasattr(record, 'user_id'):
            log_entry["user_id"] = record.user_id
        if hasattr(record, 'source'):
            log_entry["elevation_source"] = record.source
        if hasattr(record, 'coordinates'):
            log_entry["coordinates"] = record.coordinates
        if hasattr(record, 'cost_mb'):
            log_entry["cost_mb"] = record.cost_mb
        if hasattr(record, 'response_time_ms'):
            log_entry["response_time_ms"] = record.response_time_ms
            
        # Add exception details if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info)
            }
            
        # Add extra fields from record
        for key, value in record.__dict__.items():
            if key not in ('name', 'msg', 'args', 'levelname', 'levelno', 
                          'pathname', 'filename', 'module', 'exc_info', 
                          'exc_text', 'stack_info', 'lineno', 'funcName', 
                          'created', 'msecs', 'relativeCreated', 'thread', 
                          'threadName', 'processName', 'process', 'getMessage',
                          'request_id', 'user_id', 'source', 'coordinates',
                          'cost_mb', 'response_time_ms'):
                if not key.startswith('_'):
                    log_entry["extra"] = log_entry.get("extra", {})
                    log_entry["extra"][key] = value
        
        return json.dumps(log_entry, default=str, separators=(',', ':'))

class DevelopmentFormatter(logging.Formatter):
    """Human-readable formatter for development"""
    
    def __init__(self):
        super().__init__(
            fmt='%(asctime)s | %(levelname)8s | %(name)20s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

def setup_logging(
    level: str = "INFO", 
    use_json: bool = None,
    service_name: str = "dem-backend"
) -> None:
    """Setup logging configuration for the DEM backend service"""
    
    # Auto-detect environment
    if use_json is None:
        # Use JSON in production (Railway) or when explicitly requested
        use_json = (
            os.environ.get('RAILWAY_ENVIRONMENT') == 'production' or
            os.environ.get('LOG_FORMAT', '').lower() == 'json'
        )
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    
    if use_json:
        formatter = StructuredJSONFormatter(service_name)
    else:
        formatter = DevelopmentFormatter()
    
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)
    
    # Configure specific loggers
    configure_dem_loggers(level)
    
    # Log setup completion
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={
            "log_format": "json" if use_json else "development",
            "log_level": level,
            "service": service_name
        }
    )

def configure_dem_loggers(level: str) -> None:
    """Configure specific loggers for DEM backend components"""
    
    # DEM service loggers
    loggers = [
        'src.dem_service',
        'src.enhanced_source_selector', 
        'src.gpxz_client',
        'src.s3_source_manager',
        'src.error_handling',
        'src.config'
    ]
    
    for logger_name in loggers:
        logger = logging.getLogger(logger_name)
        logger.setLevel(getattr(logging, level.upper()))
    
    # Suppress noisy third-party loggers
    logging.getLogger('boto3').setLevel(logging.WARNING)
    logging.getLogger('botocore').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('asyncio').setLevel(logging.WARNING)

def get_source_selection_logger(source: str, coordinates: tuple, cost_mb: float = None):
    """Get logger with source selection context"""
    logger = logging.getLogger('src.enhanced_source_selector')
    
    # Add context to logger
    class ContextAdapter(logging.LoggerAdapter):
        def process(self, msg, kwargs):
            extra = kwargs.get('extra', {})
            extra.update({
                'source': source,
                'coordinates': {'lat': coordinates[0], 'lon': coordinates[1]},
            })
            if cost_mb is not None:
                extra['cost_mb'] = cost_mb
            kwargs['extra'] = extra
            return msg, kwargs
    
    return ContextAdapter(logger, {})