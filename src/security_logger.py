"""
Structured Security Logging - Phase B.3

Provides centralized, structured logging for security events with correlation IDs
and standardized event formats. This enables comprehensive security monitoring,
auditing, and incident response.

Features:
- Structured JSON logging for machine parsing
- Event correlation with timestamps
- Security event categorization
- Stack trace capture for violations
- Log level appropriate to event severity

Author: DEM Backend Security Team
Phase: B.3 - Structured Security Logging
"""
import logging
import json
from datetime import datetime
from typing import Dict, Any, Optional
import traceback
import uuid


class SecurityLogger:
    """
    Structured logging for security events with correlation IDs.
    
    Provides standardized security event logging with appropriate severity levels
    and detailed context for security monitoring and incident response.
    """
    
    def __init__(self, logger_name: str = "security"):
        """
        Initialize security logger.
        
        Args:
            logger_name: Name for the logger instance
        """
        self.logger = logging.getLogger(logger_name)
        
        # Only add handler if none exists (avoid duplicate handlers)
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            # Use plain format - the JSON structure provides all needed info
            formatter = logging.Formatter('%(message)s')
            handler.setFormatter(formatter)
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
        
        # Prevent propagation to root logger to avoid double logging
        self.logger.propagate = False
    
    def _create_event(self, event_type: str, **kwargs) -> Dict[str, Any]:
        """
        Create standardized event structure.
        
        Args:
            event_type: Type of security event
            **kwargs: Event-specific data
            
        Returns:
            Structured event dictionary
        """
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "event_type": event_type,
            "correlation_id": str(uuid.uuid4()),
            **kwargs
        }
    
    def log_auth_attempt(self, success: bool, user_id: Optional[str] = None, 
                         reason: Optional[str] = None, ip: Optional[str] = None,
                         endpoint: Optional[str] = None):
        """
        Log authentication attempts.
        
        Args:
            success: Whether authentication succeeded
            user_id: User identifier (if available)
            reason: Failure reason (for failed attempts)
            ip: Client IP address
            endpoint: Requested endpoint
        """
        event = self._create_event(
            "auth_attempt",
            success=success,
            user_id=user_id,
            reason=reason,
            client_ip=ip,
            endpoint=endpoint
        )
        
        # Use INFO for success, WARNING for failure
        level = logging.INFO if success else logging.WARNING
        self.logger.log(level, json.dumps(event))
    
    def log_rate_limit(self, key: str, allowed: bool, 
                       current_count: int = 0, limit: int = 0,
                       window_seconds: int = 0, endpoint: Optional[str] = None):
        """
        Log rate limiting decisions.
        
        Args:
            key: Rate limit key (usually IP or user ID)
            allowed: Whether request was allowed
            current_count: Current request count
            limit: Maximum requests allowed
            window_seconds: Time window in seconds
            endpoint: Affected endpoint
        """
        event = self._create_event(
            "rate_limit",
            key=key,
            allowed=allowed,
            current_count=current_count,
            limit=limit,
            window_seconds=window_seconds,
            endpoint=endpoint
        )
        
        # Use INFO for allowed, WARNING for rate limited
        level = logging.INFO if allowed else logging.WARNING
        self.logger.log(level, json.dumps(event))
    
    def log_security_violation(self, violation_type: str, 
                              details: Dict[str, Any],
                              stack_trace: bool = True,
                              severity: str = "high"):
        """
        Log security violations.
        
        Args:
            violation_type: Type of violation (e.g., "sql_injection", "auth_bypass")
            details: Violation-specific details
            stack_trace: Whether to include stack trace
            severity: Violation severity (low, medium, high, critical)
        """
        event = self._create_event(
            "security_violation",
            violation_type=violation_type,
            severity=severity,
            details=details
        )
        
        if stack_trace:
            event["stack_trace"] = traceback.format_exc()
        
        # Always use CRITICAL for security violations
        self.logger.critical(json.dumps(event))
    
    def log_startup_validation(self, checks: Dict[str, bool],
                              environment: str = "unknown"):
        """
        Log startup security validation results.
        
        Args:
            checks: Dictionary of check names and results
            environment: Environment (production, development, etc.)
        """
        all_passed = all(checks.values())
        failed_checks = [name for name, passed in checks.items() if not passed]
        
        event = self._create_event(
            "startup_validation",
            checks=checks,
            all_passed=all_passed,
            failed_checks=failed_checks,
            environment=environment
        )
        
        # Use INFO if all passed, ERROR if any failed
        level = logging.INFO if all_passed else logging.ERROR
        self.logger.log(level, json.dumps(event))
    
    def log_config_change(self, setting_name: str, old_value: Any, new_value: Any,
                         changed_by: Optional[str] = None):
        """
        Log security-relevant configuration changes.
        
        Args:
            setting_name: Name of the configuration setting
            old_value: Previous value (will be redacted if sensitive)
            new_value: New value (will be redacted if sensitive)
            changed_by: Who made the change
        """
        # Redact sensitive values
        sensitive_patterns = ["secret", "key", "password", "token", "credential"]
        is_sensitive = any(pattern in setting_name.lower() for pattern in sensitive_patterns)
        
        display_old = "[REDACTED]" if is_sensitive else old_value
        display_new = "[REDACTED]" if is_sensitive else new_value
        
        event = self._create_event(
            "config_change",
            setting_name=setting_name,
            old_value=display_old,
            new_value=display_new,
            changed_by=changed_by,
            is_sensitive=is_sensitive
        )
        
        self.logger.warning(json.dumps(event))
    
    def log_endpoint_access(self, endpoint: str, method: str, 
                           client_ip: Optional[str] = None,
                           user_id: Optional[str] = None,
                           status_code: Optional[int] = None,
                           response_time_ms: Optional[float] = None):
        """
        Log access to security-sensitive endpoints.
        
        Args:
            endpoint: Accessed endpoint
            method: HTTP method
            client_ip: Client IP address
            user_id: User identifier
            status_code: HTTP response status
            response_time_ms: Response time in milliseconds
        """
        event = self._create_event(
            "endpoint_access",
            endpoint=endpoint,
            method=method,
            client_ip=client_ip,
            user_id=user_id,
            status_code=status_code,
            response_time_ms=response_time_ms
        )
        
        # Use WARNING for 4xx/5xx responses, INFO for others
        if status_code and status_code >= 400:
            level = logging.WARNING
        else:
            level = logging.INFO
            
        self.logger.log(level, json.dumps(event))
    
    def log_redis_fallback(self, fallback_mode: str, reason: str,
                          service: str = "rate_limiter"):
        """
        Log Redis fallback events for security monitoring.
        
        Args:
            fallback_mode: Fallback mode used (strict, degraded, local)
            reason: Reason for fallback
            service: Service that needed fallback
        """
        event = self._create_event(
            "redis_fallback",
            fallback_mode=fallback_mode,
            reason=reason,
            service=service
        )
        
        # Use ERROR for strict mode (service impact), WARNING for others
        level = logging.ERROR if fallback_mode == "strict" else logging.WARNING
        self.logger.log(level, json.dumps(event))
    
    def log_debug_endpoint_attempt(self, endpoint: str, client_ip: Optional[str] = None,
                                  user_agent: Optional[str] = None):
        """
        Log attempts to access debug endpoints (should all be 404).
        
        Args:
            endpoint: Debug endpoint that was attempted
            client_ip: Client IP address
            user_agent: Client user agent
        """
        event = self._create_event(
            "debug_endpoint_attempt",
            endpoint=endpoint,
            client_ip=client_ip,
            user_agent=user_agent
        )
        
        # Always WARNING - debug endpoints should not be accessed in production
        self.logger.warning(json.dumps(event))


# Global security logger instance
security_logger = SecurityLogger()


def get_security_logger() -> SecurityLogger:
    """Get the global security logger instance."""
    return security_logger


# Convenience functions for common security events
def log_auth_success(user_id: str, ip: Optional[str] = None, endpoint: Optional[str] = None):
    """Log successful authentication."""
    security_logger.log_auth_attempt(True, user_id=user_id, ip=ip, endpoint=endpoint)


def log_auth_failure(reason: str, ip: Optional[str] = None, endpoint: Optional[str] = None):
    """Log failed authentication."""
    security_logger.log_auth_attempt(False, reason=reason, ip=ip, endpoint=endpoint)


def log_rate_limited(key: str, endpoint: Optional[str] = None):
    """Log rate limiting event."""
    security_logger.log_rate_limit(key, False, endpoint=endpoint)


def log_security_incident(incident_type: str, details: Dict[str, Any]):
    """Log security incident."""
    security_logger.log_security_violation(incident_type, details, severity="critical")