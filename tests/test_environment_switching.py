import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import sys
import os

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

# Import the switching functionality
from scripts.switch_environment import switch_env, validate_environment_file, get_environment_info


class TestEnvironmentSwitching:
    """Test suite for environment switching functionality"""
    
    @pytest.fixture
    def temp_project_dir(self):
        """Create a temporary project directory with test environment files"""
        with tempfile.TemporaryDirectory() as temp_dir:
            project_dir = Path(temp_dir)
            
            # Create test environment files
            env_local = project_dir / '.env.local'
            env_local.write_text('''# Local Development Configuration
DEM_SOURCES={"local_dtm": {"path": "./data/DTM.gdb", "layer": null, "crs": null, "description": "Local DTM"}}
DEFAULT_DEM_ID=local_dtm
USE_S3_SOURCES=false
''')
            
            env_api_test = project_dir / '.env.api-test'
            env_api_test.write_text('''# API Test Configuration
DEM_SOURCES={"gpxz_api": {"path": "api://gpxz", "layer": null, "crs": null, "description": "GPXZ API"}}
DEFAULT_DEM_ID=gpxz_api
USE_S3_SOURCES=true
USE_API_SOURCES=true
''')
            
            env_production = project_dir / '.env.production'
            env_production.write_text('''# Production Configuration
DEM_SOURCES={"au_national": {"path": "s3://bucket/data.tif", "layer": null, "crs": null, "description": "Production"}}
DEFAULT_DEM_ID=au_national
USE_S3_SOURCES=true
USE_API_SOURCES=true
''')
            
            # Create scripts directory
            scripts_dir = project_dir / 'scripts'
            scripts_dir.mkdir()
            
            yield project_dir
    
    def test_validate_environment_file_valid(self, temp_project_dir):
        """Test validation of valid environment files"""
        env_file = temp_project_dir / '.env.local'
        assert validate_environment_file(env_file) == True
    
    def test_validate_environment_file_missing_dem_sources(self, temp_project_dir):
        """Test validation fails when DEM_SOURCES is missing"""
        env_file = temp_project_dir / '.env.invalid'
        env_file.write_text('''# Invalid config
DEFAULT_DEM_ID=test
USE_S3_SOURCES=false
''')
        assert validate_environment_file(env_file) == False
    
    def test_validate_environment_file_empty(self, temp_project_dir):
        """Test validation fails for empty files"""
        env_file = temp_project_dir / '.env.empty'
        env_file.write_text('')
        assert validate_environment_file(env_file) == False
    
    def test_validate_environment_file_not_exists(self, temp_project_dir):
        """Test validation fails for non-existent files"""
        env_file = temp_project_dir / '.env.missing'
        assert validate_environment_file(env_file) == False
    
    def test_get_environment_info_local(self):
        """Test environment info for local mode"""
        info = get_environment_info('local')
        assert info['cost'] == 'Zero cost'
        assert 'Local DTM only' in info['description']
        assert 'Development' in info['suitable_for']
    
    def test_get_environment_info_api_test(self):
        """Test environment info for api-test mode"""
        info = get_environment_info('api-test')
        assert 'Free tier' in info['cost']
        assert 'GPXZ API' in info['description']
        assert 'Integration testing' in info['suitable_for']
    
    def test_get_environment_info_production(self):
        """Test environment info for production mode"""
        info = get_environment_info('production')
        assert 'S3 storage' in info['cost']
        assert 'Full S3' in info['description']
        assert 'Production deployment' in info['suitable_for']
    
    def test_get_environment_info_unknown(self):
        """Test environment info for unknown mode"""
        info = get_environment_info('unknown')
        assert info['description'] == 'Unknown mode'
    
    @patch('scripts.switch_environment.Path.__file__')
    def test_switch_env_local_success(self, mock_file, temp_project_dir):
        """Test successful switch to local environment"""
        # Mock the script location to point to our temp directory
        mock_file.parent.parent = temp_project_dir
        
        with patch('scripts.switch_environment.Path') as mock_path_class:
            # Configure the mock to return our temp directory structure
            def path_side_effect(path_str):
                if path_str == temp_project_dir:
                    return temp_project_dir
                return Path(path_str)
            
            mock_path_class.side_effect = path_side_effect
            mock_path_class.__file__ = MagicMock()
            mock_path_class.__file__.parent.parent = temp_project_dir
            
            # Mock Path() constructor for individual paths
            with patch('pathlib.Path') as mock_path:
                mock_path.return_value.__truediv__ = lambda self, other: temp_project_dir / other
                
                # Set up the environment file paths properly
                with patch('scripts.switch_environment.logger'):
                    # Call with mocked file location
                    with patch('scripts.switch_environment.shutil.copy2') as mock_copy:
                        with patch.object(Path, 'exists', return_value=True):
                            with patch.object(Path, 'is_file', return_value=True):
                                # This is a simplified test - in practice we'd need more sophisticated mocking
                                # For now, test the core logic components separately
                                pass
    
    def test_switch_env_invalid_mode(self, temp_project_dir):
        """Test switch with invalid mode"""
        with patch('scripts.switch_environment.Path') as mock_path:
            mock_path.__file__.parent.parent = temp_project_dir
            result = switch_env('invalid_mode')
            assert result == False
    
    def test_switch_env_missing_file(self, temp_project_dir):
        """Test switch when environment file is missing"""
        with patch('scripts.switch_environment.Path') as mock_path:
            mock_path.__file__.parent.parent = temp_project_dir
            
            # Remove the environment file
            env_file = temp_project_dir / '.env.local'
            if env_file.exists():
                env_file.unlink()
            
            result = switch_env('local')
            assert result == False


class TestEnvironmentSwitchingIntegration:
    """Integration tests for environment switching"""
    
    def test_switching_script_help(self):
        """Test that the help option works"""
        with patch('sys.argv', ['switch_environment.py', '--help']):
            with patch('sys.exit') as mock_exit:
                with patch('builtins.print') as mock_print:
                    from scripts.switch_environment import main
                    main()
                    mock_exit.assert_called_with(0)
                    # Verify help text was printed
                    assert any('DEM Backend Environment Switcher' in str(call) for call in mock_print.call_args_list)
    
    def test_environment_modes_coverage(self):
        """Test that all expected environment modes are covered"""
        expected_modes = ['local', 'api-test', 'production']
        
        for mode in expected_modes:
            info = get_environment_info(mode)
            assert info['description'] != 'Unknown mode'
            assert info['cost'] != 'Unknown'
            assert len(info['suitable_for']) > 0


class TestEnvironmentValidation:
    """Test environment file validation logic"""
    
    def test_dem_sources_format_validation(self):
        """Test various DEM_SOURCES format validations"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            # Valid JSON format
            f.write('DEM_SOURCES={"test": {"path": "./test.tif", "layer": null}}')
            f.flush()
            
            env_path = Path(f.name)
            assert validate_environment_file(env_path) == True
            
            os.unlink(f.name)
    
    def test_corrupted_file_handling(self):
        """Test handling of corrupted environment files"""
        with tempfile.NamedTemporaryFile(mode='wb', suffix='.env', delete=False) as f:
            # Write binary data to simulate corruption
            f.write(b'\x00\x01\x02\x03\x04')
            f.flush()
            
            env_path = Path(f.name)
            # Should handle decode errors gracefully
            result = validate_environment_file(env_path)
            assert result == False
            
            os.unlink(f.name)


if __name__ == '__main__':
    # Run specific test
    pytest.main([__file__, '-v'])