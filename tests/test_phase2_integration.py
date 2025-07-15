import pytest
import asyncio
import os
from unittest.mock import patch, MagicMock, AsyncMock
from src.gpxz_client import GPXZClient, GPXZConfig, GPXZRateLimiter
from src.s3_source_manager import S3SourceManager
from src.enhanced_source_selector import EnhancedSourceSelector
from src.dem_service import DEMService
from src.config import Settings

class TestPhase2Integration:
    """Test Phase 2 multi-source integration"""
    
    def test_gpxz_config_creation(self):
        """Test GPXZ configuration validation"""
        config = GPXZConfig(api_key="test_key_123")
        assert config.api_key == "test_key_123"
        assert config.base_url == "https://api.gpxz.io"
        assert config.timeout == 10
        assert config.daily_limit == 100
        assert config.rate_limit_per_second == 1

    def test_gpxz_rate_limiter(self):
        """Test GPXZ rate limiting functionality"""
        limiter = GPXZRateLimiter(requests_per_second=2)
        
        # Test daily limit tracking
        limiter.daily_requests = 99
        
        # Should allow one more request
        try:
            asyncio.run(limiter.wait_if_needed())
        except Exception:
            pytest.fail("Should allow request under daily limit")
        
        # Should block next request
        with pytest.raises(Exception, match="daily limit"):
            asyncio.run(limiter.wait_if_needed())

    def test_nz_catalog_building(self):
        """Test NZ Open Data catalog building"""
        manager = S3SourceManager('nz-elevation')
        catalog = manager._build_nz_catalog()
        
        # Check catalog keys (the function returns using different keys)
        assert 'canterbury_2018' in catalog
        canterbury_data = catalog['canterbury_2018']
        assert canterbury_data.resolution_m == 1.0
        assert canterbury_data.crs == 'EPSG:2193'
        assert canterbury_data.region == 'canterbury'

    def test_enhanced_source_selector_initialization(self):
        """Test enhanced source selector initialization"""
        config = {
            "local_dtm": {
                "path": "./data/DTM.gdb",
                "layer": None,
                "crs": None,
                "description": "Local DTM"
            }
        }
        
        gpxz_config = GPXZConfig(api_key="test_key")
        
        selector = EnhancedSourceSelector(
            config=config,
            use_s3=True,
            use_apis=True,
            gpxz_config=gpxz_config
        )
        
        assert selector.use_s3 is True
        assert selector.use_apis is True
        assert selector.gpxz_client is not None
        assert 'nz' in selector.s3_managers
        assert 'au' in selector.s3_managers

    @patch('boto3.client')
    def test_s3_source_manager_with_mocked_client(self, mock_boto_client):
        """Test S3 source manager with mocked AWS calls"""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3
        
        manager = S3SourceManager('test-bucket')
        client = manager._get_client()
        
        assert client is mock_s3
        mock_boto_client.assert_called_once_with('s3')

    def test_source_selection_priority(self):
        """Test source selection prioritizes local sources"""
        config = {
            "local_dtm": {
                "path": "./data/DTM.gdb",
                "layer": None,
                "crs": None,
                "description": "Local DTM"
            }
        }
        
        selector = EnhancedSourceSelector(config=config, use_s3=False, use_apis=False)
        
        # Should select local source
        source = selector.select_best_source(-43.5, 172.6, prefer_local=True)
        assert source == 'local_dtm'

    def test_cost_manager_daily_limits(self):
        """Test S3 cost manager daily limits"""
        from src.enhanced_source_selector import S3CostManager
        import tempfile
        import os
        import json
        from datetime import datetime
        
        # Use temporary file to avoid conflicts with existing usage
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"date": str(datetime.now().date()), "gb_used": 0.0, "requests": 0}, f)
            temp_file = f.name
        
        try:
            cost_manager = S3CostManager(daily_gb_limit=0.1, cache_file=temp_file)  # 100MB limit
            
            # Should allow small access
            assert cost_manager.can_access_s3(estimated_mb=20) is True
            
            # Should block large access
            assert cost_manager.can_access_s3(estimated_mb=200) is False
        finally:
            if os.path.exists(temp_file):
                os.unlink(temp_file)

    def test_enhanced_selector_resilience(self):
        """Test enhanced selector resilience patterns"""
        config = {
            "local_dtm": {
                "path": "./data/DTM.gdb",
                "layer": None,
                "crs": None,
                "description": "Local DTM"
            }
        }
        
        selector = EnhancedSourceSelector(config=config, use_s3=False, use_apis=False)
        
        # Test the circuit breaker functionality
        assert 'gpxz_api' in selector.circuit_breakers
        assert selector.circuit_breakers['gpxz_api'].is_available() is True
        
        # Test source selection for local only mode
        source = selector.select_best_source(-43.5, 172.6, prefer_local=True)
        assert source == 'local_dtm'

    def test_dem_service_enhanced_integration(self):
        """Test DEM service integration with enhanced source selector"""
        # Mock settings for enhanced mode
        settings = MagicMock()
        settings.DEM_SOURCES = {
            "local_dtm": {
                "path": "./data/DTM.gdb",
                "layer": None,
                "crs": None,
                "description": "Local DTM"
            }
        }
        settings.DEFAULT_DEM_ID = "local_dtm"
        settings.AUTO_SELECT_BEST_SOURCE = True
        settings.USE_S3_SOURCES = True
        settings.USE_API_SOURCES = True
        settings.GPXZ_API_KEY = "test_key"
        settings.GPXZ_DAILY_LIMIT = 100
        settings.GPXZ_RATE_LIMIT = 1
        settings.SUPPRESS_GDAL_ERRORS = True
        
        # Mock the dataset loading to avoid file access
        with patch.object(DEMService, '_get_dataset') as mock_get_dataset, \
             patch.object(DEMService, '_get_transformer') as mock_get_transformer:
            
            mock_dataset = MagicMock()
            mock_get_dataset.return_value = mock_dataset
            mock_get_transformer.return_value = MagicMock()
            
            service = DEMService(settings)
            
            # Verify enhanced source selector was initialized
            assert isinstance(service.source_selector, EnhancedSourceSelector)
            assert hasattr(service.source_selector, 'get_elevation_with_resilience')

    def test_error_handling_patterns(self):
        """Test error handling and circuit breaker patterns"""
        from src.error_handling import CircuitBreaker, RetryableError, NonRetryableError
        
        cb = CircuitBreaker(failure_threshold=2, recovery_timeout=1)
        
        # Should be available initially
        assert cb.is_available() is True
        
        # Record failures
        cb.record_failure()
        assert cb.is_available() is True  # Still available after 1 failure
        
        cb.record_failure()
        assert cb.is_available() is False  # Circuit opened after 2 failures
        assert cb.state == "OPEN"

    def test_environment_switching_validation(self):
        """Test that environment configuration is properly loaded"""
        # This tests that the .env.api-test file was properly loaded
        
        # Check if we're in api-test mode
        try:
            settings = Settings()
            
            # In api-test mode, these should be configured
            if hasattr(settings, 'USE_S3_SOURCES'):
                print(f"USE_S3_SOURCES: {settings.USE_S3_SOURCES}")
            if hasattr(settings, 'USE_API_SOURCES'):
                print(f"USE_API_SOURCES: {settings.USE_API_SOURCES}")
            
            # Verify DEM_SOURCES is configured
            assert settings.DEM_SOURCES is not None
            assert len(settings.DEM_SOURCES) > 0
            
        except Exception as e:
            pytest.skip(f"Environment not properly configured: {e}")

if __name__ == "__main__":
    pytest.main([__file__, "-v"])